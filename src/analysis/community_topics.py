import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypedDict

from sqlmodel import Session, col, select

from src.storage.models import KeywordSearchVolume, RawItem, TopicSignal

DEFAULT_TOPIC_LIMIT = 15
MIN_USABLE_OPPORTUNITY_SCORE = 68.0
MIN_COMMUNITY_FIT_SCORE = 74.0
MAX_SATURATED_CAFE_TOTAL = 300_000
MAX_SATURATED_BLOG_TOTAL = 500_000

BLOCKED_TITLE_TERMS = {
    "ET포토",
    "포토",
    "속보",
    "공천",
    "윤리위",
    "집회",
    "대통령",
    "특검",
    "국힘",
    "조국",
    "송언석",
    "윤석열",
    "이재명",
    "전광훈",
    "김정은",
    "북한",
    "트럼프",
    "이란",
    "제재",
    "차관세",
    "미군",
    "해운사",
    "손흥민",
    "안우진",
    "두산",
    "키움",
    "LAFC",
    "다저스",
    "외인투수",
    "드래프트",
    "1군",
    "무승부",
    "득점",
    "패전",
    "국가폭력",
    "추모제",
    "협박범",
    "청주여자교도소",
    "선발투수",
    "ERA",
    "NC전",
    "LG 좌완",
    "정시",
    "수시선발",
    "서울대",
    "의대",
    "이지스구축함",
}

LOW_VALUE_KEYWORD_TERMS = {
    "AI",
    "가격",
    "사고",
    "설정",
    "평균",
    "예측",
    "서울",
    "한국",
    "미국",
    "중국",
    "일본",
    "지난달",
    "올해",
}

DYNAMIC_KEYWORD_TERMS = (
    "개인지방소득세",
    "청년내일저축계좌",
    "모바일 신분증",
    "AI 범죄자 콘텐츠",
    "범죄자 AI 콘텐츠",
    "중고차 계약 결제",
    "중고차",
    "계좌 동결",
    "보이스피싱",
    "아파트 정전",
    "아파트 화재",
    "오토바이 소음",
    "개인용 국채",
    "불법대부",
    "명품 인상",
    "웨딩비용",
    "중고 카메라",
    "어린이 교통사고",
    "어린이날 OTT",
    "아동안전",
    "초등학교 소풍",
    "기술탈취 신문고",
    "AI 페르소나",
    "챗GPT 대화",
    "알뜰폰 매장",
    "통신비",
    "광장시장 위생",
    "밥태기",
    "기름값",
    "소득세 신고",
    "보험사 M&A",
    "주식 도박",
    "금리 통장",
    "어린이날 콘텐츠",
    "편의점 협업상품",
)

class CommunityTopic(TypedDict):
    keyword: str
    community_topic: str
    description: str
    audience: str
    community_types: str
    post_angle: str
    topic: str
    score: float
    fit_score: float
    opportunity_score: float
    reason: str
    related_keywords: str
    source_title: str
    has_signals: bool
    has_search_volume: bool
    monthly_pc: int
    monthly_mobile: int
    monthly_total: int
    search_competition: str
    cafe_total: int
    blog_total: int
    kin_total: int
    news_total: int


@dataclass(frozen=True)
class TopicRule:
    keyword: str
    description: str
    audience: str
    community_types: tuple[str, ...]
    post_angle: str
    topic: str
    required_terms: tuple[str, ...]
    reason: str
    score: float
    fit_score: float
    related_keywords: tuple[str, ...]


@dataclass(frozen=True)
class DynamicTopicProfile:
    name: str
    trigger_terms: tuple[str, ...]
    audience: str
    community_types: tuple[str, ...]
    description_template: str
    topic_template: str
    post_angle_template: str
    reason: str
    score: float
    fit_score: float
    related_terms: tuple[str, ...]


