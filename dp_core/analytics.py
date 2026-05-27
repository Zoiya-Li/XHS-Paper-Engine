"""
Publication recording module.

Records each published paper into a small SQLite table. This backs
deduplication (see dp_core/dedup.py) and `get_publish_history`.

Usage:
    from dp_core.analytics import PerformanceTracker
    tracker = PerformanceTracker()
    tracker.record_publication(post_id, paper_info, content_meta)
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from dataclasses import dataclass


# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "analytics.db"


@dataclass
class PublicationRecord:
    """A single publication record."""
    post_id: str
    paper_arxiv_id: str
    paper_title: str
    topic: str
    publish_time: str
    platform: str  # e.g. xiaohongshu
    title: str
    title_style: str  # question / statement / data / exclamation
    emoji_count: int
    content_length: int
    image_count: int
    tags: str  # JSON array


class DatabaseManager:
    """SQLite storage for publication records."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the publications table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT UNIQUE,
                    paper_arxiv_id TEXT,
                    paper_title TEXT,
                    topic TEXT,
                    publish_time DATETIME,
                    platform TEXT,
                    title TEXT,
                    title_style TEXT,
                    emoji_count INTEGER,
                    content_length INTEGER,
                    image_count INTEGER,
                    tags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_publications_topic ON publications(topic);
                CREATE INDEX IF NOT EXISTS idx_publications_publish_time ON publications(publish_time);
            """)
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row access by name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


class PerformanceTracker:
    """Records published papers."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db = DatabaseManager(db_path)

    def record_publication(
        self,
        post_id: str,
        paper_info: Dict[str, Any],
        content_meta: Dict[str, Any],
        platform: str = "xiaohongshu"
    ) -> bool:
        """
        Record a publication.

        Args:
            post_id: Post ID after publishing
            paper_info: {arxiv_id, title, topic}
            content_meta: {title, title_style, emoji_count, content_length, image_count, tags}
            platform: Platform name

        Returns:
            Whether successful
        """
        try:
            record = PublicationRecord(
                post_id=post_id,
                paper_arxiv_id=paper_info.get("arxiv_id", ""),
                paper_title=paper_info.get("title", ""),
                topic=paper_info.get("topic", "general"),
                publish_time=datetime.now().isoformat(),
                platform=platform,
                title=content_meta.get("title", ""),
                title_style=self._detect_title_style(content_meta.get("title", "")),
                emoji_count=content_meta.get("emoji_count", 0),
                content_length=content_meta.get("content_length", 0),
                image_count=content_meta.get("image_count", 0),
                tags=json.dumps(content_meta.get("tags", []), ensure_ascii=False)
            )

            conn = self.db.get_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO publications
                    (post_id, paper_arxiv_id, paper_title, topic, publish_time,
                     platform, title, title_style, emoji_count, content_length,
                     image_count, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.post_id, record.paper_arxiv_id, record.paper_title,
                    record.topic, record.publish_time, record.platform,
                    record.title, record.title_style, record.emoji_count,
                    record.content_length, record.image_count, record.tags
                ))
                conn.commit()
            finally:
                conn.close()

            print(f"✅ Recorded publication: {post_id} (arXiv: {record.paper_arxiv_id})")
            return True

        except Exception as e:
            print(f"❌ Failed to record publication: {e}")
            return False

    def _detect_title_style(self, title: str) -> str:
        """Classify the title style (stored for reference)."""
        if not title:
            return "unknown"
        if "？" in title or "?" in title:
            return "question"
        if any(c.isdigit() for c in title) and ("%" in title or "倍" in title or "x" in title.lower()):
            return "data"
        if "！" in title or "!" in title:
            return "exclamation"
        return "statement"
