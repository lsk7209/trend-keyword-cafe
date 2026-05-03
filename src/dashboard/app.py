import html
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st
from sqlmodel import Session, col, select

from src.analysis.community_niches import (
    CommunityNiche,
    get_accumulated_community_niches,
    get_community_niches,
)
from src.analysis.trend_compare import (
    detect_new_keywords,
    detect_rising_keywords,
    get_top_keywords,
)
from src.storage.database import engine, init_db
from src.storage.models import CollectionSourceRun, DailyDigest, RawItem

TOP_KEYWORD_LIMIT = 30
SIGNAL_KEYWORD_LIMIT = 10
COPY_TABLE_HEIGHT = 480


def main() -> None:
    st.set_page_config(page_title="Topic Radar", layout="wide")
    st.title("Topic Radar - 커뮤니티 니치 레이더")

    init_db()
    target_date = st.date_input("조회 날짜", value=date.today(), format="YYYY-MM-DD")
    today = target_date.strftime("%Y-%m-%d")
    yesterday = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")

    with Session(engine) as session:
        digest = session.exec(select(DailyDigest).where(DailyDigest.date == today)).first()
        if not digest:
            st.warning(
                f"{today} 다이제스트가 없습니다. "
                "`python scripts/run_pipeline.py`를 실행하세요."
            )
            st.stop()

        render_metrics(digest)
        render_collection_status(session, today)
        render_overseas_trend_signals(session, today)
        render_youtube_trend_signals(session, today)
        render_community_niches(session, today)
        render_raw_keyword_diagnostics(session, today, yesterday)


def render_metrics(digest: DailyDigest) -> None:
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("수집 항목", digest.total_items_collected)
    col2.metric("키워드 수", digest.total_keywords_extracted)
    col3.metric("신규 키워드", digest.new_keywords_count)
    col4.metric("급상승 키워드", digest.rising_keywords_count)

    if digest.pipeline_status != "success":
        failed = digest.failed_sources or "알 수 없음"
        st.info(f"부분 성공 상태입니다. 실패 출처: {failed}")


def render_collection_status(session: Session, today: str) -> None:
    runs = session.exec(
        select(CollectionSourceRun)
        .where(CollectionSourceRun.date == today)
        .order_by(CollectionSourceRun.source)
    ).all()
    if not runs:
        return

    with st.expander("수집 상태"):
        st.dataframe(
            [
                {
                    "소스": run.source,
                    "상태": run.status,
                    "수집건수": run.items_collected,
                    "요청수": run.request_count,
                    "성공": run.success_count,
                    "실패": run.failure_count,
                    "캐시": run.cache_hits,
                    "오류": run.error_message,
                }
                for run in runs
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "소스": st.column_config.TextColumn(width="medium"),
                "상태": st.column_config.TextColumn(width="small"),
                "수집건수": st.column_config.NumberColumn(format="%d", width="small"),
                "요청수": st.column_config.NumberColumn(format="%d", width="small"),
                "성공": st.column_config.NumberColumn(format="%d", width="small"),
                "실패": st.column_config.NumberColumn(format="%d", width="small"),
                "캐시": st.column_config.NumberColumn(format="%d", width="small"),
                "오류": st.column_config.TextColumn(width="large"),
            },
        )


def render_overseas_trend_signals(session: Session, today: str) -> None:
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
    if not items:
        return

    rows = []
    for item in items[:50]:
        content = parse_raw_content(item.content)
        rows.append(
            {
                "국가": content.get("geo", ""),
                "검색어": item.title,
                "트래픽": content.get("traffic", ""),
                "수집시각": item.collected_at.strftime("%H:%M"),
            }
        )
    with st.expander("해외 선행 신호"):
        st.caption(
            "해외 Google Trends RSS에서 수집한 조기 신호입니다. "
            "국내 후보는 네이버 검색량/문서수 검증 후 반영됩니다."
        )
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "국가": st.column_config.TextColumn(width="small"),
                "검색어": st.column_config.TextColumn(width="large"),
                "트래픽": st.column_config.TextColumn(width="small"),
                "수집시각": st.column_config.TextColumn(width="small"),
            },
        )


