# 집 PC에서 원격 연결·기존 서버 주소 복구 — 2026-10-22

월세구멍 집 PC에서 실제로 작업해줘. 계획만 설명하지 말고 가능한 작업은 직접 실행해. 사용자가 관리자 허용을 눌러야 할 때만 요청해. 비밀번호·접속키·개인키는 채팅이나 Git에 올리지 마.

매장에서 확인한 사실: 집 DESKTOP-QTP7F26 / Tailscale 100.97.57.86은 ping에 응답하지만 SSH 22·22222, WinRM 5985·5986, RDP 3389, 기존 서비스 후보 8012는 연결 안 됨. 이것이 서비스 종료나 방화벽 원인이라고 단정하지 마. 저장된 doe-books 및 witness trycloudflare 주소는 공용 DNS NXDOMAIN. 매장 IP는 100.73.90.64. 같은 계정 Tailscale 경로로 복구한다. 공개 인터넷에 DB·SSH를 열지 않는다.

1. 이 PC가 정말 집 PC인지 확인한다. 실제 사용자·Tailscale IP·프로젝트 경로·AGENTS·Git 상태·origin을 확인한다. 개인 origin은 https://github.com/jhj120219-art/yeardream_rent_trap_detector.git 이다. 미커밋 변경·환경변수·기존 DB를 보존하고 fetch한다. 안전한 fast-forward가 가능할 때만 pull한다. 충돌이면 보존·비교하고 force/reset hard/clean을 사용하지 않는다. 이번 인계 문서와 backend/scripts/finish_home_remote.ps1을 확인한다.

2. 집의 실제 서버 실행 경로와 프로세스를 찾는다. C:/Users/wlsdu/AppData/Local/YeardreamRentBackend는 후보이므로 존재부터 확인한다. connection.json·tunnel.log·시작 스크립트·실행 인자를 읽되 접속키나 환경변수 전체를 출력하지 않는다. 여러 복사본 중 현재 실행 중인 것을 구분한다. 서비스가 정상이라면 불필요하게 중지하지 않는다.

3. Tailscale 서비스·로그인·현재 IP와 매장 장치 IP를 확인한다. 기존 OpenSSH 서비스·설정·authorized_keys·호스트키·방화벽을 먼저 읽고 백업한다. 새 개인키를 만들거나 기존 호스트키를 바꾸지 않는다. 매장 공개키는 아래 값이며 인증용 비밀이 아니다. 이 공개키만 집에 등록하고 개인키는 집으로 가져오지 않는다.

SHOP_PUBLIC_KEY:
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOUKvm8dBmIUjxCvVwRESaso3IMZfpMrv5dR24E+Bf6m yeardream-shop-to-home

4. 기존 sshd가 중지돼 있고 이름/IP/사용자가 일치한다면 backend/scripts/finish_home_remote.ps1을 관리자 권한으로 실행한다. 공개키를 비공개 임시 파일로 저장해 -PublicKeyFile 인자로 전달한다. 나머지 인자는 -ShopIP 100.73.90.64 -HomeIP 100.97.57.86 -ExpectedHomeName DESKTOP-QTP7F26 -HomeUser wlsdu 이다. 관리자 허용 창은 사용자에게 한 번 눌러달라고 한다. 사용자·IP가 달라졌으면 실제 값을 확인하고 정합성을 검토한 후 사용한다. 임의 계정을 만들지 않는다.

이미 sshd가 실행 중이면 도우미는 일부러 중단된다. 이때 서비스를 무작정 종료하거나 스크립트의 보호 검사를 제거하지 말고 기존 접속을 보존하면서 설정을 검토한다. 매장 공개키 접속과 VPN 범위만 허용되도록 최소 변경하고 구문 검사 후 필요한 경우에만 재시작한다. 이 작업의 목적은 VPN 한정 공개키 인증이며 비밀번호 인증·전체 방화벽 해제·공개망 포트 개방이 아니다. Tailnet ACL 때문에 막힌 경우 정확한 사유를 기록한다.

5. 성공하면 sshd 자동 시작·VPN 수신·22222 리스닝·매장 IP 한정 방화벽·키 파일 권한을 확인한다. 호스트 공개키 지문을 출력하고 C:/ProgramData/YeardreamRentRemote/yeardream-home-connection.json 생성 여부를 확인한다. 매장에서 실제 SSH 성공 여부는 매장에서 검증해야 하므로 집의 로컬 검사만으로 완료라고 하지 않는다.

6. 기존 MySQL과 기존 API의 실제 로컬 /health·/ready 응답을 확인한다. DB 비밀번호를 바꾸거나 DB를 새로 만들지 않는다. 서버가 꺼져 있다면 기존 설정·원래 시작 방법으로 재시작한다. 기존 터널이 정상이라면 그대로 쓴다. 터널이 종료됐거나 주소가 무효라면 원래 시작 도구로 터널을 재시작하고 새 주소가 실제 /ready 응답하는지 확인한다. 접속키는 기존 로컬 파일에서 읽고 다른 호스트로 리다이렉트 전송하지 않는다. 새 주소가 나온 사실만으로 성공 처리하지 않는다. /ready 응답이 503이면 DB·분석 자료 문제를 구분하고 원본을 보존해 수정한다.

7. 확인 결과를 backend/HOME_CONNECTION_RESULT_20261022.md에 남긴다. 넣을 내용: 확인 시각·실행 경로·적용 커밋·로컬 health/ready 상태·현재 공개 서버 URL·VPN IP·SSH 포트·호스트 공개키 지문·성공/미완료 항목과 이유. 공개 서버 URL·공개 호스트 지문만 기록하고 접속키·DB 비밀번호·개인키·세션 토큰·DB 원본은 넣지 않는다. 명시적으로 이 결과 문서만 stage하고 개인 GitHub에 commit/push한다. 다른 코드와 환경 설정을 통째로 커밋하지 않는다. 집 연결 JSON은 비공개 로컬에 보존한다. 팀 저장소에 강제로 변경하지 않는다.

끝나면 쉽게 보고한다: ① 여기서 실제 복구한 것 ② 매장에서 확인해야 할 SSH ③ 현재 서버 주소와 API 상태 ④ 남은 문제. 관리자 승인을 제외한 명령 실행을 사용자에게 떠넘기지 않는다. 이번 작업은 원격 통로·기존 서비스 주소 복구에 집중하며 전체 DB 전환이나 추가 기능 개발을 섞지 않는다.
