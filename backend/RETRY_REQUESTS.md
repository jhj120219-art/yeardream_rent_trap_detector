# 저장·분석 요청 재시도 — 프론트 연결 안내

통신이 끊겼을 때 서버는 이미 저장했지만 화면이 응답을 못 받는 경우가 있다. 같은 요청을 다시 보내면 자료가 중복 생성될 수 있어 선택 헤더 `Idempotency-Key`를 지원한다. 기존 요청 본문·응답·만원/㎡·분석 정책·세션은 그대로다. 헤더 없이 호출하면 기존처럼 매번 새 자료를 만든다.

## 프론트에서 할 일

1. 사용자가 최종 확인 후 **새 저장 작업을 시작할 때** `crypto.randomUUID()`로 저장용 키를 한 번 만든다.
2. `POST /listings`에 `Idempotency-Key` 헤더를 보낸다. 같은 작업의 재시도에는 같은 키·같은 입력 JSON·같은 Bearer 세션을 사용한다. 재시도 때 새 키를 만들면 중복 방지가 안 된다.
3. `POST /listings/{id}/analyses`에는 분석 작업용 키를 따로 만들어 보낸다. 해당 분석의 재시도에서만 재사용한다.
4. 입력값을 수정하거나 새로운 분석을 의도적으로 실행할 때는 새 키를 쓴다. 저장 ID를 받았다면 입력 저장부터 다시 시작하지 않고 해당 ID로 다음 단계만 진행한다.
5. 409는 같은 키를 다른 입력에 재사용했거나 이전 결과가 삭제된 경우다. 무한 자동 재시도하지 말고 현재 작업을 확인한다. 삭제한 자료를 복원하려는 용도로 쓰지 않는다.

키는 8~128자의 영문·숫자·점·밑줄·콜론·하이픈을 허용한다. UUID 문자열 사용을 권장한다. 팀 접속키·세션 토큰과는 다른 값이며 주소·개인정보를 키에 넣지 않는다. 자동 페이지 새로고침만으로 입력·세션·작업 키가 복구되는 기능은 아니다. 제출 중 버튼 잠금과 명확한 실패 단계 안내도 유지한다.

```javascript
// 새 사용자 작업 시작 시 한 번 생성하고, 같은 작업의 재시도에는 아래 값을 유지합니다.
const saveKey = crypto.randomUUID();
const analysisKey = crypto.randomUUID();
const headers = {
  'Content-Type': 'application/json',
  'X-Team-Key': teamKey, // 테스트 시작 시 따로 입력받은 값
  Authorization: `Bearer ${token}`
};
const savedResponse = await fetch(`${base}/listings`, {
  method: 'POST', headers: {...headers, 'Idempotency-Key': saveKey},
  body: JSON.stringify(confirmedInput)
});
if (!savedResponse.ok) throw new Error(`저장 실패: ${savedResponse.status}`);
const saved = await savedResponse.json();
const analysisResponse = await fetch(`${base}/listings/${saved.id}/analyses`, {
  method: 'POST', headers: {...headers, 'Idempotency-Key': analysisKey}
});
if (!analysisResponse.ok) throw new Error(`분석 실패: ${analysisResponse.status}`);
```

## 서버 처리와 범위

- 같은 세션·같은 작업 경로·같은 키를 동일한 입력으로 재전송하면 기존 매물/분석 ID를 반환한다. 성공·재전송 모두 기존 201 응답을 유지한다. 완료된 분석의 순차 재시도는 분석 코드를 다시 실행하지 않는다.
- 같은 키를 쓰더라도 다른 사용자 세션·다른 매물의 분석 경로는 독립된 작업이다. 팀 접속키나 Bearer 인증을 대체하지 않는다. `/capabilities`의 `retry_key_supported=true`로 지원 여부를 확인할 수 있다.
- 기존 objects 테이블의 비공개 `request_receipt` 레코드와 기본키를 사용한다. 처리 영수증과 생성 객체는 같은 DB 트랜잭션에 저장한다. 새 테이블·스키마 변경·추가 권한·DB 전환은 없다. 동시 요청의 저장 결과는 하나이며, 동시 분석 계산 자체가 한 번만 실행되는 것은 보장하지 않는다.
- 영수증에는 입력의 SHA-256, 결과 ID만 저장하며 키 원문·입력 주소·이미지는 넣지 않는다. 영수증은 매물 목록·보고서에서 노출하지 않는다. 매물 삭제 후에도 영수증은 남아 동일 키로 재생성되는 것을 막는다. 세션 삭제 시 해당 영수증까지 삭제된다. 별도 만료 시간·기간별 자동 정리는 아직 없다.
- 기존 SQLite→MySQL 이전과 DB 백업은 objects 행 전체를 보존하므로 영수증도 함께 보존한다. 세션 토큰과 작업 키를 잃었을 때 복구하는 계정 기능은 제공하지 않는다.

## 검증

SQLite/실제 MySQL 각각 동시 4요청의 단일 저장, 다른 입력 충돌, 트랜잭션 실패 후 영수증 롤백, 삭제 결과 재생성 거절, 사용자 간 독립, 세션 삭제 후 영수증 정리, 독립 HTTP 프로세스 종료·재시작 후 같은 매물/분석 응답을 확인했다. 전체 백엔드 162 passed, 0 skipped, 도구 안내 1건. 별도 공개 HTTPS 검사에서도 같은 저장·분석 요청이 같은 결과 ID를 반환했다. 기존 v1.1 응답에 내부 영수증을 추가하지 않는다. 실거래 가격 정확도나 고객 로그인 검증과는 다르다.