TOPIC_RULES = (
    TopicRule(
        keyword="혼수 가전 가격비교",
        description="혼수 준비자가 실제 구매가 차이를 비교하기 좋은 생활형 주제",
        audience="예비부부",
        community_types=("결혼준비", "가전", "지역맘카페"),
        post_angle="견적 받은 가격과 매장별 차이를 댓글로 모으기",
        topic="혼수 가전 가격 차이, 구매 전에 비교할 점",
        required_terms=("혼수", "가전"),
        reason="구매 경험과 가격 비교 댓글을 만들기 좋음",
        score=95.0,
        fit_score=93.0,
        related_keywords=("혼수", "가전", "가격 비교"),
    ),
    TopicRule(
        keyword="보험약관 변경",
        description="가입자가 내 보험에 어떤 영향이 있는지 확인하게 만드는 정보 주제",
        audience="보험 가입자",
        community_types=("재테크", "생활정보", "맘카페"),
        post_angle="내 보험 약관에서 확인할 항목 체크리스트로 풀기",
        topic="보험약관 쉽게 바뀐다는데, 가입자가 확인할 핵심 변화",
        required_terms=("보험", "약관"),
        reason="실제 가입자에게 필요한 정보성 주제",
        score=92.0,
        fit_score=82.0,
        related_keywords=("보험", "약관", "보험금"),
    ),
    TopicRule(
        keyword="RSV 예방",
        description="아이 건강을 걱정하는 부모층이 반응하기 쉬운 육아·건강 주제",
        audience="영유아 부모",
        community_types=("육아", "맘카페", "건강"),
        post_angle="증상·예방접종·병원 방문 기준을 질문형으로 정리",
        topic="RSV 예방 사각지대, 아이 있는 집이 확인할 정보",
        required_terms=("RSV", "예방"),
        reason="육아·건강 카페에서 질문이 생기기 쉬움",
        score=90.0,
        fit_score=96.0,
        related_keywords=("RSV", "예방", "아이 건강"),
    ),
    TopicRule(
        keyword="5월 축제 선거법",
        description="지역 행사 참여자와 운영자가 헷갈릴 수 있는 실용 정보",
        audience="지역 행사 참여자",
        community_types=("지역카페", "축제", "소상공인"),
        post_angle="무료 나눔·상금 이벤트가 가능한지 사례별로 묻기",
        topic="5월 축제 무료 나눔·상금, 달라진 기준 확인",
        required_terms=("축제", "선거법"),
        reason="지역 카페 운영자와 참여자 모두에게 실용적임",
        score=88.0,
        fit_score=94.0,
        related_keywords=("축제", "무료 나눔", "상금"),
    ),
    TopicRule(
        keyword="계정 탈취 보안",
        description="사용자가 바로 점검할 수 있는 계정 보안 체크 주제",
        audience="일반 앱 사용자",
        community_types=("생활정보", "IT", "맘카페"),
        post_angle="오늘 바로 바꿀 보안 설정 3가지를 체크리스트로 제안",
        topic="계정 탈취 공격, 지금 점검할 보안 설정",
        required_terms=("계정 탈취",),
        reason="누구나 바로 확인할 수 있는 안전 체크 주제",
        score=87.0,
        fit_score=90.0,
        related_keywords=("계정 탈취", "보안", "설정"),
    ),
    TopicRule(
        keyword="LPG 가격 상승",
        description="운전자와 자영업자가 체감하는 비용 부담 주제",
        audience="차량 운전자",
        community_types=("자동차", "지역카페", "자영업"),
        post_angle="한 달 연료비가 얼마나 늘었는지 경험 댓글 유도",
        topic="LPG 가격 상승, 운전자 비용 부담 체크",
        required_terms=("LPG", "가격"),
        reason="차량 이용자에게 체감되는 생활비 주제",
        score=86.0,
        fit_score=84.0,
        related_keywords=("LPG", "가격", "운전자"),
    ),
    TopicRule(
        keyword="휴머노이드 로봇 쇼룸",
        description="신기술 체험과 방문 후기를 유도하기 좋은 트렌드 주제",
        audience="신기술 관심층",
        community_types=("IT", "테크", "전시"),
        post_angle="직접 보러 갈 가치가 있는지 체험 기대 포인트 비교",
        topic="휴머노이드 로봇 쇼룸, 직접 체험해볼 만할까",
        required_terms=("휴머노이드", "쇼룸"),
        reason="신기술 체험담과 호기심 댓글을 만들기 좋음",
        score=84.0,
        fit_score=70.0,
        related_keywords=("휴머노이드", "로봇", "쇼룸"),
    ),
    TopicRule(
        keyword="에어팟 울트라",
        description="구매 대기자 사이에서 기대 기능을 비교하기 좋은 제품 주제",
        audience="애플 제품 구매 대기자",
        community_types=("전자기기", "애플", "쇼핑"),
        post_angle="기존 에어팟과 비교해 기다릴 만한 기능 묻기",
        topic="에어팟 울트라와 AI 기능, 새 제품을 기다릴 만할까",
        required_terms=("에어팟", "AI"),
        reason="구매 대기자에게 비교·토론거리가 됨",
        score=83.0,
        fit_score=80.0,
        related_keywords=("에어팟", "AI 기능", "애플"),
    ),
    TopicRule(
        keyword="하이브리드차 구매",
        description="차량 구매 전 연비·가격·대기 수요를 비교하기 좋은 주제",
        audience="차량 구매 예정자",
        community_types=("자동차", "재테크", "지역카페"),
        post_angle="가솔린·전기차와 유지비를 비교하는 구매 상담글로 전환",
        topic="하이브리드차 판매 증가, 구매 전 비교할 포인트",
        required_terms=("하이브리드", "판매"),
        reason="차량 구매 고민을 정보성 글로 풀기 좋음",
        score=82.0,
        fit_score=86.0,
        related_keywords=("하이브리드", "현대차", "기아"),
    ),
    TopicRule(
        keyword="전주 5월 여행",
        description="지역 방문 코스와 축제 후기를 모으기 좋은 여행 주제",
        audience="주말 여행자",
        community_types=("여행", "지역카페", "맛집"),
        post_angle="영화제 전후로 갈 만한 동선과 맛집 추천을 묻기",
        topic="전주 5월 여행, 영화제와 지역 코스 추천",
        required_terms=("전주", "영화제"),
        reason="지역·여행 카페에서 경험 공유가 쉬움",
        score=80.0,
        fit_score=88.0,
        related_keywords=("전주", "영화제", "여행"),
    ),
    TopicRule(
        keyword="보험금 거절",
        description="보험금 청구 경험과 약관 확인 댓글을 만들기 좋은 주제",
        audience="보험금 청구 경험자",
        community_types=("재테크", "생활정보", "법률상담"),
        post_angle="거절 사유별로 약관에서 확인할 문구를 정리",
        topic="보험금 거절 사례, 약관에서 꼭 확인할 부분",
        required_terms=("보험금",),
        reason="실제 분쟁 사례를 바탕으로 정보성 댓글을 만들기 좋음",
        score=79.0,
        fit_score=82.0,
        related_keywords=("보험금", "약관", "보험사"),
    ),
    TopicRule(
        keyword="말차 디저트",
        description="카페 메뉴 취향과 신제품 추천으로 확장하기 좋은 소비 주제",
        audience="카페·디저트 관심층",
        community_types=("맛집", "카페", "쇼핑"),
        post_angle="최근 먹어본 말차 메뉴 추천과 실패 후기를 모으기",
        topic="말차 음료·디저트 유행, 카페 메뉴로 볼 만한 변화",
        required_terms=("말차",),
        reason="취향 공유와 메뉴 추천 댓글을 만들기 좋음",
        score=78.0,
        fit_score=84.0,
        related_keywords=("말차", "디저트", "음료"),
    ),
    TopicRule(
        keyword="게임 얼리액세스",
        description="출시 전 구매 판단과 후기 공유를 유도하기 좋은 게임 주제",
        audience="게임 구매 예정자",
        community_types=("게임", "콘솔", "PC"),
        post_angle="정식 출시 전 구매할 가치가 있는지 후기를 모으기",
        topic="게임 얼리액세스 출시, 구매 전 확인할 점",
        required_terms=("얼리액세스",),
        reason="게임 커뮤니티에서 구매 판단 토론이 가능함",
        score=77.0,
        fit_score=85.0,
        related_keywords=("게임", "얼리액세스", "가격"),
    ),
    TopicRule(
        keyword="주사기 구매 사기",
        description="피해 예방과 사기 사례 공유가 가능한 안전 정보 주제",
        audience="온라인 구매자",
        community_types=("생활정보", "안전", "사기예방"),
        post_angle="구매 유도 사기 문구와 신고 방법을 사례형으로 정리",
        topic="주사기 구매 유도 사기, 피해 예방 체크",
        required_terms=("주사기", "사기"),
        reason="사기 예방 정보를 공유하기 좋음",
        score=76.0,
        fit_score=76.0,
        related_keywords=("사기", "구매 유도", "주의"),
    ),
    TopicRule(
        keyword="청년정책 서포터즈",
        description="지역 청년 참여 기회로 공지·모집 글에 쓰기 좋은 주제",
        audience="지역 청년",
        community_types=("지역카페", "청년정책", "취업"),
        post_angle="지원 자격과 활동 혜택을 모집 공지형으로 정리",
        topic="청년정책 서포터즈, 지역 청년이 참여할 기회",
        required_terms=("청년정책", "서포터즈"),
        reason="지역 카페 공지·참여형 글로 쓰기 좋음",
        score=75.0,
        fit_score=82.0,
        related_keywords=("청년정책", "서포터즈", "지역"),
    ),
    TopicRule(
        keyword="노후산단 리모델링",
        description="지역 일자리와 생활권 변화를 이야기하기 좋은 지역 주제",
        audience="해당 지역 거주자",
        community_types=("지역카페", "부동산", "일자리"),
        post_angle="출퇴근·상권·일자리 변화가 있을지 지역 반응 묻기",
        topic="노후산단 리모델링, 지역 일자리와 생활권에 미칠 영향",
        required_terms=("노후산단",),
        reason="지역 카페에서 생활권 변화 주제로 다루기 좋음",
        score=74.5,
        fit_score=62.0,
        related_keywords=("노후산단", "경기도", "지역"),
    ),
    TopicRule(
        keyword="AI 보안 솔루션",
        description="계정 보호와 서비스 보안을 묶어 설명하기 좋은 IT 주제",
        audience="서비스 운영자",
        community_types=("IT", "보안", "스타트업"),
        post_angle="개인이 설정할 수 있는 보안과 기업 솔루션 차이를 설명",
        topic="AI 보안 솔루션과 계정 보호, 이용자가 알아둘 점",
        required_terms=("AI 보안",),
        reason="서비스 이용자 보안 점검 주제로 전환 가능함",
        score=74.0,
        fit_score=68.0,
        related_keywords=("AI 보안", "계정", "보안"),
    ),
    TopicRule(
        keyword="웨딩비용 절약템",
        description="예비부부가 결혼 준비 비용을 줄이는 방법을 비교하기 좋은 주제",
        audience="예비부부",
        community_types=("결혼준비", "쇼핑", "생활정보"),
        post_angle="직접 써본 절약템과 아낀 금액을 댓글로 모으기",
        topic="웨딩비용 아끼는 필수템, 실제로 도움이 되는지 비교",
        required_terms=("웨딩비용",),
        reason="구매 경험과 비용 인증 댓글을 유도하기 좋음",
        score=91.0,
        fit_score=96.0,
        related_keywords=("웨딩비용", "결혼준비", "절약템"),
    ),
    TopicRule(
        keyword="중고 카메라 구매",
        description="고가 취미 장비를 중고로 살 때 확인할 기준을 묻기 좋은 주제",
        audience="취미 장비 구매자",
        community_types=("사진", "중고거래", "취미"),
        post_angle="구매 전 확인할 컷수·렌즈·거래 방식 체크리스트",
        topic="중고 카메라 고가 구매, 사기 전에 확인할 체크포인트",
        required_terms=("중고 카메라",),
        reason="구매 전 상담과 경험 공유가 활발한 주제",
        score=88.0,
        fit_score=91.0,
        related_keywords=("중고 카메라", "카메라 구매", "중고거래"),
    ),
    TopicRule(
        keyword="불법대부 이자",
        description="대출 피해자가 상환 여부와 신고 방법을 확인하게 만드는 생활 법률 주제",
        audience="대출 피해자",
        community_types=("생활정보", "법률상담", "재테크"),
        post_angle="법정 최고금리 초과 시 갚아야 하는지 Q&A로 정리",
        topic="불법대부 이자 무효, 피해자가 확인할 상환 기준",
        required_terms=("불법대부",),
        reason="실제 피해 예방과 상담 수요가 있는 정보성 주제",
        score=90.0,
        fit_score=90.0,
        related_keywords=("불법대부", "법정 최고금리", "대출 피해"),
    ),
    TopicRule(
        keyword="개인용 국채 청약",
        description="예금 대안으로 고민하는 사람이 조건을 비교하기 좋은 재테크 주제",
        audience="안정형 투자자",
        community_types=("재테크", "직장인", "생활정보"),
        post_angle="예금·적금과 비교해 청약할 만한지 계산 예시로 풀기",
        topic="개인용 국채 청약, 예금 대신 넣어도 될지 비교",
        required_terms=("개인용 국채",),
        reason="투자 판단 전 비교 질문을 만들기 좋음",
        score=87.0,
        fit_score=88.0,
        related_keywords=("개인용 국채", "청약", "예금"),
    ),
    TopicRule(
        keyword="청년내일저축계좌",
        description="지원 자격과 실제 수령액을 확인하려는 청년층 수요가 큰 정책 주제",
        audience="청년·사회초년생",
        community_types=("청년정책", "재테크", "취업"),
        post_angle="월 납입액과 정부지원금을 표로 정리하고 자격 질문 받기",
        topic="청년내일저축계좌 모집, 내가 받을 수 있는지 확인",
        required_terms=("청년내일저축계좌",),
        reason="신청 기간이 있는 정책이라 즉시성 있는 글감",
        score=89.0,
        fit_score=94.0,
        related_keywords=("청년내일저축계좌", "청년 저축", "정부지원금"),
    ),
    TopicRule(
        keyword="AI 대화 증거",
        description="챗GPT 대화가 분쟁 자료가 될 수 있는지 궁금해하는 실용 법률 주제",
        audience="AI 서비스 사용자",
        community_types=("IT", "생활법률", "직장인"),
        post_angle="회사·거래·분쟁에서 AI 대화를 저장해도 되는지 묻기",
        topic="챗GPT 대화도 증거가 될까, 저장 전 확인할 점",
        required_terms=("챗GPT", "증거"),
        reason="새로운 사용 습관과 법률 궁금증이 만나는 주제",
        score=86.0,
        fit_score=86.0,
        related_keywords=("챗GPT", "AI 대화", "증거"),
    ),
    TopicRule(
        keyword="명품 가격 인상",
        description="구매 대기자가 인상 전 구매 여부를 비교하기 좋은 소비 주제",
        audience="명품 구매 예정자",
        community_types=("쇼핑", "패션", "중고거래"),
        post_angle="가격 인상 전 살지 기다릴지 브랜드별 의견 모으기",
        topic="명품 가격 인상 전 구매, 지금 사도 될지 비교",
        required_terms=("명품", "인상"),
        reason="구매 고민과 가격 정보 댓글을 만들기 좋음",
        score=86.0,
        fit_score=86.0,
        related_keywords=("명품", "가격 인상", "구매"),
    ),
    TopicRule(
        keyword="알뜰폰 오프라인 개통",
        description="온라인 개통이 어려운 사용자가 매장 개통 장단점을 비교하기 좋은 주제",
        audience="알뜰폰 전환 예정자",
        community_types=("통신비절약", "생활정보", "시니어"),
        post_angle="이마트 매장 개통과 온라인 셀프개통 차이를 비교",
        topic="알뜰폰 매장 개통, 온라인보다 편한지 비교",
        required_terms=("알뜰폰", "매장"),
        reason="통신비 절약과 실사용 경험 댓글을 유도하기 좋음",
        score=85.0,
        fit_score=88.0,
        related_keywords=("알뜰폰", "매장 개통", "통신비"),
    ),
    TopicRule(
        keyword="어린이날 OTT 추천",
        description="가족이 함께 볼 콘텐츠를 찾는 계절성 수요에 맞는 주제",
        audience="아이 있는 가족",
        community_types=("육아", "OTT", "가족"),
        post_angle="연령대별로 볼 만한 작품과 피해야 할 작품을 추천받기",
        topic="어린이날 가족 OTT 콘텐츠, 연령대별 추천",
        required_terms=("OTT 콘텐츠",),
        reason="가정의 달 수요와 경험 공유가 맞물림",
        score=84.0,
        fit_score=90.0,
        related_keywords=("어린이날", "OTT", "가족 콘텐츠"),
    ),
    TopicRule(
        keyword="어린이날 게임 행사",
        description="아이와 함께 갈 만한 체험 행사 정보를 비교하기 좋은 계절성 주제",
        audience="아이 있는 가족",
        community_types=("육아", "게임", "지역카페"),
        post_angle="연령대별 즐길 거리, 대기시간, 혼잡도 후기를 댓글로 모으기",
        topic="어린이날 게임 행사, 아이와 가볼 만한지 후기 모으기",
        required_terms=("어린이날", "게임"),
        reason="가정의 달 체험 수요와 후기 공유가 맞물림",
        score=85.0,
        fit_score=91.0,
        related_keywords=("어린이날", "게임 행사", "아이 체험"),
    ),
    TopicRule(
        keyword="아동안전 편의점",
        description="아이를 둔 부모가 위급 상황 대처법으로 저장하기 좋은 지역 안전 주제",
        audience="초등학생 부모",
        community_types=("육아", "지역카페", "안전"),
        post_angle="길 잃었을 때 아이에게 알려줄 장소와 행동요령 정리",
        topic="길 잃은 아이가 편의점으로 가도 될까, 아동안전 체크",
        required_terms=("아동안전",),
        reason="부모가 바로 공유하고 저장하기 좋은 안전 정보",
        score=87.0,
        fit_score=95.0,
        related_keywords=("아동안전", "편의점", "가정의 달"),
    ),
    TopicRule(
        keyword="오토바이 소음 민원",
        description="창문 여는 계절에 지역 주민이 바로 공감하는 생활 민원 주제",
        audience="주거지 주민",
        community_types=("지역카페", "생활민원", "아파트"),
        post_angle="신고 기준과 시간대별 대응 경험을 댓글로 모으기",
        topic="오토바이 소음 민원, 신고 기준과 실제 대응법",
        required_terms=("오토바이 소음",),
        reason="지역 카페에서 경험 공유와 해결책 논의가 쉬움",
        score=86.0,
        fit_score=94.0,
        related_keywords=("오토바이 소음", "민원", "신고"),
    ),
    TopicRule(
        keyword="아파트 정전 대처",
        description="단지 주민이 정전 때 확인할 보상·엘리베이터·냉장고 문제를 묻기 좋은 주제",
        audience="아파트 거주자",
        community_types=("아파트", "지역카페", "생활정보"),
        post_angle="정전 24시간 이상 지속 시 관리사무소에 물을 항목 정리",
        topic="아파트 정전 사흘째, 주민이 확인할 대처와 보상",
        required_terms=("전기 공급", "아파트"),
        reason="지역 커뮤니티에서 즉시 공유 가치가 큰 생활 이슈",
        score=88.0,
        fit_score=96.0,
        related_keywords=("아파트 정전", "전기 공급", "보상"),
    ),
    TopicRule(
        keyword="계좌 동결 해제",
        description="보이스피싱 연루 오해를 받은 사람이 절차를 확인하기 좋은 금융 안전 주제",
        audience="금융 앱 사용자",
        community_types=("재테크", "생활정보", "사기예방"),
        post_angle="억울한 계좌 동결 때 이의제기 순서를 단계별로 정리",
        topic="보이스피싱 계좌 동결, 억울할 때 해제 절차",
        required_terms=("계좌 동결",),
        reason="피해·오해 상황에서 검색과 질문 수요가 큼",
        score=90.0,
        fit_score=93.0,
        related_keywords=("계좌 동결", "보이스피싱", "이의제기"),
    ),
    TopicRule(
        keyword="어린이 교통사고",
        description="어린이날 전후 부모가 확인할 동선·보행 안전 주제",
        audience="초등학생 부모",
        community_types=("육아", "지역카페", "안전"),
        post_angle="아이와 외출 전 체크할 횡단보도·주차장 위험 포인트",
        topic="어린이날 교통사고 증가, 외출 전 안전 체크",
        required_terms=("어린이 교통사고",),
        reason="부모 커뮤니티에서 예방 정보로 전환하기 좋음",
        score=87.0,
        fit_score=93.0,
        related_keywords=("어린이 교통사고", "어린이날", "보행 안전"),
    ),
    TopicRule(
        keyword="모바일 신분증",
        description="실사용자가 어디서 쓸 수 있는지 확인하려는 생활 디지털 주제",
        audience="스마트폰 사용자",
        community_types=("생활정보", "IT", "직장인"),
        post_angle="병원·은행·편의점에서 사용 가능한지 사례별로 정리",
        topic="모바일 신분증 민간개방, 어디서 쓸 수 있을까",
        required_terms=("모바일 신분증",),
        reason="사용처 확인과 설치 경험 공유가 쉬움",
        score=86.0,
        fit_score=88.0,
        related_keywords=("모바일 신분증", "민간개방", "사용처"),
    ),
    TopicRule(
        keyword="기술탈취 신고",
        description="중소기업·스타트업이 무료 법률 도움을 확인할 수 있는 사업자 주제",
        audience="중소기업·스타트업",
        community_types=("창업", "소상공인", "법률상담"),
        post_angle="아이디어·기술을 빼앗겼을 때 신고 전 준비자료 정리",
        topic="기술탈취 신문고, 스타트업이 알아둘 신고 절차",
        required_terms=("기술탈취", "신문고"),
        reason="사업자 커뮤니티에서 실무형 정보로 쓰기 좋음",
        score=84.0,
        fit_score=84.0,
        related_keywords=("기술탈취", "신문고", "법률도움"),
    ),
    TopicRule(
        keyword="안전이별 방법",
        description="데이트폭력 위험을 느끼는 사람이 도움 요청 경로를 확인할 안전 주제",
        audience="연애·이별 고민자",
        community_types=("생활상담", "여성", "안전"),
        post_angle="위험 신호와 주변에 알려야 할 기준을 체크리스트로 정리",
        topic="안전이별, 위험 신호와 도움 요청 기준",
        required_terms=("안전이별",),
        reason="경험 공유보다 안전 정보 중심으로 다룰 가치가 큼",
        score=87.0,
        fit_score=89.0,
        related_keywords=("안전이별", "데이트폭력", "도움 요청"),
    ),
    TopicRule(
        keyword="AI 범죄자 콘텐츠",
        description="AI로 만든 범죄자 콘텐츠의 2차 가해 문제를 설명하기 좋은 디지털 안전 주제",
        audience="SNS 이용자·학부모",
        community_types=("디지털안전", "생활정보", "학부모"),
        post_angle="아이에게 보여도 되는 콘텐츠 기준과 신고 방법을 체크리스트로 정리",
        topic="AI 범죄자 콘텐츠 확산, 2차 가해를 막기 위해 확인할 점",
        required_terms=("AI 콘텐츠", "2차 가해"),
        reason="새로운 디지털 피해 사례라 주의 환기형 글감으로 적합함",
        score=86.0,
        fit_score=89.0,
        related_keywords=("AI 범죄자 콘텐츠", "2차 가해", "신고"),
    ),
    TopicRule(
        keyword="광장시장 위생 논란",
        description="맛집 방문 전 위생과 가격 후기를 확인하려는 여행·맛집 주제",
        audience="시장 방문 예정자",
        community_types=("맛집", "여행", "지역카페"),
        post_angle="최근 방문자가 느낀 위생·가격·대기 경험을 모으기",
        topic="광장시장 위생 논란, 방문 전 확인할 후기 포인트",
        required_terms=("광장시장", "재사용"),
        reason="방문 경험과 최신 후기 댓글을 만들기 좋음",
        score=84.0,
        fit_score=86.0,
        related_keywords=("광장시장", "위생", "방문 후기"),
    ),
    TopicRule(
        keyword="초등학교 소풍 감소",
        description="아이 학교 행사와 체험학습을 걱정하는 부모가 반응하기 좋은 주제",
        audience="초등학생 부모",
        community_types=("육아", "학부모", "지역카페"),
        post_angle="우리 학교는 소풍을 가는지, 대체 체험은 있는지 묻기",
        topic="초등학교 소풍 감소, 우리 아이 체험활동은 괜찮을까",
        required_terms=("소풍",),
        reason="학부모 커뮤니티에서 비교 경험이 잘 모이는 주제",
        score=84.0,
        fit_score=90.0,
        related_keywords=("초등학교 소풍", "체험학습", "학부모"),
    ),
    TopicRule(
        keyword="밥태기 아이 식단",
        description="아이 식사 고민을 가진 부모가 바로 질문하기 좋은 육아 주제",
        audience="영유아 부모",
        community_types=("육아", "맘카페", "식단"),
        post_angle="밥태기 때 먹힌 메뉴와 실패한 메뉴를 댓글로 모으기",
        topic="밥태기 아이 식단, 실제로 먹힌 메뉴 공유",
        required_terms=("밥태기",),
        reason="경험 댓글과 추천이 활발한 육아형 주제",
        score=88.0,
        fit_score=97.0,
        related_keywords=("밥태기", "아이 식단", "육아"),
    ),
)

