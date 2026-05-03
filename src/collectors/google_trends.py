import xml.etree.ElementTree as ET
from datetime import datetime
from typing import TypedDict

from src.collectors.http_client import get_with_retry

DEFAULT_GOOGLE_TRENDS_GEO = "KR"
GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss"
GOOGLE_TRENDS_NAMESPACE = {"ht": "https://trends.google.com/trending/rss"}
REQUEST_TIMEOUT_SECONDS = 10
MAX_ARTICLES_PER_TREND = 5


class TrendArticle(TypedDict):
    title: str
    url: str
    source_name: str
    published_at: datetime | None


class TrendItem(TypedDict):
    title: str
    source_name: str
    geo: str
    traffic: str
    published_at: datetime | None
    articles: list[TrendArticle]


class GoogleTrendsCollector:
    """Google Trends RSS 기반 트렌드 수집기."""

    def fetch_trending_searches(
        self,
        geo: str = DEFAULT_GOOGLE_TRENDS_GEO,
    ) -> list[TrendItem]:
        """Google Trends RSS에서 지정 지역의 트렌드와 관련 뉴스 제목을 반환합니다."""

        try:
            response = get_with_retry(
                GOOGLE_TRENDS_RSS_URL,
                params={"geo": geo},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            return parse_trends_rss(response.content, geo)
        except Exception as exc:
            print(f"[google_trends] {geo} RSS 수집 실패: {exc}")
            return []


def parse_trends_rss(
    xml_content: bytes,
    geo: str = DEFAULT_GOOGLE_TRENDS_GEO,
) -> list[TrendItem]:
    root = ET.fromstring(xml_content)
    trends: list[TrendItem] = []

    for item in root.findall(".//item"):
        title = get_text(item, "title")
        if not title:
            continue

        trends.append(
            {
                "title": title,
                "source_name": f"google_trends_{geo.lower()}_rss",
                "geo": geo,
                "traffic": get_namespaced_text(item, "approx_traffic") or "",
                "published_at": parse_rss_datetime(get_text(item, "pubDate")),
                "articles": parse_news_articles(item),
            }
        )

    return trends


def parse_news_articles(item: ET.Element) -> list[TrendArticle]:
    articles: list[TrendArticle] = []

    for news_item in item.findall("ht:news_item", GOOGLE_TRENDS_NAMESPACE)[
        :MAX_ARTICLES_PER_TREND
    ]:
        title = get_namespaced_text(news_item, "news_item_title")
        url = get_namespaced_text(news_item, "news_item_url") or ""
        source = get_namespaced_text(news_item, "news_item_source") or "google_trends_news"
        if not title:
            continue

        articles.append(
            {
                "title": title,
                "url": url,
                "source_name": source,
                "published_at": None,
            }
        )

    return articles


def get_text(item: ET.Element, tag: str) -> str | None:
    element = item.find(tag)
    if element is None or element.text is None:
        return None
    return element.text.strip()


def get_namespaced_text(item: ET.Element, tag: str) -> str | None:
    element = item.find(f"ht:{tag}", GOOGLE_TRENDS_NAMESPACE)
    if element is None or element.text is None:
        return None
    return element.text.strip()


def parse_rss_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %z").replace(tzinfo=None)
    except ValueError:
        return None
