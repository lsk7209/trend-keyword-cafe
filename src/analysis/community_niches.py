import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import log10
from typing import TypedDict

from sqlmodel import Session, select

from src.storage.models import KeywordSearchVolume, TopicSignal

DEFAULT_NICHE_LIMIT = 100
MIN_MONTHLY_SEARCH_VOLUME = 100
MIN_EXPANDED_MONTHLY_SEARCH_VOLUME = 300
MIN_QUESTION_MONTHLY_SEARCH_VOLUME = 100
LOW_CAFE_DOCUMENT_THRESHOLD = 10_000
HIGH_CAFE_DOCUMENT_THRESHOLD = 200_000
HIGH_BLOG_DOCUMENT_THRESHOLD = 500_000
HIGH_KAKAO_CAFE_DOCUMENT_THRESHOLD = 100_000
HIGH_SHOPPING_DOCUMENT_THRESHOLD = 300_000
QUESTION_SIGNAL_THRESHOLD = 1_000
HIGH_SEARCH_VOLUME_THRESHOLD = 100_000
PRACTICAL_CAFE_SOFT_CAP = 150_000
PRACTICAL_BLOG_SOFT_CAP = 450_000
CLUSTER_DISPLAY_LIMIT = 2
MAX_CATEGORY_TOP_SHARE = 0.4

HIGH_RISK_TERMS = ("대출", "해외선물", "사채", "급전", "개인회생", "성범죄")
MEDIUM_RISK_TERMS = ("보험", "병원", "개원의", "창업", "투자", "주식")
LOW_VALUE_EXPANDED_TERMS = (
    "가격",
    "비용",
    "추천",
    "순위",
    "사이트",
    "광고",
    "대행",
    "정상수치",
    "수치",
    "측정기",
    "응시자격",
    "관리자",
    "기사",
)
COMMUNITY_INTENT_TERMS = (
    "관리",
    "식단",
    "혈당",
    "창업",
    "운영",
    "키우기",
    "입문",
    "자격",
    "구인",
    "구직",
    "후기",
    "모임",
    "동호회",
    "공부",
    "재활",
    "장비",
    "세금",
    "신고",
)
CAFE_TITLE_SIGNAL_TERMS = (
    "후기",
    "질문",
    "문의",
    "공유",
    "인증",
    "모임",
    "입문",
    "초보",
    "운영",
    "창업",
    "관리",
    "구인",
    "구직",
    "나눔",
    "분양",
)


class CommunityNiche(TypedDict):
    niche: str
    keyword: str
    monthly_total: int
    monthly_pc: int
    monthly_mobile: int
    search_competition: str
    cafe_total: int
    blog_total: int
    kin_total: int
    news_total: int
    kakao_cafe_total: int
    shopping_total: int
    saturation: str
    opportunity_label: str
    supply_gap_score: float
    community_fit_label: str
    risk_label: str
    keyword_scope: str
    topic_reason: str
    benchmark_cafes: str
    target_members: str
    category: str
    growth_signal: str
    differentiation: str
    monetization: str
    repeat_reason: str
    difficulty: str
    recommendation_score: float
    practical_score: float
    cluster_key: str


class AccumulatedNiche(TypedDict):
    niche: str
    keyword: str
    category: str
    period_days: int
    appeared_days: int
    avg_monthly_total: int
    max_practical_score: float
    avg_practical_score: float
    avg_cafe_total: int
    avg_kin_total: int
    avg_kakao_cafe_total: int
    avg_shopping_total: int
    saturation: str
    cumulative_score: float
    judgment: str
    reason: str


NaverDocumentTotals = dict[str, int]


@dataclass(frozen=True)
class NicheRule:
    niche: str
    keyword: str
    category: str
    benchmark_cafes: tuple[str, ...]
    target_members: str
    growth_signal: str
    differentiation: str
    monetization: str
    repeat_reason: str
    difficulty: str
    base_score: float
    sustainability: int
    monetization_score: int
    competition_penalty: int


