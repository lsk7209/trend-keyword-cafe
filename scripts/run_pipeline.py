import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TypedDict

from sqlmodel import Session, col, delete, select

from src.analysis.community_niches import NICHE_RULES, is_usable_expanded_keyword
from src.analysis.community_topics import get_community_topics
from src.analysis.trend_compare import detect_new_keywords, detect_rising_keywords
from src.collectors.google_trends import GoogleTrendsCollector, TrendArticle, TrendItem
from src.collectors.kakao_search import KakaoCafeSearchResult, KakaoSearchCollector
from src.collectors.naver_search import NaverSearchCollector, NaverSearchResult, serialize_titles
from src.collectors.naver_search_ad import KeywordVolumeResult, NaverSearchAdCollector
from src.collectors.rss_feeds import ArticleItem, RSSCollector
from src.collectors.youtube import YouTubeCollector, YouTubeVideo
from src.processors.content_extractor import ContentExtractor
from src.processors.keyword_extractor import KeywordExtractor
from src.processors.korean_nlp import KoreanNLP
from src.storage.database import engine, init_db
from src.storage.models import (
    CollectionSourceRun,
    DailyDigest,
    Keyword,
    KeywordSearchVolume,
    RawItem,
    TopicSignal,
)

RSS_HOURS_BACK = 24
RSS_MAX_PER_SOURCE = 30
ARTICLE_KEYWORD_LIMIT = 5
SIGNAL_TOPIC_LIMIT = 35
RELATED_KEYWORD_LIMIT_PER_SEED = 30
DOCUMENT_EXPANDED_KEYWORD_LIMIT = 100
SECOND_LEVEL_SEED_LIMIT = 30
SECOND_LEVEL_RELATED_KEYWORD_LIMIT = 15
OVERSEAS_GOOGLE_TRENDS_GEOS = ("US", "JP", "GB", "CA", "AU", "SG", "TW")
GLOBAL_TREND_KEYWORD_LIMIT = 30
YOUTUBE_REGIONS = ("KR", "US", "JP", "GB", "CA", "AU", "SG", "TW")
YOUTUBE_MAX_RESULTS_PER_REGION = 10
YOUTUBE_TREND_KEYWORD_LIMIT = 30
MAX_SEARCH_SEED_LENGTH = 40


class KeywordBucket(TypedDict):
    freq: int
    scores: list[float]
    display: str
    sources: set[str]


class CollectionStats(TypedDict):
    request_count: int
    success_count: int
    failure_count: int
    cache_hits: int
    errors: list[str]


def normalize_keyword(keyword: str) -> str:
    normalized = re.sub(r"\s+", "", keyword.lower())
    return re.sub(r"[^\w가-힣]", "", normalized)


def main() -> None:
    init_db()

    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    failed_sources: list[str] = []

    print("=" * 60)
    print(f"Topic Radar Pipeline - {today}")
    print("=" * 60)

    trends = collect_trends(failed_sources)
    global_trends = collect_global_trends(failed_sources)
    youtube_videos = collect_youtube_videos(failed_sources)
    articles = collect_articles(failed_sources)
    enriched_articles = enrich_articles(articles, failed_sources)
    keyword_aggregator = aggregate_keywords(
        trends,
        global_trends,
        youtube_videos,
        enriched_articles,
    )

    new_count, rising_count = save_results(
        today=today,
        yesterday=yesterday,
        trends=trends,
        global_trends=global_trends,
        youtube_videos=youtube_videos,
        enriched_articles=enriched_articles,
        keyword_aggregator=keyword_aggregator,
        failed_sources=failed_sources,
    )

    print("=" * 60)
    print("파이프라인 완료")
    print(f"신규 키워드: {new_count}, 급상승: {rising_count}")
    print("대시보드 실행: python scripts/run_dashboard.py")
    print("=" * 60)


def collect_trends(failed_sources: list[str]) -> list[TrendItem]:
    trends = GoogleTrendsCollector().fetch_trending_searches()
    if not trends:
        failed_sources.append("google_trends")
    print(f"Google Trends 수집: {len(trends)}개")
    return trends


