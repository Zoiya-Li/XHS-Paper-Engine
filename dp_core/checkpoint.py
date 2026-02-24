"""
Checkpoint recovery module - Supports pipeline interruption recovery

Usage:
    from dp_core.checkpoint import CheckpointManager

    checkpoint = CheckpointManager(work_dir)

    if not checkpoint.is_step_completed("step_12_draft"):
        checkpoint.mark_step_started("step_12_draft")
        # ... execute step ...
        checkpoint.mark_step_completed("step_12_draft")
    else:
        print("Skip completed step")
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime


# Define pipeline steps and their output files
PIPELINE_STEPS = {
    "step_2_search": {
        "name": "Paper search",
        "description": "Search papers from arXiv and Semantic Scholar",
        "output_check": None  # Search results in cache directory, not in work_dir
    },
    "step_6_select": {
        "name": "Paper selection",
        "description": "Use LLM to filter best papers",
        "output_file": "paper_info.json"
    },
    "step_8_download": {
        "name": "PDF download",
        "description": "Download paper PDF",
        "output_pattern": "paper_pdf/*.pdf"
    },
    "step_9_convert": {
        "name": "PDF to MD",
        "description": "Convert PDF to Markdown using OCR",
        "output_file": "paper.md"
    },
    "step_10_extract": {
        "name": "Figure extraction",
        "description": "Extract figures and tables from paper",
        "output_pattern": "extracted_figures_tables/figures/*.png",
        "fallback_check": "extracted_figures_tables/extraction_results.json"
    },
    "step_12_draft": {
        "name": "Draft writing",
        "description": "Write draft using the configured text model",
        "output_file": "01_draft.md"
    },
    "step_13_enhance": {
        "name": "Figure insertion",
        "description": "Insert figures and optimize",
        "output_file": "02_enhanced_with_figures.md"
    },
    "step_14_final": {
        "name": "Final polish",
        "description": "Final polish using the configured text model",
        "output_file": "03_final.md"
    },
    "step_15_publish": {
        "name": "Xiaohongshu publish",
        "description": "Publish to Xiaohongshu",
        "output_file": "04_xiaohongshu.md"  # Optional
    }
}


class CheckpointManager:
    """Checkpoint manager"""

    def __init__(self, work_dir: Path):
        """
        Initialize checkpoint manager

        Args:
            work_dir: Working directory path
        """
        self.work_dir = Path(work_dir)
        self.checkpoint_file = self.work_dir / ".checkpoint.json"
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load checkpoint state"""
        if self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "completed_steps": [],
            "current_step": None,
            "last_update": None,
            "metadata": {}
        }

    def _save_state(self):
        """Save checkpoint state"""
        self.state["last_update"] = datetime.now().isoformat()

        # Ensure directory exists
        self.work_dir.mkdir(parents=True, exist_ok=True)

        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _check_output_exists(self, step_name: str) -> bool:
        """Check if step's output file exists"""
        step_config = PIPELINE_STEPS.get(step_name, {})

        # Check single output file
        if "output_file" in step_config:
            output_path = self.work_dir / step_config["output_file"]
            if output_path.exists() and output_path.stat().st_size > 0:
                return True

        # Check output file pattern (glob)
        if "output_pattern" in step_config:
            pattern = step_config["output_pattern"]
            files = list(self.work_dir.glob(pattern))
            if files:
                return True

        # Check fallback check file
        if "fallback_check" in step_config:
            fallback_path = self.work_dir / step_config["fallback_check"]
            if fallback_path.exists():
                return True

        return False

    def is_step_completed(self, step_name: str) -> bool:
        """
        Check if step is completed

        Args:
            step_name: Step name (e.g. "step_12_draft")

        Returns:
            Whether completed
        """
        # First check state record
        if step_name in self.state["completed_steps"]:
            return True

        # Then check if output file exists
        return self._check_output_exists(step_name)

    def mark_step_started(self, step_name: str):
        """
        Mark step as started

        Args:
            step_name: Step name
        """
        self.state["current_step"] = step_name
        self.state["current_step_started"] = datetime.now().isoformat()
        self._save_state()

        step_info = PIPELINE_STEPS.get(step_name, {})
        print(f"▶️  Starting: {step_info.get('name', step_name)}")

    def mark_step_completed(self, step_name: str, metadata: Optional[Dict] = None):
        """
        Mark step as completed

        Args:
            step_name: Step name
            metadata: Optional metadata
        """
        if step_name not in self.state["completed_steps"]:
            self.state["completed_steps"].append(step_name)

        self.state["current_step"] = None
        self.state.pop("current_step_started", None)

        if metadata:
            self.state["metadata"][step_name] = metadata

        self._save_state()

        step_info = PIPELINE_STEPS.get(step_name, {})
        print(f"  ✓ Checkpoint saved: {step_info.get('name', step_name)}")

    def mark_step_failed(self, step_name: str, error: str):
        """
        Mark step as failed

        Args:
            step_name: Step name
            error: Error message
        """
        self.state["failed_step"] = step_name
        self.state["failure_reason"] = error
        self.state["failure_time"] = datetime.now().isoformat()
        self._save_state()

        step_info = PIPELINE_STEPS.get(step_name, {})
        print(f"  ✗ Step failed: {step_info.get('name', step_name)}")
        print(f"    Error: {error[:200]}")

    def get_resume_point(self) -> Optional[str]:
        """
        Get resume point (next step to execute)

        Returns:
            Step name, or None if all steps completed
        """
        for step_name in PIPELINE_STEPS.keys():
            if not self.is_step_completed(step_name):
                return step_name
        return None

    def get_completed_steps(self) -> List[str]:
        """Get list of completed steps"""
        completed = []
        for step_name in PIPELINE_STEPS.keys():
            if self.is_step_completed(step_name):
                completed.append(step_name)
        return completed

    def get_progress_summary(self) -> str:
        """Get progress summary"""
        total = len(PIPELINE_STEPS)
        completed = len(self.get_completed_steps())
        return f"Progress: {completed}/{total} steps completed"

    def get_step_metadata(self, step_name: str) -> Optional[Dict]:
        """Get step metadata"""
        return self.state.get("metadata", {}).get(step_name)

    def reset(self):
        """Reset all checkpoints (use with caution)"""
        self.state = {
            "completed_steps": [],
            "current_step": None,
            "last_update": None,
            "metadata": {}
        }
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        print("🔄 Checkpoints reset")

    def print_status(self):
        """Print current status"""
        print(f"\n{'='*50}")
        print(f"📊 Pipeline status - {self.work_dir.name}")
        print(f"{'='*50}")
        print(f"{self.get_progress_summary()}")
        print()

        for step_name, step_info in PIPELINE_STEPS.items():
            status = "✅" if self.is_step_completed(step_name) else "⬜"
            print(f"  {status} {step_info['name']}")

        if self.state.get("failed_step"):
            print(f"\n❌ Failed step: {self.state['failed_step']}")
            print(f"   Reason: {self.state.get('failure_reason', 'Unknown')[:100]}")

        print(f"{'='*50}\n")


def check_resume(work_dir: Path) -> Optional[str]:
    """
    Check if can resume from checkpoint

    Args:
        work_dir: Working directory

    Returns:
        Resume point step name, or None if new process
    """
    checkpoint_file = work_dir / ".checkpoint.json"

    if not checkpoint_file.exists():
        return None

    manager = CheckpointManager(work_dir)
    resume_point = manager.get_resume_point()

    if resume_point:
        step_info = PIPELINE_STEPS.get(resume_point, {})
        print(f"\n🔄 Detected incomplete process")
        print(f"   {manager.get_progress_summary()}")
        print(f"   Will continue from '{step_info.get('name', resume_point)}'")
        return resume_point

    return None
