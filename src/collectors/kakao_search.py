import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from src.collectors.http_client import get_with_retry
from src.collectors.naver_search import clean_html

KAKAO_SEARCH_CAFE_URL = "https://dapi.kakao.com/v2/search/cafe"
DEFAULT_KEY_FILE = Path("D:/env/키파일.txt")
REQUEST_TIMEOUT_SECONDS = 10


class KakaoCafeSearchResult(TypedDict):
    service: str
    total: int
    titles: list[str]
    ok: NotRequired[bool]
    error: NotRequired[str]


@dataclass(frozen=True)
class KakaoCredentials:
    rest_api_key: str


class KakaoSearchCollector:
    """Kakao/Daum 카페 검색 신호 수집기."""

    def __init__(self, credentials: KakaoCredentials) -> None:
        self.credentials = credentials

    @classmethod
    def from_environment(cls) -> "KakaoSearchCollector | None":
        credentials = load_credentials()
        if not credentials:
            return None
        return cls(credentials)

    def search_cafe(self, query: str, size: int = 5) -> KakaoCafeSearchResult:
        try:
            response = get_with_retry(
                KAKAO_SEARCH_CAFE_URL,
                headers={"Authorization": f"KakaoAK {self.credentials.rest_api_key}"},
                params={
                    "query": query,
                    "size": str(size),
                    "page": "1",
                    "sort": "recency",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            payload: dict[str, Any] = response.json()
            metadata = payload.get("meta", {})
            documents = payload.get("documents", [])
            if not isinstance(metadata, dict):
                metadata = {}
            if not isinstance(documents, list):
                documents = []
            return {
                "service": "kakao_cafe",
                "total": int(metadata.get("pageable_count") or metadata.get("total_count") or 0),
                "titles": [
                    clean_html(str(document.get("title") or ""))
                    for document in documents
                    if isinstance(document, dict)
                ],
                "ok": True,
            }
        except Exception as exc:
            print(f"[kakao_search] 카페 검색 실패: {safe_log_text(query)}")
            return {
                "service": "kakao_cafe",
                "total": 0,
                "titles": [],
                "ok": False,
                "error": str(exc),
            }


def load_credentials(key_file: Path = DEFAULT_KEY_FILE) -> KakaoCredentials | None:
    rest_api_key = os.getenv("KAKAO_REST_API_KEY")
    if rest_api_key:
        return KakaoCredentials(rest_api_key=rest_api_key.strip())

    if not key_file.exists():
        return None

    text = key_file.read_text(encoding="utf-8")
    match = re.search(r"#카카오 REST API 키\s*(.*?)(?:\n#|\Z)", text, flags=re.S)
    if not match:
        return None
    api_key = "".join(line.strip() for line in match.group(1).splitlines() if line.strip())
    if not api_key:
        return None
    return KakaoCredentials(rest_api_key=api_key)


def safe_log_text(value: str, limit: int = 80) -> str:
    return value[:limit].encode("unicode_escape").decode("ascii")
