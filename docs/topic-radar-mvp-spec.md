# Topic Radar MVP — Claude Code 개발 핸드오프 사양서

> **프로젝트 코드명**: topic-radar
> **목표**: 운영 중인 커뮤니티의 신규 주제 발굴을 위한 일일 키워드 다이제스트 시스템 (1주차 최소판)
> **개발 방식**: Claude Code 자율 개발
> **예상 개발 기간**: 1~2일 (단일 세션 가능)
> **버전**: MVP v1.0
> **작성일**: 2026-05-02

---

## 0. Claude Code에게 — 개발 시작 전 필수 확인

### 0.1 이 문서의 우선순위
이 사양서의 모든 결정은 **MVP 정신**을 따른다:
- **추가 기능보다 작동하는 최소 시스템 우선**
- **확장성보다 명확성 우선** — 나중에 리팩토링 가능
- **추상화보다 직접 구현 우선** — 의존성·복잡도 최소화
- 모호한 결정이 발생하면 **더 단순한 쪽**을 선택하고 README에 기록

### 0.2 절대 추가하지 말 것 (MVP 범위 외)
- Reddit, YouTube, X/Twitter 수집 (v2)
- BERTrend 시계열 토픽 분석 (v3)
- 디시·네이트판 등 한국 커뮤니티 (v4)
- LLM API 호출 (Gemini, Claude API)
- Docker, Kubernetes
- 사용자 인증, 멀티유저
- 클라우드 배포 설정
- 테스트 코드 (수동 검증으로 충분, MVP 정신)

### 0.3 명시된 가정사항
사용자가 spec 검토 후 조정 가능. 명시 없으면 아래 그대로 진행:
- **도메인**: 한국 시사·IT 일반 (yml 파일에 RSS 출처 정의)
- **일일 분량**: Top 30 키워드 + 신규 신호 10개
- **언어**: Python 3.11+
- **OS**: macOS / Linux 우선 (Windows 미지원)
- **운영**: 로컬 수동 실행

---

## 1. 시스템 아키텍처

### 1.1 4단 구조
```
┌──────────────────────────────────────────────┐
│  [수집 레이어]                                │
│  ├─ Google Trends (pytrends)                 │
│  └─ 한국 뉴스 RSS (feedparser)                │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│  [처리 레이어]                                │
│  ├─ trafilatura: HTML → 정제된 본문            │
│  ├─ Kiwi: 한국어 형태소 분석 → 명사 추출       │
│  └─ KeyBERT: 임베딩 기반 키워드 추출           │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│  [저장 레이어] SQLite + SQLModel              │
│  ├─ raw_items: 수집된 원본 항목                │
│  ├─ keywords: 추출된 키워드 (일별)             │
│  └─ daily_digests: 일일 다이제스트 메타        │
└──────────────────────────────────────────────┘
                    ↓
┌──────────────────────────────────────────────┐
│  [표시 레이어] Streamlit                      │
│  └─ 일별 Top 30 + 신규/급상승 키워드           │
└──────────────────────────────────────────────┘
```

### 1.2 데이터 흐름 (1회 파이프라인 실행)
1. `run_pipeline.py` 실행
2. Google Trends에서 한국 일일 인기 검색어 20개 수집
3. RSS 출처에서 최근 24시간 기사 메타데이터 수집 (출처당 최대 30개)
4. 각 기사 URL을 trafilatura로 본문 추출
5. 본문을 Kiwi로 형태소 분석 → 명사만 필터링
6. KeyBERT로 의미 기반 키워드 추출 (기사당 Top 5)
7. 한국어 정규화 + 동일 키워드 빈도 합산
8. SQLite에 저장 (오늘 날짜 기준)
9. 어제 데이터와 비교 → 신규/급상승 키워드 식별
10. daily_digests 테이블에 메타 기록

---

## 2. 폴더 구조