DYNAMIC_TOPIC_PROFILES = (
    DynamicTopicProfile(
        name="parenting",
        trigger_terms=(
            "아이",
            "어린이",
            "아동",
            "초등",
            "이유식",
            "밥태기",
            "소풍",
            "교통사고",
            "아동안전",
            "RSV",
            "OTT 콘텐츠",
        ),
        audience="아이 있는 가족",
        community_types=("육아", "맘카페", "학부모"),
        description_template="{keyword}를 부모 입장에서 바로 확인하기 좋은 주제",
        topic_template="{keyword}, 부모가 지금 확인할 기준과 경험",
        post_angle_template="{keyword} 관련 실제 경험과 대처 기준을 댓글로 모으기",
        reason="육아·학부모 카페에서 질문과 경험 공유가 잘 생김",
        score=86.0,
        fit_score=92.0,
        related_terms=("육아", "아이", "부모"),
    ),
    DynamicTopicProfile(
        name="local_living",
        trigger_terms=(
            "아파트",
            "정전",
            "화재",
            "소음",
            "민원",
            "지역",
            "시장",
            "축제",
            "창문",
            "공원",
            "교통혼잡",
            "광장시장",
        ),
        audience="지역 주민",
        community_types=("지역카페", "아파트", "생활민원"),
        description_template="{keyword}를 지역 주민 관점에서 묻기 좋은 생활 이슈",
        topic_template="{keyword}, 우리 동네에서는 어떻게 대응할까",
        post_angle_template="{keyword} 관련 동네별 경험과 신고·대처 방법 묻기",
        reason="지역 카페에서 경험 댓글과 해결책 논의가 쉬움",
        score=85.0,
        fit_score=91.0,
        related_terms=("지역", "민원", "생활정보"),
    ),
    DynamicTopicProfile(
        name="money",
        trigger_terms=(
            "가격",
            "비용",
            "금리",
            "만원",
            "인상",
            "국채",
            "청약",
            "소득세",
            "세금",
            "신고",
            "대출",
            "불법대부",
            "통장",
            "지원금",
        ),
        audience="직장인·가계 소비자",
        community_types=("재테크", "생활정보", "직장인"),
        description_template="{keyword}를 비용·조건 관점에서 비교하기 좋은 주제",
        topic_template="{keyword}, 지금 확인할 비용 변화와 조건",
        post_angle_template="{keyword} 실제 부담액·신청 조건·절약 방법을 비교",
        reason="돈과 조건이 걸린 주제라 검색·질문 수요가 큼",
        score=84.0,
        fit_score=88.0,
        related_terms=("비용", "조건", "재테크"),
    ),
    DynamicTopicProfile(
        name="shopping",
        trigger_terms=(
            "중고",
            "구매",
            "결제",
            "명품",
            "매장",
            "알뜰폰",
            "카메라",
            "가전",
            "웨딩비용",
            "뷰티",
            "립스틱",
            "편의점",
            "협업 상품",
        ),
        audience="구매 예정자",
        community_types=("쇼핑", "중고거래", "생활정보"),
        description_template="{keyword}를 구매 전 비교·후기로 풀기 좋은 소비 주제",
        topic_template="{keyword}, 구매 전에 확인할 장단점",
        post_angle_template="{keyword} 직접 써본 후기와 가격 차이를 댓글로 모으기",
        reason="구매 전 상담과 실사용 후기 댓글을 만들기 좋음",
        score=84.0,
        fit_score=88.0,
        related_terms=("구매", "후기", "가격비교"),
    ),
    DynamicTopicProfile(
        name="digital_safety",
        trigger_terms=(
            "AI",
            "챗GPT",
            "계정",
            "보안",
            "모바일 신분증",
            "보이스피싱",
            "계좌 동결",
            "범죄자 콘텐츠",
            "2차 가해",
            "페르소나",
            "개인정보",
        ),
        audience="디지털 서비스 사용자",
        community_types=("IT", "생활정보", "사기예방"),
        description_template="{keyword}를 안전 점검과 사용법으로 풀기 좋은 디지털 주제",
        topic_template="{keyword}, 이용자가 지금 확인할 안전 기준",
        post_angle_template="{keyword} 관련 설정·저장·신고 기준을 체크리스트로 정리",
        reason="새 기술과 안전 이슈가 겹쳐 질문형 글감으로 전환 가능함",
        score=84.0,
        fit_score=86.0,
        related_terms=("보안", "디지털", "주의"),
    ),
    DynamicTopicProfile(
        name="policy_help",
        trigger_terms=(
            "모집",
            "지원",
            "청년",
            "정책",
            "저축계좌",
            "신고",
            "신문고",
            "공모전",
            "사업",
            "법률도움",
            "개설 운영",
        ),
        audience="신청 대상자",
        community_types=("생활정보", "정책지원", "지역카페"),
        description_template="{keyword}를 신청 자격과 절차로 정리하기 좋은 정책 주제",
        topic_template="{keyword}, 내가 신청할 수 있는지 확인",
        post_angle_template="{keyword} 대상·기간·준비서류를 Q&A로 정리",
        reason="마감과 자격 조건이 있어 즉시성 있는 글감",
        score=83.0,
        fit_score=86.0,
        related_terms=("지원", "신청", "자격"),
    ),
    DynamicTopicProfile(
        name="hobby_content",
        trigger_terms=(
            "게임",
            "OTT",
            "콘텐츠",
            "웹툰",
            "스티커",
            "카페",
            "디저트",
            "여행",
            "영화제",
        ),
        audience="취미·여가 관심층",
        community_types=("취미", "여행", "콘텐츠"),
        description_template="{keyword}를 추천·후기·취향 공유로 풀기 좋은 여가 주제",
        topic_template="{keyword}, 직접 경험해볼 만한지 의견 모으기",
        post_angle_template="{keyword} 추천과 비추천 경험을 댓글로 모으기",
        reason="취향 기반 댓글과 후기 공유가 쉬움",
        score=81.0,
        fit_score=82.0,
        related_terms=("추천", "후기", "취향"),
    ),
)