def collect_global_trends(failed_sources: list[str]) -> list[TrendItem]:
    collector = GoogleTrendsCollector()
    global_trends: list[TrendItem] = []

    for geo in OVERSEAS_GOOGLE_TRENDS_GEOS:
        trends = collector.fetch_trending_searches(geo=geo)
        global_trends.extend(trends)

    if not global_trends:
        failed_sources.append("google_trends_global")
    print(f"해외 Google Trends 수집: {len(global_trends)}개")
    return global_trends


def collect_youtube_videos(failed_sources: list[str]) -> list[YouTubeVideo]:
    collector = YouTubeCollector.from_environment()
    if not collector:
        failed_sources.append("youtube_credentials")
        print("YouTube 인기 영상 수집: API 키 없음")
        return []

    videos: list[YouTubeVideo] = []
    for region in YOUTUBE_REGIONS:
        videos.extend(
            collector.fetch_most_popular(
                region_code=region,
                max_results=YOUTUBE_MAX_RESULTS_PER_REGION,
            )
        )

    if not videos:
        failed_sources.append("youtube_most_popular")
    print(f"YouTube 인기 영상 수집: {len(videos)}개")
    return videos


def collect_articles(failed_sources: list[str]) -> list[ArticleItem]:
    articles = RSSCollector().fetch_recent_articles(
        hours_back=RSS_HOURS_BACK,
        max_per_source=RSS_MAX_PER_SOURCE,
    )
    if not articles:
        failed_sources.append("rss_all")
    print(f"RSS 메타 수집: {len(articles)}개")
    return articles


def enrich_articles(articles: list[ArticleItem], failed_sources: list[str]) -> list[ArticleItem]:
    extractor = ContentExtractor()
    enriched_articles: list[ArticleItem] = []

    for article in articles:
        url = str(article.get("url") or "")
        content = extractor.extract(url) if url else None
        if content:
            article["content"] = content
            enriched_articles.append(article)

    if articles and not enriched_articles:
        failed_sources.append("content_extraction")

    print(f"본문 추출: {len(enriched_articles)} / {len(articles)}개")
    return enriched_articles


def aggregate_keywords(
    trends: list[TrendItem],
    global_trends: list[TrendItem],
    youtube_videos: list[YouTubeVideo],
    enriched_articles: list[ArticleItem],
) -> dict[str, KeywordBucket]:
    keyword_aggregator: dict[str, KeywordBucket] = defaultdict(
        lambda: {"freq": 0, "scores": [], "display": "", "sources": set()}
    )

    for trend in trends:
        add_keyword(keyword_aggregator, trend["title"], 1.0, "google_trends")
        for trend_article in trend["articles"]:
            add_keyword(keyword_aggregator, trend_article["title"], 0.8, "google_trends")

    for trend in global_trends:
        add_keyword(keyword_aggregator, trend["title"], 0.6, "google_trends_global")

    for video in youtube_videos:
        add_keyword(keyword_aggregator, video["title"], 0.65, "youtube_most_popular")

    nlp = KoreanNLP()
    keyword_extractor = KeywordExtractor()

    for article in enriched_articles:
        text = f"{article.get('title') or ''}\n{article.get('content') or ''}"
        nouns = nlp.extract_nouns(text)
        if not nouns:
            continue

        keywords = keyword_extractor.extract(
            text,
            candidates=sorted(set(nouns)),
            top_n=ARTICLE_KEYWORD_LIMIT,
        )
        for keyword, score in keywords:
            add_keyword(keyword_aggregator, keyword, score, "rss")

    print(f"키워드 집계: {len(keyword_aggregator)}개")
    return dict(keyword_aggregator)


def add_keyword(
    keyword_aggregator: dict[str, KeywordBucket],
    keyword: str,
    score: float,
    source_type: str,
) -> None:
    normalized = normalize_keyword(keyword)
    if not normalized:
        return

    bucket = keyword_aggregator[normalized]
    bucket["freq"] += 1
    bucket["scores"].append(score)
    bucket["display"] = keyword
    bucket["sources"].add(source_type)


