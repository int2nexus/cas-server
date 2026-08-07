# cas-server 차트 변경 이력

각 `##` 섹션이 그대로 해당 버전의 **GitHub Release 본문**이 됩니다
(`scripts/extract-release-notes.sh` 가 발췌 → chart-releaser 가 릴리스 본문으로 사용).

`Chart.yaml` 의 `version` 을 올릴 때 이 파일 맨 위에 섹션을 함께 추가하세요.
섹션이 없으면 릴리스 워크플로가 실패합니다.

해당 사항이 없는 항목도 **"없음"이라고 적습니다** — 도입하는 쪽이 *없었다* 와 *안 썼다* 를
구별할 수 있어야 합니다.

```markdown
## <version>

image: `int2jieun/cas-server:<tag>` (변경 없음이면 그렇게 적기)

**동작 변경** — 없음
**마이그레이션** — 없음
**설정 키** — 없음
```

### 선택 라벨

세 항목은 **최소**입니다. 더 알려야 할 게 있으면 아래 라벨을 같은 모양(`**라벨** — 내용`)으로
덧붙입니다. 같은 라벨을 여러 번 써서 묶어도 됩니다.

- `**호환성**` — 요구하는 최소 appVersion·이미지 태그, 맞지 않을 때 벌어지는 일
- `**운영 조치**` — 이 버전 때문에 되돌리거나 새로 해야 하는 운영 작업
- `**주의**` — 버전과 무관하게 지켜야 하는 제약을 이 릴리스에서 처음 문서화한 경우

라벨 볼드 안에 수식어까지 넣지 마세요 — `**동작 변경 — 차트**` 가 아니라
`**동작 변경** — 차트` 입니다. 도입하는 쪽이 라벨을 훑어 찾기 때문에 라벨 자체가
고정된 문자열이어야 합니다.

### 마이그레이션 항목 쓰는 법

cas-server 는 기동 시 `CREATE TABLE IF NOT EXISTS` 만 실행하므로 보통 `없음` 입니다.
이미지가 스키마를 바꾸는 버전이면 아래 세 줄을 함께 적습니다 — 도입하는 쪽이 점검창을
잡고 백업 시점을 정하는 데 필요한 정보입니다.

- **영향받는 테이블** — 이름을 나열합니다
- **예상 소요시간** — 행 수 기준으로 적습니다. 스키마 작업이 기동 중에 일어나므로 그
  시간만큼 Pod 가 Ready 되지 않습니다
- **롤백** — 둘 중 해당하는 쪽을 명시합니다
  - **추가만 하는 변경**(테이블·컬럼 추가): 이전 이미지가 새 스키마에서 그대로 기동하므로
    `helm rollback <release> <revision>` 으로 안전하게 되돌아갑니다. "롤백 안전"이라고 적습니다.
  - **파괴적 변경**(삭제·타입 변경·NOT NULL 추가): **"이 버전은 DB 마이그레이션을 포함하며
    이전 버전으로 롤백할 수 없습니다"** 를 그대로 적습니다. `helm rollback` 은 차트와 이미지만
    되돌리고 **이미 적용된 스키마는 되돌리지 않으므로**, 되돌리려면 업그레이드 전에 떠 둔
    DB 스냅샷(`pg_dump`)을 복원하는 방법밖에 없습니다. 업그레이드 전 스냅샷이 필요하다는
    점을 항목에 함께 씁니다.

<!-- 새 버전 섹션은 이 줄 바로 아래에, 최신이 위로 오게 추가하세요 -->

## 0.1.23

image: `int2jieun/cas-server:0.1.17`

**호환성** — **이 차트는 appVersion 0.1.17 이상을 요구합니다.** 0.1.16 이하 이미지에는
`/_internal/live` 엔드포인트가 없어 404가 프로브 실패로 계산되고, 파드가 계속
재시작합니다. 이미지를 고정해 쓰는 배포는 이미지를 함께 올리거나,
`livenessProbe.httpGet.path` 와 `startupProbe.httpGet.path` 를
`/_internal/health` 로 되돌려야 합니다.

**동작 변경** — 이미지 0.1.17: 로그에서 비밀값 제거

로그에 남던 자격증명을 지웠습니다. 파드 로그 열람 권한만 있으면(Secret 읽기 권한이
없어도) 값을 얻을 수 있던 자리라, 봉인 Secret으로 주입해도 막히지 않던 경로입니다.

- 기동 로그의 `db_url` 에서 **DB 비밀번호가 마스킹**됩니다.
  `db_url=postgresql://cas:***@postgres.svc:5432/cas_metadata`
  호스트·포트·DB명·사용자명은 진단에 필요하므로 그대로 남습니다.
- 요청 로그의 **presigned 서명(`X-Amz-Signature`)이 마스킹**됩니다.
  서명은 만료 전까지 그 요청을 재현할 수 있는 값이라, 로그 열람자가 그대로 재사용할 수
  있었습니다. `X-Amz-Security-Token` 도 함께 지웁니다. `X-Amz-Credential`(키 ID)과 나머지
  쿼리는 진단 가치가 있어 유지합니다.
- 설정 구조체의 `Debug` 출력에서 `secret_master_key` / `admin_token` / `root_secret_key` /
  S3 `secret_access_key` 가 `<set>` · `<unset>` 로만 표시됩니다. 값은 가리되 **설정 여부는
  보여줍니다** — ConfigMap 키 오타로 안 먹은 것과 설정했는데 틀린 것을 구분해야 하기
  때문입니다. 현재 설정 전체를 출력하는 경로는 없지만(어느 로그 레벨에서도), 진단용으로
  한 줄 추가하는 순간 전부 새는 구조였습니다.
