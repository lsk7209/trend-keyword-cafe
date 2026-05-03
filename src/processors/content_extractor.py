from typing import Any

import trafilatura

from src.collectors.http_client import get_with_retry


class ContentExtractor:
    """URL에서 한국어 본문을 추출합니다."""

    def extract(self, url: str, timeout: int = 10) -> str | None:
        try:
            response = get_with_retry(url, timeout=timeout)
            downloaded: Any = response.text
            if not downloaded:
                return None

            text: str | None = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                target_language="ko",
            )
            return text.strip() if text else None
        except Exception as exc:
            print(f"[content_extractor] {url} 실패: {exc}")
            return None