def save_results(
    today: str,
    yesterday: str,
    trends: list[TrendItem],
    global_trends: list[TrendItem],
    youtube_videos: list[YouTubeVideo],
    enriched_articles: list[ArticleItem],
    keyword_aggregator: dict[str, KeywordBucket],
    failed_sources: list[str],
) -> tuple[int, int]:
    with Session(engine) as session:
        clear_today_digest(session, today)
        save_raw_trends(session, trends)
        save_raw_global_trends(session, global_trends)
        save_raw_youtube_videos(session, youtube_videos)
        save_raw_articles(session, enriched_articles)
        save_keywords(session, today, keyword_aggregator)
        record_source_run(
            session,
            today,
            source="google_trends",
            status="success" if trends else "failed",
            items_collected=len(trends),
            request_count=1,
            success_count=1 if trends else 0,
            failure_count=0 if trends else 1,
        )
        record_source_run(
            session,
            today,
            source="google_trends_global",
            status="success" if global_trends else "failed",
            items_collected=len(global_trends),
            request_count=len(OVERSEAS_GOOGLE_TRENDS_GEOS),
            success_count=len({trend["geo"] for trend in global_trends}),
            failure_count=max(
                len(OVERSEAS_GOOGLE_TRENDS_GEOS) - len({trend["geo"] for trend in global_trends}),
                0,
            ),
        )
        youtube_regions = {video["region"] for video in youtube_videos}
        youtube_status = "success" if youtube_videos else "failed"
        record_source_run(
            session,
            today,
            source="youtube_most_popular",
            status=youtube_status,
            items_collected=len(youtube_videos),
            request_count=len(YOUTUBE_REGIONS),
            success_count=len(youtube_regions),
            failure_count=max(len(YOUTUBE_REGIONS) - len(youtube_regions), 0),
        )
        record_source_run(
            session,
            today,
            source="rss_articles",
            status="success" if enriched_articles else "failed",
            items_collected=len(enriched_articles),
            request_count=len(trends) + len(enriched_articles),
            success_count=len(enriched_articles),
            failure_count=0 if enriched_articles else 1,
        )
        session.commit()
        save_keyword_search_volumes(session, today, failed_sources)
        save_topic_signals(session, today, failed_sources)
        save_naver_shopping_signals(session, today, failed_sources)
        save_kakao_cafe_signals(session, today, failed_sources)

        new_keywords = detect_new_keywords(session, today, yesterday)
        rising_keywords = detect_rising_keywords(session, today, yesterday)
        status = decide_pipeline_status(failed_sources, keyword_aggregator)

        session.add(
            DailyDigest(
                date=today,
                total_items_collected=(
                    len(trends)
                    + len(global_trends)
                    + len(youtube_videos)
                    + len(enriched_articles)
                ),
                total_keywords_extracted=len(keyword_aggregator),
                new_keywords_count=len(new_keywords),
                rising_keywords_count=len(rising_keywords),
                pipeline_status=status,
                failed_sources=",".join(sorted(set(failed_sources))),
            )
        )
        session.commit()

    return len(new_keywords), len(rising_keywords)


def clear_today_digest(session: Session, today: str) -> None:
    session.exec(delete(Keyword).where(col(Keyword.date) == today))
    session.exec(delete(DailyDigest).where(col(DailyDigest.date) == today))
    session.exec(delete(CollectionSourceRun).where(col(CollectionSourceRun.date) == today))


def save_raw_trends(session: Session, trends: list[TrendItem]) -> None:
    for trend in trends:
        title = trend["title"]
        exists = session.exec(
            select(RawItem).where(
                RawItem.source_type == "google_trends",
                RawItem.title == title,
            )
        ).first()
        if exists:
            continue

        session.add(
            RawItem(
                source_type="google_trends",
                source_name=trend["source_name"],
                title=title,
                content=f"traffic={trend['traffic']}",
                published_at=trend["published_at"],
                collected_at=datetime.utcnow(),
            )
        )

        for article in trend["articles"]:
            save_raw_trend_article(session, article, title)


def save_raw_trend_article(session: Session, article: TrendArticle, trend_title: str) -> None:
    title = article["title"]
    if not title:
        return

    exists = session.exec(
        select(RawItem).where(
            RawItem.source_type == "google_trends_news",
            RawItem.title == title,
        )
    ).first()
    if exists:
        return

    session.add(
        RawItem(
            source_type="google_trends_news",
            source_name=article["source_name"],
            title=title,
            url=article["url"],
            content=f"trend={trend_title}",
            published_at=article["published_at"],
            collected_at=datetime.utcnow(),
        )
    )


