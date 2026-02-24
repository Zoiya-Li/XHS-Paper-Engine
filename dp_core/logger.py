"""
Logger module - Unified logging management

Usage:
    from dp_core.logger import get_logger, log_info, log_success, log_error

    # Method 1: Use convenience functions
    log_info("Processing...")
    log_success("Completed")
    log_error("Failed")

    # Method 2: Use logger instance
    logger = get_logger()
    logger.info("Processing...")
"""

import sys
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional


class EmojiFormatter(logging.Formatter):
    """Formatter that preserves emojis (for console)"""

    def format(self, record):
        return record.getMessage()


class CleanFormatter(logging.Formatter):
    """Formatter that removes emojis (for files)"""

    # Emoji regex pattern
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols and pictographs
        "\U0001F680-\U0001F6FF"  # Transport and map
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002702-\U000027B0"  # Miscellaneous symbols
        "\U000024C2-\U0001F251"  # Enclosed characters
        "\U0001F900-\U0001F9FF"  # Supplemental symbols
        "\U0001FA00-\U0001FA6F"  # Chess symbols
        "\U0001FA70-\U0001FAFF"  # Symbols extended
        "\U00002600-\U000026FF"  # Miscellaneous symbols
        "\U00002700-\U000027BF"  # Dingbats
        "]+",
        flags=re.UNICODE
    )

    def format(self, record):
        msg = record.getMessage()
        # Remove emojis
        msg = self.EMOJI_PATTERN.sub('', msg)
        # Remove extra spaces
        msg = ' '.join(msg.split())
        record.msg = msg
        record.args = ()
        return super().format(record)


class PipelineLogger:
    """Pipeline-specific logger"""

    def __init__(self, name: str = "XHS Paper Engine", log_dir: Optional[Path] = None):
        """
        Initialize logger

        Args:
            name: Logger name
            log_dir: Log file directory (optional)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # Clear existing handlers

        # Console handler (preserves emoji output)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(EmojiFormatter())
        self.logger.addHandler(console_handler)

        # File handler (detailed logs, no emojis)
        self.log_file = None
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(CleanFormatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            ))
            self.logger.addHandler(file_handler)

    # === Basic logging methods ===

    def debug(self, msg: str):
        """Debug information (only writes to file)"""
        self.logger.debug(msg)

    def info(self, msg: str):
        """General information"""
        self.logger.info(msg)

    def warning(self, msg: str):
        """Warning information"""
        self.logger.warning(msg)

    def error(self, msg: str):
        """Error information"""
        self.logger.error(msg)

    # === Semantic logging methods ===

    def success(self, msg: str):
        """Success message"""
        self.logger.info(f"✅ {msg}")

    def fail(self, msg: str):
        """Failure message"""
        self.logger.error(f"❌ {msg}")

    def progress(self, msg: str):
        """Progress information"""
        self.logger.info(f"⏳ {msg}")

    def step(self, step_num: int, total: int, description: str):
        """Step information"""
        self.logger.info(f"\n[{step_num}/{total}] {description}")

    def section(self, title: str, width: int = 60, char: str = "="):
        """Separator line"""
        self.logger.info(f"\n{char * width}")
        self.logger.info(title)
        self.logger.info(f"{char * width}")

    def subsection(self, title: str, width: int = 40, char: str = "-"):
        """Sub-separator line"""
        self.logger.info(f"\n{char * width}")
        self.logger.info(title)
        self.logger.info(f"{char * width}")

    def item(self, key: str, value: str):
        """Key-value information"""
        self.logger.info(f"  {key}: {value}")

    def bullet(self, msg: str):
        """Bullet point"""
        self.logger.info(f"  • {msg}")


# === Global logger management ===

_logger: Optional[PipelineLogger] = None


def get_logger(log_dir: Optional[Path] = None) -> PipelineLogger:
    """
    Get global logger

    Args:
        log_dir: Log directory (only effective on first call)

    Returns:
        PipelineLogger instance
    """
    global _logger
    if _logger is None:
        _logger = PipelineLogger(log_dir=log_dir)
    return _logger


def init_logger(log_dir: Path) -> PipelineLogger:
    """
    Initialize logger (specify log directory)

    Args:
        log_dir: Log directory

    Returns:
        PipelineLogger instance
    """
    global _logger
    _logger = PipelineLogger(log_dir=log_dir)
    return _logger


# === Convenience functions (can directly replace print) ===

def log_info(msg: str):
    """Log general information"""
    get_logger().info(msg)


def log_debug(msg: str):
    """Log debug information"""
    get_logger().debug(msg)


def log_success(msg: str):
    """Log success information"""
    get_logger().success(msg)


def log_error(msg: str):
    """Log error information"""
    get_logger().fail(msg)


def log_warning(msg: str):
    """Log warning information"""
    get_logger().warning(msg)


def log_section(title: str, width: int = 60):
    """Log separator line"""
    get_logger().section(title, width)


def log_step(step_num: int, total: int, description: str):
    """Log step information"""
    get_logger().step(step_num, total, description)
