from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class RawItem(SQLModel, table=True):
    """수집된 Google Trends 검색어 또는 RSS 기사."""

    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_type", "url", name="uq_raw_items_source_url"),
        UniqueConstraint("source_type", "title", name="uq_raw_items_source_title"),
    )

    id: int | None = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)
    source_name: str = Field(index=True)
    title: str
    url: str | None = Field(default=None)
    content: str | None = Field(default=None)
    published_at: datetime | None = Field(default=None, index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class Keyword(SQLModel, table=True):
    """일별로 집계된 키워드."""

    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("keyword", "date", name="uq_keywords_keyword_date"),)

    id: int | None = Field(default=None, primary_key=True)
    keyword: str = Field(index=True)
    keyword_display: str
    date: str = Field(index=True)
    frequency: int = Field(default=1)
    avg_score: float = Field(default=0.0)
    source_types: str = Field(default="")


class DailyDigest(SQLModel, table=True):
    """일일 다이제스트 메타데이터."""

    __tablename__ = "daily_digests"

    id: int | None = Field(default=None, primary_key=True)
    date: str = Field(unique=True, index=True)
    total_items_collected: int
    total_keywords_extracted: int
    new_keywords_count: int
    rising_keywords_count: int
    pipeline_status: str
    failed_sources: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CollectionSourceRun(SQLModel, table=True):
    """일별 소스 수집 상태."""

    __tablename__ = "collection_source_runs"
    __table_args__ = (
        UniqueConstraint("date", "source", name="uq_collection_source_run_date_source"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    source: str = Field(index=True)
    status: str = Field(index=True)
    items_collected: int = Field(default=0)
    request_count: int = Field(default=0)
    success_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    cache_hits: int = Field(default=0)
    error_message: str = Field(default="")
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class TopicSignal(SQLModel, table=True):
    """커뮤니티 주제별 네이버 검색 신호."""

    __tablename__ = "topic_signals"
    __table_args__ = (UniqueConstraint("date", "topic", "service", name="uq_topic_signal"),)

    id: int | None = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    topic: str = Field(index=True)
    query: str
    service: str = Field(index=True)
    total: int = Field(default=0)
    sample_titles: str = Field(default="")
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class KeywordSearchVolume(SQLModel, table=True):
    """네이버 검색광고 키워드도구 월검색량."""

    __tablename__ = "keyword_search_volumes"
    __table_args__ = (
        UniqueConstraint("date", "keyword", name="uq_keyword_search_volume_date_keyword"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: str = Field(index=True)
    keyword: str = Field(index=True)
    query: str
    monthly_pc: int = Field(default=0)
    monthly_mobile: int = Field(default=0)
    monthly_total: int = Field(default=0, index=True)
    competition: str = Field(default="")
    checked_at: datetime = Field(default_factory=datetime.utcnow)