def save_raw_global_trends(session: Session, trends: list[TrendItem]) -> None:
    for trend in trends:
        title = trend["title"]
        exists = session.exec(
            select(RawItem).where(
                RawItem.source_type == "google_trends_global",
                RawItem.title == title,
            )
        ).first()
        if exists:
            exists.source_name = trend["source_name"]
            exists.content = f"geo={trend['geo']};traffic={trend['traffic']}"
            exists.published_at = trend["published_at"]
            exists.collected_at = datetime.utcnow()
            session.add(exists)
            continue

        session.add(
            RawItem(
                source_type="google_trends_global",
                source_name=trend["source_name"],
                title=title,
                content=f"geo={trend['geo']};traffic={trend['traffic']}",
                published_at=trend["published_at"],
                collected_at=datetime.utcnow(),
            )
        )


def save_raw_youtube_videos(session: Session, videos: list[YouTubeVideo]) -> None:
    for video in videos:
        title = video["title"]
        video_id = video["video_id"]
        if not title or not video_id:
            continue

        exists = session.exec(
            select(RawItem).where(
                RawItem.source_type == "youtube_most_popular",
                RawItem.url == video_id,
            )
        ).first()
        content = (
            f"region={video['region']};"
            f"category={video['category_id']};"
            f"views={video['view_count']}"
        )
        if exists:
            exists.source_name = video["channel_title"]
            exists.title = title
            exists.content = content
            exists.published_at = video["published_at"]
            exists.collected_at = datetime.utcnow()
            session.add(exists)
            continue

        session.add(
            RawItem(
                source_type="youtube_most_popular",
                source_name=video["channel_title"],
                title=title,
                url=video_id,
                content=content,
                published_at=video["published_at"],
                collected_at=datetime.utcnow(),
            )
        )


def save_raw_articles(session: Session, articles: list[ArticleItem]) -> None:
    seen_titles: set[str] = set()
    for article in articles:
        url = str(article.get("url") or "")
        title = str(article.get("title") or "")
        if not url or not title:
            continue
        if title in seen_titles:
            continue

        exists = session.exec(
            select(RawItem).where(
                RawItem.source_type == "rss",
                (RawItem.url == url) | (RawItem.title == title),
            )
        ).first()
        if exists:
            continue
        seen_titles.add(title)

        session.add(
            RawItem(
                source_type="rss",
                source_name=str(article.get("source_name") or ""),
                title=title,
                url=url,
                content=str(article.get("content") or ""),
                published_at=article.get("published_at"),
                collected_at=datetime.utcnow(),
            )
        )


def save_keywords(
    session: Session,
    today: str,
    keyword_aggregator: dict[str, KeywordBucket],
) -> None:
    for normalized, data in keyword_aggregator.items():
        scores = data["scores"]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        session.add(
            Keyword(
                keyword=normalized,
                keyword_display=data["display"],
                date=today,
                frequency=data["freq"],
                avg_score=avg_score,
                source_types=",".join(sorted(data["sources"])),
            )
        )


def decide_pipeline_status(
    failed_sources: list[str],
    keyword_aggregator: dict[str, KeywordBucket],
) -> str:
    if not keyword_aggregator:
        return "failed"
    if failed_sources:
        return "partial"
    return "success"