def parse_raw_content(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    pairs: dict[str, str] = {}
    for part in value.split(";"):
        key, separator, raw_value = part.partition("=")
        if separator:
            pairs[key.strip()] = raw_value.strip()
    return pairs


def render_youtube_trend_signals(session: Session, today: str) -> None:
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
    if not items:
        return

    rows = []
    for item in items[:50]:
        content = parse_raw_content(item.content)
        rows.append(
            {
                "국가": content.get("region", ""),
                "영상 제목": item.title,
                "채널": item.source_name,
                "조회수": parse_int_text(content.get("views", "")),
                "카테고리": content.get("category", ""),
            }
        )
    with st.expander("YouTube 인기 영상 신호"):
        st.caption(
            "YouTube mostPopular에서 수집한 선행 신호입니다. "
            "국내 후보는 네이버 검색량/문서수 검증 후 반영됩니다."
        )
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            column_config={
                "국가": st.column_config.TextColumn(width="small"),
                "영상 제목": st.column_config.TextColumn(width="large"),
                "채널": st.column_config.TextColumn(width="medium"),
                "조회수": st.column_config.NumberColumn(format="%d", width="small"),
                "카테고리": st.column_config.TextColumn(width="small"),
            },
        )


def parse_int_text(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0


def render_community_niches(session: Session, today: str) -> None:
    st.subheader("커뮤니티 니치 후보")
    tab_today, tab_week, tab_month = st.tabs(["오늘 후보", "7일 누적", "30일 누적"])
    with tab_today:
        render_today_niches(session, today)
    with tab_week:
        render_accumulated_niches(session, today, period_days=7)
    with tab_month:
        render_accumulated_niches(session, today, period_days=30)


def render_today_niches(session: Session, today: str) -> None:
    sort_label = st.radio(
        "정렬 기준",
        options=("실전후보순", "월검색량순"),
        horizontal=True,
        key="today_niche_sort",
    )
    sort_by = "monthly_total" if sort_label == "월검색량순" else "practical"
    niches = get_community_niches(session, today, sort_by=sort_by)
    if not niches:
        st.info("추천할 커뮤니티 니치가 없습니다. 파이프라인을 다시 실행해 검색량을 수집하세요.")
        return

    rows = build_niche_rows(niches)
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "순위": st.column_config.NumberColumn(width="small"),
            "세부 주제": st.column_config.TextColumn(width="large"),
            "대표 검색키워드": st.column_config.TextColumn(width="medium"),
            "월검색량": st.column_config.NumberColumn(format="%d", width="small"),
            "PC": st.column_config.NumberColumn(format="%d", width="small"),
            "모바일": st.column_config.NumberColumn(format="%d", width="small"),
            "카페글": st.column_config.NumberColumn(format="%d", width="small"),
            "블로그": st.column_config.NumberColumn(format="%d", width="small"),
            "지식iN": st.column_config.NumberColumn(format="%d", width="small"),
            "뉴스": st.column_config.NumberColumn(format="%d", width="small"),
            "다음카페": st.column_config.NumberColumn(format="%d", width="small"),
            "쇼핑": st.column_config.NumberColumn(format="%d", width="small"),
            "수요공급점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "포화도": st.column_config.TextColumn(width="small"),
            "카페형판정": st.column_config.TextColumn(width="small"),
            "기회해석": st.column_config.TextColumn(width="medium"),
            "리스크": st.column_config.TextColumn(width="small"),
            "키워드범위": st.column_config.TextColumn(width="small"),
            "왜 주제형인가": st.column_config.TextColumn(width="large"),
            "세분화 방향": st.column_config.TextColumn(width="large"),
            "검색경쟁": st.column_config.TextColumn(width="small"),
            "카테고리": st.column_config.TextColumn(width="medium"),
            "난이도": st.column_config.TextColumn(width="small"),
            "실전점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "추천점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "클러스터": st.column_config.TextColumn(width="medium"),
        },
    )
    render_copy_tools(rows, key_prefix="today")


