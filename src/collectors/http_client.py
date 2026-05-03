import time
from collections.abc import Mapping

import requests

DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 1.5
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
USER_AGENT = "trend-keyword-radar/0.1"


class HttpRequestError(RuntimeError):
    """재시도 후에도 실패한 HTTP 요청."""


def get_with_retry(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    params: Mapping[str, str] | None = None,
    timeout: int = 10,
    retries: int = DEFAULT_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> requests.Response:
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                headers=request_headers,
                params=params,
                timeout=timeout,
            )
            if response.status_code not in RETRY_STATUS_CODES:
                response.raise_for_status()
                return response
            last_error = HttpRequestError(f"HTTP {response.status_code}")
        except requests.RequestException as exc:
            last_error = exc

        if attempt < retries:
            time.sleep(backoff_seconds * attempt)

    raise HttpRequestError(str(last_error) if last_error else "unknown error")