NICHE_RULES = (
    NicheRule(
        niche="부모 돌봄·요양시설 후기",
        keyword="장기요양",
        category="돌봄/시니어",
        benchmark_cafes=("부모안심센터", "은퇴 후 50년", "복지 아는게 힘"),
        target_members="부모 요양을 준비하는 4050 자녀",
        growth_signal="씨앗 단계 카페가 높은 점수 상승을 보이며 돌봄 상담형 수요 확인",
        differentiation="시설 후기, 등급 신청, 요양비 비교를 보호자 관점으로 좁힘",
        monetization="요양 상담, 시설 제휴, 체크리스트, 보험 상담",
        repeat_reason="등급 신청, 시설 선택, 비용, 후기 질문이 반복됨",
        difficulty="중",
        base_score=92.0,
        sustainability=10,
        monetization_score=9,
        competition_penalty=4,
    ),
    NicheRule(
        niche="임신성당뇨 혈당관리",
        keyword="임신성당뇨",
        category="임신/건강",
        benchmark_cafes=("맘스센스", "맘스홀릭 베이비", "지후맘"),
        target_members="임신성당뇨 진단을 받은 임산부",
        growth_signal="세부 질환형 맘카페가 작아도 강한 체류 수요를 보임",
        differentiation="식단 인증, 공복혈당, 병원/소모품 경험으로 특화",
        monetization="혈당측정기, 식단, 산모용품, 병원 제휴",
        repeat_reason="매일 식단·혈당 기록과 질문이 발생함",
        difficulty="중",
        base_score=93.0,
        sustainability=10,
        monetization_score=8,
        competition_penalty=5,
    ),
    NicheRule(
        niche="공유숙박 운영자 실무",
        keyword="에어비앤비",
        category="숙박/사업자",
        benchmark_cafes=(
            "공유숙박 정보교환",
            "나리테일 숙박업 이야기",
            "아마존 셀러 공식 커뮤니티",
        ),
        target_members="에어비앤비·위홈 운영자와 예비 호스트",
        growth_signal="새싹 단계에서도 운영자 실무형 카페가 빠르게 점수 상승",
        differentiation="허가, 세금, 청소, 리뷰 관리, 플랫폼 정책 변경을 실무형으로 묶음",
        monetization="운영대행, 청소/사진/가격관리 제휴, 교육자료",
        repeat_reason="예약, 민원, 정책, 세금 문제가 계속 반복됨",
        difficulty="중",
        base_score=91.0,
        sustainability=9,
        monetization_score=10,
        competition_penalty=5,
    ),
    NicheRule(
        niche="초보 프리다이빙·수영복 후기",
        keyword="프리다이빙",
        category="취미/스포츠",
        benchmark_cafes=("물로그", "수영 코디카페", "여자혼자가는여행"),
        target_members="수영·프리다이빙 입문자와 휴양지 여행자",
        growth_signal="수영복+프리다이빙 결합 카페가 새싹 단계에서 강한 상승",
        differentiation="장비 후기, 체형별 수영복, 강습 후기, 여행 코스 결합",
        monetization="수영복 제휴, 강습, 여행상품, 장비 공동구매",
        repeat_reason="장비·강습·후기·사진 공유가 반복됨",
        difficulty="중",
        base_score=89.0,
        sustainability=8,
        monetization_score=9,
        competition_penalty=4,
    ),
    NicheRule(
        niche="만성염증·혈당·이너뷰티 루틴",
        keyword="이너뷰티",
        category="건강/뷰티",
        benchmark_cafes=("클린바디", "스킨로그", "가벼운습관"),
        target_members="피부·혈당·피로를 루틴으로 관리하려는 2030 여성",
        growth_signal="건강 루틴형 소형 카페가 상승세, 뷰티와 건강 경계가 커짐",
        differentiation="제품 광고보다 루틴 기록, 수치 변화, 식단 인증 중심",
        monetization="건기식, 뷰티, 식단, 챌린지, 체험단",
        repeat_reason="매일 루틴 인증과 제품 후기가 발생함",
        difficulty="중",
        base_score=88.0,
        sustainability=9,
        monetization_score=10,
        competition_penalty=7,
    ),
    NicheRule(
        niche="공부방·교습소 운영 실무",
        keyword="공부방 창업",
        category="교육사업",
        benchmark_cafes=(
            "공부방 운영에 도움 주는 비상교육 카페",
            "강한 영어학원 만들기",
            "해보쌤 카페",
        ),
        target_members="공부방·교습소·소규모 학원 운영자",
        growth_signal="교육 사업자형 카페는 자료·운영 노하우 수요가 안정적",
        differentiation="홍보, 교재, 학부모 상담, 월매출 관리까지 운영자 관점 특화",
        monetization="교재 제휴, 운영 강의, 양식 판매, 광고",
        repeat_reason="학생 모집, 상담, 교재, 시험 기간 질문이 반복됨",
        difficulty="중",
        base_score=90.0,
        sustainability=9,
        monetization_score=9,
        competition_penalty=5,
    ),
    NicheRule(
        niche="입주예정자·신축단지 운영 템플릿",
        keyword="입주예정자 카페",
        category="지역/부동산",
        benchmark_cafes=("운정신도시 입주자 카페", "진접2지구 A1", "창릉신도시 S5"),
        target_members="신축 아파트 입주예정자와 운영진",
        growth_signal="새 단지별 카페가 계속 생기고 초기 결집 속도가 빠름",
        differentiation="단일 단지가 아니라 입예협 운영 템플릿과 공동구매 노하우 제공",
        monetization="입주청소, 줄눈, 탄성코트, 이사, 공동구매",
        repeat_reason="입주 일정, 하자, 공동구매, 관리 이슈가 반복됨",
        difficulty="중",
        base_score=87.0,
        sustainability=8,
        monetization_score=10,
        competition_penalty=4,
    ),
    NicheRule(
        niche="개원의·페이닥터 병원 운영",
        keyword="개원의",
        category="전문직/의료",
        benchmark_cafes=("닥터인사이트", "히어링허브", "병원을 맘대로"),
        target_members="개원의, 개원 예정의, 페이닥터",
        growth_signal="전문직 폐쇄형 니치가 작은 멤버수 대비 높은 점수 상승",
        differentiation="좋은 업체, 세무, 노무, 인테리어, 마케팅 후기 중심",
        monetization="병원 마케팅, 세무/노무, 장비, 인테리어 제휴",
        repeat_reason="개원 준비와 운영 문제는 정보 비대칭이 커 반복 상담됨",
        difficulty="상",
        base_score=91.0,
        sustainability=9,
        monetization_score=10,
        competition_penalty=3,
    ),
    NicheRule(
        niche="금주·단주 회복 커뮤니티",
        keyword="금주",
        category="회복/건강",
        benchmark_cafes=("AA 길잡이", "김진현 다이어트", "하늘사랑"),
        target_members="술을 줄이거나 끊고 싶은 사람과 가족",
        growth_signal="고통 해결형 카페는 소규모라도 결속과 재방문이 강함",
        differentiation="익명 기록, 위기 대처, 가족 관점 가이드로 안전하게 운영",
        monetization="상담, 기록지, 프로그램, 도서/강의",
        repeat_reason="매일 기록과 재발 방지, 응원 글이 반복됨",
        difficulty="상",
        base_score=88.0,
        sustainability=10,
        monetization_score=7,
        competition_penalty=3,
    ),
    NicheRule(
        niche="브롬톤·접이식 자전거 오너",
        keyword="브롬톤",
        category="취미/장비",
        benchmark_cafes=("브롬톤 Bromptonia", "버디 자전거 클럽", "춘천 로드 벙개"),
        target_members="브롬톤·미니벨로 오너와 구매 예정자",
        growth_signal="브랜드 장비형 카페는 구매·튜닝·라이딩 글이 지속됨",
        differentiation="입문 구매, 튜닝, 중고 시세, 코스 인증을 결합",
        monetization="부품, 정비, 투어, 중고거래, 제휴",
        repeat_reason="튜닝, 정비, 시세, 라이딩 인증이 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=8,
        monetization_score=8,
        competition_penalty=4,
    ),
    NicheRule(
        niche="희귀식물·호야·알로카시아 키우기",
        keyword="호야 키우기",
        category="취미/식물",
        benchmark_cafes=("오늘의 호야", "빛나는 초록이들", "유실수와식물"),
        target_members="희귀식물·호야·알로카시아 입문자",
        growth_signal="작은 식물 니치가 경매·삽목·성장기록으로 활동 밀도 높음",
        differentiation="식물별 성장일지, 삽목 실패, 병충해, 분양 후기 특화",
        monetization="식물 분양, 화분/흙, 경매, 클래스",
        repeat_reason="성장 기록, 분양, 질문이 계절마다 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=9,
        monetization_score=8,
        competition_penalty=4,
    ),
    NicheRule(
        niche="심리상담사 자격·구인구직",
        keyword="심리상담사",
        category="전문직/교육",
        benchmark_cafes=("진격의 심리상담사들", "응급구조사 EMT", "영식이"),
        target_members="심리상담사 준비생과 현직자",
        growth_signal="직무형 커뮤니티는 자격증·취업·사례 질문이 꾸준함",
        differentiation="대학원, 자격증, 수련, 구인구직을 한곳에 묶음",
        monetization="강의, 교재, 채용광고, 슈퍼비전",
        repeat_reason="시험, 수련기관, 채용 정보가 반복됨",
        difficulty="중",
        base_score=87.0,
        sustainability=9,
        monetization_score=8,
        competition_penalty=4,
    ),
    NicheRule(
        niche="보험 리모델링·태아보험 상담",
        keyword="보험 리모델링",
        category="보험/금융",
        benchmark_cafes=("보험읽어주는카페", "보험하이킥", "보험 아지트"),
        target_members="보험 점검이 필요한 가족·예비부모",
        growth_signal="보험 세부 카페가 작은 단계에서도 상담 수요가 강함",
        differentiation="광고성 설계보다 보장분석 체크리스트와 사례 리뷰 중심",
        monetization="상담, 리드, 제휴, 비교표",
        repeat_reason="태아보험, 실손, 암보험, 리모델링 질문이 반복됨",
        difficulty="상",
        base_score=84.0,
        sustainability=8,
        monetization_score=10,
        competition_penalty=8,
    ),
    NicheRule(
        niche="소상공인 창업·폐업·지원금",
        keyword="소상공인 창업",
        category="창업/자영업",
        benchmark_cafes=("아프니까 사장이다", "창업잇다", "생생성공통"),
        target_members="소상공인·자영업자·예비창업자",
        growth_signal="지원금·마케팅·폐업까지 반복 문제를 가진 대형 시장",
        differentiation="업종별 체크리스트와 정부지원금 실전 신청 중심",
        monetization="교육, 광고, 세무, 마케팅, 제휴",
        repeat_reason="지원금, 매출, 세무, 알바, 폐업 질문이 계속 생김",
        difficulty="상",
        base_score=86.0,
        sustainability=9,
        monetization_score=10,
        competition_penalty=8,
    ),
    NicheRule(
        niche="노후준비·재취업·부업",
        keyword="노후준비",
        category="시니어/재테크",
        benchmark_cafes=("우아한 노후의 기술", "은퇴 후 새로운 도전", "은퇴 후 50년"),
        target_members="50대 이상 은퇴 준비자",
        growth_signal="시니어 니치는 멤버수는 작아도 지속성과 구매력이 있음",
        differentiation="돈, 건강, 일자리, 관계를 노후 생활 설계로 묶음",
        monetization="강의, 상담, 재취업, 보험, 금융 제휴",
        repeat_reason="연금, 일자리, 건강, 생활비 질문이 반복됨",
        difficulty="중",
        base_score=88.0,
        sustainability=10,
        monetization_score=9,
        competition_penalty=5,
    ),
    NicheRule(
        niche="수산물 유통·횟집 창업",
        keyword="수산물 유통",
        category="업종/창업",
        benchmark_cafes=("수산대", "농라", "식당레시피연구소"),
        target_members="수산물 유통·일식·횟집 창업자",
        growth_signal="업종 실무형 카페는 작은 규모에서도 정보 가치가 높음",
        differentiation="도매, 활어, 원가, 레시피, 창업 질문으로 좁힘",
        monetization="도매 연결, 교육, 장비, 창업 컨설팅",
        repeat_reason="시세, 거래처, 조리, 창업 질문이 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=9,
        monetization_score=9,
        competition_penalty=4,
    ),
    NicheRule(
        niche="키 작은 여성 패션 커뮤니티",
        keyword="키작은여자",
        category="패션/체형",
        benchmark_cafes=("키여모", "헤이든", "OFAD"),
        target_members="키 작은 여성과 체형별 쇼핑 고민자",
        growth_signal="정체성 기반 소형 카페가 공감과 구매 후기로 성장 가능",
        differentiation="체형별 핏 후기, 브랜드 추천, 중고거래를 결합",
        monetization="제휴, 공동구매, 체험단, 중고거래",
        repeat_reason="사이즈, 핏, 브랜드, 후기 글이 계속 생김",
        difficulty="중",
        base_score=84.0,
        sustainability=8,
        monetization_score=9,
        competition_penalty=5,
    ),
    NicheRule(
        niche="편의점 점주 운영 커뮤니티",
        keyword="편의점 창업",
        category="자영업/편의점",
        benchmark_cafes=("편장사", "아프니까 사장이다", "소자본창업지원센터"),
        target_members="편의점 점주와 창업 예정자",
        growth_signal="편의점 실무는 매일 운영 이슈가 쌓이는 반복형 니치",
        differentiation="발주, 알바, 폐기, 본사 정책, 매출 인증 중심",
        monetization="세무, 노무, POS, 보험, 창업 상담",
        repeat_reason="운영, 알바, 본사, 매출 고민이 매일 반복됨",
        difficulty="중",
        base_score=85.0,
        sustainability=9,
        monetization_score=9,
        competition_penalty=5,
    ),
    NicheRule(
        niche="소형 반려동물·햄스터 키우기",
        keyword="햄스터 키우기",
        category="반려동물",
        benchmark_cafes=("햄스터최고야", "댕냥살롱", "파사모"),
        target_members="햄스터·소동물 초보 집사",
        growth_signal="초보 질문과 사진 인증이 반복되는 작지만 선명한 니치",
        differentiation="사육환경, 병원, 먹이, 사진자랑을 초보자 중심으로 구성",
        monetization="용품, 사료, 병원, 제휴, 콘텐츠",
        repeat_reason="사육 질문, 건강, 사진, 용품 후기가 반복됨",
        difficulty="하",
        base_score=84.0,
        sustainability=8,
        monetization_score=7,
        competition_penalty=4,
    ),
    NicheRule(
        niche="지역 러닝크루·마라톤 입문",
        keyword="러닝크루",
        category="운동/모임",
        benchmark_cafes=("호매실 러닝크루", "무등산 트레일런", "한걸음산악회"),
        target_members="동네에서 같이 달릴 사람을 찾는 2030 입문자",
        growth_signal="소규모 지역 운동 모임이 오프라인 참여로 빠르게 결집",
        differentiation="지역별 모임, 초보 페이스, 장비 후기, 대회 준비로 좁힘",
        monetization="러닝화, 의류, 대회, 코칭, 모임 운영비",
        repeat_reason="코스, 모임 일정, 장비, 기록 인증이 반복됨",
        difficulty="중",
        base_score=85.0,
        sustainability=8,
        monetization_score=7,
        competition_penalty=3,
    ),
    NicheRule(
        niche="수영·프리다이빙 장비 후기",
        keyword="수영복 후기",
        category="운동/장비",
        benchmark_cafes=("물로그", "수영 코디카페", "여자혼자가는여행"),
        target_members="수영복·수경·프리다이빙 장비를 고르는 입문자",
        growth_signal="수영복과 물놀이 장비는 시즌성 검색과 후기 수요가 강함",
        differentiation="체형별 착용 후기, 브랜드 비교, 강습 후기 중심",
        monetization="장비 제휴, 공동구매, 강습, 여행상품",
        repeat_reason="사이즈, 착용감, 브랜드, 강습 질문이 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=8,
        monetization_score=9,
        competition_penalty=4,
    ),
    NicheRule(
        niche="지역 맘카페·학원·병원 생활정보",
        keyword="지역맘카페",
        category="지역/육아",
        benchmark_cafes=("부산맘", "파주 운정맘", "광주맘"),
        target_members="동네 육아·교육·병원 정보를 찾는 부모",
        growth_signal="지역 생활형 카페는 신규 택지와 학군 변화 때 계속 생김",
        differentiation="맘카페 운영자 관점으로 지역 정보판, 학원, 병원, 체험단 구성",
        monetization="지역 광고, 체험단, 공동구매, 학원/병원 제휴",
        repeat_reason="학원, 병원, 맛집, 행사, 중고거래 질문이 반복됨",
        difficulty="상",
        base_score=85.0,
        sustainability=10,
        monetization_score=9,
        competition_penalty=6,
    ),
    NicheRule(
        niche="혼자 여행·동행·여행친구",
        keyword="여자혼자여행",
        category="여행/모임",
        benchmark_cafes=("여혼여", "체크인유럽", "네일동"),
        target_members="혼자 여행을 준비하거나 동행을 찾는 여성 여행자",
        growth_signal="여행 동행과 후기형 카페는 계절마다 검색 수요가 반복",
        differentiation="안전, 동행, 숙소, 일정 공유, 후기 인증으로 특화",
        monetization="여행상품, 보험, 숙소, 투어, 제휴",
        repeat_reason="일정, 숙소, 동행, 안전 질문이 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=8,
        monetization_score=8,
        competition_penalty=5,
    ),
    NicheRule(
        niche="초보 백패킹·차박 장비",
        keyword="백패킹 장비",
        category="캠핑/장비",
        benchmark_cafes=("백패킹카페 캠백", "캠핑퍼스트", "차박과여행"),
        target_members="캠핑·백패킹·차박 입문자",
        growth_signal="장비 선택과 장소 후기가 반복되는 구매형 커뮤니티 니치",
        differentiation="초보 세팅, 장비 실패담, 계절별 코스, 중고거래 중심",
        monetization="장비 제휴, 공동구매, 캠핑장, 클래스",
        repeat_reason="장비 추천, 코스, 날씨, 중고 시세 질문이 반복됨",
        difficulty="중",
        base_score=87.0,
        sustainability=8,
        monetization_score=9,
        competition_penalty=5,
    ),
    NicheRule(
        niche="키덜트 피규어·3D프린팅 커스텀",
        keyword="피규어 커스텀",
        category="취미/제작",
        benchmark_cafes=("잡덕 메이커들의 커스텀 놀이터", "6인치 액션피규어", "보부상"),
        target_members="피규어 수집가와 3D프린팅 커스텀 입문자",
        growth_signal="굿즈·피규어·프린팅은 작은 커뮤니티에서도 거래와 제작 질문이 활발",
        differentiation="모델링, 출력, 도색, 거래, 제작 의뢰를 한곳에 묶음",
        monetization="프린팅, 도색 의뢰, 중고거래, 부품 판매",
        repeat_reason="제작 방법, 장비, 도색, 거래 글이 반복됨",
        difficulty="중",
        base_score=84.0,
        sustainability=8,
        monetization_score=8,
        competition_penalty=4,
    ),
    NicheRule(
        niche="신상 라면·간편식 후기",
        keyword="신상라면",
        category="생활/식품",
        benchmark_cafes=("식사로그", "비교의기술", "리얼리뷰 공유소"),
        target_members="신상 간편식과 라면 후기를 찾는 소비자",
        growth_signal="신제품이 계속 나와 반복 콘텐츠 생산이 쉬움",
        differentiation="신상컵라면, 냉동식품, 편의점 음식 리뷰로 좁힘",
        monetization="제휴, 체험단, 공동구매, 콘텐츠 광고",
        repeat_reason="신제품 후기, 맛 비교, 편의점 구매 인증이 반복됨",
        difficulty="하",
        base_score=82.0,
        sustainability=8,
        monetization_score=7,
        competition_penalty=4,
    ),
    NicheRule(
        niche="중년 싱글·돌싱 취미 모임",
        keyword="돌싱모임",
        category="4050/모임",
        benchmark_cafes=("굿바이싱글", "싱글즈 골프클럽", "온앤오프 카페온"),
        target_members="3040·4050 싱글, 미혼, 돌싱",
        growth_signal="관계·취미 기반 모임은 체류와 오프라인 전환이 강함",
        differentiation="골프, 등산, 맛집, 지역 모임처럼 안전한 취미 중심으로 운영",
        monetization="모임비, 제휴, 이벤트, 취미 클래스",
        repeat_reason="벙개, 정모, 후기, 동네친구 글이 반복됨",
        difficulty="상",
        base_score=83.0,
        sustainability=8,
        monetization_score=6,
        competition_penalty=5,
    ),
    NicheRule(
        niche="입주민 공동구매·하자 공유",
        keyword="입주민 공동구매",
        category="입주민/생활",
        benchmark_cafes=("인덕원 퍼스비엘 공동구매", "포레시안", "문현 롯데캐슬 인피니엘"),
        target_members="신축 아파트 입주민과 입주예정자",
        growth_signal="입주 시점마다 짧고 강한 공동구매·하자 공유 수요 발생",
        differentiation="단지별 카페보다 운영 템플릿, 업체 비교, 후기 DB 중심",
        monetization="줄눈, 탄성코트, 입주청소, 가전, 가구 공동구매",
        repeat_reason="하자, 공동구매, 입주 일정, 업체 후기 글이 반복됨",
        difficulty="중",
        base_score=88.0,
        sustainability=8,
        monetization_score=10,
        competition_penalty=4,
    ),
    NicheRule(
        niche="AI 도구·캔바 실무 교육",
        keyword="캔바 AI",
        category="AI/교육",
        benchmark_cafes=("캔바AI스쿨", "키엔엑스", "노트북 사용자들을 위한 IT카페"),
        target_members="소상공인, 강사, 블로거, 마케터",
        growth_signal="AI 도구는 신규 기능이 많아 질문과 튜토리얼 수요가 계속 발생",
        differentiation="캔바, 블로그, 카드뉴스, 상세페이지 제작 실무로 좁힘",
        monetization="강의, 템플릿, 구독 제휴, 컨설팅",
        repeat_reason="기능 사용법, 템플릿, 수익화, 오류 질문이 반복됨",
        difficulty="중",
        base_score=86.0,
        sustainability=8,
        monetization_score=9,
        competition_penalty=5,
    ),
)


