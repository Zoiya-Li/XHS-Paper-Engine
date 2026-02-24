"""
Paper deduplication module - Avoid publishing the same paper repeatedly

Usage:
    from dp_core.dedup import PaperDeduplicator

    dedup = PaperDeduplicator()
    unique_papers = dedup.filter_published(papers)
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

    def filter_published(
        self,
        papers: List[Dict[str, Any]],
        days: int = 90,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Filter out already published papers

        Args:
            papers: Paper list
            days: Check recent N days
            verbose: Whether to print detailed information

        Returns:
            Filtered paper list
        """
        if not papers:
            return []

        # Preload published data
        published_ids = self.get_published_arxiv_ids(days)
        published_titles = self.get_published_titles(days)

        if verbose:
            print(f"\n🔍 Deduplication check: {len(published_ids)} papers published in last {days} days")

        unique_papers = []
        duplicates = []

        for paper in papers:
            is_dup = False
            dup_reason = ""

            # Check arXiv ID
            arxiv_id = self._extract_arxiv_id(paper)
            if arxiv_id and arxiv_id in published_ids:
                is_dup = True
                dup_reason = f"Duplicate arXiv ID: {arxiv_id}"

            # Check title
            if not is_dup:
                paper_title = paper.get("Title", paper.get("title", ""))
                if paper_title:
                    normalized = self._normalize_title(paper_title)

                    if normalized in published_titles:
                        is_dup = True
                        dup_reason = "Title exact match"
                    else:
                        # Fuzzy match
                        for pub_title in published_titles:
                            sim = self._title_similarity(normalized, pub_title)
                            if sim > 0.85:
                                is_dup = True
                                dup_reason = f"Title similarity {sim:.0%}"
                                break

            if is_dup:
                duplicates.append((paper, dup_reason))
            else:
                unique_papers.append(paper)

        if verbose:
            print(f"   Input: {len(papers)} papers")
            print(f"   Duplicates: {len(duplicates)} papers")
            print(f"   Kept: {len(unique_papers)} papers")

            if duplicates and len(duplicates) <= 5:
                print(f"\n   Filtered duplicate papers:")
                for paper, reason in duplicates:
                    title = paper.get("Title", paper.get("title", ""))[:40]
                    print(f"   • {title}... ({reason})")

        return unique_papers

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

    def print_published_summary(self, days: int = 30):
        """Print published papers summary"""
        published = self.get_published_papers(days)

        print(f"\n{'='*60}")
        print(f"📊 Publication records for last {days} days")
        print(f"{'='*60}")

        if not published:
            print("No publication records")
            return

        # Statistics by topic
        topic_counts = {}
        for p in published:
            topic = p.get("topic", "Other")
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

        print(f"Total publications: {len(published)} papers")
        print(f"\nDistribution by topic:")
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {topic}: {count} papers")

        print(f"\nRecent publications:")
        for p in published[:5]:
            title = p.get("title", "")[:40]
            date = p.get("publish_time", "")[:10]
            platform = p.get("platform", "")
            print(f"  • [{date}] [{platform}] {title}...")


# Convenience functions
def filter_published_papers(papers: List[Dict], days: int = 90) -> List[Dict]:
    """Filter published papers (convenience function)"""
    dedup = PaperDeduplicator()
    return dedup.filter_published(papers, days)


def is_paper_published(paper: Dict, days: int = 90) -> bool:
    """Check if paper is published (convenience function)"""
    dedup = PaperDeduplicator()
    return dedup.is_published(paper, days)