def save_topic_signals(session: Session, today: str, failed_sources: list[str]) -> None:
    collector = NaverSearchCollector.from_environment()
    if not collector:
        failed_sources.append("naver_search_credentials")
        record_source_run(
            session,
            today,
            source="naver_search_documents",
            status="failed",
            error_message="credentials missing",
        )
        return

    request_count = 0
    success_count = 0
    failure_count = 0
    cache_hits = 0
    errors: list[str] = []

    topics = get_community_topics(
        session,
        today,
        limit=SIGNAL_TOPIC_LIMIT,
        require_signals=False,
        require_search_volume=False,
    )

    for topic in topics:
        query = pick_signal_query(topic["related_keywords"], topic["topic"])
        if has_all_topic_signals(session, today, topic["topic"]):
            cache_hits += 4
            continue
        for signal in collector.fetch_topic_signals(query):
            request_count += 1
            if not signal.get("ok", True):
                failure_count += 1
                errors.append(f"{query}/{signal['service']}: {signal.get('error', '')}")
                continue
            upsert_topic_signal(session, today, topic["topic"], query, signal)
            success_count += 1

    for rule in NICHE_RULES:
        if has_all_topic_signals(session, today, rule.niche):
            cache_hits += 4
            continue
        for signal in collector.fetch_topic_signals(rule.keyword):
            request_count += 1
            if not signal.get("ok", True):
                failure_count += 1
                errors.append(f"{rule.keyword}/{signal['service']}: {signal.get('error', '')}")
                continue
            upsert_topic_signal(session, today, rule.niche, rule.keyword, signal)
            success_count += 1

    for volume in get_expanded_document_keywords(session, today):
        if has_all_topic_signals(session, today, volume.keyword):
            cache_hits += 4
            continue
        for signal in collector.fetch_topic_signals(volume.keyword):
            request_count += 1
            if not signal.get("ok", True):
                failure_count += 1
                errors.append(f"{volume.keyword}/{signal['service']}: {signal.get('error', '')}")
                continue
            upsert_topic_signal(session, today, volume.keyword, volume.keyword, signal)
            success_count += 1
    status = decide_source_status(success_count + cache_hits, failure_count)
    if failure_count:
        failed_sources.append("naver_search_documents")
    record_source_run(
        session,
        today,
        source="naver_search_documents",
        status=status,
        items_collected=success_count,
        request_count=request_count,
        success_count=success_count,
        failure_count=failure_count,
        cache_hits=cache_hits,
        error_message=" | ".join(errors[:5]),
    )
    session.commit()


def save_kakao_cafe_signals(session: Session, today: str, failed_sources: list[str]) -> None:
    collector = KakaoSearchCollector.from_environment()
    if not collector:
        failed_sources.append("kakao_search_credentials")
        record_source_run(
            session,
            today,
            source="kakao_cafe_documents",
            status="failed",
            error_message="credentials missing",
        )
        return

    request_count = 0
    success_count = 0
    failure_count = 0
    cache_hits = 0
    errors: list[str] = []

    for volume in get_expanded_document_keywords(session, today):
        if has_topic_signal(session, today, volume.keyword, "kakao_cafe"):
            cache_hits += 1
            continue
        signal = collector.search_cafe(volume.keyword)
        request_count += 1
        if not signal.get("ok", True):
            failure_count += 1
            errors.append(f"{volume.keyword}: {signal.get('error', '')}")
            continue
        upsert_kakao_cafe_signal(session, today, volume.keyword, volume.keyword, signal)
        success_count += 1

    status = decide_source_status(success_count + cache_hits, failure_count)
    if failure_count:
        failed_sources.append("kakao_cafe_documents")
    record_source_run(
        session,
        today,
        source="kakao_cafe_documents",
        status=status,
        items_collected=success_count,
        request_count=request_count,
        success_count=success_count,
        failure_count=failure_count,
        cache_hits=cache_hits,
        error_message=" | ".join(errors[:5]),
    )
    session.commit()


def save_naver_shopping_signals(session: Session, today: str, failed_sources: list[str]) -> None:
    collector = NaverSearchCollector.from_environment()
    if not collector:
        failed_sources.append("naver_search_credentials")
        record_source_run(
            session,
            today,
            source="naver_shopping_documents",
            status="failed",
            error_message="credentials missing",
        )
        return

    request_count = 0
    success_count = 0
    failure_count = 0
    cache_hits = 0
    errors: list[str] = []

    for volume in get_expanded_document_keywords(session, today):
        if has_topic_signal(session, today, volume.keyword, "shop"):
            cache_hits += 1
            continue
        signal = collector.search_shopping(volume.keyword)
        request_count += 1
        if not signal.get("ok", True):
            failure_count += 1
            errors.append(f"{volume.keyword}: {signal.get('error', '')}")
            continue
        upsert_topic_signal(session, today, volume.keyword, volume.keyword, signal)
        success_count += 1

    status = decide_source_status(success_count + cache_hits, failure_count)
    if failure_count:
        failed_sources.append("naver_shopping_documents")
    record_source_run(
        session,
        today,
        source="naver_shopping_documents",
        status=status,
        items_collected=success_count,
        request_count=request_count,
        success_count=success_count,
        failure_count=failure_count,
        cache_hits=cache_hits,
        error_message=" | ".join(errors[:5]),
    )
    session.commit()