```
topic-radar/
├── README.md                    ← 설치·실행·트러블슈팅
├── pyproject.toml               ← 의존성 + 메타
├── requirements.txt             ← pyproject 미사용 시 fallback
├── .env.example                 ← 환경변수 템플릿
├── .gitignore                   ← venv, *.db, __pycache__ 등
├── config/
│   └── rss_sources.yml          ← RSS 출처 정의 (도메인 변경 시 여기만)
├── src/
│   ├── __init__.py
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── google_trends.py     ← pytrends 래퍼
│   │   └── rss_feeds.py         ← feedparser + trafilatura
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── korean_nlp.py        ← Kiwi 형태소 분석
│   │   ├── keyword_extractor.py ← KeyBERT
│   │   └── content_extractor.py ← trafilatura 래퍼
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── models.py            ← SQLModel 정의
│   │   └── database.py          ← engine, session
│   ├── analysis/
│   │   ├── __init__.py
│   │   └── trend_compare.py     ← 어제 대비 신규/급상승
│   └── dashboard/
│       ├── __init__.py
│       └── app.py               ← Streamlit 앱
├── scripts/
│   ├── run_pipeline.py          ← 수집→처리→저장 1회 실행
│   └── run_dashboard.py         ← Streamlit 띄우기
└── data/
    └── topic_radar.db           ← SQLite (gitignore)
```

### 2.1 모듈 책임 분리 원칙
- **collectors**: 외부 데이터 가져오기. 처리·저장 모름.
- **processors**: 텍스트 변환. 외부 API·DB 모름.
- **storage**: DB 모델·세션. 비즈니스 로직 없음.
- **analysis**: SQL 쿼리 + Python 비교. 표시 로직 없음.
- **dashboard**: 표시만. 데이터 변환 없음.

각 모듈은 import 시 다른 레이어에 의존 가능하지만 **위→아래 방향만 허용**. (예: dashboard는 storage를 import 가능, storage는 dashboard를 import 불가)

---

## 3. 데이터베이스 스키마 (SQLModel)

### 3.1 테이블 정의

```python
# src/storage/models.py
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship


class RawItem(SQLModel, table=True):
    """수집된 원본 항목 — Google Trends 검색어 또는 RSS 기사"""
    __tablename__ = "raw_items"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_type: str = Field(index=True)  # "google_trends" | "rss"
    source_name: str = Field(index=True)  # "south_korea" | "naver_it" 등
    title: str
    url: Optional[str] = None
    content: Optional[str] = None  # trafilatura 추출 본문
    published_at: Optional[datetime] = Field(default=None, index=True)
    collected_at: datetime = Field(default_factory=datetime.utcnow, index=True)

    # 중복 방지: source_type + url (URL 있을 때) 또는 source_type + title
    class Config:
        # SQLModel은 unique constraint를 별도 정의 필요 (아래 __table_args__로)
        pass


class Keyword(SQLModel, table=True):
    """추출된 키워드 (일별 집계)"""
    __tablename__ = "keywords"

    id: Optional[int] = Field(default=None, primary_key=True)
    keyword: str = Field(index=True)  # 정규화된 키워드 (소문자, 공백 제거 등)
    keyword_display: str  # 표시용 원본
    date: str = Field(index=True)  # "YYYY-MM-DD" 형식 (일별 집계 키)
    frequency: int = Field(default=1)  # 해당 일자 등장 횟수
    avg_score: float = Field(default=0.0)  # KeyBERT 코사인 유사도 평균
    source_types: str = Field(default="")  # "google_trends,rss" 콤마 구분


class DailyDigest(SQLModel, table=True):
    """일일 다이제스트 메타데이터"""
    __tablename__ = "daily_digests"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: str = Field(unique=True, index=True)  # "YYYY-MM-DD"
    total_items_collected: int
    total_keywords_extracted: int
    new_keywords_count: int  # 어제 없던 키워드 수
    rising_keywords_count: int  # 어제 대비 급상승 키워드 수
    pipeline_status: str  # "success" | "partial" | "failed"
    failed_sources: str = Field(default="")  # 실패한 출처 콤마 구분
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 3.2 인덱스 및 제약
- `raw_items`: (source_type, url) UNIQUE — URL 있는 RSS는 중복 방지. 인덱스: collected_at, published_at
- `keywords`: (keyword, date) UNIQUE — 일자별 키워드 1행. 인덱스: date, keyword
- `daily_digests`: date UNIQUE

### 3.3 마이그레이션 전략
- MVP는 단순화: `SQLModel.metadata.create_all(engine)` 한 번만 실행
- alembic 미사용 (스키마 변경 시 db 파일 삭제 후 재생성)
- README에 명시: "스키마 변경 시 data/topic_radar.db 삭제 후 재실행"

---

## 4. 핵심 모듈 의사코드

### 4.1 src/collectors/google_trends.py

```python
from pytrends.request import TrendReq
from typing import List, Dict
import time

