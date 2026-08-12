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

## 0.1.24

image: `int2jieun/cas-server:0.1.18`

**호환성** — 차트 자체는 0.1.17 이미지로도 동작합니다. 아래 두 항목은 **이미지 0.1.18
이상**에서만 효과가 있습니다. 0.1.17 이하 이미지에서 `auth-metrics-token` 을 넣으면
서버가 그 값을 무시하므로, 그 토큰으로 스크레이프하면 401 이 됩니다.

**동작 변경** — 이미지 0.1.18: 유휴 메모리 바닥값을 밀어 올리던 항 하나를 제거했습니다

서버 내부의 해시별 쓰기 락 테이블을 **요청이 끝날 때 즉시 회수**합니다. 이전에는
GC 실행 시에만 회수했기 때문에 **회수 주기가 GC 주기와 같았습니다.** 주기적으로
GC 를 돌리는 배포에서는 그 주기만큼(기본 스케줄이 주 1회이므로 최대 일주일치) 쌓이고,
`gc.enabled: false` 배포(초기 마이그레이션 중 권장 설정)에서는 회수 경로가 아예
없었습니다.

항목은 **고유 해시마다 하나씩** 생기고 항목당 약 180~240바이트입니다. 대량 적재는
고유 해시율이 요청율과 거의 같은 구간이라 증가율이 최대가 됩니다 — 2026-08 운영
사례에서 유휴 바닥값이 4.9일간 **하루 330~430 MiB** 씩 단조 상승했고, 그 기울기를
요청당 비용으로 역산하면 약 234바이트로 위 범위 안에 들어옵니다.

**이것이 관측된 상승분 전부를 설명하는지는 실환경 검증 대기입니다.** 자릿수가 맞고
축소 환경 재현이 실패한 이유까지 설명되지만, 실측으로 확정된 것은 아닙니다.
아래 운영 조치의 완충 유지 항목을 함께 읽으십시오.

`cas_blob_lock_map_entries` 게이지의 **의미가 바뀝니다**:

| 이미지 | 의미 | 유휴 시 기대값 |
|---|---|---|
| 0.1.17 이하 | 누적 고유 해시 수 (GC 시에만 회수) | GC 주기까지 계속 증가 |
| 0.1.18 이상 | 진행 중인 쓰기 건수 | **0** |

0.1.18 이상에서 이 값이 유휴 구간에 0으로 떨어지지 않으면 항목 유출 신호입니다.

GC의 회수 단계를 advisory lock 앞으로 옮겼습니다. 뒤에 있어서 **advisory lock 획득에
실패하거나 DB 오류가 나면** 이 정리까지 함께 건너뛰던 문제가 해소됩니다.
(HTTP 로 GC 를 중복 트리거하는 경우는 핸들러가 `run_gc` 호출 전에 409 를 돌려주므로
원래 회수 단계에 도달하지 않습니다 — 그쪽은 이 이동으로 달라지지 않습니다.)

**동작 변경** — 롤아웃 전략이 `Recreate` 가 됩니다 (짧은 중단이 생깁니다)

지금까지는 `strategy` 를 지정하지 않아 쿠버네티스 기본값 `RollingUpdate` 가 적용됐고,
`replicas: 1` 에서도 `maxSurge = 1` 이라 **모든 업그레이드와 `rollout restart` 에서
구·신 파드가 동시에 Ready 상태로 겹쳤습니다.** 그 창에서 두 프로세스가 서로 다른
per-hash 뮤텍스 맵을 잡습니다 — 차트가 `replicaCount: 1` 을 강제하는 근거가 바로 그
맵의 공유인데, 롤아웃마다 그 근거가 깨지고 있었습니다. GC 가 다른 파드에서 커밋
직전인 blob 을 참조 없음으로 오판해 물리 삭제할 수 있습니다.

**이번 업그레이드부터 롤아웃 중 짧은 중단이 생깁니다.** `replicaCount: 1` 이라 노드
재기동만으로도 어차피 생기는 중단이고, durability 를 그 대가로 사는 편이 낫다고
판단했습니다. 무중단이 더 중요하면 `updateStrategy.type: RollingUpdate` 로 되돌릴 수
있으나, 위 겹침 위험을 감수하는 결정이므로 기록으로 남기십시오.

**설정 키** — `updateStrategy` (기본값 `{type: Recreate}`)

**설정 키** — `auth.metricsToken` (기본값 `""`)

`GET /_internal/metrics` 전용 **읽기 전용** Bearer 토큰입니다. 지금까지 이 엔드포인트는
`admin_token` 을 요구했고, 그 토큰은 `POST /_internal/gc`(blob 물리 삭제)와
`/_admin/*`(액세스 키 관리)까지 여는 자격증명입니다. 스크레이프를 붙이려면 삭제 권한을
모니터링 스택에 배포하거나 메트릭을 포기하거나 둘 중 하나를 골라야 했습니다.

