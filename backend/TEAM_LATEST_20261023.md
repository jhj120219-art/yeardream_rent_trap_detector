# 팀 최신 변경 연동 확인 — 2026-10-23

확인한 팀 main: a5d432e (PR #7 이미지 추출 경계 중복 정리, PR #8 미사용 분석 보조 파일 정리).
프론트 작업 브랜치 eea7055와 main도 비교했습니다. main에 스타일은 반영되어 있고, 남은 차이는 main의 서비스명이 더 최신인 제목 차이뿐이므로 이전 브랜치로 되돌리지 않았습니다.

## 실제 반영
- 개인 저장소의 오래된 machine 파일을 팀 main의 추적 파일로 갱신했습니다. 팀 코드·정책을 임의 수정하지 않았습니다. 기존 개인 전용 파일과 원본 자료는 삭제하지 않았습니다.
- 가구에너지패널 reference_data/energy_reference_2023.csv는 팀에서 관리 중인 공개 서울 집계표입니다. 실거래 원본·개인 가구 로우데이터를 추가하지 않았습니다.
- 집 서버가 사용하는 backend/data/team_upstream_checkout를 856dc01 → a5d432e로 fast-forward 적용했습니다. 새 OCR 요청은 해당 최신 분석 스크립트를 사용합니다.
- 삭제된 보조 양식은 백엔드 실행에서 읽지 않습니다. vision.py가 실제 읽는 image_extraction_example.json과 image_prompt_ko.md는 남아 있으며 검사에서 정상 로딩됐습니다.
- 공개 화면 파일 backend/web이 Docker 배포에 빠지지 않도록 COPY와 허용 목록을 보완했습니다. Docker 실행 도구가 없어 실제 컨테이너 빌드는 미검증입니다.
- 기존 API·MySQL·공개 터널을 종료하거나 재시작하지 않았습니다. 비공개 키·DB·환경설정은 보존했습니다.

## 이번 검증
- 갱신한 개인 저장소 backend/tests: 261 passed, 21 skipped, 경고 4. 이전 개인 분석 코드에서 data_files 모듈 누락으로 실패했던 2건은 이번 최신 코드에서 통과했습니다.
- 분석 담당 test_partial_fields.py / test_consensus.py / test_read_cards.py: 각각 실패 0. 합성·가짜 OCR 출력 기반 회귀 검사이며 실제 이미지 정확도 수치가 아닙니다.
- 집 PC에서도 최신 test_partial_fields.py 실패 0 확인.
- 키 없는 공개 URL: 서버 설정란 숨김, 세션 생성 → 가상 매물 저장 → 월세 COMPARED → 관리비 참고 분석 → 5항목 report 조회 성공.
- 시험 세션은 자체 생성한 토큰으로 삭제 완료. 다른 사용자 자료는 수정하지 않았습니다.

현재 공개 체험: https://schemes-subscriber-participating-gale.trycloudflare.com/
기존 chatgpt.site 주소의 재배포는 여전히 권한 미확인입니다. 공개 중계를 재시작하면 임시 체험 주소가 바뀔 수 있습니다.
분석가 README의 새 정확도 설명은 평가 조건과 한계를 포함한 정정입니다. 이를 서비스 전체 정확도로 주장하지 않습니다.
