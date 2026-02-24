#!/usr/bin/env python
"""
Automatically extract figures and tables from PDFs (including captions)

Features:
    - Automatically detect and extract figures and tables from PDFs
    - Intelligently merge figure/table body with caption regions for complete content
    - Generate detailed JSON result reports

Usage:
    python -m dp_core.extract_figures_tables --pdf path/to/your.pdf --output-dir ./output

Or call from code:
    from dp_core.extract_figures_tables import extract_figures_and_tables
    extract_figures_and_tables('path/to/your.pdf', './output')
"""

import os
import sys
import json
import cv2
import argparse
from pathlib import Path

# Detect available layout analysis libraries
LAYOUT_PARSER_AVAILABLE = False

try:
    import layoutparser as lp
    LAYOUT_PARSER_AVAILABLE = True
except ImportError:
    pass

# Check detectron2 model availability
DETECTRON2_MODEL_AVAILABLE = False
if LAYOUT_PARSER_AVAILABLE:
    try:
        lp.Detectron2LayoutModel
        DETECTRON2_MODEL_AVAILABLE = True
    except:
        pass


def remove_incomplete_text_borders(image, white_threshold=240, edge_margin=3):
    """
    Detect and remove incomplete text at image borders (especially truncated captions at bottom)
    """
    import numpy as np

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    h, w = gray.shape

    if h < 50:
        return image

    row_intensity = np.mean(gray, axis=1)
    crop_top = 0
    crop_bottom = h

    # Detect if there is truncated text at the bottom
    bottom_region_size = min(30, int(h * 0.15))
    bottom_region = gray[-bottom_region_size:, :]
    bottom_rows_dark = np.sum(row_intensity[-bottom_region_size:] < white_threshold)

    if bottom_rows_dark > 3:
        check_range = int(h * 0.1)
        above_bottom = row_intensity[-bottom_region_size-check_range:-bottom_region_size]
        white_rows_above = np.sum(above_bottom > white_threshold)

        if white_rows_above > check_range * 0.7:
            for i in range(h - bottom_region_size, int(h * 0.3), -1):
                if row_intensity[i] > white_threshold:
                    crop_bottom = i + 1
                    break

    # Detect if there is truncated text at the top
    top_region_size = min(30, int(h * 0.15))
    top_rows_dark = np.sum(row_intensity[:top_region_size] < white_threshold)

    if top_rows_dark > 3:
        check_range = int(h * 0.1)
        below_top = row_intensity[top_region_size:top_region_size+check_range]
        white_rows_below = np.sum(below_top > white_threshold)

        if white_rows_below > check_range * 0.7:
            for i in range(top_region_size, int(h * 0.7)):
                if row_intensity[i] > white_threshold:
                    crop_top = i
                    break

    if crop_top > 0 or crop_bottom < h:
        image = image[crop_top:crop_bottom, :]

    return image


def balance_horizontal_whitespace(image, white_threshold=250, min_padding=5):
    """Balance whitespace borders around image"""
    import numpy as np

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    h, w = gray.shape

    col_is_white = np.mean(gray, axis=0) > white_threshold
    left_content = 0
    for i in range(w):
        if not col_is_white[i]:
            left_content = i
            break

    right_content = w - 1
    for i in range(w-1, -1, -1):
        if not col_is_white[i]:
            right_content = i
            break

    left_white = left_content
    right_white = w - 1 - right_content

    row_is_white = np.mean(gray, axis=1) > white_threshold
    top_content = 0
    for i in range(h):
        if not row_is_white[i]:
            top_content = i
            break

    bottom_content = h - 1
    for i in range(h-1, -1, -1):
        if not row_is_white[i]:
            bottom_content = i
            break

    top_white = top_content
    bottom_white = h - 1 - bottom_content

    target_white = max(left_white, right_white, top_white, bottom_white, min_padding)

    add_left = target_white - left_white
    add_right = target_white - right_white
    add_top = target_white - top_white
    add_bottom = target_white - bottom_white

    if add_left > 0 or add_right > 0 or add_top > 0 or add_bottom > 0:
        border_color = (255, 255, 255) if len(image.shape) == 3 else 255

        balanced = cv2.copyMakeBorder(
            image,
            top=add_top,
            bottom=add_bottom,
            left=add_left,
            right=add_right,
            borderType=cv2.BORDER_CONSTANT,
            value=border_color
        )
        return balanced
    else:
        return image