def get_community_topics(
    session: Session,
    target_date: str,
    limit: int = DEFAULT_TOPIC_LIMIT,
    require_signals: bool = True,
    require_search_volume: bool = True,
) -> list[CommunityTopic]:
    """키워드가 아니라 커뮤니티에 올릴 수 있는 주제 문장을 반환합니다."""

    topics = build_topics_from_titles(session, target_date)
    apply_topic_signals(session, target_date, topics)
    apply_search_volumes(session, target_date, topics)
    topics = filter_usable_topics(
        dedupe_topics(topics),
        require_signals=require_signals,
        require_search_volume=require_search_volume,
    )
    topics.sort(key=lambda topic: topic["opportunity_score"], reverse=True)
    return topics[:limit]


def build_topics_from_titles(session: Session, target_date: str) -> list[CommunityTopic]:
    titles = get_titles_for_date(session, target_date)
    topics: list[CommunityTopic] = []

    for title in titles:
        clean_title = clean_source_title(title)
        if not clean_title or is_blocked_title(clean_title):
            continue
        if not has_korean_text(clean_title):
            continue

        matched_rule = False
        for rule in TOPIC_RULES:
            if matches_rule(clean_title, rule):
                base_score = calculate_base_score(rule, clean_title)
                topics.append(build_rule_topic(rule, clean_title, base_score))
                matched_rule = True
                break

        if matched_rule:
            continue

        dynamic_topic = build_dynamic_topic(clean_title)
        if dynamic_topic:
            topics.append(dynamic_topic)

    return topics