- 비워 두면 `admin_token` 으로 폴백합니다 — **기존 배포의 동작이 바뀌지 않습니다.**
- `admin_token` 은 계속 메트릭을 읽을 수 있습니다. 업그레이드가 스크레이프를 끊지 않습니다.
- `metricsToken` 은 metrics 엔드포인트에서만 통합니다. GC 도 admin API 도 열지 않습니다.
- **`metricsToken` 만 채우고 `adminToken` 을 비우면 서버가 기동을 거부합니다.**
  그 조합에서는 metrics 만 잠기고 `POST /_internal/gc`(blob 물리 삭제)가 무인증으로
  열려, 401 을 보고 보호된다고 오해하게 되기 때문입니다. `replicaCount: 1` 이라
  기동 실패는 곧 전면 중단이므로, 둘을 함께 설정하거나 `metricsToken` 을 비워 두십시오.

**운영 조치** — Secret 을 갱신했으면 파드를 직접 재시작하십시오.

`secrets.useExternalSecret: true`(기본값)에서는 Helm 이 Secret 내용을 볼 수 없어
체크섬을 걸 수 없습니다. `kubectl apply -f sealed-secret.yaml` 만으로는 파드가
교체되지 않고, env 는 파드 생성 시점에 주입되므로 새 토큰이 반영되지 않습니다.
그 상태에서 모니터링을 새 토큰으로 바꾸면 스크레이프가 401 이 되고 원인이
"토큰이 틀렸나"로 보입니다.

```bash
kubectl rollout restart -n <namespace> deploy/cas-server
```

업그레이드와 함께 갱신한다면 **Secret 을 먼저 적용**하고 `helm upgrade` 하면 파드
교체와 함께 들어갑니다. (차트가 Secret 을 만드는 `useExternalSecret: false` 배포에는
이번 릴리스에서 `checksum/secret` 애노테이션을 추가해 자동 재시작됩니다.)

**운영 조치** — 모니터링 스택에 admin 토큰을 배포해 두셨다면 이 토큰으로 교체하십시오.

`secrets.useExternalSecret: true`(기본값)면 sealed-secret 에 `auth-metrics-token` 키를
추가합니다. 이 키는 **선택 항목**이고, deployment 에서 `optional: true` 로 참조하므로
키를 추가하지 않아도 파드는 정상 기동합니다. 기존 7개 키 Secret 그대로
업그레이드하셔도 됩니다.

```bash
kubectl create secret generic cas-server   --namespace=<namespace>   --from-literal=db-password='...'   --from-literal=s3-access-key-id='...'   --from-literal=s3-secret-access-key='...'   --from-literal=auth-secret-master-key='...'   --from-literal=auth-admin-token='...'   --from-literal=auth-metrics-token='...'   --from-literal=auth-root-access-key-id='...'   --from-literal=auth-root-secret-key='...'   --dry-run=client -o yaml > /tmp/secret-plain.yaml
kubeseal --format yaml < /tmp/secret-plain.yaml > sealed-secret.yaml && rm /tmp/secret-plain.yaml
```

**운영 조치** — `resources.limits.memory` 는 `6Gi` 를 유지하십시오.

0.1.16/0.1.17 에서 관측된 바닥값 상승의 원인이 위 항목으로 짚였으나, 실환경에서
상승이 멈춘 것이 확인되기 전에는 완충을 내리지 마십시오. 하향 전제는
`values.yaml` 의 `resources` 주석에 적었습니다.

**주의** — `gc.enabled: false` 와 메모리의 관계를 이번에 처음 문서화했습니다.

**이미지 0.1.17 이하**에서 GC 를 끄면 위 락 테이블의 회수 경로도 함께 사라집니다.
그 이미지로 GC 를 끈 채 대량 적재해야 한다면, 적재 기간에
`POST /_internal/gc?dry_run=true`(admin 토큰 필요)를 주기 실행해 완화하십시오 —
blob 물리 삭제도 advisory lock 도 없이 그 테이블을 회수합니다. 함께 도는 것은
읽기 전용 쿼리 두 개(orphan 후보 COUNT, 만료 멀티파트 목록)이고, 회수 자체는
샤드를 하나씩 잠그고 지나가므로 쓰기 경로 전체를 멈추지는 않습니다.
**주기를 정하기 전에 한 번 수동으로 돌려 소요 시간을 재십시오.**

**`kubectl exec` 로는 칠 수 없습니다.** 런타임 이미지(`debian:bookworm-slim`)에
`curl` 도 `wget` 도 없습니다. 클러스터 안에서 주기 실행하려면 `curl` 이 있는 이미지의
CronJob 이 필요하고(차트의 `gc-cronjob` 이 참고가 됩니다), 일회성 확인은
`kubectl port-forward` 후 로컬 `curl` 로 하십시오.

다만 주기 실행이 항상 최선은 아닙니다 — 이 테이블은 프로세스 메모리라 **파드 재시작이면
통째로 사라지고**, 단편화까지 함께 회수됩니다. 0.1.18 로 올릴 때까지의 간격이 짧다면
재시작 한 번이 더 낫습니다. 세 선택지의 판단 기준은
[README 의 "GC와 메모리 회수" 절](https://github.com/int2nexus/cas-server/blob/main/charts/cas-server/README.md#gc와-메모리-회수-이미지-0117-이하)에 있습니다.

0.1.18 이상은 이 완화가 전부 필요하지 않습니다.

**마이그레이션** — 없음

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