def render_accumulated_niches(session: Session, today: str, period_days: int) -> None:
    niches = get_accumulated_community_niches(session, today, period_days=period_days)
    if not niches:
        st.info("누적 후보가 없습니다. 며칠간 파이프라인을 실행하면 누적 랭킹이 채워집니다.")
        return

    rows = build_accumulated_rows(niches)
    st.caption(f"{period_days}일 안에 반복 등장한 후보를 누적점수순으로 정렬합니다.")
    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
        column_config={
            "순위": st.column_config.NumberColumn(width="small"),
            "세부 주제": st.column_config.TextColumn(width="large"),
            "대표 검색키워드": st.column_config.TextColumn(width="medium"),
            "판단": st.column_config.TextColumn(width="small"),
            "출현일수": st.column_config.NumberColumn(format="%d", width="small"),
            "평균 월검색량": st.column_config.NumberColumn(format="%d", width="small"),
            "평균 실전점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "최고 실전점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "카페글": st.column_config.NumberColumn(format="%d", width="small"),
            "지식iN": st.column_config.NumberColumn(format="%d", width="small"),
            "다음카페": st.column_config.NumberColumn(format="%d", width="small"),
            "쇼핑": st.column_config.NumberColumn(format="%d", width="small"),
            "포화도": st.column_config.TextColumn(width="small"),
            "누적점수": st.column_config.NumberColumn(format="%.1f", width="small"),
            "카테고리": st.column_config.TextColumn(width="medium"),
            "판단 근거": st.column_config.TextColumn(width="large"),
        },
    )
    render_copy_tools(rows, key_prefix=f"accumulated_{period_days}")


