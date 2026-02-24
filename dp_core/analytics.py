"""
Analytics module - Collect publish data, analyze performance, generate reports

Usage:
    from dp_core.analytics import PerformanceTracker, AnalyticsReport

    # Record publication
    tracker = PerformanceTracker()
    tracker.record_publication(post_id, paper_info, content_meta)

    # Get performance data
    tracker.fetch_metrics(post_id)

    # Generate analysis report
    report = AnalyticsReport()
    report.generate_report()
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
import statistics


# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "analytics.db"


@dataclass
class PublicationRecord:
    """Publication record"""
    post_id: str
    paper_arxiv_id: str
    paper_title: str
    topic: str
    publish_time: str
    platform: str  # xiaohongshu
    title: str
    title_style: str  # question / statement / data / suspense
    emoji_count: int
    content_length: int
    image_count: int
    tags: str  # JSON array


@dataclass
class MetricsRecord:
    """Performance metrics"""
    post_id: str
    fetch_time: str
    views: int
    likes: int
    favorites: int
    comments: int
    shares: int


class DatabaseManager:
    """Database management"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Publication records table
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

                -- Performance metrics table
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT,
                    fetch_time DATETIME,
                    views INTEGER DEFAULT 0,
                    likes INTEGER DEFAULT 0,
                    favorites INTEGER DEFAULT 0,
                    comments INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    FOREIGN KEY (post_id) REFERENCES publications(post_id)
                );

                -- Topic performance summary table
                CREATE TABLE IF NOT EXISTS topic_performance (
                    topic TEXT PRIMARY KEY,
                    total_posts INTEGER DEFAULT 0,
                    avg_views REAL DEFAULT 0,
                    avg_likes REAL DEFAULT 0,
                    avg_favorites REAL DEFAULT 0,
                    avg_comments REAL DEFAULT 0,
                    last_covered DATE,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                -- Publish time performance table
                CREATE TABLE IF NOT EXISTS time_performance (
                    hour INTEGER,
                    day_of_week INTEGER,
                    total_posts INTEGER DEFAULT 0,
                    avg_views REAL DEFAULT 0,
                    avg_likes REAL DEFAULT 0,
                    avg_engagement REAL DEFAULT 0,
                    PRIMARY KEY (hour, day_of_week)
                );

                -- Writing style performance table
                CREATE TABLE IF NOT EXISTS style_performance (
                    style_key TEXT PRIMARY KEY,
                    style_value TEXT,
                    total_posts INTEGER DEFAULT 0,
                    avg_views REAL DEFAULT 0,
                    avg_likes REAL DEFAULT 0,
                    correlation REAL DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_publications_topic ON publications(topic);
                CREATE INDEX IF NOT EXISTS idx_publications_publish_time ON publications(publish_time);
                CREATE INDEX IF NOT EXISTS idx_metrics_post_id ON metrics(post_id);
                CREATE INDEX IF NOT EXISTS idx_metrics_fetch_time ON metrics(fetch_time);
            """)
            conn.commit()

    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


class PerformanceTracker:
    """Performance data collector"""

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
        Record publication information

        Args:
            post_id: Post ID after publishing
            paper_info: Paper information {arxiv_id, title, topic, tags}
            content_meta: Content metadata {title, title_style, emoji_count, content_length, image_count, tags}
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

            # Use explicit connection with proper error handling
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
                # Force flush to ensure data is written
                conn.execute("PRAGMA wal_checkpoint(FULL)")
            finally:
                conn.close()

            print(f"✅ Recorded publication: {post_id} (arXiv: {record.paper_arxiv_id})")
            return True

        except Exception as e:
            print(f"❌ Failed to record publication: {e}")
            import traceback
            traceback.print_exc()
            return False

    def record_metrics(
        self,
        post_id: str,
        views: int = 0,
        likes: int = 0,
        favorites: int = 0,
        comments: int = 0,
        shares: int = 0
    ) -> bool:
        """
        Record performance metrics

        Args:
            post_id: Post ID
            views: View count
            likes: Like count
            favorites: Favorite count
            comments: Comment count
            shares: Share count

        Returns:
            Whether successful
        """
        try:
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT INTO metrics (post_id, fetch_time, views, likes, favorites, comments, shares)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (post_id, datetime.now().isoformat(), views, likes, favorites, comments, shares))
                conn.commit()

            print(f"✅ Recorded metrics: {post_id} - 👁 {views} ❤️ {likes} ⭐ {favorites}")
            return True

        except Exception as e:
            print(f"❌ Failed to record metrics: {e}")
            return False

    def get_latest_metrics(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get latest performance metrics"""
        with self.db.get_connection() as conn:
            row = conn.execute("""
                SELECT * FROM metrics
                WHERE post_id = ?
                ORDER BY fetch_time DESC
                LIMIT 1
            """, (post_id,)).fetchone()

            if row:
                return dict(row)
        return None

    def get_publication_history(
        self,
        days: int = 30,
        platform: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get publication history

        Args:
            days: Recent N days
            platform: Platform filter

        Returns:
            Publication record list
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self.db.get_connection() as conn:
            if platform:
                rows = conn.execute("""
                    SELECT p.*,
                           (SELECT views FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_views,
                           (SELECT likes FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_likes,
                           (SELECT favorites FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_favorites,
                           (SELECT comments FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_comments
                    FROM publications p
                    WHERE p.publish_time >= ? AND p.platform = ?
                    ORDER BY p.publish_time DESC
                """, (cutoff, platform)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT p.*,
                           (SELECT views FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_views,
                           (SELECT likes FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_likes,
                           (SELECT favorites FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_favorites,
                           (SELECT comments FROM metrics WHERE post_id = p.post_id ORDER BY fetch_time DESC LIMIT 1) as latest_comments
                    FROM publications p
                    WHERE p.publish_time >= ?
                    ORDER BY p.publish_time DESC
                """, (cutoff,)).fetchall()

            return [dict(row) for row in rows]

    def _detect_title_style(self, title: str) -> str:
        """Detect title style"""
        if not title:
            return "unknown"

        if "？" in title or "?" in title:
            return "question"
        elif any(c.isdigit() for c in title) and ("%" in title or "倍" in title or "x" in title.lower()):
            return "data"
        elif "！" in title or "!" in title:
            return "exclamation"
        else:
            return "statement"


class AnalyticsReport:
    """Analysis report generator"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db = DatabaseManager(db_path)
        self.tracker = PerformanceTracker(db_path)

    def generate_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive analysis report

        Args:
            days: Analyze data from recent N days

        Returns:
            Analysis report
        """
        history = self.tracker.get_publication_history(days)

        if not history:
            return {
                "status": "no_data",
                "message": f"No publish records in the last {days} days"
            }

        report = {
            "period": f"Last {days} days",
            "generated_at": datetime.now().isoformat(),
            "summary": self._generate_summary(history),
            "topic_analysis": self._analyze_topics(history),
            "time_analysis": self._analyze_publish_time(history),
            "style_analysis": self._analyze_writing_style(history),
            "recommendations": self._generate_recommendations(history)
        }

        return report

    def _generate_summary(self, history: List[Dict]) -> Dict[str, Any]:
        """Generate overall summary"""
        total_posts = len(history)
        posts_with_metrics = [h for h in history if h.get("latest_views") is not None]

        if not posts_with_metrics:
            return {
                "total_posts": total_posts,
                "posts_with_metrics": 0,
                "message": "No performance data yet, please collect metrics first"
            }

        views = [h["latest_views"] or 0 for h in posts_with_metrics]
        likes = [h["latest_likes"] or 0 for h in posts_with_metrics]
        favorites = [h["latest_favorites"] or 0 for h in posts_with_metrics]

        return {
            "total_posts": total_posts,
            "posts_with_metrics": len(posts_with_metrics),
            "total_views": sum(views),
            "total_likes": sum(likes),
            "total_favorites": sum(favorites),
            "avg_views": round(statistics.mean(views), 1) if views else 0,
            "avg_likes": round(statistics.mean(likes), 1) if likes else 0,
            "avg_favorites": round(statistics.mean(favorites), 1) if favorites else 0,
            "best_post": max(posts_with_metrics, key=lambda x: (x.get("latest_views") or 0)) if posts_with_metrics else None,
            "engagement_rate": round(sum(likes) / sum(views) * 100, 2) if sum(views) > 0 else 0
        }

    def _analyze_topics(self, history: List[Dict]) -> Dict[str, Any]:
        """Analyze topic performance"""
        topic_stats = {}

        for h in history:
            topic = h.get("topic", "general")
            if topic not in topic_stats:
                topic_stats[topic] = {
                    "count": 0,
                    "views": [],
                    "likes": [],
                    "favorites": []
                }

            topic_stats[topic]["count"] += 1
            if h.get("latest_views") is not None:
                topic_stats[topic]["views"].append(h["latest_views"] or 0)
                topic_stats[topic]["likes"].append(h["latest_likes"] or 0)
                topic_stats[topic]["favorites"].append(h["latest_favorites"] or 0)

        # Calculate average performance for each topic
        topic_performance = {}
        for topic, stats in topic_stats.items():
            if stats["views"]:
                topic_performance[topic] = {
                    "post_count": stats["count"],
                    "avg_views": round(statistics.mean(stats["views"]), 1),
                    "avg_likes": round(statistics.mean(stats["likes"]), 1),
                    "avg_favorites": round(statistics.mean(stats["favorites"]), 1),
                    "engagement_score": round(
                        (statistics.mean(stats["likes"]) + statistics.mean(stats["favorites"])) /
                        max(statistics.mean(stats["views"]), 1) * 100, 2
                    )
                }
            else:
                topic_performance[topic] = {
                    "post_count": stats["count"],
                    "avg_views": 0,
                    "avg_likes": 0,
                    "avg_favorites": 0,
                    "engagement_score": 0
                }

        # Sort to find best topics
        sorted_topics = sorted(
            topic_performance.items(),
            key=lambda x: x[1]["avg_views"],
            reverse=True
        )

        return {
            "topic_performance": topic_performance,
            "best_topics": [t[0] for t in sorted_topics[:3]],
            "underperforming_topics": [t[0] for t in sorted_topics[-3:] if t[1]["post_count"] >= 2]
        }

    def _analyze_publish_time(self, history: List[Dict]) -> Dict[str, Any]:
        """Analyze publish time effectiveness"""
        time_stats = {}  # {(hour, day_of_week): [metrics]}

        for h in history:
            try:
                pub_time = datetime.fromisoformat(h["publish_time"])
                key = (pub_time.hour, pub_time.weekday())

                if key not in time_stats:
                    time_stats[key] = {"views": [], "likes": []}

                if h.get("latest_views") is not None:
                    time_stats[key]["views"].append(h["latest_views"] or 0)
                    time_stats[key]["likes"].append(h["latest_likes"] or 0)
            except:
                continue

        # Calculate average performance for each time slot
        time_performance = {}
        for (hour, dow), stats in time_stats.items():
            if stats["views"]:
                time_performance[f"{hour}:00_day{dow}"] = {
                    "hour": hour,
                    "day_of_week": dow,
                    "post_count": len(stats["views"]),
                    "avg_views": round(statistics.mean(stats["views"]), 1),
                    "avg_likes": round(statistics.mean(stats["likes"]), 1)
                }

        # Find best publish times
        best_times = sorted(
            time_performance.values(),
            key=lambda x: x["avg_views"],
            reverse=True
        )[:5]

        # Aggregate by hour
        hourly_stats = {}
        for (hour, _), stats in time_stats.items():
            if hour not in hourly_stats:
                hourly_stats[hour] = {"views": [], "likes": []}
            hourly_stats[hour]["views"].extend(stats["views"])
            hourly_stats[hour]["likes"].extend(stats["likes"])

        best_hours = sorted(
            [(h, statistics.mean(s["views"]) if s["views"] else 0) for h, s in hourly_stats.items()],
            key=lambda x: x[1],
            reverse=True
        )[:3]

        return {
            "time_performance": time_performance,
            "best_times": best_times,
            "best_hours": [h[0] for h in best_hours],
            "recommendation": f"Recommended to publish around {best_hours[0][0]}:00" if best_hours else "Insufficient data"
        }

    def _analyze_writing_style(self, history: List[Dict]) -> Dict[str, Any]:
        """Analyze writing style effectiveness"""
        style_stats = {
            "title_style": {},
            "emoji_count": {"low": [], "medium": [], "high": []},
            "content_length": {"short": [], "medium": [], "long": []}
        }

        for h in history:
            if h.get("latest_views") is None:
                continue

            metrics = {
                "views": h["latest_views"] or 0,
                "likes": h["latest_likes"] or 0
            }

            # Title style
            title_style = h.get("title_style", "unknown")
            if title_style not in style_stats["title_style"]:
                style_stats["title_style"][title_style] = []
            style_stats["title_style"][title_style].append(metrics)

            # Emoji count classification
            emoji_count = h.get("emoji_count", 0)
            if emoji_count <= 3:
                style_stats["emoji_count"]["low"].append(metrics)
            elif emoji_count <= 7:
                style_stats["emoji_count"]["medium"].append(metrics)
            else:
                style_stats["emoji_count"]["high"].append(metrics)

            # Content length classification
            content_length = h.get("content_length", 0)
            if content_length <= 300:
                style_stats["content_length"]["short"].append(metrics)
            elif content_length <= 500:
                style_stats["content_length"]["medium"].append(metrics)
            else:
                style_stats["content_length"]["long"].append(metrics)

        # Calculate average performance for each style
        def calc_avg(metrics_list):
            if not metrics_list:
                return {"avg_views": 0, "avg_likes": 0, "count": 0}
            return {
                "avg_views": round(statistics.mean([m["views"] for m in metrics_list]), 1),
                "avg_likes": round(statistics.mean([m["likes"] for m in metrics_list]), 1),
                "count": len(metrics_list)
            }

        title_style_perf = {k: calc_avg(v) for k, v in style_stats["title_style"].items()}
        emoji_perf = {k: calc_avg(v) for k, v in style_stats["emoji_count"].items()}
        length_perf = {k: calc_avg(v) for k, v in style_stats["content_length"].items()}

        # Find best style
        best_title_style = max(title_style_perf.items(), key=lambda x: x[1]["avg_views"])[0] if title_style_perf else "unknown"
        best_emoji_level = max(emoji_perf.items(), key=lambda x: x[1]["avg_views"])[0] if emoji_perf else "medium"
        best_length_level = max(length_perf.items(), key=lambda x: x[1]["avg_views"])[0] if length_perf else "medium"

        return {
            "title_style_performance": title_style_perf,
            "emoji_performance": emoji_perf,
            "content_length_performance": length_perf,
            "best_title_style": best_title_style,
            "best_emoji_level": best_emoji_level,
            "best_content_length": best_length_level,
            "optimal_parameters": {
                "title_style": best_title_style,
                "emoji_count": {"low": "1-3", "medium": "4-7", "high": "8+"}[best_emoji_level],
                "content_length": {"short": "≤300", "medium": "300-500", "long": ">500"}[best_length_level]
            }
        }

    def _generate_recommendations(self, history: List[Dict]) -> List[str]:
        """Generate optimization recommendations"""
        recommendations = []

        posts_with_metrics = [h for h in history if h.get("latest_views") is not None]

        if len(posts_with_metrics) < 5:
            recommendations.append("📊 Insufficient data. Continue publishing and collecting metrics for more accurate analysis.")
            return recommendations

        # Generate recommendations based on analysis results
        topic_analysis = self._analyze_topics(history)
        time_analysis = self._analyze_publish_time(history)
        style_analysis = self._analyze_writing_style(history)

        # Topic recommendations
        if topic_analysis.get("best_topics"):
            best_topics = topic_analysis["best_topics"][:2]
            recommendations.append(f"🎯 Hot topics: {', '.join(best_topics)} perform best, focus on papers in these areas")

        # Time recommendations
        if time_analysis.get("best_hours"):
            best_hour = time_analysis["best_hours"][0]
            recommendations.append(f"⏰ Best publish time: Content published around {best_hour}:00 gets highest views")

        # Style recommendations
        optimal = style_analysis.get("optimal_parameters", {})
        if optimal:
            if optimal.get("title_style") == "question":
                recommendations.append("❓ Title style: Question titles perform better, try asking questions to spark curiosity")
            elif optimal.get("title_style") == "data":
                recommendations.append("📈 Title style: Data-driven titles are more attractive, try adding specific numbers to titles")

            if optimal.get("emoji_count"):
                recommendations.append(f"😊 Emoji usage: Posts with {optimal['emoji_count']} emojis perform best")

            if optimal.get("content_length"):
                recommendations.append(f"📝 Content length: Content with {optimal['content_length']} characters performs best")

        return recommendations

    def print_report(self, days: int = 30):
        """Print formatted analysis report"""
        report = self.generate_report(days)

        if report.get("status") == "no_data":
            print(f"\n⚠️  {report['message']}")
            return

        print("\n" + "="*60)
        print(f"📊 效果分析报告 - {report['period']}")
        print("="*60)

        # 总体摘要
        summary = report.get("summary", {})
        print(f"\n📈 总体表现")
        print(f"   发布总数: {summary.get('total_posts', 0)} 篇")
        print(f"   有数据的: {summary.get('posts_with_metrics', 0)} 篇")
        if summary.get("total_views"):
            print(f"   总阅读量: {summary.get('total_views', 0)}")
            print(f"   总点赞数: {summary.get('total_likes', 0)}")
            print(f"   平均阅读: {summary.get('avg_views', 0)}")
            print(f"   平均点赞: {summary.get('avg_likes', 0)}")
            print(f"   互动率:   {summary.get('engagement_rate', 0)}%")

        # 主题分析
        topic = report.get("topic_analysis", {})
        if topic.get("best_topics"):
            print(f"\n🎯 最佳主题: {', '.join(topic['best_topics'])}")

        # 时间分析
        time = report.get("time_analysis", {})
        if time.get("best_hours"):
            print(f"\n⏰ 最佳发布时间: {time['best_hours']}点")

        # 风格分析
        style = report.get("style_analysis", {})
        optimal = style.get("optimal_parameters", {})
        if optimal:
            print(f"\n✍️  最佳写作风格:")
            print(f"   标题风格: {optimal.get('title_style', 'N/A')}")
            print(f"   Emoji数量: {optimal.get('emoji_count', 'N/A')}")
            print(f"   内容长度: {optimal.get('content_length', 'N/A')}")

        # 建议
        recommendations = report.get("recommendations", [])
        if recommendations:
            print(f"\n💡 优化建议:")
            for rec in recommendations:
                print(f"   {rec}")

        print("\n" + "="*60)


class AnalyticsCollector:
    """Analytics helper for tools (report + recommendations)."""

    def __init__(self, db_path: Path = DB_PATH):
        self.reporter = AnalyticsReport(db_path)
        self.tracker = PerformanceTracker(db_path)

    def generate_report(self, days: int = 30) -> Dict[str, Any]:
        """Generate report for recent days."""
        return self.reporter.generate_report(days)

    def get_best_publish_times(self, platform: Optional[str] = None, days: int = 30) -> List[Dict[str, Any]]:
        """Get best publish times based on recent history."""
        history = self.tracker.get_publication_history(days=days, platform=platform)
        if not history:
            return []
        analysis = self.reporter._analyze_publish_time(history)
        return analysis.get("best_times", [])

    def get_hot_topics(self, days: int = 7, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get hot topics based on recent history."""
        history = self.tracker.get_publication_history(days=days, platform=platform)
        if not history:
            return []
        analysis = self.reporter._analyze_topics(history)
        topic_perf = analysis.get("topic_performance", {})
        topics = [{"topic": k, **v} for k, v in topic_perf.items()]
        topics.sort(key=lambda t: t.get("avg_views", 0), reverse=True)
        return topics


def update_topic_performance():
    """更新主题效果汇总表（可定期运行）"""
    db = DatabaseManager()

    with db.get_connection() as conn:
        # 计算各主题的平均效果
        conn.execute("""
            INSERT OR REPLACE INTO topic_performance (topic, total_posts, avg_views, avg_likes, avg_favorites, last_covered, updated_at)
            SELECT
                p.topic,
                COUNT(*) as total_posts,
                AVG(m.views) as avg_views,
                AVG(m.likes) as avg_likes,
                AVG(m.favorites) as avg_favorites,
                MAX(DATE(p.publish_time)) as last_covered,
                CURRENT_TIMESTAMP as updated_at
            FROM publications p
            LEFT JOIN (
                SELECT post_id, views, likes, favorites,
                       ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY fetch_time DESC) as rn
                FROM metrics
            ) m ON p.post_id = m.post_id AND m.rn = 1
            GROUP BY p.topic
        """)
        conn.commit()

    print("✅ 主题效果汇总已更新")


# 便捷函数
def record_publication(post_id: str, paper_info: Dict, content_meta: Dict, platform: str = "xiaohongshu"):
    """记录发布（便捷函数）"""
    tracker = PerformanceTracker()
    return tracker.record_publication(post_id, paper_info, content_meta, platform)


def record_metrics(post_id: str, views: int, likes: int, favorites: int = 0, comments: int = 0, shares: int = 0):
    """记录效果指标（便捷函数）"""
    tracker = PerformanceTracker()
    return tracker.record_metrics(post_id, views, likes, favorites, comments, shares)


def print_analytics_report(days: int = 30):
    """打印分析报告（便捷函数）"""
    report = AnalyticsReport()
    report.print_report(days)
