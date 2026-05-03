import base64
import hashlib
import hmac
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from src.collectors.http_client import get_with_retry

NAVER_SEARCHAD_BASE_URL = "https://api.searchad.naver.com"
KEYWORD_TOOL_PATH = "/keywordstool"
DEFAULT_KEY_FILE = Path("D:/env/키파일.txt")
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_RELATED_KEYWORD_LIMIT = 10


class KeywordVolumeResult(TypedDict):
    keyword: str
    query: str
    monthly_pc: int
    monthly_mobile: int
    monthly_total: int
    competition: str
    ok: NotRequired[bool]
    error: NotRequired[str]


@dataclass(frozen=True)
class NaverSearchAdCredentials:
    api_key: str
    secret_key: str
    customer_id: str


class NaverSearchAdCollector:
    """네이버 검색광고 키워드도구 월검색량 수집기."""

    def __init__(self, credentials: NaverSearchAdCredentials) -> None:
        self.credentials = credentials

    @classmethod
    def from_environment(cls) -> "NaverSearchAdCollector | None":
        credentials = load_credentials()
        if not credentials:
            return None
        return cls(credentials)

    def fetch_keyword_volume(self, keyword: str) -> KeywordVolumeResult:
        query = normalize_query(keyword)
        if not query:
            return empty_result(keyword, query)

        try:
            payload = self.request_keyword_tool(query)
            keyword_items = payload.get("keywordList", [])
            item = pick_keyword_item(keyword_items, query)
            if not item:
                return empty_result(keyword, query)

            return build_keyword_volume_result(keyword, query, item)
        except Exception as exc:
            print(f"[naver_search_ad] 월검색량 수집 실패: {safe_log_text(keyword)}")
            result = empty_result(keyword, query)
            result["ok"] = False
            result["error"] = str(exc)
            return result

    def fetch_related_keyword_volumes(
        self,
        seed_keyword: str,
        limit: int = DEFAULT_RELATED_KEYWORD_LIMIT,
    ) -> list[KeywordVolumeResult]:
        query = normalize_query(seed_keyword)
        if not query:
            return []

        try:
            payload = self.request_keyword_tool(query)
            keyword_items = payload.get("keywordList", [])
            results = [
                build_keyword_volume_result(
                    keyword=str(item.get("relKeyword") or ""),
                    query=normalize_query(str(item.get("relKeyword") or "")),
                    item=item,
                )
                for item in keyword_items
                if item.get("relKeyword")
            ]
            results = [result for result in results if result["query"]]
            results.sort(key=lambda result: result["monthly_total"], reverse=True)
            return results[:limit]
        except Exception:
            print(f"[naver_search_ad] 연관키워드 수집 실패: {safe_log_text(seed_keyword)}")
            return []

    def request_keyword_tool(self, query: str) -> dict[str, Any]:
        response = get_with_retry(
            f"{NAVER_SEARCHAD_BASE_URL}{KEYWORD_TOOL_PATH}",
            headers=build_headers(self.credentials, "GET", KEYWORD_TOOL_PATH),
            params={"hintKeywords": query, "showDetail": "1"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        payload: dict[str, Any] = response.json()
        return payload


def load_credentials(key_file: Path = DEFAULT_KEY_FILE) -> NaverSearchAdCredentials | None:
    api_key = os.getenv("NAVER_SEARCHAD_API_KEY")
    secret_key = os.getenv("NAVER_SEARCHAD_SECRET_KEY")
    customer_id = os.getenv("NAVER_SEARCHAD_CUSTOMER_ID")
    if api_key and secret_key and customer_id:
        return NaverSearchAdCredentials(
            api_key=api_key,
            secret_key=secret_key,
            customer_id=customer_id,
        )

    if not key_file.exists():
        return None

    text = key_file.read_text(encoding="utf-8")
    api_key = find_value(text, ("엑세스라이선스", "액세스라이선스", "Access License"))
    secret_key = find_value(text, ("비밀키", "Secret Key", "SECRET_KEY"))
    customer_id = find_value(text, ("CUSTOMER_ID", "Customer ID", "고객 ID"))
    if not api_key or not secret_key or not customer_id:
        return None

    return NaverSearchAdCredentials(
        api_key=api_key,
        secret_key=secret_key,
        customer_id=customer_id,
    )


def find_value(text: str, labels: tuple[str, ...]) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        for label in labels:
            if not stripped.lower().startswith(label.lower()):
                continue
            if ":" in stripped:
                return stripped.split(":", 1)[1].strip()
            if "=" in stripped:
                return stripped.split("=", 1)[1].strip()
    return None


def build_headers(
    credentials: NaverSearchAdCredentials,
    method: str,
    uri: str,
) -> dict[str, str]:
    timestamp = str(round(time.time() * 1000))
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": credentials.api_key,
        "X-Customer": credentials.customer_id,
        "X-Signature": generate_signature(timestamp, method, uri, credentials.secret_key),
    }


def generate_signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def normalize_query(keyword: str) -> str:
    return re.sub(r"\s+", "", keyword.strip())


def safe_log_text(value: str, limit: int = 80) -> str:
    text = value[:limit]
    return text.encode("unicode_escape").decode("ascii")


def pick_keyword_item(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized_query = normalize_query(query).lower()
    for item in items:
        rel_keyword = normalize_query(str(item.get("relKeyword") or "")).lower()
        if rel_keyword == normalized_query:
            return item
    return items[0] if items else None


def build_keyword_volume_result(
    keyword: str,
    query: str,
    item: dict[str, Any],
) -> KeywordVolumeResult:
    monthly_pc = parse_count(item.get("monthlyPcQcCnt"))
    monthly_mobile = parse_count(item.get("monthlyMobileQcCnt"))
    return {
        "keyword": keyword,
        "query": query,
        "monthly_pc": monthly_pc,
        "monthly_mobile": monthly_mobile,
        "monthly_total": monthly_pc + monthly_mobile,
        "competition": str(item.get("compIdx") or ""),
        "ok": True,
    }


def parse_count(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value or "").replace(",", "").strip()
    if not text or text.startswith("<"):
        return 0
    if text.isdigit():
        return int(text)
    return 0


def empty_result(keyword: str, query: str) -> KeywordVolumeResult:
    return {
        "keyword": keyword,
        "query": query,
        "monthly_pc": 0,
        "monthly_mobile": 0,
        "monthly_total": 0,
        "competition": "",
        "ok": True,
    }