def get_titles_for_date(session: Session, target_date: str) -> list[str]:
    target = datetime.strptime(target_date, "%Y-%m-%d")
    start = target - timedelta(hours=9)
    end = target + timedelta(days=1, hours=-9)
    statement = (
        select(RawItem.title)
        .where(
            col(RawItem.source_type).in_(["rss", "google_trends_news"]),
            col(RawItem.collected_at) >= start,
            col(RawItem.collected_at) < end,
        )
        .order_by(col(RawItem.id).desc())
    )
    titles = [title for title in session.exec(statement)]
    if titles:
        return titles

    fallback_statement = (
        select(RawItem.title)
        .where(col(RawItem.source_type).in_(["rss", "google_trends_news"]))
        .order_by(col(RawItem.id).desc())
        .limit(300)
    )
    return [title for title in session.exec(fallback_statement)]


def calculate_base_score(rule: TopicRule, title: str) -> float:
    return rule.score + get_title_quality_bonus(title) + get_fit_bonus(rule.fit_score)


def build_rule_topic(rule: TopicRule, title: str, base_score: float) -> CommunityTopic:
    search_keyword = pick_search_keyword(rule.keyword, rule.related_keywords)
    return {
        "keyword": search_keyword,
        "community_topic": rule.topic,
        "description": rule.description,
        "audience": rule.audience,
        "community_types": ", ".join(rule.community_types),
        "post_angle": rule.post_angle,
        "topic": rule.topic,
        "score": base_score,
        "fit_score": rule.fit_score,
        "opportunity_score": base_score,
        "reason": rule.reason,
        "related_keywords": build_related_keywords(search_keyword, rule.related_keywords),
        "source_title": title,
        "has_signals": False,
        "has_search_volume": False,
        "monthly_pc": 0,
        "monthly_mobile": 0,
        "monthly_total": 0,
        "search_competition": "",
        "cafe_total": 0,
        "blog_total": 0,
        "kin_total": 0,
        "news_total": 0,
    }