def get_community_niches(
    session: Session,
    target_date: str,
    limit: int = DEFAULT_NICHE_LIMIT,
    sort_by: str = "practical",
) -> list[CommunityNiche]:
    volumes = load_search_volumes(session, target_date)
    documents = load_document_totals(session, target_date)
    kakao_documents = load_kakao_cafe_totals(session, target_date)
    shopping_documents = load_shopping_totals(session, target_date)
    niches = [
        build_niche(
            rule,
            volumes.get(rule.keyword),
            documents.get(rule.niche),
            kakao_documents.get(rule.keyword),
            shopping_documents.get(rule.keyword),
        )
        for rule in NICHE_RULES
    ]
    niches.extend(build_expanded_niches(volumes, documents, kakao_documents, shopping_documents))
    kin_questions = load_kin_questions(session, target_date)
    niches.extend(
        build_question_niches(
            volumes,
            documents,
            kakao_documents,
            shopping_documents,
            kin_questions,
        )
    )
    cafe_titles = load_cafe_titles(session, target_date)
    niches.extend(
        build_cafe_title_niches(
            volumes,
            documents,
            kakao_documents,
            shopping_documents,
            cafe_titles,
        )
    )
    niches = [niche for niche in niches if niche["monthly_total"] >= MIN_MONTHLY_SEARCH_VOLUME]
    niches = dedupe_niches(niches)
    if sort_by == "monthly_total":
        niches.sort(
            key=lambda niche: (niche["monthly_total"], niche["practical_score"]),
            reverse=True,
        )
    else:
        niches = limit_cluster_repetition(niches)
        niches.sort(
            key=lambda niche: (niche["practical_score"], niche["monthly_total"]),
            reverse=True,
        )
        niches = diversify_categories(niches, limit)
    return niches[:limit]


