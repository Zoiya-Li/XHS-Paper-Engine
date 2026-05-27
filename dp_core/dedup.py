"""
Paper deduplication module - Avoid publishing the same paper repeatedly

Usage:
    from dp_core.dedup import PaperDeduplicator

    dedup = PaperDeduplicator()
    if not dedup.is_published(paper):   # checks arXiv id + title similarity
        ...
"""

import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from difflib import SequenceMatcher

from .analytics import DatabaseManager, DB_PATH


class PaperDeduplicator:
    """Paper deduplicator - Avoid duplicate publishing"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db = DatabaseManager(db_path)
        self._published_cache: Optional[Set[str]] = None
        self._cache_time: Optional[datetime] = None

    def get_published_papers(self, days: int = 90) -> List[Dict[str, Any]]:
        """
        Get list of recently published papers

        Args:
            days: Query publication records from recent N days

        Returns:
            Published paper list
        """
        published = []

        try:
            with self.db.get_connection() as conn:
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

                rows = conn.execute("""
                    SELECT DISTINCT
                        paper_arxiv_id,
                        paper_title,
                        topic,
                        publish_time,
                        platform
                    FROM publications
                    WHERE publish_time >= ?
                    ORDER BY publish_time DESC
                """, (cutoff_date,)).fetchall()

                for row in rows:
                    published.append({
                        "arxiv_id": row["paper_arxiv_id"],
                        "title": row["paper_title"],
                        "topic": row["topic"],
                        "publish_time": row["publish_time"],
                        "platform": row["platform"]
                    })

        except Exception as e:
            print(f"⚠️  Failed to get published papers: {e}")

        return published

    def get_published_arxiv_ids(self, days: int = 90) -> Set[str]:
        """
        Get set of published paper arXiv IDs

        Args:
            days: Query recent N days

        Returns:
            arXiv ID set
        """
        # Use cache
        if self._published_cache and self._cache_time:
            if (datetime.now() - self._cache_time).seconds < 60:
                return self._published_cache

        arxiv_ids = set()

        try:
            with self.db.get_connection() as conn:
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

                rows = conn.execute("""
                    SELECT DISTINCT paper_arxiv_id
                    FROM publications
                    WHERE publish_time >= ?
                    AND paper_arxiv_id IS NOT NULL
                    AND paper_arxiv_id != ''
                """, (cutoff_date,)).fetchall()

                arxiv_ids = {row["paper_arxiv_id"] for row in rows}

        except Exception as e:
            print(f"⚠️  Failed to get published arXiv IDs: {e}")

        self._published_cache = arxiv_ids
        self._cache_time = datetime.now()

        return arxiv_ids

    def get_published_titles(self, days: int = 90) -> Set[str]:
        """
        Get set of published paper titles (normalized)

        Args:
            days: Query recent N days

        Returns:
            Title set (lowercase, special characters removed)
        """
        titles = set()

        try:
            with self.db.get_connection() as conn:
                cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

                rows = conn.execute("""
                    SELECT DISTINCT paper_title
                    FROM publications
                    WHERE publish_time >= ?
                    AND paper_title IS NOT NULL
                    AND paper_title != ''
                """, (cutoff_date,)).fetchall()

                titles = {self._normalize_title(row["paper_title"]) for row in rows}

        except Exception as e:
            print(f"⚠️  Failed to get published titles: {e}")

        return titles

    def is_published(self, paper: Dict[str, Any], days: int = 90) -> bool:
        """
        Check if paper has been published

        Args:
            paper: Paper information
            days: Check recent N days

        Returns:
            Whether published
        """
        # 1. Check arXiv ID
        arxiv_id = self._extract_arxiv_id(paper)
        if arxiv_id:
            published_ids = self.get_published_arxiv_ids(days)
            if arxiv_id in published_ids:
                return True

        # 2. Check title similarity
        paper_title = paper.get("Title", paper.get("title", ""))
        if paper_title:
            normalized_title = self._normalize_title(paper_title)
            published_titles = self.get_published_titles(days)

            # Exact match
            if normalized_title in published_titles:
                return True

            # Fuzzy match (similarity > 0.85)
            for pub_title in published_titles:
                if self._title_similarity(normalized_title, pub_title) > 0.85:
                    return True

        return False

    def _extract_arxiv_id(self, paper: Dict[str, Any]) -> Optional[str]:
        """Extract arXiv ID from paper information"""
        # Direct arxiv_id field
        arxiv_id = paper.get("arxiv_id", "")
        if arxiv_id:
            return arxiv_id

        # Extract from link
        link = paper.get("Link", paper.get("link", ""))
        if "arxiv.org" in link:
            # Match arXiv ID format: 2401.12345 or cs/0601001
            match = re.search(r'(\d{4}\.\d{4,5}|[a-z-]+/\d{7})', link)
            if match:
                return match.group(1)

        return None

    def _normalize_title(self, title: str) -> str:
        """Normalize title (for comparison)"""
        # Convert to lowercase
        title = title.lower()
        # Remove special characters, keep only alphanumeric and spaces
        title = re.sub(r'[^a-z0-9\s]', '', title)
        # Compress whitespace
        title = ' '.join(title.split())
        return title

    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate similarity between two titles"""
        return SequenceMatcher(None, title1, title2).ratio()