def save_keyword_search_volumes(
    session: Session,
    today: str,
    failed_sources: list[str],
) -> None:
    collector = NaverSearchAdCollector.from_environment()
    if not collector:
        failed_sources.append("naver_search_ad_credentials")
        record_source_run(
            session,
            today,
            source="naver_search_ad_volume",
            status="failed",
            error_message="credentials missing",
        )
        return

    topics = get_community_topics(
        session,
        today,
        limit=SIGNAL_TOPIC_LIMIT,
        require_signals=False,
        require_search_volume=False,
    )

    seen_keywords: set[str] = set()
    request_count = 0
    success_count = 0
    failure_count = 0
    cache_hits = 0
    errors: list[str] = []
    for topic in topics:
        result = save_keyword_volume(session, today, collector, topic["keyword"], seen_keywords)
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])

    for rule in NICHE_RULES:
        result = save_keyword_volume(session, today, collector, rule.keyword, seen_keywords)
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])

    for rule in NICHE_RULES:
        result = save_related_keyword_volumes(
            session,
            today,
            collector,
            rule.keyword,
            seen_keywords,
        )
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])

    for keyword in get_global_trend_keywords(session, today):
        result = save_keyword_volume(session, today, collector, keyword, seen_keywords)
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])

    for keyword in get_youtube_trend_keywords(session, today):
        result = save_keyword_volume(session, today, collector, keyword, seen_keywords)
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])

    for seed_keyword in get_second_level_seed_keywords(session, today):
        result = save_related_keyword_volumes(
            session,
            today,
            collector,
            seed_keyword,
            seen_keywords,
            limit=SECOND_LEVEL_RELATED_KEYWORD_LIMIT,
        )
        request_count += result["request_count"]
        success_count += result["success_count"]
        failure_count += result["failure_count"]
        cache_hits += result["cache_hits"]
        errors.extend(result["errors"])
    if failure_count:
        failed_sources.append("naver_search_ad_volume")
    record_source_run(
        session,
        today,
        source="naver_search_ad_volume",
        status=decide_source_status(success_count + cache_hits, failure_count),
        items_collected=success_count,
        request_count=request_count,
        success_count=success_count,
        failure_count=failure_count,
        cache_hits=cache_hits,
        error_message=" | ".join(errors[:5]),
    )
    session.commit()


def save_keyword_volume(
    session: Session,
    today: str,
    collector: NaverSearchAdCollector,
    keyword: str,
    seen_keywords: set[str],
) -> CollectionStats:
    stats: CollectionStats = {
        "request_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "cache_hits": 0,
        "errors": [],
    }
    if keyword in seen_keywords:
        return stats
    seen_keywords.add(keyword)

    existing = get_keyword_volume(session, today, keyword)
    if existing:
        stats["cache_hits"] = 1
        return stats

    volume = collector.fetch_keyword_volume(keyword)
    stats["request_count"] = 1
    if not volume.get("ok", True):
        stats["failure_count"] = 1
        stats["errors"] = [f"{keyword}: {volume.get('error', '')}"]
        return stats

    upsert_keyword_volume(session, today, keyword, volume)
    stats["success_count"] = 1
    return stats


def save_related_keyword_volumes(
    session: Session,
    today: str,
    collector: NaverSearchAdCollector,
    seed_keyword: str,
    seen_keywords: set[str],
    limit: int = RELATED_KEYWORD_LIMIT_PER_SEED,
) -> CollectionStats:
    stats: CollectionStats = {
        "request_count": 1,
        "success_count": 0,
        "failure_count": 0,
        "cache_hits": 0,
        "errors": [],
    }
    related_volumes = collector.fetch_related_keyword_volumes(
        seed_keyword,
        limit=limit,
    )
    if not related_volumes:
        return stats

    for volume in related_volumes:
        keyword = volume["keyword"]
        if keyword in seen_keywords:
            continue
        seen_keywords.add(keyword)
        if get_keyword_volume(session, today, keyword):
            stats["cache_hits"] += 1
            continue
        if volume["monthly_total"] < 100:
            continue
        upsert_keyword_volume(session, today, keyword, volume)
        stats["success_count"] += 1
    return stats