def extract_with_layoutparser(pdf_path, output_dir, min_score=0.7, dpi=300):
    """
    使用 layoutparser 提取图片和表格
    """
    import numpy as np
    import fitz  # PyMuPDF
    import requests

    print("=" * 80)
    print("PDF Figure/Table Extraction Tool (LayoutParser + Detectron2)")
    print("=" * 80)
    print(f"Input PDF: {pdf_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Confidence Threshold: {min_score}")
    print(f"Image Resolution: {dpi} DPI")
    print()

    # Create output directories
    output_dir = Path(output_dir)
    figures_dir = output_dir / 'figures'
    tables_dir = output_dir / 'tables'

    figures_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Load Detectron2 model
    print("[1/3] Initializing Detectron2 model...")

    def _download_file(urls, dest_path: Path):
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if dest_path.exists() and dest_path.stat().st_size > 0:
            return
        print(f"⬇️  Downloading {dest_path.name} ...")
        last_err = None
        for url in urls:
            try:
                with requests.get(url, stream=True, timeout=120, allow_redirects=True) as r:
                    r.raise_for_status()
                    with open(dest_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                return
            except Exception as e:
                last_err = e
                continue
        raise last_err

    def _ensure_publaynet_model(model_dir: Path) -> tuple[Path, Path]:
        config_path = model_dir / "config.yml"
        weights_path = model_dir / "model_final.pth"

        if not config_path.exists() or config_path.stat().st_size == 0:
            _download_file(
                [
                    "https://hf-mirror.com/layoutparser/detectron2/resolve/main/"
                    "PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config.yml",
                    "https://huggingface.co/layoutparser/detectron2/resolve/main/"
                    "PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config.yml",
                ],
                config_path
            )

        if not weights_path.exists() or weights_path.stat().st_size == 0:
            _download_file(
                [
                    "https://hf-mirror.com/layoutparser/detectron2/resolve/main/"
                    "PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/model_final.pth",
                    "https://huggingface.co/layoutparser/detectron2/resolve/main/"
                    "PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/model_final.pth",
                ],
                weights_path
            )

        return config_path, weights_path

    # Optional local PubLayNet model directory (config.yml + model_final.pth)
    local_model_dir = os.getenv("PUBLAYNET_MODEL_DIR", "").strip()
    if not local_model_dir:
        try:
            from dp_core.config import config as dp_config
            local_model_dir = str(dp_config.get("extraction.model_dir", "")).strip()
        except Exception:
            local_model_dir = ""

    if not local_model_dir:
        new_dir = Path.home() / ".xhs-paper-engine" / "publaynet"
        old_dir = Path.home() / ".dailypaper" / "publaynet"
        local_model_dir = str(new_dir if new_dir.exists() or not old_dir.exists() else old_dir)

    LOCAL_CONFIG = None
    LOCAL_WEIGHTS = None
    if local_model_dir:
        local_model_dir = Path(local_model_dir)
        LOCAL_CONFIG = local_model_dir / 'config.yml'
        LOCAL_WEIGHTS = local_model_dir / 'model_final.pth'

        if not (LOCAL_CONFIG.exists() and LOCAL_WEIGHTS.exists()):
            try:
                LOCAL_CONFIG, LOCAL_WEIGHTS = _ensure_publaynet_model(local_model_dir)
            except Exception as e:
                print(f"⚠️ Failed to download PubLayNet model files: {e}")

    # Disable iopath telemetry
    os.environ['IOPATH_DISABLE_TELEMETRY'] = '1'

    try:
        # Use local model files
        if LOCAL_CONFIG and LOCAL_WEIGHTS and LOCAL_CONFIG.exists() and LOCAL_WEIGHTS.exists():
            print(f"Using local PubLayNet model from: {local_model_dir}")
            model = lp.Detectron2LayoutModel(
                config_path=str(LOCAL_CONFIG),
                model_path=str(LOCAL_WEIGHTS),
                extra_config=[
                    'MODEL.ROI_HEADS.SCORE_THRESH_TEST', str(min_score),
                    'MODEL.DEVICE', 'cpu'
                ]
            )
        else:
            # Try remote download (may fail due to SSL issues)
            model = lp.Detectron2LayoutModel(
                config_path='lp://PubLayNet/mask_rcnn_X_101_32x8d_FPN_3x/config',
                extra_config=[
                    'MODEL.ROI_HEADS.SCORE_THRESH_TEST', str(min_score),
                    'MODEL.DEVICE', 'cpu'
                ]
            )
    except Exception as e:
        raise ImportError(
            "PubLayNet model unavailable. Please set `extraction.model_dir` "
            "or `PUBLAYNET_MODEL_DIR` with config.yml + model_final.pth."
        ) from e

    print("✅ Model loaded successfully")
    print()

    # Open PDF
    doc = fitz.open(pdf_path)

    stats = {
        'total_pages': len(doc),
        'figures_count': 0,
        'tables_count': 0,
        'figures': [],
        'tables': []
    }

    print("[2/3] Analyzing PDF layout...")

    for page_num in range(len(doc)):
        # Render page to image
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        page = doc[page_num]
        page_image = page.get_pixmap(matrix=mat)
        img_bytes = page_image.tobytes("png")
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            continue

        # 使用模型检测布局
        layout = model.detect(img)

        # PubLayNet type mapping
        PUBlayNET_TYPE_MAP = {
            0: 'Text',
            1: 'Title',
            2: 'List',
            3: 'Table',
            4: 'Figure'
        }

        # Get all elements
        elements = layout

        page_figures = 0
        page_tables = 0

        for element in elements:
            # Get element type (handle both int and string)
            raw_type = element.type
            if isinstance(raw_type, int):
                element_type = PUBlayNET_TYPE_MAP.get(raw_type, 'Text')
            else:
                element_type = raw_type

            score = element.score if hasattr(element, 'score') else 1.0

            # Filter low confidence detections
            if score < min_score:
                continue

            # Only process Figure and Table types
            if element_type not in ['Figure', 'Table']:
                continue

            # Get bounding box (handle both bbox and coordinates)
            if hasattr(element, 'bbox'):
                x1, y1, x2, y2 = element.bbox
            elif hasattr(element, 'coordinates'):
                x1, y1, x2, y2 = element.coordinates
            else:
                continue

            # 扩展边界框
            h, w = img.shape[:2]
            expand_margin = 15
            x1 = max(0, int(x1 - expand_margin))
            y1 = max(0, int(y1 - expand_margin))
            x2 = min(w, int(x2 + expand_margin))
            y2 = min(h, int(y2 + expand_margin))

            if x2 <= x1 or y2 <= y1:
                continue

            cropped = img[y1:y2, x1:x2]

            # Post-processing
            cropped = remove_incomplete_text_borders(cropped)
            cropped = balance_horizontal_whitespace(cropped)

            safe_caption = f"page{page_num + 1}"

            if element_type == 'Figure':
                filename = f'figure_{safe_caption}_{stats["figures_count"]:03d}.png'
                save_path = figures_dir / filename

                cv2.imwrite(str(save_path), cropped)

                stats['figures_count'] += 1
                stats['figures'].append({
                    'filename': filename,
                    'page': page_num + 1,
                    'bbox': [x1, y1, x2, y2],
                    'score': score,
                    'caption': ''
                })
                page_figures += 1

            elif element_type == 'Table':
                filename = f'table_{safe_caption}_{stats["tables_count"]:03d}.png'
                save_path = tables_dir / filename

                cv2.imwrite(str(save_path), cropped)

                stats['tables_count'] += 1
                stats['tables'].append({
                    'filename': filename,
                    'page': page_num + 1,
                    'bbox': [x1, y1, x2, y2],
                    'score': score,
                    'caption': ''
                })
                page_tables += 1

        if page_figures > 0 or page_tables > 0:
            print(f"  📄 Page {page_num + 1}: {page_figures} figures, {page_tables} tables")

    doc.close()

    print()
    print("=" * 80)
    print("Extraction Results:")
    print("=" * 80)
    print(f"📊 Total Pages: {stats['total_pages']}")
    print(f"🖼️  Figures: {stats['figures_count']}")
    print(f"📋 Tables: {stats['tables_count']}")
    print()
    print(f"💾 Figures saved to: {figures_dir}")
    print(f"💾 Tables saved to: {tables_dir}")
    print()

    # Save JSON results
    json_path = output_dir / 'extraction_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


def extract_figures_and_tables(pdf_path, output_dir, min_score=0.7, save_json=True, dpi=300):
    """
    Extract figures and tables from PDF

    Args:
        pdf_path (str): Path to PDF file
        output_dir (str): Output directory
        min_score (float): Minimum confidence threshold (0-1), default 0.7
        save_json (bool): Whether to save detection results as JSON
        dpi (int): Resolution for PDF to image conversion (DPI), default 300

    Returns:
        dict: Extraction result statistics
    """
    import numpy as np

    # 转换为绝对路径
    pdf_path = os.path.abspath(pdf_path)
    output_dir = os.path.abspath(output_dir)

    # Validate PDF file
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Check library support
    if not LAYOUT_PARSER_AVAILABLE:
        raise ImportError(
            "layoutparser library not found. Please install:\n"
            "  conda activate xhs-paper-engine\n"
            "  pip install layoutparser detectron2\n\n"
            "Ensure using Python 3.10 environment."
        )

    if not DETECTRON2_MODEL_AVAILABLE:
        raise ImportError(
            "Detectron2 model not available. Please ensure detectron2 is properly installed."
        )

    # Use layoutparser + Detectron2 for extraction
    return extract_with_layoutparser(pdf_path, output_dir, min_score, dpi)


def main():
    """Command line entry point"""
    parser = argparse.ArgumentParser(
        description='Automatically extract figures and tables from PDFs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m dp_core.extract_figures_tables --pdf paper.pdf --output-dir ./extracted
    python -m dp_core.extract_figures_tables --pdf paper.pdf --output-dir ./extracted --min-score 0.8 --dpi 600
        """
    )

    parser.add_argument('--pdf', required=True, help='Path to PDF file')
    parser.add_argument('--output-dir', default='./extracted', help='Output directory (default: ./extracted)')
    parser.add_argument('--min-score', type=float, default=0.7, help='Minimum confidence threshold (0-1) (default: 0.7)')
    parser.add_argument('--dpi', type=int, default=300, help='Image resolution DPI (default: 300, recommended: 150/300/600)')
    parser.add_argument('--no-json', action='store_true', help='Do not save JSON results')

    args = parser.parse_args()

    try:
        extract_figures_and_tables(
            pdf_path=args.pdf,
            output_dir=args.output_dir,
            min_score=args.min_score,
            save_json=not args.no_json,
            dpi=args.dpi
        )
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