def build_dynamic_topic(title: str) -> CommunityTopic | None:
    profile = pick_dynamic_profile(title)
    if not profile or is_noise_dynamic_title(title):
        return None

    keyword_override = extract_keyword_override(title)
    if not keyword_override and not contains_community_intent(title):
        return None

    keyword = extract_dynamic_keyword(title, profile, keyword_override)
    if not is_valid_dynamic_keyword(keyword):
        return None

    base_score = calculate_dynamic_base_score(profile, title)
    topic = profile.topic_template.format(keyword=keyword)
    return {
        "keyword": keyword,
        "community_topic": topic,
        "description": profile.description_template.format(keyword=keyword),
        "audience": profile.audience,
        "community_types": ", ".join(profile.community_types),
        "post_angle": profile.post_angle_template.format(keyword=keyword),
        "topic": topic,
        "score": base_score,
        "fit_score": profile.fit_score,
        "opportunity_score": base_score,
        "reason": profile.reason,
        "related_keywords": build_dynamic_related_keywords(keyword, profile),
        "source_title": title,
        "has_signals": False,
        "has_search_volume": False,
        "monthly_pc": 0,
        "monthly_mobile": 0,
        "monthly_total": 0,
        "search_competition": "",
        "cafe_total": 0,
        "blog_total": 0,
        "kin_total": 0,
        "news_total": 0,
    }