def get_expanded_document_keywords(
    session: Session,
    today: str,
) -> list[KeywordSearchVolume]:
    rule_keywords = {rule.keyword for rule in NICHE_RULES}
    volumes = session.exec(
        select(KeywordSearchVolume).where(KeywordSearchVolume.date == today)
    ).all()
    sorted_volumes = sorted(volumes, key=lambda volume: volume.monthly_total, reverse=True)
    candidates = [
        volume
        for volume in sorted_volumes
        if volume.keyword not in rule_keywords
        and is_usable_expanded_keyword(volume.keyword, volume.monthly_total)
    ]
    return candidates[:DOCUMENT_EXPANDED_KEYWORD_LIMIT]


def get_second_level_seed_keywords(session: Session, today: str) -> list[str]:
    first_level = get_expanded_document_keywords(session, today)
    return [volume.keyword for volume in first_level[:SECOND_LEVEL_SEED_LIMIT]]


def get_global_trend_keywords(session: Session, today: str) -> list[str]:
    start_at = datetime.strptime(today, "%Y-%m-%d")
    end_at = start_at + timedelta(days=1)
    items = session.exec(
        select(RawItem)
        .where(
            RawItem.source_type == "google_trends_global",
            RawItem.collected_at >= start_at,
            RawItem.collected_at < end_at,
        )
        .order_by(col(RawItem.collected_at).desc())
    ).all()
    keywords: list[str] = []
    seen: set[str] = set()
    for item in items:
        keyword = clean_search_seed(item.title)
        if not keyword:
            continue
        normalized = normalize_keyword(keyword)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(keyword)
        if len(keywords) >= GLOBAL_TREND_KEYWORD_LIMIT:
            break
    return keywords


def get_youtube_trend_keywords(session: Session, today: str) -> list[str]:
    start_at = datetime.strptime(today, "%Y-%m-%d")
    end_at = start_at + timedelta(days=1)
    items = session.exec(
        select(RawItem)
        .where(
            RawItem.source_type == "youtube_most_popular",
            RawItem.collected_at >= start_at,
            RawItem.collected_at < end_at,
        )
        .order_by(col(RawItem.collected_at).desc())
    ).all()
    keywords: list[str] = []
    seen: set[str] = set()
    for item in items:
        keyword = clean_search_seed(item.title)
        if not keyword:
            continue
        normalized = normalize_keyword(keyword)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(keyword)
        if len(keywords) >= YOUTUBE_TREND_KEYWORD_LIMIT:
            break
    return keywords


