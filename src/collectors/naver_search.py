import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from src.collectors.http_client import get_with_retry

NAVER_OPENAPI_BASE_URL = "https://openapi.naver.com/v1/search"
DEFAULT_KEY_FILE = Path("D:/env/키파일.txt")
REQUEST_TIMEOUT_SECONDS = 10

SEARCH_SERVICES = ("cafearticle", "blog", "kin", "news")
SHOPPING_SEARCH_SERVICE = "shop"
SUPPORTED_SEARCH_SERVICES = (*SEARCH_SERVICES, SHOPPING_SEARCH_SERVICE)


class NaverSearchResult(TypedDict):
    service: str
    total: int
    titles: list[str]
    ok: NotRequired[bool]
    error: NotRequired[str]


@dataclass(frozen=True)
class NaverOpenApiCredentials:
    client_id: str
    client_secret: str


class NaverSearchCollector:
    """네이버 OpenAPI 검색 신호 수집기."""

    def __init__(self, credentials: NaverOpenApiCredentials) -> None:
        self.credentials = credentials

    @classmethod
    def from_environment(cls) -> "NaverSearchCollector | None":
        credentials = load_credentials()
        if not credentials:
            return None
        return cls(credentials)

    def search(self, service: str, query: str, display: int = 5) -> NaverSearchResult:
        if service not in SUPPORTED_SEARCH_SERVICES:
            raise ValueError(f"지원하지 않는 네이버 검색 서비스입니다: {service}")

        try:
            response = get_with_retry(
                f"{NAVER_OPENAPI_BASE_URL}/{service}.json",
                headers={
                    "X-Naver-Client-Id": self.credentials.client_id,
                    "X-Naver-Client-Secret": self.credentials.client_secret,
                },
                params={
                    "query": query,
                    "display": str(display),
                    "start": "1",
                    "sort": "date",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            payload: dict[str, Any] = response.json()
            return {
                "service": service,
                "total": int(payload.get("total", 0)),
                "titles": [clean_html(item.get("title", "")) for item in payload.get("items", [])],
                "ok": True,
            }
        except Exception as exc:
            print(f"[naver_search] {service} 검색 실패: {exc}")
            return {"service": service, "total": 0, "titles": [], "ok": False, "error": str(exc)}

    def fetch_topic_signals(self, query: str) -> list[NaverSearchResult]:
        return [self.search(service, query) for service in SEARCH_SERVICES]

    def search_shopping(self, query: str, display: int = 5) -> NaverSearchResult:
        return self.search(SHOPPING_SEARCH_SERVICE, query, display=display)


def load_credentials(key_file: Path = DEFAULT_KEY_FILE) -> NaverOpenApiCredentials | None:
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if client_id and client_secret:
        return NaverOpenApiCredentials(client_id=client_id, client_secret=client_secret)

    if not key_file.exists():
        return None

    text = key_file.read_text(encoding="utf-8")
    client_id_match = re.search(r"Client ID\s*:\s*(\S+)", text)
    client_secret_match = re.search(r"Client Secret\s*:\s*(\S+)", text)
    if not client_id_match or not client_secret_match:
        return None

    return NaverOpenApiCredentials(
        client_id=client_id_match.group(1),
        client_secret=client_secret_match.group(1),
    )


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return value.replace("&quot;", '"').replace("&amp;", "&").strip()


def serialize_titles(titles: list[str]) -> str:
    return json.dumps(titles, ensure_ascii=False)
