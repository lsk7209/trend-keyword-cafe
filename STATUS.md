# Status | 마지막: 2026-05-04
## 현재 작업
Vercel JSON 라우팅 오류 수정 완료
## 최근 변경 (최근 5개만)
- 05-04: /data/* 라우트를 public/data 정적 파일로 직접 연결
- 05-04: run_daily_pipeline.ps1에 summary.json 변경 시 git commit/push 자동화 추가
- 05-04: 로컬 DB 후보를 public/data/summary.json으로 export하는 스크립트 추가
- 05-04: Vercel 정적 페이지에서 오늘/7일/30일 후보 표 렌더링
- 05-04: Vercel Python Lambda 빌드 대신 public 정적 배포로 전환
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
- Vercel: Streamlit/Python deps를 배포하지 않고 public 정적 상태 페이지만 제공
- 정적 대시보드 데이터: public/data/summary.json, 로컬 export 후 Git push 시 Vercel 반영
- Vercel 라우팅: /data/*는 JSON 정적 파일, 나머지는 index.html
- 자동 게시: summary.json 변경 시 작업 스케줄러가 커밋/푸시하고 Vercel 자동 재배포
- 검증: 파이프라인, ruff/mypy/compileall, Streamlit AppTest, localhost 200 확인
## 주의
- Streamlit: http://localhost:8501
- 자동 수집 로그: logs/daily_pipeline.log
- 첫 실행 시 KeyBERT/SentenceTransformer 모델 다운로드로 시간이 걸릴 수 있음