def clean_search_seed(title: str) -> str:
    cleaned = re.sub(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】", " ", title)
    cleaned = re.split(r"\s[-|｜:]\s| - |｜|ㅣ|\|", cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"#\S+", " ", cleaned)
    cleaned = re.sub(r"[^\w가-힣\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not re.search(r"[가-힣]", cleaned):
        return ""
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", cleaned):
        return ""
    if len(cleaned) > MAX_SEARCH_SEED_LENGTH:
        return ""
    return cleaned


def has_all_topic_signals(session: Session, today: str, topic: str) -> bool:
    services = {
        signal.service
        for signal in session.exec(
            select(TopicSignal).where(
                TopicSignal.date == today,
                TopicSignal.topic == topic,
            )
        )
    }
    return {"cafearticle", "blog", "kin", "news"}.issubset(services)


def has_topic_signal(session: Session, today: str, topic: str, service: str) -> bool:
    return (
        session.exec(
            select(TopicSignal).where(
                TopicSignal.date == today,
                TopicSignal.topic == topic,
                TopicSignal.service == service,
            )
        ).first()
        is not None
    )


def upsert_topic_signal(
    session: Session,
    today: str,
    topic: str,
    query: str,
    signal: NaverSearchResult,
) -> None:
    existing = session.exec(
        select(TopicSignal).where(
            TopicSignal.date == today,
            TopicSignal.topic == topic,
            TopicSignal.service == signal["service"],
        )
    ).first()
    titles = signal.get("titles", [])
    if not isinstance(titles, list):
        titles = []
    if existing:
        existing.query = query
        existing.total = int(signal["total"])
        existing.sample_titles = serialize_titles([str(title) for title in titles])
        existing.checked_at = datetime.utcnow()
        session.add(existing)
        return
    session.add(
        TopicSignal(
            date=today,
            topic=topic,
            query=query,
            service=str(signal["service"]),
            total=int(signal["total"]),
            sample_titles=serialize_titles([str(title) for title in titles]),
        )
    )


def upsert_kakao_cafe_signal(
    session: Session,
    today: str,
    topic: str,
    query: str,
    signal: KakaoCafeSearchResult,
) -> None:
    existing = session.exec(
        select(TopicSignal).where(
            TopicSignal.date == today,
            TopicSignal.topic == topic,
            TopicSignal.service == "kakao_cafe",
        )
    ).first()
    titles = signal.get("titles", [])
    if not isinstance(titles, list):
        titles = []
    if existing:
        existing.query = query
        existing.total = int(signal["total"])
        existing.sample_titles = serialize_titles([str(title) for title in titles])
        existing.checked_at = datetime.utcnow()
        session.add(existing)
        return
    session.add(
        TopicSignal(
            date=today,
            topic=topic,
            query=query,
            service="kakao_cafe",
            total=int(signal["total"]),
            sample_titles=serialize_titles([str(title) for title in titles]),
        )
    )


def get_keyword_volume(
    session: Session,
    today: str,
    keyword: str,
) -> KeywordSearchVolume | None:
    return session.exec(
        select(KeywordSearchVolume).where(
            KeywordSearchVolume.date == today,
            KeywordSearchVolume.keyword == keyword,
        )
    ).first()


def upsert_keyword_volume(
    session: Session,
    today: str,
    keyword: str,
    volume: KeywordVolumeResult,
) -> None:
    existing = get_keyword_volume(session, today, keyword)
    if existing:
        existing.query = str(volume["query"])
        existing.monthly_pc = int(volume["monthly_pc"])
        existing.monthly_mobile = int(volume["monthly_mobile"])
        existing.monthly_total = int(volume["monthly_total"])
        existing.competition = str(volume["competition"])
        existing.checked_at = datetime.utcnow()
        session.add(existing)
        return
    session.add(
        KeywordSearchVolume(
            date=today,
            keyword=keyword,
            query=str(volume["query"]),
            monthly_pc=int(volume["monthly_pc"]),
            monthly_mobile=int(volume["monthly_mobile"]),
            monthly_total=int(volume["monthly_total"]),
            competition=str(volume["competition"]),
        )
    )


def decide_source_status(success_count: int, failure_count: int) -> str:
    if success_count and failure_count:
        return "partial"
    if success_count:
        return "success"
    if failure_count:
        return "failed"
    return "cached"


def record_source_run(
    session: Session,
    today: str,
    source: str,
    status: str,
    items_collected: int = 0,
    request_count: int = 0,
    success_count: int = 0,
    failure_count: int = 0,
    cache_hits: int = 0,
    error_message: str = "",
) -> None:
    existing = session.exec(
        select(CollectionSourceRun).where(
            CollectionSourceRun.date == today,
            CollectionSourceRun.source == source,
        )
    ).first()
    if existing:
        existing.status = status
        existing.items_collected = items_collected
        existing.request_count = request_count
        existing.success_count = success_count
        existing.failure_count = failure_count
        existing.cache_hits = cache_hits
        existing.error_message = error_message
        existing.checked_at = datetime.utcnow()
        session.add(existing)
        return
    session.add(
        CollectionSourceRun(
            date=today,
            source=source,
            status=status,
            items_collected=items_collected,
            request_count=request_count,
            success_count=success_count,
            failure_count=failure_count,
            cache_hits=cache_hits,
            error_message=error_message,
        )
    )


def pick_signal_query(related_keywords: str, topic: str) -> str:
    keywords = [keyword.strip() for keyword in related_keywords.split(",") if keyword.strip()]
    if len(keywords) >= 2:
        return " ".join(keywords[:2])
    if keywords:
        return keywords[0]
    return topic


if __name__ == "__main__":
    main()