class GoogleTrendsCollector:
    def __init__(self):
        # 한국 트렌드 + 한국어 + KST
        self.pytrends = TrendReq(
            hl='ko-KR',
            tz=540,
            timeout=(10, 25),
            retries=3,
            backoff_factor=0.5,
        )

    def fetch_trending_searches(self) -> List[Dict]:
        """한국 일일 인기 검색어 반환

        Returns:
            [{"title": "검색어", "source_name": "south_korea"}, ...]
        """
        try:
            df = self.pytrends.trending_searches(pn='south_korea')
            # 첫 번째 컬럼이 검색어 리스트
            keywords = df.iloc[:, 0].tolist()
            time.sleep(60)  # 다음 호출 위한 안전 sleep
            return [
                {"title": kw, "source_name": "south_korea"}
                for kw in keywords
            ]
        except Exception as e:
            # 절대 raise하지 않음 — graceful degradation
            print(f"[google_trends] 수집 실패: {e}")
            return []
```

**주의사항**:
- pytrends는 비공식 API라 자주 끊김. 절대 raise하지 않고 빈 리스트 반환.
- `pn='south_korea'` 외에 `realtime_trending_searches`는 한국 미지원이니 사용 금지.

### 4.2 src/collectors/rss_feeds.py

```python
import feedparser
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict

class RSSCollector:
    def __init__(self, config_path: str = "config/rss_sources.yml"):
        with open(config_path, encoding="utf-8") as f:
            self.sources = yaml.safe_load(f)["sources"]

    def fetch_recent_articles(
        self,
        hours_back: int = 24,
        max_per_source: int = 30,
    ) -> List[Dict]:
        """최근 N시간 내 기사 메타데이터 수집

        Returns:
            [{"title": ..., "url": ..., "published_at": datetime,
              "source_name": "naver_it"}, ...]
        """
        cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        articles = []

        for src in self.sources:
            try:
                feed = feedparser.parse(src["url"])

                for entry in feed.entries[:max_per_source]:
                    # published_parsed가 없는 RSS도 있음
                    pub_dt = self._parse_published(entry)
                    if pub_dt and pub_dt < cutoff:
                        continue

                    articles.append({
                        "title": entry.get("title", "").strip(),
                        "url": entry.get("link", ""),
                        "published_at": pub_dt,
                        "source_name": src["name"],
                    })
            except Exception as e:
                print(f"[rss] {src['name']} 실패: {e}")
                # 다음 출처로 계속
                continue

        return articles

    def _parse_published(self, entry) -> datetime | None:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        return None
```

### 4.3 src/processors/content_extractor.py

```python
import trafilatura
from typing import Optional

class ContentExtractor:
    """URL → 정제된 본문"""

    def extract(self, url: str, timeout: int = 10) -> Optional[str]:
        try:
            downloaded = trafilatura.fetch_url(url, no_ssl=True)
            if not downloaded:
                return None

            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,  # readability fallback 사용
                target_language="ko",  # 한국어 외 필터링
            )
            return text
        except Exception as e:
            print(f"[content_extractor] {url} 실패: {e}")
            return None
```

**중요**: `target_language="ko"` 설정으로 한국 RSS에 섞인 영어 기사 자동 필터링.

### 4.4 src/processors/korean_nlp.py

```python
from kiwipiepy import Kiwi
from typing import List

class KoreanNLP:
    def __init__(self):
        self.kiwi = Kiwi()
        # 의미 없는 명사 필터 (필요시 yml로 분리)
        self.stopwords = {
            "기자", "뉴스", "일보", "신문", "방송",
            "오늘", "어제", "내일", "지난",
            "관련", "해당", "이번", "지난번",
            # ... README에서 확장 가이드 제공
        }

    def extract_nouns(self, text: str, min_length: int = 2) -> List[str]:
        """텍스트에서 명사만 추출

        - 일반명사(NNG), 고유명사(NNP)만 수집
        - 2글자 미만, stopwords 제외
        """
        if not text:
            return []

        result = self.kiwi.tokenize(text)
        nouns = []
        for token in result:
            if token.tag in ("NNG", "NNP") \
               and len(token.form) >= min_length \
               and token.form not in self.stopwords:
                nouns.append(token.form)
        return nouns
```

### 4.5 src/processors/keyword_extractor.py

```python
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from typing import List, Tuple

