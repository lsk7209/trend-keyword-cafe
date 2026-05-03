# Status | 마지막: 2026-05-04
## 현재 작업
Vercel Python 엔트리포인트 추가 완료
## 최근 변경 (최근 5개만)
- 05-04: Vercel 빌드용 루트 app.py WSGI 상태 페이지 추가
- 05-04: TrendKeywordCafeDaily 작업 스케줄러 등록, 매일 06:30 실행
- 05-04: scripts/run_daily_pipeline.ps1 추가, 실행 로그 logs/daily_pipeline.log 저장
- 05-03: 대시보드에서 타입 전용 AccumulatedNiche 런타임 import 제거
- 05-03: 러닝·수영·지역맘카페·여행·백패킹·피규어·간편식 등 seed 10개 추가
## TODO
- [ ] Reddit OAuth 키 확보 시 Reddit 커뮤니티 질문/후기 신호 추가
- [ ] Stack Exchange Q&A형 니치 신호 추가 검토
- [ ] 네이버 카페 랭킹 스냅샷 자동 수집 검토
## 결정사항
- 기본 출력: 일반 뉴스 키워드보다 반복 질문, 후기, 거래, 상담이 생기는 커뮤니티 니치 우선
- 후보 수: 실전후보순 82개, 월검색량순 85개
- Kakao/Daum 카페 신호는 정확한 전체 문서수보다 카페형 존재/활동 보조 신호로 사용
- 네이버 쇼핑 신호는 제품·장비·후기·공구형 주제의 보조 신호로 사용
- 실전후보순은 같은 카테고리가 상위권을 과점하지 않도록 40% 소프트 캡 적용
- SearchAd 확장은 니치 규칙 관련어 1회 + 2단 seed 관련어 1회 구조로 유지
- 누적 탭은 보유 데이터 날짜만 기준으로 점수 보정, 매일 쌓이면 자동으로 7일/30일화
- seed는 교육/자격증 쏠림 완화를 위해 취미·지역·육아·운동·여행·생활형 주제를 계속 보강
- 대시보드 타입 힌트는 런타임 import 오류를 피하기 위해 Mapping 기반으로 처리
- 자동 수집: Windows 작업 스케줄러 TrendKeywordCafeDaily, 매일 06:30, LastTaskResult 0 확인
- Vercel: Streamlit 직접 실행이 아니라 WSGI 상태 페이지로 빌드 엔트리포인트 제공
- 검증: 파이프라인, ruff/mypy/compileall, Streamlit AppTest, localhost 200 확인
## 주의
- Streamlit: http://localhost:8501
- 자동 수집 로그: logs/daily_pipeline.log
- 첫 실행 시 KeyBERT/SentenceTransformer 모델 다운로드로 시간이 걸릴 수 있음