- DB 연결 실패 오류에서 접속 문자열을 스크럽합니다. 기동 실패 시 이 오류가 그대로
  파드 로그로 나갑니다.

**운영 조치** — 로그 필터를 되돌릴 수 있습니다. 위 유출을 막으려고
`RUST_LOG=warn,cas_server::api=info` 같은 필터를 걸어 두셨다면 `info` 로 복귀하십시오.
그 필터는 `cas_server` 타깃의 INFO를 통째로 없애서 업로드 상한 적용 여부, `listening on`,
백엔드 등록 같은 기동 진단 로그까지 함께 잃습니다. 또한 그 필터는 요청 로그를 켜 둔
채이므로 **presigned 서명은 계속 남고 있었습니다** — 이번 버전에서 그쪽이 해소됩니다.
장애 분석용으로 로그를 외부에 전달할 때 별도 마스킹 스크립트를 돌리던 절차도
더 이상 필요하지 않습니다.

**동작 변경** — 이미지 0.1.17: 설정 오류 시 기동 실패 방식

- 설정 파싱에 실패하면 **기본값으로 폴백하지 않고 즉시 종료**합니다(exit 1). 실패한
  필드명과 소속 섹션, 대응 환경변수를 종료 메시지에 담습니다.

  ```
  ERROR cas_server: 설정 로드 실패: missing field `admin_token`
    → `admin_token`은 [auth] 섹션의 필수 항목입니다. config/default.toml의 [auth]에 추가하세요.
       환경변수로는 CAS__AUTH__ADMIN_TOKEN 입니다.
    기본값으로 대체하지 않고 기동을 중단합니다 — ...
  ```

  종전에는 파일 전체를 버리고 기본값으로 진행했는데, 그 기본값에는 `storage_backends` 가
  없어 곧바로 `storage_backends가 비어있습니다` 패닉으로 끝났습니다. **기동 실패라는
  결과는 같고 메시지만 바뀝니다** — 즉 지금 정상 기동 중인 배포가 이 변경으로 뜨지 못하게
  되는 경우는 없습니다. 종전 메시지는 실제 원인(예: `[auth]` 필드 하나)과 무관한 곳을
  가리켜 오진을 유발했습니다.
- 부수 효과로 원인 로그가 사라지지 않습니다. 종전에는 원인을 알려주는 WARN이 기동 시
  1회만 나와 로그 로테이션 뒤에는 사후 확인이 불가능했습니다. 이제 파드가 종료되므로
  CrashLoopBackOff 재시작마다 같은 ERROR가 다시 남습니다.

**동작 변경** — 차트

- `startupProbe` 추가 (`startupProbe.enabled: true`, 기본 예산 600초).
  기동이 끝날 때까지 liveness/readiness가 평가되지 않습니다. DB 마이그레이션이
  liveness 예산을 넘겨 파드가 kill되던 문제를 해소합니다 — 0.1.16 최초 배포에서
  `object_versions` 인덱스 생성이 114초 걸려 실제로 발생했습니다.
- `livenessProbe` 대상이 `/_internal/health` → `/_internal/live` 로 바뀝니다.
  종전에는 liveness가 DB와 blob 백엔드 가용성까지 확인해서, DB failover나 NAS
  순간 장애에 파드가 죽었습니다. 재시작으로는 외부 의존성이 복구되지 않으므로
  CrashLoopBackOff 백오프만큼 중단이 오히려 길어집니다.
  `readinessProbe` 는 `/_internal/health` 를 그대로 씁니다(의존성 확인이 맞는 자리).
- `livenessProbe`/`readinessProbe` 의 `timeoutSeconds` 가 실제로 적용됩니다.
  종전 템플릿이 이 필드를 렌더링하지 않아 values의 `5` 가 무시되고 쿠버네티스
  기본값 **1초**가 적용되고 있었습니다. 프로브가 설정보다 훨씬 쉽게 실패하던
  상태이므로, 이 값을 조정해 두셨다면 실제 반영 결과를 확인하세요.
- `terminationGracePeriodSeconds` 가 실제로 적용됩니다. 같은 이유로 values의 `60` 이
  무시되고 기본값 **30초**가 적용되고 있었습니다. 종료 유예가 30초에서 60초로 늘어납니다.

**마이그레이션** — 없음 (이미지 0.1.17은 스키마를 바꾸지 않습니다)

**설정 키**

- 추가: `startupProbe.enabled`, `startupProbe.httpGet.path`, `startupProbe.httpGet.port`,
  `startupProbe.periodSeconds`, `startupProbe.timeoutSeconds`, `startupProbe.failureThreshold`
- 기본값 변경: `livenessProbe.httpGet.path` (`/_internal/health` → `/_internal/live`)
- 삭제 — 없음

**주의** — **`replicaCount` 는 1을 유지하세요.**
GC의 blob 물리 삭제와 진행 중인 PUT 사이의 durability 보호가 프로세스 내부
per-hash 뮤텍스에 의존합니다. 파드가 둘 이상이면 이 락이 공유되지 않아, 한 파드의
GC가 다른 파드에서 커밋 직전인 blob을 삭제해 메타데이터만 남는 상태가 될 수 있습니다.
이번 버전에서 values.yaml에 근거를 명시했습니다. 종전 차트에는 이 제약이 문서화되어
있지 않았습니다.

## 0.1.22

image: `int2jieun/cas-server:0.1.16`

이 버전부터 변경 이력을 남깁니다.
