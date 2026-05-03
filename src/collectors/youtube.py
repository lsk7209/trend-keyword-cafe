import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from src.collectors.http_client import get_with_retry

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
DEFAULT_KEY_FILE = Path("D:/env/키파일.txt")
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESULTS = 10


class YouTubeVideo(TypedDict):
    title: str
    region: str
    channel_title: str
    video_id: str
    category_id: str
    published_at: datetime | None
    view_count: int
    ok: NotRequired[bool]
    error: NotRequired[str]


@dataclass(frozen=True)
class YouTubeCredentials:
    api_key: str


class YouTubeCollector:
    """YouTube Data API 기반 인기 영상 수집기."""

    def __init__(self, credentials: YouTubeCredentials) -> None:
        self.credentials = credentials

    @classmethod
    def from_environment(cls) -> "YouTubeCollector | None":
        credentials = load_credentials()
        if not credentials:
            return None
        return cls(credentials)

    def fetch_most_popular(
        self,
        region_code: str,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> list[YouTubeVideo]:
        try:
            response = get_with_retry(
                YOUTUBE_VIDEOS_URL,
                params={
                    "part": "snippet,statistics",
                    "chart": "mostPopular",
                    "regionCode": region_code,
                    "maxResults": str(max_results),
                    "key": self.credentials.api_key,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            payload: dict[str, Any] = response.json()
            return [
                parse_video_item(item, region_code)
                for item in payload.get("items", [])
                if isinstance(item, dict)
            ]
        except Exception as exc:
            print(f"[youtube] {region_code} 인기 영상 수집 실패: {exc}")
            return []


def parse_video_item(item: dict[str, Any], region_code: str) -> YouTubeVideo:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    if not isinstance(snippet, dict):
        snippet = {}
    if not isinstance(statistics, dict):
        statistics = {}

    return {
        "title": str(snippet.get("title") or "").strip(),
        "region": region_code,
        "channel_title": str(snippet.get("channelTitle") or "").strip(),
        "video_id": str(item.get("id") or "").strip(),
        "category_id": str(snippet.get("categoryId") or "").strip(),
        "published_at": parse_youtube_datetime(str(snippet.get("publishedAt") or "")),
        "view_count": parse_int(statistics.get("viewCount")),
        "ok": True,
    }


def parse_youtube_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_credentials(key_file: Path = DEFAULT_KEY_FILE) -> YouTubeCredentials | None:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if api_key:
        return YouTubeCredentials(api_key=api_key.strip())

    if not key_file.exists():
        return None

    text = key_file.read_text(encoding="utf-8")
    section_match = re.search(r"#유튜브 api 키\s*(.*?)(?:\n#|\Z)", text, flags=re.S)
    if not section_match:
        return None

    api_key = "".join(line.strip() for line in section_match.group(1).splitlines() if line.strip())
    if not api_key:
        return None
    return YouTubeCredentials(api_key=api_key)
