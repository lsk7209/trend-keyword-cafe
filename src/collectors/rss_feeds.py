from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import yaml

ArticleItem = dict[str, Any]


class RSSCollector:
    """YAML에 정의된 RSS 출처에서 최근 기사 메타데이터를 수집합니다."""

    def __init__(self, config_path: str | Path = "config/rss_sources.yml") -> None:
        path = Path(config_path)
        if not path.is_absolute():
            path = Path.cwd() / path

        with path.open(encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or {}
        self.sources: list[dict[str, str]] = loaded.get("sources", [])

    def fetch_recent_articles(
        self,
        hours_back: int = 24,
        max_per_source: int = 30,
    ) -> list[ArticleItem]:
        """최근 N시간 내 RSS 기사 메타데이터를 수집합니다."""

        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        articles: list[ArticleItem] = []

        for source in self.sources:
            source_name = source.get("name", "unknown")
            source_url = source.get("url", "")
            if not source_url:
                continue

            try:
                feed = feedparser.parse(source_url)
                for entry in feed.entries[:max_per_source]:
                    published_at = self._parse_published(entry)
                    if published_at and published_at < cutoff:
                        continue

                    title = str(entry.get("title", "")).strip()
                    url = str(entry.get("link", "")).strip()
                    if not title or not url:
                        continue

                    articles.append(
                        {
                            "title": title,
                            "url": url,
                            "published_at": published_at,
                            "source_name": source_name,
                        }
                    )
            except Exception as exc:
                print(f"[rss] {source_name} 실패: {exc}")
                continue

        return articles

    def _parse_published(self, entry: Any) -> datetime | None:
        parsed = getattr(entry, "published_parsed", None)
        if parsed:
            return datetime(*parsed[:6])

        updated = getattr(entry, "updated_parsed", None)
        if updated:
            return datetime(*updated[:6])

        return None