def get_accumulated_community_niches(
    session: Session,
    end_date: str,
    period_days: int,
    limit: int = DEFAULT_NICHE_LIMIT,
) -> list[AccumulatedNiche]:
    candidates_by_keyword: dict[str, list[CommunityNiche]] = {}
    active_dates = 0
    for target_date in get_period_dates(end_date, period_days):
        daily_niches = get_community_niches(session, target_date, sort_by="practical")
        if daily_niches:
            active_dates += 1
        for niche in daily_niches:
            candidates_by_keyword.setdefault(niche["keyword"], []).append(niche)

    scoring_days = max(1, active_dates)
    accumulated = [
        build_accumulated_niche(keyword, niches, period_days, scoring_days)
        for keyword, niches in candidates_by_keyword.items()
    ]
    accumulated.sort(
        key=lambda niche: (
            niche["cumulative_score"],
            niche["appeared_days"],
            niche["avg_monthly_total"],
        ),
        reverse=True,
    )
    return accumulated[:limit]


def get_period_dates(end_date: str, period_days: int) -> list[str]:
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    start = end - timedelta(days=period_days - 1)
    return [
        (start + timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in range(period_days)
    ]


def build_accumulated_niche(
    keyword: str,
    niches: list[CommunityNiche],
    period_days: int,
    scoring_days: int,
) -> AccumulatedNiche:
    appeared_days = len(niches)
    representative = max(niches, key=lambda niche: niche["practical_score"])
    avg_practical = average_float([niche["practical_score"] for niche in niches])
    max_practical = max(niche["practical_score"] for niche in niches)
    avg_monthly_total = average_int([niche["monthly_total"] for niche in niches])
    avg_cafe_total = average_int([niche["cafe_total"] for niche in niches])
    avg_kin_total = average_int([niche["kin_total"] for niche in niches])
    avg_kakao_total = average_int([niche["kakao_cafe_total"] for niche in niches])
    avg_shopping_total = average_int([niche["shopping_total"] for niche in niches])
    cumulative_score = calculate_cumulative_score(
        avg_practical,
        max_practical,
        appeared_days,
        scoring_days,
        avg_monthly_total,
        avg_cafe_total,
        avg_kin_total,
    )
    return {
        "niche": representative["niche"],
        "keyword": keyword,
        "category": representative["category"],
        "period_days": period_days,
        "appeared_days": appeared_days,
        "avg_monthly_total": avg_monthly_total,
        "max_practical_score": round(max_practical, 1),
        "avg_practical_score": round(avg_practical, 1),
        "avg_cafe_total": avg_cafe_total,
        "avg_kin_total": avg_kin_total,
        "avg_kakao_cafe_total": avg_kakao_total,
        "avg_shopping_total": avg_shopping_total,
        "saturation": representative["saturation"],
        "cumulative_score": cumulative_score,
        "judgment": get_accumulated_judgment(appeared_days, scoring_days, avg_monthly_total),
        "reason": get_accumulated_reason(
            appeared_days,
            scoring_days,
            avg_monthly_total,
            avg_kin_total,
            avg_cafe_total,
        ),
    }


def calculate_cumulative_score(
    avg_practical: float,
    max_practical: float,
    appeared_days: int,
    period_days: int,
    avg_monthly_total: int,
    avg_cafe_total: int,
    avg_kin_total: int,
) -> float:
    persistence_score = (appeared_days / period_days) * 28.0
    search_score = min(16.0, log10(avg_monthly_total + 1) * 3.2)
    question_score = min(10.0, log10(avg_kin_total + 1) * 2.2)
    saturation_penalty = 10.0 if avg_cafe_total >= HIGH_CAFE_DOCUMENT_THRESHOLD else 0.0
    score = avg_practical * 0.55 + max_practical * 0.2
    score += persistence_score + search_score + question_score - saturation_penalty
    return round(max(0.0, score), 1)


def get_accumulated_judgment(
    appeared_days: int,
    period_days: int,
    avg_monthly_total: int,
) -> str:
    if appeared_days >= max(3, period_days // 3):
        return "장기운영형"
    if appeared_days >= 2:
        return "안정성장형"
    if avg_monthly_total >= 2_000:
        return "급상승형"
    return "관찰필요"


def get_accumulated_reason(
    appeared_days: int,
    period_days: int,
    avg_monthly_total: int,
    avg_kin_total: int,
    avg_cafe_total: int,
) -> str:
    if appeared_days >= max(3, period_days // 3):
        return "기간 내 반복 등장해 일회성 노이즈 가능성이 낮음"
    if avg_kin_total >= QUESTION_SIGNAL_THRESHOLD and avg_cafe_total < HIGH_CAFE_DOCUMENT_THRESHOLD:
        return "질문 수요가 있고 카페 공급이 과하지 않음"
    if avg_monthly_total >= 2_000:
        return "검색량 기준으로 우선 관찰할 만함"
    return "누적 데이터가 더 쌓이면 재판단 필요"


def average_int(values: list[int]) -> int:
    return round(sum(values) / len(values)) if values else 0


def average_float(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def dedupe_niches(niches: list[CommunityNiche]) -> list[CommunityNiche]:
    best_by_keyword: dict[str, CommunityNiche] = {}
    for niche in niches:
        key = normalize_candidate_key(niche["keyword"])
        existing = best_by_keyword.get(key)
        if existing is None or niche["recommendation_score"] > existing["recommendation_score"]:
            best_by_keyword[key] = niche
    return list(best_by_keyword.values())


def limit_cluster_repetition(niches: list[CommunityNiche]) -> list[CommunityNiche]:
    sorted_niches = sorted(
        niches,
        key=lambda niche: (niche["practical_score"], niche["monthly_total"]),
        reverse=True,
    )
    selected: list[CommunityNiche] = []
    cluster_counts: dict[str, int] = {}
    for niche in sorted_niches:
        cluster_key = niche["cluster_key"]
        count = cluster_counts.get(cluster_key, 0)
        if count >= CLUSTER_DISPLAY_LIMIT:
            continue
        cluster_counts[cluster_key] = count + 1
        selected.append(niche)
    return selected


def diversify_categories(niches: list[CommunityNiche], limit: int) -> list[CommunityNiche]:
    grouped: dict[str, list[CommunityNiche]] = {}
    for niche in niches:
        grouped.setdefault(niche["category"], []).append(niche)

    for category_niches in grouped.values():
        category_niches.sort(
            key=lambda niche: (niche["practical_score"], niche["monthly_total"]),
            reverse=True,
        )

    selected: list[CommunityNiche] = []
    previous_category = ""
    category_counts: dict[str, int] = {}
    while grouped and len(selected) < limit:
        category = pick_next_category(
            grouped,
            previous_category,
            category_counts,
            len(selected),
        )
        next_niche = grouped[category].pop(0)
        selected.append(next_niche)
        previous_category = category
        category_counts[category] = category_counts.get(category, 0) + 1
        if not grouped[category]:
            del grouped[category]

    return selected


def pick_next_category(
    grouped: dict[str, list[CommunityNiche]],
    previous_category: str,
    category_counts: dict[str, int],
    selected_count: int,
) -> str:
    categories = sorted(
        grouped,
        key=lambda category: (
            grouped[category][0]["practical_score"],
            grouped[category][0]["monthly_total"],
        ),
        reverse=True,
    )
    allowed_categories = [
        category
        for category in categories
        if is_category_under_soft_cap(category, category_counts, selected_count)
    ]
    if not allowed_categories:
        allowed_categories = categories
    if len(allowed_categories) == 1 or allowed_categories[0] != previous_category:
        return allowed_categories[0]
    return allowed_categories[1]


def is_category_under_soft_cap(
    category: str,
    category_counts: dict[str, int],
    selected_count: int,
) -> bool:
    max_count = max(2, int((selected_count + 1) * MAX_CATEGORY_TOP_SHARE))
    return category_counts.get(category, 0) < max_count


def build_expanded_niches(
    volumes: dict[str, KeywordSearchVolume],
    documents: dict[str, NaverDocumentTotals],
    kakao_documents: dict[str, int],
    shopping_documents: dict[str, int],
) -> list[CommunityNiche]:
    rule_keywords = {rule.keyword for rule in NICHE_RULES}
    normalized_rule_keywords = {normalize_candidate_key(keyword) for keyword in rule_keywords}
    expanded: list[CommunityNiche] = []
    for volume in volumes.values():
        keyword = volume.keyword.strip()
        if keyword in rule_keywords:
            continue
        if normalize_candidate_key(keyword) in normalized_rule_keywords:
            continue
        if not is_usable_expanded_keyword(keyword, volume.monthly_total):
            continue
        rule = build_expanded_rule(keyword)
        expanded.append(
            build_niche(
                rule,
                volume,
                documents.get(keyword),
                kakao_documents.get(keyword),
                shopping_documents.get(keyword),
            )
        )
    return expanded


def build_question_niches(
    volumes: dict[str, KeywordSearchVolume],
    documents: dict[str, NaverDocumentTotals],
    kakao_documents: dict[str, int],
    shopping_documents: dict[str, int],
    questions_by_keyword: dict[str, list[str]],
) -> list[CommunityNiche]:
    existing_keys = {normalize_candidate_key(rule.keyword) for rule in NICHE_RULES}
    question_niches: list[CommunityNiche] = []
    for keyword, questions in questions_by_keyword.items():
        volume = volumes.get(keyword)
        monthly_total = volume.monthly_total if volume else 0
        if normalize_candidate_key(keyword) in existing_keys:
            continue
        if monthly_total < MIN_QUESTION_MONTHLY_SEARCH_VOLUME:
            continue
        if not is_question_based_candidate(keyword, questions):
            continue
        rule = build_question_rule(keyword, questions)
        question_niches.append(
            build_niche(
                rule,
                volume,
                documents.get(keyword),
                kakao_documents.get(keyword),
                shopping_documents.get(keyword),
            )
        )
    return question_niches


def build_cafe_title_niches(
    volumes: dict[str, KeywordSearchVolume],
    documents: dict[str, NaverDocumentTotals],
    kakao_documents: dict[str, int],
    shopping_documents: dict[str, int],
    titles_by_keyword: dict[str, list[str]],
) -> list[CommunityNiche]:
    existing_keys = {normalize_candidate_key(rule.keyword) for rule in NICHE_RULES}
    cafe_niches: list[CommunityNiche] = []
    for keyword, titles in titles_by_keyword.items():
        volume = volumes.get(keyword)
        monthly_total = volume.monthly_total if volume else 0
        if normalize_candidate_key(keyword) in existing_keys:
            continue
        if monthly_total < MIN_QUESTION_MONTHLY_SEARCH_VOLUME:
            continue
        if not is_cafe_title_candidate(keyword, titles):
            continue
        rule = build_cafe_title_rule(keyword, titles)
        cafe_niches.append(
            build_niche(
                rule,
                volume,
                documents.get(keyword),
                kakao_documents.get(keyword),
                shopping_documents.get(keyword),
            )
        )
    return cafe_niches


def is_cafe_title_candidate(keyword: str, titles: list[str]) -> bool:
    if not titles:
        return False
    compact = keyword.replace(" ", "")
    if any(term in compact for term in LOW_VALUE_EXPANDED_TERMS):
        return False
    joined = " ".join(titles)
    return any(term in joined for term in CAFE_TITLE_SIGNAL_TERMS)


def is_question_based_candidate(keyword: str, questions: list[str]) -> bool:
    if not questions:
        return False
    joined = " ".join(questions)
    if any(term in keyword for term in LOW_VALUE_EXPANDED_TERMS):
        return False
    if any(term in joined for term in ("어떻게", "왜", "가능", "괜찮", "문의", "질문")):
        return True
    return any(term in keyword for term in COMMUNITY_INTENT_TERMS)


def build_question_rule(keyword: str, questions: list[str]) -> NicheRule:
    return NicheRule(
        niche=format_question_niche(keyword, questions),
        keyword=keyword,
        category=infer_expanded_category(keyword),
        benchmark_cafes=(),
        target_members="지식iN에서 반복 질문을 남기는 검색 사용자",
        growth_signal="지식iN 샘플 질문에서 커뮤니티형 문제 확인",
        differentiation=get_question_direction(keyword, questions),
        monetization="",
        repeat_reason=get_question_topic_reason(questions),
        difficulty="중",
        base_score=82.0,
        sustainability=9,
        monetization_score=0,
        competition_penalty=3,
    )


def build_cafe_title_rule(keyword: str, titles: list[str]) -> NicheRule:
    return NicheRule(
        niche=format_cafe_title_niche(keyword, titles),
        keyword=keyword,
        category=infer_expanded_category(keyword),
        benchmark_cafes=(),
        target_members="네이버 카페글에서 반복 활동을 보이는 검색 사용자",
        growth_signal="네이버 카페글 샘플 제목에서 활동 패턴 확인",
        differentiation=get_cafe_title_direction(keyword, titles),
        monetization="",
        repeat_reason=get_cafe_title_topic_reason(titles),
        difficulty="중",
        base_score=84.0,
        sustainability=9,
        monetization_score=0,
        competition_penalty=3,
    )


def format_question_niche(keyword: str, questions: list[str]) -> str:
    if any(term in keyword for term in ("관리", "식단", "운영", "창업", "키우기", "입문")):
        return keyword
    if any("후기" in question for question in questions):
        return f"{keyword} 후기·질문"
    return f"{keyword} 질문·경험"


def format_cafe_title_niche(keyword: str, titles: list[str]) -> str:
    if any("후기" in title for title in titles):
        return f"{keyword} 후기·정보"
    if any(term in " ".join(titles) for term in ("모임", "인증", "공유")):
        return f"{keyword} 경험공유"
    return f"{keyword} 카페 주제"


def get_question_direction(keyword: str, questions: list[str]) -> str:
    sample = questions[0] if questions else keyword
    return f"지식iN 질문 예시: {sample}"


def get_question_topic_reason(questions: list[str]) -> str:
    if any("어떻게" in question for question in questions):
        return "방법을 묻는 질문이 반복되어 경험 공유 주제로 확장 가능"
    if any("가능" in question for question in questions):
        return "가능 여부와 사례 질문이 반복됨"
    if any("후기" in question for question in questions):
        return "후기 확인 수요가 반복됨"
    return "지식iN 질문이 반복되어 커뮤니티형 주제로 검토 가능"


def get_cafe_title_direction(keyword: str, titles: list[str]) -> str:
    sample = titles[0] if titles else keyword
    return f"카페글 예시: {sample}"


def get_cafe_title_topic_reason(titles: list[str]) -> str:
    joined = " ".join(titles)
    if any(term in joined for term in ("후기", "인증")):
        return "후기와 인증 글이 반복되어 커뮤니티형 주제로 적합"
    if any(term in joined for term in ("질문", "문의")):
        return "질문과 답변 글이 반복되어 커뮤니티형 주제로 적합"
    if any(term in joined for term in ("모임", "공유", "나눔")):
        return "모임·공유형 글이 보여 커뮤니티 주제로 검토 가능"
    return "카페글 샘플에서 반복 활동 신호가 확인됨"


def is_usable_expanded_keyword(keyword: str, monthly_total: int) -> bool:
    compact = keyword.replace(" ", "")
    if monthly_total < MIN_EXPANDED_MONTHLY_SEARCH_VOLUME:
        return False
    if len(compact) < 4:
        return False
    if compact.isdigit():
        return False
    if any(term in compact for term in LOW_VALUE_EXPANDED_TERMS):
        return False
    return any(term in keyword for term in COMMUNITY_INTENT_TERMS)


def normalize_candidate_key(keyword: str) -> str:
    return keyword.replace(" ", "").lower()


def build_expanded_rule(keyword: str) -> NicheRule:
    return NicheRule(
        niche=format_expanded_niche(keyword),
        keyword=keyword,
        category=infer_expanded_category(keyword),
        benchmark_cafes=(),
        target_members="반복 질문이 있는 세부 검색 사용자",
        growth_signal="검색광고 연관키워드에서 확장 발견",
        differentiation=get_expanded_direction(keyword),
        monetization="",
        repeat_reason=get_expanded_topic_reason(keyword),
        difficulty="중",
        base_score=78.0,
        sustainability=8,
        monetization_score=0,
        competition_penalty=3,
    )


def format_expanded_niche(keyword: str) -> str:
    if any(term in keyword for term in ("키우기", "창업", "운영", "관리", "자격")):
        return keyword
    return f"{keyword} 정보·후기"


def infer_expanded_category(keyword: str) -> str:
    if any(term in keyword for term in ("혈당", "식단", "건강", "재활", "금주")):
        return "건강"
    if any(term in keyword for term in ("창업", "운영", "세금", "신고")):
        return "사업/실무"
    if any(term in keyword for term in ("키우기", "식물", "호야", "햄스터")):
        return "취미/반려"
    if any(term in keyword for term in ("자격", "공부", "구인", "구직")):
        return "교육/직무"
    return "세부키워드"


def get_expanded_direction(keyword: str) -> str:
    if any(term in keyword for term in ("가격", "비용", "추천")):
        return "단순 비교보다 실제 경험·후기 중심으로 세분화 필요"
    if any(term in keyword for term in ("식단", "혈당", "관리")):
        return "매일 기록·질문이 가능한 관리형 주제로 검토"
    if any(term in keyword for term in ("창업", "운영", "세금", "신고")):
        return "실무 체크리스트와 사례 중심 주제로 검토"
    return "질문·후기·경험 공유가 반복되는지 검토"


def get_expanded_topic_reason(keyword: str) -> str:
    if any(term in keyword for term in ("식단", "혈당", "관리")):
        return "개인 상황별 질문과 기록이 반복됨"
    if any(term in keyword for term in ("창업", "운영", "세금", "신고")):
        return "실무 문제와 사례 질문이 반복됨"
    if any(term in keyword for term in ("키우기", "장비", "입문")):
        return "초보 질문과 후기 공유가 반복됨"
    return "검색 수요가 있는 세부 질문으로 확장 가능"


def build_niche(
    rule: NicheRule,
    volume: KeywordSearchVolume | None,
    documents: NaverDocumentTotals | None,
    kakao_cafe_total: int | None,
    shopping_total: int | None,
) -> CommunityNiche:
    monthly_total = volume.monthly_total if volume else 0
    monthly_pc = volume.monthly_pc if volume else 0
    monthly_mobile = volume.monthly_mobile if volume else 0
    competition = volume.competition if volume else ""
    cafe_total = get_document_total(documents, "cafearticle")
    blog_total = get_document_total(documents, "blog")
    kin_total = get_document_total(documents, "kin")
    news_total = get_document_total(documents, "news")
    kakao_total = kakao_cafe_total or 0
    shop_total = shopping_total or 0
    return {
        "niche": rule.niche,
        "keyword": rule.keyword,
        "monthly_total": monthly_total,
        "monthly_pc": monthly_pc,
        "monthly_mobile": monthly_mobile,
        "search_competition": competition,
        "cafe_total": cafe_total,
        "blog_total": blog_total,
        "kin_total": kin_total,
        "news_total": news_total,
        "kakao_cafe_total": kakao_total,
        "shopping_total": shop_total,
        "saturation": get_saturation_label(cafe_total, blog_total),
        "opportunity_label": get_opportunity_label(monthly_total, cafe_total, kin_total),
        "supply_gap_score": calculate_supply_gap_score(
            monthly_total,
            cafe_total,
            blog_total,
            kin_total,
        ),
        "community_fit_label": get_community_fit_label(rule, kin_total, cafe_total),
        "risk_label": get_risk_label(rule),
        "keyword_scope": get_keyword_scope(rule.keyword, monthly_total, cafe_total, blog_total),
        "topic_reason": rule.repeat_reason,
        "benchmark_cafes": ", ".join(rule.benchmark_cafes),
        "target_members": rule.target_members,
        "category": rule.category,
        "growth_signal": rule.growth_signal,
        "differentiation": rule.differentiation,
        "monetization": rule.monetization,
        "repeat_reason": rule.repeat_reason,
        "difficulty": rule.difficulty,
        "recommendation_score": calculate_niche_score(
            rule,
            monthly_total,
            competition,
            cafe_total,
            blog_total,
            kin_total,
            news_total,
            kakao_total,
            shop_total,
        ),
        "practical_score": calculate_practical_score(
            rule,
            monthly_total,
            competition,
            cafe_total,
            blog_total,
            kin_total,
            news_total,
            kakao_total,
            shop_total,
        ),
        "cluster_key": get_cluster_key(rule.keyword),
    }


def load_search_volumes(
    session: Session,
    target_date: str,
) -> dict[str, KeywordSearchVolume]:
    statement = select(KeywordSearchVolume).where(KeywordSearchVolume.date == target_date)
    return {volume.keyword: volume for volume in session.exec(statement)}


def load_document_totals(
    session: Session,
    target_date: str,
) -> dict[str, NaverDocumentTotals]:
    statement = select(TopicSignal).where(TopicSignal.date == target_date)
    totals: dict[str, NaverDocumentTotals] = {}
    for signal in session.exec(statement):
        if signal.topic not in totals:
            totals[signal.topic] = {"cafearticle": 0, "blog": 0, "kin": 0, "news": 0}
        if signal.service in totals[signal.topic]:
            totals[signal.topic][signal.service] = signal.total
    return totals


def load_kakao_cafe_totals(
    session: Session,
    target_date: str,
) -> dict[str, int]:
    statement = select(TopicSignal).where(
        TopicSignal.date == target_date,
        TopicSignal.service == "kakao_cafe",
    )
    return {signal.topic: signal.total for signal in session.exec(statement)}


def load_shopping_totals(
    session: Session,
    target_date: str,
) -> dict[str, int]:
    statement = select(TopicSignal).where(
        TopicSignal.date == target_date,
        TopicSignal.service == "shop",
    )
    return {signal.topic: signal.total for signal in session.exec(statement)}


def load_kin_questions(
    session: Session,
    target_date: str,
) -> dict[str, list[str]]:
    statement = select(TopicSignal).where(
        TopicSignal.date == target_date,
        TopicSignal.service == "kin",
    )
    questions: dict[str, list[str]] = {}
    for signal in session.exec(statement):
        titles = parse_sample_titles(signal.sample_titles)
        if titles:
            questions.setdefault(signal.query, []).extend(titles)
    return questions


def load_cafe_titles(
    session: Session,
    target_date: str,
) -> dict[str, list[str]]:
    statement = select(TopicSignal).where(
        TopicSignal.date == target_date,
        TopicSignal.service == "cafearticle",
    )
    titles_by_keyword: dict[str, list[str]] = {}
    for signal in session.exec(statement):
        titles = parse_sample_titles(signal.sample_titles)
        if titles:
            titles_by_keyword.setdefault(signal.query, []).extend(titles)
    return titles_by_keyword


def parse_sample_titles(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def get_document_total(documents: NaverDocumentTotals | None, service: str) -> int:
    if documents is None:
        return 0
    return documents.get(service, 0)


def calculate_niche_score(
    rule: NicheRule,
    monthly_total: int,
    competition: str,
    cafe_total: int,
    blog_total: int,
    kin_total: int,
    news_total: int,
    kakao_cafe_total: int,
    shopping_total: int,
) -> float:
    score = rule.base_score
    supply_gap_score = calculate_supply_gap_score(monthly_total, cafe_total, blog_total, kin_total)
    score += rule.sustainability * 2.8
    score += get_specificity_bonus(rule.keyword, rule.niche)
    score += supply_gap_score * 0.35
    score -= rule.competition_penalty * 1.8
    score -= get_risk_penalty(rule)
    score -= get_scope_penalty(rule.keyword, monthly_total, cafe_total, blog_total)
    score += get_search_volume_bonus(monthly_total)
    score += get_competition_bonus(competition)
    score += get_document_opportunity_bonus(
        cafe_total,
        blog_total,
        kin_total,
        news_total,
        kakao_cafe_total,
        shopping_total,
    )
    return round(score, 1)


def calculate_practical_score(
    rule: NicheRule,
    monthly_total: int,
    competition: str,
    cafe_total: int,
    blog_total: int,
    kin_total: int,
    news_total: int,
    kakao_cafe_total: int,
    shopping_total: int,
) -> float:
    score = calculate_niche_score(
        rule,
        monthly_total,
        competition,
        cafe_total,
        blog_total,
        kin_total,
        news_total,
        kakao_cafe_total,
        shopping_total,
    )
    score += calculate_supply_gap_score(monthly_total, cafe_total, blog_total, kin_total) * 0.45
    score += get_practical_search_volume_score(monthly_total)
    score += get_practical_document_score(
        cafe_total,
        blog_total,
        kin_total,
        news_total,
        kakao_cafe_total,
        shopping_total,
    )
    score += get_cluster_specificity_bonus(rule.keyword)
    score -= get_practical_risk_penalty(rule, cafe_total, blog_total)
    return round(max(0.0, score), 1)


def get_practical_search_volume_score(monthly_total: int) -> float:
    if monthly_total < 500:
        return -6.0
    if monthly_total < 2_000:
        return 3.0
    if monthly_total < 20_000:
        return 10.0
    if monthly_total < 100_000:
        return 6.0
    return -4.0


def get_practical_document_score(
    cafe_total: int,
    blog_total: int,
    kin_total: int,
    news_total: int,
    kakao_cafe_total: int,
    shopping_total: int,
) -> float:
    score = 0.0
    if 0 < cafe_total < LOW_CAFE_DOCUMENT_THRESHOLD:
        score += 14.0
    elif cafe_total < PRACTICAL_CAFE_SOFT_CAP:
        score += 5.0
    else:
        score -= 18.0

    if blog_total > PRACTICAL_BLOG_SOFT_CAP:
        score -= 12.0
    elif blog_total > 0:
        score += 3.0

    if kin_total >= QUESTION_SIGNAL_THRESHOLD:
        score += 10.0
    elif kin_total > 0:
        score += 4.0

    if 0 < kakao_cafe_total < LOW_CAFE_DOCUMENT_THRESHOLD:
        score += 7.0
    elif kakao_cafe_total < HIGH_KAKAO_CAFE_DOCUMENT_THRESHOLD:
        score += 2.0
    else:
        score -= 8.0

    if 0 < shopping_total < HIGH_SHOPPING_DOCUMENT_THRESHOLD:
        score += 4.0
    elif shopping_total >= HIGH_SHOPPING_DOCUMENT_THRESHOLD:
        score -= 4.0

    if news_total > cafe_total + blog_total:
        score -= 8.0
    return score


def get_cluster_specificity_bonus(keyword: str) -> float:
    compact = keyword.replace(" ", "")
    if len(compact) >= 8:
        return 8.0
    if len(compact) >= 5:
        return 4.0
    return -3.0


def get_practical_risk_penalty(rule: NicheRule, cafe_total: int, blog_total: int) -> float:
    penalty = 0.0
    if get_risk_label(rule) == "높음":
        penalty += 25.0
    elif get_risk_label(rule) == "중간":
        penalty += 8.0
    if cafe_total >= HIGH_CAFE_DOCUMENT_THRESHOLD:
        penalty += 12.0
    if blog_total >= HIGH_BLOG_DOCUMENT_THRESHOLD:
        penalty += 8.0
    return penalty


def get_search_volume_bonus(monthly_total: int) -> float:
    if monthly_total <= 0:
        return -40.0
    if monthly_total < 500:
        return 1.0
    if monthly_total < 2_000:
        return 4.0
    if monthly_total < 10_000:
        return 7.0
    if monthly_total < 100_000:
        return 9.0
    return 6.0


def get_competition_bonus(competition: str) -> float:
    if competition == "낮음":
        return 3.0
    if competition == "높음":
        return -3.0
    return 0.0


def get_document_opportunity_bonus(
    cafe_total: int,
    blog_total: int,
    kin_total: int,
    news_total: int,
    kakao_cafe_total: int,
    shopping_total: int,
) -> float:
    score = 0.0
    if 0 < cafe_total < LOW_CAFE_DOCUMENT_THRESHOLD:
        score += 6.0
    elif cafe_total < HIGH_CAFE_DOCUMENT_THRESHOLD:
        score += 3.0
    else:
        score -= 6.0

    if blog_total > HIGH_BLOG_DOCUMENT_THRESHOLD:
        score -= 5.0
    elif blog_total > 0:
        score += 2.0

    if kin_total >= QUESTION_SIGNAL_THRESHOLD:
        score += 4.0
    elif kin_total > 0:
        score += 2.0

    if 0 < kakao_cafe_total < LOW_CAFE_DOCUMENT_THRESHOLD:
        score += 4.0
    elif kakao_cafe_total >= HIGH_KAKAO_CAFE_DOCUMENT_THRESHOLD:
        score -= 4.0

    if 0 < shopping_total < HIGH_SHOPPING_DOCUMENT_THRESHOLD:
        score += 2.0
    elif shopping_total >= HIGH_SHOPPING_DOCUMENT_THRESHOLD:
        score -= 2.0

    if news_total > blog_total and news_total > cafe_total:
        score -= 3.0
    return score


def calculate_supply_gap_score(
    monthly_total: int,
    cafe_total: int,
    blog_total: int,
    kin_total: int,
) -> float:
    demand_score = min(42.0, log10(monthly_total + 1) * 8.0)
    question_score = min(18.0, log10(kin_total + 1) * 3.2)
    supply_penalty = min(42.0, log10(cafe_total + blog_total * 0.45 + 1) * 6.2)
    score = 42.0 + demand_score + question_score - supply_penalty
    return round(max(0.0, min(100.0, score)), 1)


def get_specificity_bonus(keyword: str, niche: str) -> float:
    score = 0.0
    if len(keyword.replace(" ", "")) >= 5:
        score += 4.0
    if any(marker in niche for marker in ("후기", "관리", "운영", "키우기", "입문", "자격")):
        score += 5.0
    if len(niche) >= 10:
        score += 3.0
    return score


def get_risk_label(rule: NicheRule) -> str:
    text = f"{rule.niche} {rule.keyword} {rule.category}"
    if any(term in text for term in HIGH_RISK_TERMS):
        return "높음"
    if any(term in text for term in MEDIUM_RISK_TERMS):
        return "중간"
    return "낮음"


def get_risk_penalty(rule: NicheRule) -> float:
    risk_label = get_risk_label(rule)
    if risk_label == "높음":
        return 18.0
    if risk_label == "중간":
        return 7.0
    return 0.0


def get_community_fit_label(rule: NicheRule, kin_total: int, cafe_total: int) -> str:
    if rule.sustainability >= 9 and kin_total >= QUESTION_SIGNAL_THRESHOLD:
        return "강함"
    if rule.sustainability >= 8 and cafe_total > 0:
        return "보통"
    return "약함"


def get_keyword_scope(
    keyword: str,
    monthly_total: int,
    cafe_total: int,
    blog_total: int,
) -> str:
    if monthly_total >= HIGH_SEARCH_VOLUME_THRESHOLD or cafe_total >= HIGH_CAFE_DOCUMENT_THRESHOLD:
        return "넓음"
    if " " in keyword or len(keyword.replace(" ", "")) >= 5:
        return "세부"
    if blog_total >= HIGH_BLOG_DOCUMENT_THRESHOLD:
        return "넓음"
    return "보통"


def get_scope_penalty(
    keyword: str,
    monthly_total: int,
    cafe_total: int,
    blog_total: int,
) -> float:
    scope = get_keyword_scope(keyword, monthly_total, cafe_total, blog_total)
    if scope == "넓음":
        return 12.0
    if scope == "보통":
        return 3.0
    return 0.0


def get_saturation_label(cafe_total: int, blog_total: int) -> str:
    if cafe_total >= HIGH_CAFE_DOCUMENT_THRESHOLD or blog_total >= HIGH_BLOG_DOCUMENT_THRESHOLD:
        return "높음"
    if cafe_total >= LOW_CAFE_DOCUMENT_THRESHOLD:
        return "중간"
    if cafe_total > 0 or blog_total > 0:
        return "낮음"
    return "미수집"


def get_opportunity_label(monthly_total: int, cafe_total: int, kin_total: int) -> str:
    if cafe_total == 0 and kin_total == 0:
        return "문서수 미수집"
    if monthly_total >= 2_000 and cafe_total < LOW_CAFE_DOCUMENT_THRESHOLD:
        return "수요 대비 카페 공급 적음"
    if kin_total >= QUESTION_SIGNAL_THRESHOLD and cafe_total < HIGH_CAFE_DOCUMENT_THRESHOLD:
        return "질문 수요 강함"
    if cafe_total >= HIGH_CAFE_DOCUMENT_THRESHOLD:
        return "기존 카페 경쟁 높음"
    return "검토 가능"


def get_cluster_key(keyword: str) -> str:
    compact = normalize_candidate_key(keyword)
    compact = compact.replace("5월", "")
    replacements = (
        ("종소세", "종합소득세"),
        ("신고기간", "신고"),
        ("신고방법", "신고"),
        ("취득방법", "자격증"),
        ("자격증조회", "자격증"),
        ("2급", ""),
        ("1급", ""),
    )
    for source, target in replacements:
        compact = compact.replace(source, target)
    suffixes = ("기간", "방법", "조회", "시험", "자격", "후기", "정보", "카페")
    for suffix in suffixes:
        compact = compact.replace(suffix, "")
    return compact[:8] if len(compact) >= 8 else compact