def pick_dynamic_profile(title: str) -> DynamicTopicProfile | None:
    scored_profiles = [
        (calculate_profile_match_score(title, profile), profile)
        for profile in DYNAMIC_TOPIC_PROFILES
    ]
    score, profile = max(scored_profiles, key=lambda item: item[0])
    if score <= 0:
        return None
    return profile


def calculate_profile_match_score(title: str, profile: DynamicTopicProfile) -> int:
    score = 0
    for term in profile.trigger_terms:
        if is_trigger_match(title, term):
            score += 3 if len(term) >= 4 else 1
    if score == 0:
        return 0
    if contains_community_intent(title):
        score += 2
    return score


def is_trigger_match(title: str, term: str) -> bool:
    if len(term) >= 3:
        return term in title
    return term in re.split(r"[^0-9A-Za-z가-힣]+", title)


def extract_dynamic_keyword(
    title: str,
    profile: DynamicTopicProfile,
    keyword_override: str,
) -> str:
    if keyword_override:
        return keyword_override

    terms = extract_known_terms(title)
    terms.extend(extract_quoted_terms(title))
    terms.extend([term for term in profile.trigger_terms if is_trigger_match(title, term)])
    terms = unique_terms([normalize_dynamic_term(term) for term in terms])
    terms = [term for term in terms if term and term not in LOW_VALUE_KEYWORD_TERMS]

    if not terms:
        return ""
    return " ".join(terms[:3])


def extract_keyword_override(title: str) -> str:
    if "개인지방소득세" in title:
        return "개인지방소득세 신고"
    if "범죄자 AI 콘텐츠" in title or ("AI 콘텐츠" in title and "2차 가해" in title):
        return "AI 범죄자 콘텐츠"
    if "금리" in title and "통장" in title:
        return "고금리 통장"
    if "놀 권리" in title or "놀 시간 부족" in title:
        return "아동 놀 시간 부족"
    if "어린이날" in title and "게임" in title:
        return "어린이날 게임 행사"
    if "중고차" in title and ("계약" in title or "결제" in title):
        return "중고차 계약 결제"
    return ""


def extract_known_terms(title: str) -> list[str]:
    return [term for term in DYNAMIC_KEYWORD_TERMS if term in title]


def extract_quoted_terms(title: str) -> list[str]:
    quoted_terms = re.findall(r"['\"]([^'\"]{2,16})['\"]", title)
    return [term for term in quoted_terms if not is_low_value_quoted_term(term)]


def normalize_dynamic_term(term: str) -> str:
    term = term.replace("·", " ")
    term = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", term)
    term = re.sub(r"\s+", " ", term).strip()
    return term


def unique_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    for term in terms:
        if any(term == existing or term in existing for existing in result):
            continue
        result.append(term)
    return result


def is_low_value_quoted_term(term: str) -> bool:
    if len(term.strip()) < 2:
        return True
    return term in {"AI", "M&A", "US", "OO", "K"}


def is_valid_dynamic_keyword(keyword: str) -> bool:
    if not keyword:
        return False
    if keyword in LOW_VALUE_KEYWORD_TERMS:
        return False
    if len(keyword.replace(" ", "")) < 4:
        return False
    if not has_korean_text(keyword):
        return False
    return True


def is_noise_dynamic_title(title: str) -> bool:
    if "AI 콘텐츠" in title and "2차 가해" in title:
        return False

    sports_terms = (
        "드래프트",
        "외인투수",
        "다저스",
        "QS",
        "1군",
        "패전",
        "무승부",
        "선발 제외",
        "타이거즈",
        "선발투수",
        "ERA",
        "NC전",
        "LG 좌완",
    )
    if any(term in title for term in sports_terms):
        return True

    sensational_terms = ("쥐약", "협박범", "추모제", "국가폭력", "청주여자교도소")
    if any(term in title for term in sensational_terms):
        return True

    education_terms = ("정시", "수시선발", "서울대", "의대")
    if any(term in title for term in education_terms):
        return True

    foreign_incident_terms = ("이지스구축함", "홍해", "유조선")
    if any(term in title for term in foreign_incident_terms):
        return True

    business_terms = (
        "기획 플랫폼",
        "글로벌 캠페인",
        "어워드",
        "상장사",
        "타임 세계",
        "정책금융 축",
        "공급망 주권",
        "전략 투자",
        "매출",
    )
    if any(term in title for term in business_terms):
        return True
    return False


def calculate_dynamic_base_score(profile: DynamicTopicProfile, title: str) -> float:
    return (
        profile.score
        + get_title_quality_bonus(title)
        + get_fit_bonus(profile.fit_score)
        + get_community_intent_bonus(title)
    )


def get_community_intent_bonus(title: str) -> float:
    bonus = 0.0
    if contains_community_intent(title):
        bonus += 3.0
    if "만원" in title or "월 " in title or "신고" in title:
        bonus += 2.0
    if "논란" in title or "피해" in title or "주의" in title:
        bonus += 2.0
    return bonus


def contains_community_intent(title: str) -> bool:
    intent_terms = (
        "왜",
        "어떻게",
        "확인",
        "비교",
        "추천",
        "후기",
        "신고",
        "모집",
        "도움",
        "논란",
        "피해",
        "주의",
        "대처",
        "절약",
    )
    return any(term in title for term in intent_terms)


def build_dynamic_related_keywords(keyword: str, profile: DynamicTopicProfile) -> str:
    terms = unique_terms([keyword, *profile.related_terms])
    return ", ".join(terms[:4])


def pick_search_keyword(keyword: str, related_keywords: tuple[str, ...]) -> str:
    if related_keywords:
        return related_keywords[0]
    return keyword


def build_related_keywords(search_keyword: str, related_keywords: tuple[str, ...]) -> str:
    terms = unique_terms([search_keyword, *related_keywords])
    return ", ".join(terms[:4])


def get_fit_bonus(fit_score: float) -> float:
    if fit_score >= 94:
        return 5.0
    if fit_score >= 88:
        return 3.0
    if fit_score >= 82:
        return 1.0
    if fit_score < 70:
        return -5.0
    return 0.0


def matches_rule(title: str, rule: TopicRule) -> bool:
    return all(term in title for term in rule.required_terms)


def is_blocked_title(title: str) -> bool:
    return any(term in title for term in BLOCKED_TITLE_TERMS)


def has_korean_text(title: str) -> bool:
    return bool(re.search(r"[가-힣]", title))


def clean_source_title(title: str) -> str:
    title = re.sub(r"\[[^\]]+\]", "", title)
    title = title.replace("“", "").replace("”", "")
    title = title.replace("‘", "").replace("’", "")
    title = re.sub(r"\s+", " ", title).strip()
    return title