class KeywordExtractor:
    """KeyBERT 다국어 임베딩 기반"""

    def __init__(self):
        # 다국어 (한국어 포함)
        model = SentenceTransformer(
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.kw_model = KeyBERT(model=model)

    def extract(
        self,
        text: str,
        candidates: List[str] | None = None,
        top_n: int = 5,
    ) -> List[Tuple[str, float]]:
        """KeyBERT로 키워드 + 점수 추출

        Args:
            text: 원본 텍스트
            candidates: Kiwi에서 뽑은 명사 후보 (있으면 우선)
            top_n: 반환할 최대 키워드 수

        Returns:
            [(키워드, 코사인 점수), ...]
        """
        if not text or len(text) < 50:
            return []

        try:
            keywords = self.kw_model.extract_keywords(
                text,
                candidates=candidates,  # 후보 제공 시 그 안에서만 선택
                keyphrase_ngram_range=(1, 2),
                stop_words=None,  # 한국어 stopwords는 candidates에서 처리
                top_n=top_n,
                use_mmr=True,  # 다양성 확보
                diversity=0.5,
            )
            return keywords
        except Exception as e:
            print(f"[keyword_extractor] 실패: {e}")
            return []
```

**중요**:
- 첫 실행 시 `paraphrase-multilingual-MiniLM-L12-v2` 모델 자동 다운로드 (~120MB)
- 인터넷 연결 필요. README에 명시.

### 4.6 src/analysis/trend_compare.py

```python
from datetime import date, timedelta
from sqlmodel import Session, select
from src.storage.models import Keyword
from typing import List, Dict

def get_top_keywords(session: Session, target_date: str, limit: int = 30) -> List[Keyword]:
    stmt = (
        select(Keyword)
        .where(Keyword.date == target_date)
        .order_by(Keyword.frequency.desc(), Keyword.avg_score.desc())
        .limit(limit)
    )
    return list(session.exec(stmt))

def detect_new_keywords(
    session: Session,
    today: str,
    yesterday: str,
    limit: int = 10,
) -> List[Keyword]:
    """어제는 없었는데 오늘 등장한 키워드"""
    yesterday_kws = {
        k.keyword for k in session.exec(
            select(Keyword).where(Keyword.date == yesterday)
        )
    }
    today_kws = session.exec(
        select(Keyword)
        .where(Keyword.date == today)
        .order_by(Keyword.frequency.desc())
    )
    return [k for k in today_kws if k.keyword not in yesterday_kws][:limit]

def detect_rising_keywords(
    session: Session,
    today: str,
    yesterday: str,
    min_growth_ratio: float = 2.0,
    limit: int = 10,
) -> List[Dict]:
    """어제 대비 빈도 N배 이상 증가한 키워드"""
    yesterday_freq = {
        k.keyword: k.frequency
        for k in session.exec(select(Keyword).where(Keyword.date == yesterday))
    }
    today_kws = session.exec(select(Keyword).where(Keyword.date == today))

    rising = []
    for k in today_kws:
        prev = yesterday_freq.get(k.keyword, 0)
        if prev == 0:
            continue  # 신규는 별도 함수에서 처리
        ratio = k.frequency / prev
        if ratio >= min_growth_ratio:
            rising.append({
                "keyword": k.keyword_display,
                "today_freq": k.frequency,
                "yesterday_freq": prev,
                "ratio": ratio,
            })

    rising.sort(key=lambda x: x["ratio"], reverse=True)
    return rising[:limit]
```

### 4.7 src/dashboard/app.py (Streamlit)

```python
import streamlit as st
from datetime import date, timedelta
from sqlmodel import Session
from src.storage.database import engine
from src.storage.models import DailyDigest
from src.analysis.trend_compare import (
    get_top_keywords,
    detect_new_keywords,
    detect_rising_keywords,
)

st.set_page_config(page_title="Topic Radar", layout="wide")
st.title("📡 Topic Radar — 일일 키워드 다이제스트")

# 날짜 선택
target = st.date_input("조회 날짜", value=date.today())
today_str = target.strftime("%Y-%m-%d")
yesterday_str = (target - timedelta(days=1)).strftime("%Y-%m-%d")

with Session(engine) as session:
    digest = session.get(DailyDigest, today_str)

    if not digest:
        st.warning(f"{today_str} 다이제스트가 없습니다. `python scripts/run_pipeline.py` 실행 필요.")
        st.stop()

    # 메타 정보
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("수집 항목", digest.total_items_collected)
    col2.metric("키워드 수", digest.total_keywords_extracted)
    col3.metric("신규 키워드", digest.new_keywords_count)
    col4.metric("급상승 키워드", digest.rising_keywords_count)

    # 3개 탭
    tab1, tab2, tab3 = st.tabs(["🔥 Top 30", "✨ 신규", "📈 급상승"])

    with tab1:
        top = get_top_keywords(session, today_str, limit=30)
        for i, k in enumerate(top, 1):
            st.write(f"**{i}. {k.keyword_display}** — 빈도 {k.frequency}, 점수 {k.avg_score:.3f}")

    with tab2:
        new_kws = detect_new_keywords(session, today_str, yesterday_str)
        if not new_kws:
            st.info("어제 대비 신규 키워드가 없습니다.")
        for k in new_kws:
            st.write(f"- **{k.keyword_display}** (빈도 {k.frequency})")

    with tab3:
        rising = detect_rising_keywords(session, today_str, yesterday_str)
        if not rising:
            st.info("어제 대비 급상승 키워드가 없습니다.")
        for r in rising:
            st.write(
                f"- **{r['keyword']}** "
                f"({r['yesterday_freq']} → {r['today_freq']}, {r['ratio']:.1f}배)"
            )
```

### 4.8 scripts/run_pipeline.py

```python
"""수집 → 처리 → 저장 1회 실행"""
from datetime import datetime, date
from collections import defaultdict
from sqlmodel import Session
import re

from src.storage.database import engine, init_db
from src.storage.models import RawItem, Keyword, DailyDigest
from src.collectors.google_trends import GoogleTrendsCollector
from src.collectors.rss_feeds import RSSCollector
from src.processors.content_extractor import ContentExtractor
from src.processors.korean_nlp import KoreanNLP
from src.processors.keyword_extractor import KeywordExtractor


def normalize_keyword(kw: str) -> str:
    """공백·특수문자 제거, 소문자화 (영문 섞인 경우 대비)"""
    return re.sub(r"\s+", "", kw.lower())


def main():
    init_db()  # 테이블 없으면 생성

    today = date.today().strftime("%Y-%m-%d")
    failed_sources = []

    print("=" * 60)
    print(f"Topic Radar Pipeline — {today}")
    print("=" * 60)

    # 1. 수집
    gt = GoogleTrendsCollector()
    rss = RSSCollector()
    extractor = ContentExtractor()

    trends = gt.fetch_trending_searches()
    if not trends:
        failed_sources.append("google_trends")

    articles = rss.fetch_recent_articles()
    if not articles:
        failed_sources.append("rss_all")

    print(f"수집 완료: trends {len(trends)}, articles {len(articles)}")

    # 2. RSS 본문 추출
    enriched_articles = []
    for art in articles:
        content = extractor.extract(art["url"]) if art["url"] else None
        if content:
            art["content"] = content
            enriched_articles.append(art)

    print(f"본문 추출 완료: {len(enriched_articles)} / {len(articles)}")

    # 3. 한국어 NLP + 키워드 추출
    nlp = KoreanNLP()
    kw_ex = KeywordExtractor()

    keyword_aggregator = defaultdict(lambda: {
        "freq": 0, "scores": [], "display": "", "sources": set()
    })

    # Google Trends 검색어는 그 자체로 키워드
    for t in trends:
        norm = normalize_keyword(t["title"])
        keyword_aggregator[norm]["freq"] += 1
        keyword_aggregator[norm]["scores"].append(1.0)  # 트렌드는 만점
        keyword_aggregator[norm]["display"] = t["title"]
        keyword_aggregator[norm]["sources"].add("google_trends")

    # RSS 본문은 KeyBERT로 추출
    for art in enriched_articles:
        text = (art.get("title") or "") + "\n" + (art.get("content") or "")
        nouns = nlp.extract_nouns(text)
        if not nouns:
            continue

        # KeyBERT는 candidates 내에서만 선택 (Kiwi 명사 후보)
        keywords = kw_ex.extract(text, candidates=list(set(nouns)), top_n=5)
        for kw, score in keywords:
            norm = normalize_keyword(kw)
            keyword_aggregator[norm]["freq"] += 1
            keyword_aggregator[norm]["scores"].append(score)
            keyword_aggregator[norm]["display"] = kw
            keyword_aggregator[norm]["sources"].add("rss")

    print(f"키워드 집계 완료: {len(keyword_aggregator)}")

    # 4. 저장
    with Session(engine) as session:
        # raw_items 저장 (중복 무시)
        for t in trends:
            existing = session.exec(
                # title 기준 중복 체크 (URL 없음)
                ...  # SQLModel select로 구현
            )
            session.add(RawItem(
                source_type="google_trends",
                source_name=t["source_name"],
                title=t["title"],
                collected_at=datetime.utcnow(),
            ))

        for art in enriched_articles:
            session.add(RawItem(
                source_type="rss",
                source_name=art["source_name"],
                title=art["title"],
                url=art["url"],
                content=art.get("content"),
                published_at=art.get("published_at"),
                collected_at=datetime.utcnow(),
            ))

        # keywords 저장 (오늘 데이터 upsert)
        for norm, data in keyword_aggregator.items():
            avg_score = sum(data["scores"]) / len(data["scores"])
            session.add(Keyword(
                keyword=norm,
                keyword_display=data["display"],
                date=today,
                frequency=data["freq"],
                avg_score=avg_score,
                source_types=",".join(sorted(data["sources"])),
            ))

        # daily_digests 메타
        from src.analysis.trend_compare import (
            detect_new_keywords, detect_rising_keywords
        )
        from datetime import timedelta as td
        yesterday = (date.today() - td(days=1)).strftime("%Y-%m-%d")

        session.commit()  # 키워드 먼저 저장 후 분석

        new_kws = detect_new_keywords(session, today, yesterday)
        rising_kws = detect_rising_keywords(session, today, yesterday)

        session.add(DailyDigest(
            date=today,
            total_items_collected=len(trends) + len(enriched_articles),
            total_keywords_extracted=len(keyword_aggregator),
            new_keywords_count=len(new_kws),
            rising_keywords_count=len(rising_kws),
            pipeline_status="success" if not failed_sources else "partial",
            failed_sources=",".join(failed_sources),
        ))
        session.commit()

    print("=" * 60)
    print("✅ 파이프라인 완료")
    print(f"신규 키워드: {len(new_kws)}, 급상승: {len(rising_kws)}")
    print("대시보드 실행: python scripts/run_dashboard.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

**중요**: 위 코드는 의사코드. Claude Code가 SQLModel의 정확한 select·upsert 구문, datetime 처리, 예외 케이스(같은 날 두 번 실행 시 중복 등)를 구현하면서 채워야 함.

### 4.9 scripts/run_dashboard.py

```python
"""Streamlit 대시보드 실행"""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    app_path = Path(__file__).parent.parent / "src" / "dashboard" / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=True,
    )
```

---

## 5. 설정 파일

### 5.1 config/rss_sources.yml

```yaml
# RSS 출처 정의 — 도메인 변경 시 이 파일만 수정
# 출처 추가는 url과 name만 명시하면 자동 반영

sources:
  # 종합·시사
  - name: "yna_top"
    url: "https://www.yna.co.kr/rss/news.xml"
    description: "연합뉴스 주요뉴스"

  - name: "yna_society"
    url: "https://www.yna.co.kr/rss/society.xml"
    description: "연합뉴스 사회"

  - name: "hani_main"
    url: "https://www.hani.co.kr/rss/"
    description: "한겨레 종합"

  # IT·테크
  - name: "zdnet_kr"
    url: "https://feeds.feedburner.com/zdkorea"
    description: "ZDNet Korea"

  - name: "etnews_it"
    url: "https://rss.etnews.com/Section902.xml"
    description: "전자신문 IT"

  - name: "bloter"
    url: "https://www.bloter.net/rss"
    description: "블로터"

  # 경제
  - name: "mk_top"
    url: "https://www.mk.co.kr/rss/30000001/"
    description: "매일경제 주요뉴스"

  # 합리적 기본값. 사용자가 운영 커뮤니티에 맞게 추가/제거 권장
```

**Claude Code 작업**: 위 RSS 중 작동 안 하는 게 있으면 README에 트러블슈팅 추가. 모두 fail-safe로 구현되어야 한다.

### 5.2 .env.example

```bash
# Topic Radar MVP — 환경변수 템플릿
# 현재 MVP는 외부 API 키 필요 없음. v2에서 사용 예정.

# (v2 예정)
# REDDIT_CLIENT_ID=
# REDDIT_CLIENT_SECRET=
# REDDIT_USER_AGENT=topic-radar/0.1

# (v2 예정) YouTube Data API
# YOUTUBE_API_KEY=

# 로컬 운영이라 현재는 비어있어도 무방
```

### 5.3 pyproject.toml

```toml
[project]
name = "topic-radar"
version = "0.1.0"
description = "커뮤니티 주제 발굴용 일일 키워드 다이제스트 (MVP)"
requires-python = ">=3.11"
dependencies = [
    # 수집
    "pytrends>=4.9.2",
    "feedparser>=6.0.11",
    "trafilatura>=1.12.0",

    # 한국어 NLP
    "kiwipiepy>=0.17.0",

    # 키워드 추출
    "keybert>=0.8.5",
    "sentence-transformers>=2.7.0",

    # 저장
    "sqlmodel>=0.0.16",

    # 표시
    "streamlit>=1.36.0",

    # 설정
    "pyyaml>=6.0.1",
    "python-dotenv>=1.0.1",
]

[tool.setuptools]
packages = ["src"]
```

**버전 명시 이유**: MVP는 호환성보다 재현성 우선. requirements.txt 자동 생성용.

---

## 6. 실행 시나리오

### 6.1 최초 설치
```bash
git clone <repo>
cd topic-radar

# Python 3.11+ 필요
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -e .
# 또는: pip install -r requirements.txt

# .env 생성 (MVP는 사실상 빈 파일)
cp .env.example .env

# DB 초기화 + 첫 파이프라인 실행
python scripts/run_pipeline.py
# 첫 실행 시 KeyBERT 모델 다운로드 (~120MB, 1~2분)

# 대시보드 실행
python scripts/run_dashboard.py
# 브라우저 자동 열림: http://localhost:8501
```

### 6.2 일일 사용
```bash
# 매일 아침 1회 실행
python scripts/run_pipeline.py

# 대시보드 확인
python scripts/run_dashboard.py
```

### 6.3 데이터 초기화
```bash
rm data/topic_radar.db
python scripts/run_pipeline.py
```

---

## 7. 검증 기준 (Claude Code "완료" 판단)

### 7.1 필수 통과 (모두 만족해야 완료)

1. **설치 검증**: `pip install -e .` 후 import 에러 없음
2. **첫 실행 검증**: `python scripts/run_pipeline.py` 실행 후
   - `data/topic_radar.db` 생성됨
   - `raw_items` 테이블에 행 50개 이상
   - `keywords` 테이블에 행 50개 이상
   - `daily_digests` 테이블에 오늘 날짜 1행
3. **대시보드 검증**: `python scripts/run_dashboard.py` 실행 후
   - http://localhost:8501 정상 표시
   - 메타 카드 4개 (수집 항목·키워드·신규·급상승) 표시
   - "Top 30" 탭에 30개 키워드 표시
4. **2일차 검증**: 다음날 다시 파이프라인 실행 후
   - "신규" 탭에 어제 없던 키워드 표시
   - "급상승" 탭에 빈도 증가 키워드 표시
5. **장애 복구 검증**:
   - RSS 출처 1개의 URL을 일부러 잘못 입력 → 다른 출처는 계속 수집됨
   - 인터넷 끊김 시 graceful fail (DB 손상 없음)

### 7.2 README 필수 포함 항목

1. 프로젝트 소개 (3~5줄)
2. 설치 (위 6.1 그대로)
3. 일일 사용 (위 6.2)
4. 폴더 구조 (위 2번 요약)
5. RSS 출처 추가 가이드 (config/rss_sources.yml 수정 방법)
6. 트러블슈팅
   - "pytrends 429 에러": 60초 sleep 후 재시도
   - "RSS 파싱 실패": rss_sources.yml에서 해당 출처 주석 처리
   - "Streamlit 포트 충돌": `streamlit run --server.port 8502`
   - "KeyBERT 모델 다운로드 실패": 인터넷 연결 확인, HuggingFace 접근 확인
7. 향후 확장 로드맵 (1~2줄씩):
   - v2: Reddit + YouTube
   - v3: BERTrend 시계열 토픽
   - v4: 한국 커뮤니티 (디시 등)

---

## 8. 트러블슈팅·예외 처리 원칙

### 8.1 Graceful Degradation
모든 외부 호출(pytrends, RSS, trafilatura)은 **절대 raise하지 않음**:
- 실패 → `print` 로그 + 빈 결과 반환
- 다음 처리 단계 계속
- 모든 출처 실패해도 파이프라인은 "partial" 상태로 완료

### 8.2 알려진 함정

| 함정 | 대응 |
|---|---|
| pytrends 429 (Rate Limit) | retries=3 + backoff_factor=0.5 + 호출 후 60초 sleep |
| RSS feed 인코딩 오류 | feedparser가 자동 처리. 못하면 출처 제외 |
| trafilatura가 일부 사이트 차단 | no_ssl=True, target_language="ko" 필터로 노이즈 감소 |
| Kiwi 첫 실행 시 사전 다운로드 | requirements 설치 시 자동, 별도 처리 불필요 |
| KeyBERT 모델 다운로드 (120MB) | 첫 실행 시간 안내. ~/.cache/huggingface 캐시됨 |
| 같은 날 두 번 실행 | 오늘 키워드/다이제스트 행 삭제 후 재생성 (upsert) |
| SQLite 동시성 | MVP는 단일 프로세스 가정. 멀티프로세스 시 해결 필요 (v2) |

---

## 9. 향후 확장 로드맵 (참고용 — 이번 MVP에 구현하지 않음)

### v2 — Reddit + YouTube 추가 (예상 2~3일)
- collectors/reddit_praw.py — PRAW 기반 서브레딧 모니터
- collectors/youtube_ytdlp.py — yt-dlp로 트렌딩 + 댓글
- .env에 REDDIT_*, YOUTUBE_API_KEY 추가
- 대시보드에 출처별 필터 추가

### v3 — BERTrend 시계열 토픽 분석 (예상 4~5일)
- analysis/bertrend_pipeline.py — 누적 데이터로 BERTrend 학습
- "약한 신호 / 강한 신호" 자동 분류 탭 추가
- 모델 저장 및 HuggingFace Hub 푸시 옵션

### v4 — 한국 커뮤니티 추가 (예상 1주)
- collectors/dcinside.py — eunchuldev/dcinside-python3-api 활용
- collectors/community_playwright.py — 네이트판·뽐뿌
- 작동 모니터링 자동화 (GitHub Actions로 매일 동작 테스트)

### v5 — 운영 고도화 (예상 1~2주)
- Slack/이메일 자동 발송
- GitHub Actions cron 자동 실행
- 사용자 설정 UI (RSS 추가/제거 웹에서)

---

## 10. Claude Code 작업 체크리스트

순서대로 작업할 때 권장 흐름:

- [ ] pyproject.toml + .gitignore + README 골격
- [ ] config/rss_sources.yml + .env.example
- [ ] src/storage/models.py (SQLModel) + database.py
- [ ] src/collectors/google_trends.py (가장 단순, 먼저 검증)
- [ ] src/collectors/rss_feeds.py
- [ ] src/processors/content_extractor.py
- [ ] src/processors/korean_nlp.py (Kiwi 첫 실행 검증)
- [ ] src/processors/keyword_extractor.py (KeyBERT 모델 다운로드 검증)
- [ ] scripts/run_pipeline.py (전체 통합)
- [ ] **여기서 첫 실행 검증** — `python scripts/run_pipeline.py` 성공 확인
- [ ] src/analysis/trend_compare.py
- [ ] src/dashboard/app.py
- [ ] scripts/run_dashboard.py
- [ ] **두 번째 검증** — 대시보드 정상 표시
- [ ] README 완성 (트러블슈팅 포함)
- [ ] 의도적 RSS 실패 테스트 (graceful degradation 검증)

---

## 부록 A — 핵심 의사결정 기록

이 spec에서 내린 주요 선택과 그 이유:

1. **SQLite + SQLModel**: 단순성. PostgreSQL은 v2에서 데이터 누적 후 검토.
2. **Streamlit 대시보드**: Python 단일 스택 유지. Next.js 추가 시 복잡도↑
3. **LLM API 미사용**: MVP는 키워드 자체로 충분. v2에서 토픽 명명 추가.
4. **테스트 코드 미포함**: MVP 정신. 수동 검증으로 충분.
5. **KeyBERT 후보 제한**: Kiwi 명사만 candidates로 전달 → 한국어 키워드 정확도↑
6. **MMR diversity=0.5**: 너무 비슷한 키워드 중복 방지
7. **target_language="ko"**: 한국 RSS 노이즈 자동 필터
8. **graceful degradation**: 외부 API 신뢰성↓이라 raise 절대 금지

## 부록 B — 사용자가 spec 받고 조정 가능한 항목

Claude Code에게 작업 시작 전 확인:
- [ ] RSS 출처 셋이 운영 커뮤니티 도메인과 맞나? (config/rss_sources.yml 미리 변경 권장)
- [ ] Top 30 / 신규 10 / 급상승 10 — 분량 적절한가? (코드 상수)
- [ ] stopwords 목록 — 도메인 맞춤 필요 시 (korean_nlp.py)
- [ ] 한 페이지 대시보드 vs 다중 페이지 — 현재 단일 페이지 (성장하면 분리)