def build_niche_rows(niches: list[CommunityNiche]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, niche in enumerate(niches, 1):
        rows.append(
            {
                "순위": index,
                "세부 주제": niche["niche"],
                "대표 검색키워드": niche["keyword"],
                "월검색량": niche["monthly_total"],
                "PC": niche["monthly_pc"],
                "모바일": niche["monthly_mobile"],
                "카페글": niche["cafe_total"],
                "블로그": niche["blog_total"],
                "지식iN": niche["kin_total"],
                "뉴스": niche["news_total"],
                "다음카페": niche["kakao_cafe_total"],
                "쇼핑": niche["shopping_total"],
                "수요공급점수": niche["supply_gap_score"],
                "포화도": niche["saturation"],
                "카페형판정": niche["community_fit_label"],
                "기회해석": niche["opportunity_label"],
                "리스크": niche["risk_label"],
                "키워드범위": niche["keyword_scope"],
                "왜 주제형인가": niche["topic_reason"],
                "세분화 방향": niche["differentiation"],
                "검색경쟁": niche["search_competition"],
                "카테고리": niche["category"],
                "난이도": niche["difficulty"],
                "실전점수": niche["practical_score"],
                "추천점수": niche["recommendation_score"],
                "클러스터": niche["cluster_key"],
            }
        )
    return rows


def build_accumulated_rows(niches: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, niche in enumerate(niches, 1):
        rows.append(
            {
                "순위": index,
                "세부 주제": niche["niche"],
                "대표 검색키워드": niche["keyword"],
                "판단": niche["judgment"],
                "출현일수": niche["appeared_days"],
                "평균 월검색량": niche["avg_monthly_total"],
                "평균 실전점수": niche["avg_practical_score"],
                "최고 실전점수": niche["max_practical_score"],
                "카페글": niche["avg_cafe_total"],
                "지식iN": niche["avg_kin_total"],
                "다음카페": niche["avg_kakao_cafe_total"],
                "쇼핑": niche["avg_shopping_total"],
                "포화도": niche["saturation"],
                "누적점수": niche["cumulative_score"],
                "카테고리": niche["category"],
                "판단 근거": niche["reason"],
            }
        )
    return rows


def render_copy_tools(rows: list[dict[str, Any]], key_prefix: str) -> None:
    tsv = build_tsv(rows)
    st.download_button(
        "표 TSV 다운로드",
        data=tsv.encode("utf-8-sig"),
        file_name="community_niche_candidates.tsv",
        mime="text/tab-separated-values",
        key=f"{key_prefix}_download_tsv",
    )
    with st.expander("복사용 테이블"):
        st.caption("아래 표의 행을 더블클릭하면 해당 행이 TSV로 복사됩니다.")
        st.html(build_copy_table_html(rows, tsv), unsafe_allow_javascript=True)
        st.text_area("전체 TSV", value=tsv, height=160, key=f"{key_prefix}_tsv_text")


def build_tsv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join(clean_tsv_value(row[header]) for header in headers))
    return "\n".join(lines)


def clean_tsv_value(value: Any) -> str:
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def build_copy_table_html(rows: list[dict[str, Any]], tsv: str) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    row_texts = [
        "\t".join(clean_tsv_value(row[header]) for header in headers)
        for row in rows
    ]
    header_html = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    rows_html = "\n".join(
        build_copy_table_row(index, row, headers)
        for index, row in enumerate(rows)
    )
    return f"""
    <style>
      .copy-wrapper {{ height: {COPY_TABLE_HEIGHT}px; overflow: auto; font-family: sans-serif;
        color: #e5e7eb; background: #0f1117; border: 1px solid #263241; border-radius: 6px; }}
      .toolbar {{ position: sticky; top: 0; z-index: 2; padding: 8px; background: #0f1117; }}
      button {{ border: 1px solid #374151; border-radius: 6px; padding: 6px 10px;
        color: #f9fafb; background: #1f2937; cursor: pointer; }}
      #status {{ margin-left: 8px; color: #93c5fd; font-size: 12px; }}
      table {{ border-collapse: collapse; width: max-content; min-width: 100%; font-size: 13px; }}
      th, td {{ border: 1px solid #263241; padding: 7px 9px; max-width: 280px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
      th {{ position: sticky; top: 42px; background: #111827; color: #cbd5e1; z-index: 1; }}
      tr:nth-child(even) {{ background: #121826; }}
      tr:hover {{ background: #1d2a3d; }}
    </style>
    <div class="copy-wrapper">
      <div class="toolbar">
        <button id="copyAll">전체 TSV 복사</button>
        <span id="status">행 더블클릭 = 행 복사</span>
      </div>
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <script>
      const rowTexts = {json.dumps(row_texts, ensure_ascii=False)};
      const allText = {json.dumps(tsv, ensure_ascii=False)};
      async function copyText(text, label) {{
        try {{
          await navigator.clipboard.writeText(text);
          document.getElementById("status").textContent = label + " 복사됨";
        }} catch (error) {{
          const area = document.createElement("textarea");
          area.value = text;
          document.body.appendChild(area);
          area.select();
          document.execCommand("copy");
          area.remove();
          document.getElementById("status").textContent = label + " 복사됨";
        }}
      }}
      document.getElementById("copyAll").addEventListener("click", () => copyText(allText, "전체"));
      document.querySelectorAll("tbody tr").forEach((row) => {{
        row.addEventListener("dblclick", () => copyText(rowTexts[Number(row.dataset.index)], "행"));
      }});
    </script>
    """


def build_copy_table_row(index: int, row: dict[str, Any], headers: list[str]) -> str:
    cells = "".join(
        f"<td title=\"{html.escape(clean_tsv_value(row[header]))}\">"
        f"{html.escape(clean_tsv_value(row[header]))}</td>"
        for header in headers
    )
    return f'<tr data-index="{index}">{cells}</tr>'


def render_raw_keyword_diagnostics(session: Session, today: str, yesterday: str) -> None:
    if not st.checkbox("진단용 원시 키워드 보기"):
        return

    tab_top, tab_new, tab_rising = st.tabs(["Top 30", "신규", "급상승"])

    with tab_top:
        render_top_keywords(session, today)

    with tab_new:
        render_new_keywords(session, today, yesterday)

    with tab_rising:
        render_rising_keywords(session, today, yesterday)


def render_top_keywords(session: Session, today: str) -> None:
    top_keywords = get_top_keywords(session, today, limit=TOP_KEYWORD_LIMIT)
    if not top_keywords:
        st.info("표시할 키워드가 없습니다.")
    for index, keyword in enumerate(top_keywords, 1):
        st.write(
            f"**{index}. {keyword.keyword_display}** - "
            f"빈도 {keyword.frequency}, 점수 {keyword.avg_score:.3f}"
        )


def render_new_keywords(session: Session, today: str, yesterday: str) -> None:
    new_keywords = detect_new_keywords(session, today, yesterday, limit=SIGNAL_KEYWORD_LIMIT)
    if not new_keywords:
        st.info("어제 대비 신규 키워드가 없습니다.")
    for keyword in new_keywords:
        st.write(f"- **{keyword.keyword_display}** (빈도 {keyword.frequency})")


def render_rising_keywords(session: Session, today: str, yesterday: str) -> None:
    rising_keywords = detect_rising_keywords(
        session,
        today,
        yesterday,
        limit=SIGNAL_KEYWORD_LIMIT,
    )
    if not rising_keywords:
        st.info("어제 대비 급상승 키워드가 없습니다.")
    for rising_item in rising_keywords:
        st.write(
            f"- **{rising_item['keyword']}** "
            f"({rising_item['yesterday_freq']} -> {rising_item['today_freq']}, "
            f"{rising_item['ratio']:.1f}배)"
        )


if __name__ == "__main__":
    main()