def get_title_quality_bonus(title: str) -> float:
    if "?" in title or "왜" in title:
        return 3.0
    if "주의" in title or "확인" in title:
        return 2.0
    return 0.0


def dedupe_topics(topics: list[CommunityTopic]) -> list[CommunityTopic]:
    seen: set[str] = set()
    result: list[CommunityTopic] = []

    for topic in topics:
        key = normalize_topic_key(topic)
        if key in seen:
            continue
        seen.add(key)
        result.append(topic)

    return result


def normalize_topic_key(topic: CommunityTopic) -> str:
    keyword = re.sub(r"\s+", "", topic["keyword"].lower())
    return re.sub(r"[^0-9a-z가-힣]", "", keyword)


def filter_usable_topics(
    topics: list[CommunityTopic],
    require_signals: bool,
    require_search_volume: bool,
) -> list[CommunityTopic]:
    return [
        topic
        for topic in topics
        if is_usable_topic(topic, require_signals, require_search_volume)
    ]


def is_usable_topic(
    topic: CommunityTopic,
    require_signals: bool,
    require_search_volume: bool,
) -> bool:
    if topic["fit_score"] < MIN_COMMUNITY_FIT_SCORE:
        return False
    if topic["opportunity_score"] < MIN_USABLE_OPPORTUNITY_SCORE:
        return False
    if require_signals and not topic["has_signals"]:
        return False
    if require_search_volume and not has_usable_search_volume(topic):
        return False
    if not topic["has_signals"]:
        return True
    if is_saturated_topic(topic):
        return False
    return True


def has_usable_search_volume(topic: CommunityTopic) -> bool:
    return topic["has_search_volume"] and topic["monthly_total"] > 0


def is_saturated_topic(topic: CommunityTopic) -> bool:
    cafe_total = topic["cafe_total"]
    blog_total = topic["blog_total"]
    if cafe_total >= MAX_SATURATED_CAFE_TOTAL:
        return True
    if blog_total >= MAX_SATURATED_BLOG_TOTAL:
        return True
    if cafe_total >= 150_000 and blog_total >= 150_000:
        return True
    if blog_total >= 250_000 and topic["news_total"] >= 80_000:
        return True
    return False


def apply_topic_signals(
    session: Session,
    target_date: str,
    topics: list[CommunityTopic],
) -> None:
    if not topics:
        return

    signals_by_topic = load_signals_by_topic(session, target_date)
    for topic in topics:
        signals = signals_by_topic.get(topic["topic"], {})
        has_signals = bool(signals)
        cafe_total = signals.get("cafearticle", 0)
        blog_total = signals.get("blog", 0)
        kin_total = signals.get("kin", 0)
        news_total = signals.get("news", 0)

        topic["has_signals"] = has_signals
        topic["cafe_total"] = cafe_total
        topic["blog_total"] = blog_total
        topic["kin_total"] = kin_total
        topic["news_total"] = news_total
        topic["opportunity_score"] = calculate_opportunity_score(
            base_score=topic["score"],
            fit_score=topic["fit_score"],
            has_signals=has_signals,
            cafe_total=cafe_total,
            blog_total=blog_total,
            kin_total=kin_total,
            news_total=news_total,
        )
        topic["reason"] = append_signal_reason(topic["reason"], cafe_total, blog_total, kin_total)


def apply_search_volumes(
    session: Session,
    target_date: str,
    topics: list[CommunityTopic],
) -> None:
    if not topics:
        return

    volumes = load_volumes_by_keyword(session, target_date)
    for topic in topics:
        volume = volumes.get(topic["keyword"])
        if not volume:
            continue

        topic["has_search_volume"] = True
        topic["monthly_pc"] = volume.monthly_pc
        topic["monthly_mobile"] = volume.monthly_mobile
        topic["monthly_total"] = volume.monthly_total
        topic["search_competition"] = volume.competition
        topic["opportunity_score"] = apply_search_volume_score(
            topic["opportunity_score"],
            volume.monthly_total,
            volume.competition,
        )


def load_volumes_by_keyword(
    session: Session,
    target_date: str,
) -> dict[str, KeywordSearchVolume]:
    statement = select(KeywordSearchVolume).where(KeywordSearchVolume.date == target_date)
    return {volume.keyword: volume for volume in session.exec(statement)}


def apply_search_volume_score(
    score: float,
    monthly_total: int,
    competition: str,
) -> float:
    if monthly_total <= 0:
        return round(score - 100.0, 1)
    if monthly_total < 100:
        score += 1.0
    elif monthly_total < 1_000:
        score += 4.0
    elif monthly_total < 10_000:
        score += 8.0
    else:
        score += 6.0

    if competition == "높음":
        score -= 4.0
    elif competition == "낮음":
        score += 2.0
    return round(score, 1)


def load_signals_by_topic(session: Session, target_date: str) -> dict[str, dict[str, int]]:
    statement = select(TopicSignal).where(TopicSignal.date == target_date)
    result: dict[str, dict[str, int]] = {}
    for signal in session.exec(statement):
        result.setdefault(signal.topic, {})[signal.service] = signal.total
    return result


def calculate_opportunity_score(
    base_score: float,
    fit_score: float,
    has_signals: bool,
    cafe_total: int,
    blog_total: int,
    kin_total: int,
    news_total: int,
) -> float:
    score = base_score

    if not has_signals:
        return round(score, 1)

    score += min((fit_score - 74.0) / 4.0, 6.0)
    score += min(kin_total / 200.0, 10.0)
    score += min(news_total / 2_000.0, 6.0)

    if cafe_total < 100:
        score += 16.0
    elif cafe_total < 1_000:
        score += 12.0
    elif cafe_total < 5_000:
        score += 8.0
    elif cafe_total < 20_000:
        score += 2.0
    elif cafe_total > 100_000:
        score -= 30.0
    elif cafe_total > 10_000:
        score -= 15.0

    if blog_total > 200_000:
        score -= 40.0
    elif blog_total > 50_000:
        score -= 25.0
    elif blog_total > 10_000:
        score -= 10.0

    if news_total > 100_000:
        score -= 10.0

    return round(score, 1)


def append_signal_reason(reason: str, cafe_total: int, blog_total: int, kin_total: int) -> str:
    signal_reasons: list[str] = []
    if cafe_total and cafe_total < 1_000:
        signal_reasons.append("카페 경쟁 낮음")
    if kin_total >= 100:
        signal_reasons.append("질문 수요 있음")
    if cafe_total > 100_000 or blog_total > 200_000:
        signal_reasons.append("기존 콘텐츠 포화 주의")
    elif blog_total > 10_000:
        signal_reasons.append("블로그 포화 주의")

    if not signal_reasons:
        return reason
    return f"{reason} · {' · '.join(signal_reasons)}"
