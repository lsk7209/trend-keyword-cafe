import json
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from src.analysis.community_niches import (
    get_accumulated_community_niches,
    get_community_niches,
)
from src.storage.database import engine, init_db
from src.storage.models import CollectionSourceRun, DailyDigest

EXPORT_DIR = Path("public/data")
SUMMARY_PATH = EXPORT_DIR / "summary.json"
EXPORT_LIMIT = 100


def main() -> None:
    init_db()
    today = date.today().strftime("%Y-%m-%d")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        payload = build_export_payload(session, today)

    SUMMARY_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"exported {SUMMARY_PATH}")


def build_export_payload(session: Session, today: str) -> dict[str, Any]:
    digest = session.exec(select(DailyDigest).where(DailyDigest.date == today)).first()
    return {
        "date": today,
        "generated_at": date.today().isoformat(),
        "metrics": serialize_digest(digest),
        "collection_status": get_collection_status(session, today),
        "today": [
            serialize_today_niche(niche)
            for niche in get_community_niches(session, today, limit=EXPORT_LIMIT)
        ],
        "weekly": [
            serialize_accumulated_niche(niche)
            for niche in get_accumulated_community_niches(
                session,
                today,
                period_days=7,
                limit=EXPORT_LIMIT,
            )
        ],
        "monthly": [
            serialize_accumulated_niche(niche)
            for niche in get_accumulated_community_niches(
                session,
                today,
                period_days=30,
                limit=EXPORT_LIMIT,
            )
        ],
        "windows": {
            "weekly_start": (date.today() - timedelta(days=6)).isoformat(),
            "monthly_start": (date.today() - timedelta(days=29)).isoformat(),
        },
    }


def serialize_digest(digest: DailyDigest | None) -> dict[str, Any]:
    if not digest:
        return {
            "total_items_collected": 0,
            "total_keywords_extracted": 0,
            "new_keywords_count": 0,
            "rising_keywords_count": 0,
            "pipeline_status": "missing",
            "failed_sources": "",
        }
    return {
        "total_items_collected": digest.total_items_collected,
        "total_keywords_extracted": digest.total_keywords_extracted,
        "new_keywords_count": digest.new_keywords_count,
        "rising_keywords_count": digest.rising_keywords_count,
        "pipeline_status": digest.pipeline_status,
        "failed_sources": digest.failed_sources,
    }


def get_collection_status(session: Session, today: str) -> list[dict[str, Any]]:
    runs = session.exec(
        select(CollectionSourceRun).where(CollectionSourceRun.date == today)
    ).all()
    return [
        {
            "source": run.source,
            "status": run.status,
            "items_collected": run.items_collected,
            "request_count": run.request_count,
            "success_count": run.success_count,
            "failure_count": run.failure_count,
            "cache_hits": run.cache_hits,
        }
        for run in sorted(runs, key=lambda item: item.source)
    ]


def serialize_today_niche(niche: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "niche": niche["niche"],
        "keyword": niche["keyword"],
        "category": niche["category"],
        "monthly_total": niche["monthly_total"],
        "cafe_total": niche["cafe_total"],
        "kin_total": niche["kin_total"],
        "kakao_cafe_total": niche["kakao_cafe_total"],
        "shopping_total": niche["shopping_total"],
        "saturation": niche["saturation"],
        "community_fit_label": niche["community_fit_label"],
        "practical_score": niche["practical_score"],
        "supply_gap_score": niche["supply_gap_score"],
        "topic_reason": niche["topic_reason"],
        "differentiation": niche["differentiation"],
    }


def serialize_accumulated_niche(niche: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "niche": niche["niche"],
        "keyword": niche["keyword"],
        "category": niche["category"],
        "judgment": niche["judgment"],
        "appeared_days": niche["appeared_days"],
        "avg_monthly_total": niche["avg_monthly_total"],
        "avg_practical_score": niche["avg_practical_score"],
        "max_practical_score": niche["max_practical_score"],
        "avg_cafe_total": niche["avg_cafe_total"],
        "avg_kin_total": niche["avg_kin_total"],
        "avg_kakao_cafe_total": niche["avg_kakao_cafe_total"],
        "avg_shopping_total": niche["avg_shopping_total"],
        "saturation": niche["saturation"],
        "cumulative_score": niche["cumulative_score"],
        "reason": niche["reason"],
    }


if __name__ == "__main__":
    main()
