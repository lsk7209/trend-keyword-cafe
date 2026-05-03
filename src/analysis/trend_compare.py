from typing import TypedDict

from sqlmodel import Session, col, select

from src.storage.models import Keyword


class RisingKeyword(TypedDict):
    keyword: str
    today_freq: int
    yesterday_freq: int
    ratio: float


def get_top_keywords(session: Session, target_date: str, limit: int = 30) -> list[Keyword]:
    statement = (
        select(Keyword)
        .where(Keyword.date == target_date)
        .order_by(col(Keyword.frequency).desc(), col(Keyword.avg_score).desc())
        .limit(limit)
    )
    return list(session.exec(statement))


def detect_new_keywords(
    session: Session,
    today: str,
    yesterday: str,
    limit: int = 10,
) -> list[Keyword]:
    yesterday_keywords = {
        keyword.keyword
        for keyword in session.exec(select(Keyword).where(Keyword.date == yesterday))
    }
    today_keywords = session.exec(
        select(Keyword)
        .where(Keyword.date == today)
        .order_by(col(Keyword.frequency).desc(), col(Keyword.avg_score).desc())
    )
    return [keyword for keyword in today_keywords if keyword.keyword not in yesterday_keywords][
        :limit
    ]


def detect_rising_keywords(
    session: Session,
    today: str,
    yesterday: str,
    min_growth_ratio: float = 2.0,
    limit: int = 10,
) -> list[RisingKeyword]:
    yesterday_frequency = {
        keyword.keyword: keyword.frequency
        for keyword in session.exec(select(Keyword).where(Keyword.date == yesterday))
    }
    rising: list[RisingKeyword] = []

    for keyword in session.exec(select(Keyword).where(Keyword.date == today)):
        previous_frequency = yesterday_frequency.get(keyword.keyword, 0)
        if previous_frequency == 0:
            continue

        ratio = keyword.frequency / previous_frequency
        if ratio >= min_growth_ratio:
            rising.append(
                {
                    "keyword": keyword.keyword_display,
                    "today_freq": keyword.frequency,
                    "yesterday_freq": previous_frequency,
                    "ratio": ratio,
                }
            )

    rising.sort(key=lambda item: item["ratio"], reverse=True)
    return rising[:limit]
