# cas-server Helm Chart

BLAKE3 기반 CAS(Content-Addressable Storage) 서버. S3 호환 스토리지 또는 NFS를 백엔드로 사용하는
HTTP API를 제공한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/cas-server-0.1.32/charts/cas-server/docs/architecture.md)
  — 스토리지 모델(CAS·dedup·GC), 백엔드 구성, S3 호환 API 명세, 에러 코드
- [사용법](https://github.com/int2nexus/cas-server/blob/cas-server-0.1.32/charts/cas-server/docs/usage.md)
  — 배포 절차, 웹 UI 키 관리, AWS CLI/boto3 예제, 내부 API
- [변경 이력](CHANGELOG.md)
  — 버전별 동작 변경·마이그레이션·설정 키. 각 항목은 해당 GitHub Release 본문과 동일하다

## 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 시크릿 (sealed-secret) 먼저 주입

`secrets.useExternalSecret: true`(기본값)일 때 차트는 Secret을 만들지 않고, 이미 클러스터에 존재하는
`cas-server` Secret 을 참조한다. kubeseal로 암호화해 미리 주입한다:

```bash
kubectl create secret generic cas-server \
  --namespace=<namespace> \
  --from-literal=db-password='...' \
  --from-literal=s3-access-key-id='...' \
  --from-literal=s3-secret-access-key='...' \
  --from-literal=auth-secret-master-key='...' \
  --from-literal=auth-metrics-token='...' \
  --from-literal=auth-gc-token='...' \
  --from-literal=auth-root-access-key-id='...' \
  --from-literal=auth-root-secret-key='...' \
  --dry-run=client -o yaml > /tmp/secret-plain.yaml

kubeseal --format yaml < /tmp/secret-plain.yaml > sealed-secret.yaml
rm /tmp/secret-plain.yaml
kubectl apply -f sealed-secret.yaml -n <namespace>
```

위 8개 중 `s3-access-key-id` / `s3-secret-access-key` 는 **`storage.mode: "s3"` 에서만
쓰인다** — `nfs` 모드에서는 어떤 템플릿도 참조하지 않으므로 넣지 않아도 된다(넣어도 무해).

`auth-metrics-token`은 Secret 키로는 선택이다 — 없어도 파드는 기동한다. 다만 **auth 를 켠
배포에서 그 값이 없으면 스크레이프가 `401`** 이다. 용도는 [메트릭 스크레이프](#메트릭-스크레이프) 참고.

`secrets.secretMasterKey`를 비우면 NoAuth 모드(인증 없음, 내부망 전용)로 동작한다. 상세 절차와 값 교체
방법은 [`examples/sealed-secret.yaml`](https://github.com/int2nexus/cas-server/blob/cas-server-0.1.32/charts/cas-server/examples/sealed-secret.yaml) 참고.

## 설치

```bash
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

`values-prod.yaml`은 직접 작성하거나 [`examples/values-prod.yaml`](https://github.com/int2nexus/cas-server/blob/cas-server-0.1.32/charts/cas-server/examples/values-prod.yaml)을
내려받아 값을 채운 뒤 사용하세요(이 레포를 clone했다면 `charts/cas-server/examples/values-prod.yaml`).

### S3 / MinIO 모드 values 예시

```yaml
externalDatabase:
  host: "postgresql"
  port: 5432
  username: "username"
  database: "database"

storage:
  mode: "s3"
  s3:
    endpoint: "storage-endpoint-url"
    bucket: "your-bucket"
    region: ""
    keyPrefix: ""
    allowHttp: true
```

## 노출 주의 — 인증을 켜지 않으면 `/_ui` 와 `/_api` 가 열립니다

`auth` 를 켠 배포(`secrets.secretMasterKey` 설정) 기준입니다. **이미지 `0.1.21` 이상이
필요합니다.**

| 경로 | 자격증명 |
|---|---|
| `GET`/`HEAD /{bucket}/{key}` | `auth.anonymousGet: true`(기본값)이면 없음 |
| 그 밖의 데이터 평면 | 키 정책 |
| `/_api/stats` · `buckets` · `backends` · `blobs/{hash}` · `config-effective` | 유효한 키의 SigV4 서명 |
| `/_api/gc/*` | `cas:ReadGc`·`cas:RunGc` 키, root 키, GC 토큰 |
| `POST /_internal/gc` | `cas:RunGc` 키, root 키, GC 토큰 |
| `/_admin/*` | `cas:*AccessKeys` 키, root 키 |
| `/_internal/metrics` | metrics 토큰 **뿐** |
| `/_api/auth-mode` · `/_ui` | 없음 |

예외 셋을 알아 두십시오.

- **`/_api/*` 는 인증만 보고 인가는 보지 않습니다.** 대응 액션이 없어 데이터 전용 키로도
  열립니다. 키별로 좁히는 수단은 없습니다. 자격증명 값은 나가지 않습니다
  (`<set>`/`<unset>` 과 가려진 `db_url`).
- **`/_internal/metrics` 는 키로 열리지 않습니다.** `auth.metricsToken` 하나만 받고,
  그 값이 비면 auth 를 켠 배포에서는 `401`, NoAuth 배포에서는 무인증으로 열립니다.
- **`/_api/backends` 의 `endpoint_url` 은 관리 주체에게만 채웁니다** — root 키 또는
  `cas:ManageAccessKeys` 를 가진 키. 그 밖의 키에는 `null` 입니다.

`auth` 를 켜지 않으면 데이터 평면까지 포함해 위 전부가 무인증입니다.
등록되지 않은 `/_api/*` 경로는 `404` 입니다.

`service.type` 기본값이 `NodePort` 이므로 표면은 **클러스터의 모든 노드 x `nodePort`** 입니다 —
파드가 없는 노드 IP 에서도 응답합니다. 그리고 `/_api/stats` 는 2026-08 운영 사고를 일으킨 집계 경로입니다. 이미지 `0.1.18` 부터 30초 상한이 걸리지만 **그 30초 동안의 인스턴스 지연은
남습니다.**

**신뢰 네트워크 밖이라면 `service.type: ClusterIP` 로 두고 인증 프록시나 NetworkPolicy 뒤에
놓으십시오.** 차트가 제공할 수 있는 완화는 그것뿐입니다.

`/_ui` 를 브라우저로 여는 것 자체는 인증이 켜져 있으면 집계를 부르지 않습니다 — 첫 화면은
`/_api/auth-mode` 하나만 호출하고 로그인 화면을 띄웁니다. 대시보드(`/_api/stats`,
`/_api/backends`)는 로그인 성공 뒤에 부릅니다. **다만 인증이 꺼진 NoAuth 모드에서는 여는
즉시 그 둘이 나가고, 어느 모드든 `/_api/stats` 를 직접 호출하는 것은 막히지 않습니다.**

## 주요 values

| 키 | 기본값 | 설명 |
|----|--------|------|
| `storage.mode` | `s3` | `s3` 또는 `nfs` |
| `externalDatabase.host` | `""` | PostgreSQL 서비스명 |
| `externalDatabase.port` | `5432` | PostgreSQL 포트 |
| `secrets.useExternalSecret` | `true` | sealed-secret으로 Secret을 미리 주입했는지 여부 |
| `secrets.secretMasterKey` | (없음) | 설정 시 SigV4 인증 활성화, 비우면 NoAuth |
| `auth.metricsToken` | `""` | `GET /_internal/metrics` 전용 **읽기 전용** 토큰. **이 경로를 여는 유일한 수단입니다** — 비우면 auth 를 켠 배포에서 `401` 입니다 (아래 참고). `useExternalSecret: true`(기본)이면 이 값 대신 Secret 의 `auth-metrics-token` 이 쓰입니다 |
| `secrets.rootAccessKeyId` · `secrets.rootSecretKey` | (없음) | root 키. **`secretMasterKey` 를 설정하면 필수** — 없으면 서버가 기동하지 않습니다 |
| `secrets.gcToken` | `""` | GC 전용 토큰. GC CronJob 이 이것을 씁니다 (아래 참고). `useExternalSecret: true`(기본)이면 이 값 대신 Secret 의 `auth-gc-token` 이 쓰입니다 |
| `ingress.enabled` | `false` | Ingress 활성화 |
| `config.maxUploadSizeBytes` | `10737418240` | 최대 업로드 크기 (10 GiB) |
| `config.maxUploadBytesInFlight` | `3221225472` | 동시 업로드 바디의 총 상주 바이트 상한 (3 GiB). 초과분은 `503 SlowDown`. **`0` = 무제한.** `resources.limits.memory` × 0.5 를 기준으로 함께 조정할 것 |
| `config.maxConcurrentUploads` | `96` | 동시 업로드 건수 상한. 위 바이트 예산의 보조 장치. **`dbMaxConnections`와의 대소 관계는 판정 보류** — `values.yaml` 주석 참고 |
| `config.requestTimeoutSecs` | `120` | 요청 처리 타임아웃. 느린 S3 백엔드까지 포함한 요청 경로의 유일한 wall-clock 상한 |
| `config.statsStatementTimeoutSecs` | `30` | 집계 조회 전용 풀의 쿼리 상한. 이 풀은 커넥션 1개로 요청 경로와 격리된다 (대상 목록은 아래 참고) |
| `config.statsWorkMemMb` | `0` | 집계 풀의 `work_mem` (MiB). `0` = 서버 값 사용. **PostgreSQL 쪽 메모리**를 쓰므로 PG 사이징 확인 후 조정할 것 |
| `config.dbMinConnections` | `2` | 항상 유지할 유휴 커넥션. `0`이면 뜸한 뒤 첫 요청이 접속 핸드셰이크 비용을 문다(실측 68ms → 0.5ms) |
| `config.gcDbMaxConnections` | `2` | GC 전용 풀 크기 |
| `config.softDeleteRetentionSecs` | `604800` | soft-delete된 `object_versions` **행** 중 GC 가 blob 과 함께 치우지 못한 것의 보존 기간. **되돌림 창이 아니다** (아래 참고) |
| `auth.cacheTtlSecs` | `10` | 자격증명 캐시 TTL. 폐기된 키·좁힌 정책이 실제로 막히기까지의 지연. 유출 대응 시 `0` |
| `serviceAccount.create` | `false` | `true` 면 차트가 ServiceAccount 를 만든다. `false` 면 기존 것을 쓴다 |
| `serviceAccount.automountToken` | `false` | 토큰 자동 마운트. 이 서버는 쿠버네티스 API 를 부르지 않으므로 기본 `false`. IRSA/Workload Identity 를 쓸 때만 `true` |
| `serviceAccount.annotations` | `{}` | `create: true` 일 때 SA 에 붙일 애노테이션. IRSA · Workload Identity 설정 자리 |
| `resources.limits.memory` | `6Gi` | 2026-08-05 OOM 대응으로 올린 값. **당분간 유지할 것** — 하향 전제는 [values.yaml](values.yaml)의 `resources` 주석 참고 |
| `gc.enabled` | `true` | GC CronJob 활성화. 초기 마이그레이션 중에는 `false` 권장. **이미지 `0.1.17` 이하에서는 끄면 메모리 회수 경로도 사라진다** (아래 참고) |
| `gc.phases` | `"multipart,orphan,purge,sweep"` | 이 CronJob 이 돌릴 GC 단계. 쉼표 구분. **기본값은 넷 다라 CronJob 하나가 전부 돈다.** `""` 로 두면 서버 기본값(`sweep` 을 뺀 셋)이 적용된다 — `sweep` 을 `fullSweep` 으로 뗄 때 쓰는 값이다. `sweep` 만 데이터 크기를 따라간다 (아래 참고). **`orphan` 을 빼면 렌더가 거부한다** |
| `gc.fullSweep.enabled` | `false` | 전량 스캔(`sweep`)만 도는 두 번째 CronJob. **켜지 않으면 렌더가 거부한다**(`gc.phases` 에 `sweep` 을 직접 넣은 경우는 제외). `schedule` 은 UTC 이고 기본값을 그대로 쓰지 말 것 |
| `config.multipartTtlSecs` | `86400` | GC 가 미완료 멀티파트를 만료로 보는 기준(초). **운영에서 줄이지 말 것** — 진행 중인 업로드가 `5xx` 로 실패한다 |
| `config.consoleEnabled` | `true` | `/_ui` 와 콘솔용 `/_api/*` 마운트 여부. `false` 여도 `/_api/gc/*` 는 남으므로 GC CronJob 은 그대로 동작한다 |
| `replicaCount` | `1` | **1을 유지할 것.** 늘리면 GC와 PUT 사이 durability 보호가 깨진다 (아래 참고) |
| `updateStrategy.type` | `Recreate` | 롤아웃 중 구·신 파드가 겹치지 않게 한다. 기본값 `RollingUpdate`는 `replicas=1`에서도 `maxSurge=1`이라 겹침 창이 생기고, 그 창에서 위 durability 보호가 깨진다. 대가는 롤아웃 중 짧은 중단 |
| `startupProbe.failureThreshold` | `60` | 기동 허용 시간 = `periodSeconds`(10초) × 이 값 = 600초 |

`maxUploadBytesInFlight` / `maxConcurrentUploads` 는 **cas-server 이미지 `0.1.16` 이상**에서만
동작합니다(`image.tag` 확인). 그 이하 이미지에서는 값을 설정해도 서버가 무시하므로, 상한이
걸린다고 믿는 상태로 방어 없이 운영하게 됩니다.
`limits.memory` 를 변경할 때 바이트 예산을 함께 조정하지 않으면, 상한이 걸리기 전에
OOMKilled 되거나(예산 > 한도) 방어선이 실효 없이 낮게 남습니다(예산 << 한도).

전체 설정값은 [values.yaml](values.yaml)을 참고하세요.

## 메트릭 스크레이프

`GET /_internal/metrics` 는 **`auth.metricsToken` 으로만 열립니다.** 이 엔드포인트에서만
통하고 다른 어떤 경로도 열지 않습니다.

**이 경로는 액세스 키로 열리지 않습니다** — SigV4 분기가 없어 root 키로도 `401` 입니다.
`metricsToken` 이 비면 auth 를 켠 배포에서는 `401`, NoAuth 배포에서는 무인증으로 열립니다.

`sealed-secret`에 `auth-metrics-token` 키를 추가합니다. deployment가 `optional: true`로
참조하므로 추가하지 않아도 파드는 기동하지만, **auth 를 켠 배포에서는 그때 스크레이프가
`401`** 입니다. **cas-server 이미지 `0.1.18` 이상**이 필요합니다.

**auth 가 꺼진 배포(`secrets.secretMasterKey` 가 빔)에서 `metricsToken` 만 채우고 admin·GC
토큰을 둘 다 비우지 마세요.** 그 조합에서는 서버가 기동을 거부합니다 — metrics 만 잠기고
`POST /_internal/gc`(blob 물리 삭제)가 무인증으로 열려, 401 을 보고 보호된다고 오해하게 되기
때문입니다. `replicaCount: 1` 이라 기동 실패는 곧 전면 중단입니다.

auth 를 켠 배포에서는 관리 평면이 토큰 없이도 401 로 닫히므로 해당하지 않습니다.

**Secret을 갱신했으면 파드를 직접 재시작해야 합니다.** `secrets.useExternalSecret: true`
(기본값)에서는 Helm이 Secret 내용을 볼 수 없어 체크섬을 걸 수 없고, 따라서
`kubectl apply -f sealed-secret.yaml`만으로는 파드가 교체되지 않습니다. env는 파드
생성 시점에 주입되므로 새 토큰이 반영되지 않은 채 스크레이프만 401이 되고,
원인이 "토큰이 틀렸나"로 보입니다.

```bash
kubectl rollout restart -n <namespace> deploy/<fullname>   # 릴리스명이 아니라 fullname
```

업그레이드와 함께 갱신한다면 **Secret을 먼저 적용**하고 `helm upgrade`하면 파드 교체와
함께 들어가므로 별도 재시작이 필요 없습니다.

차트는 `ServiceMonitor`를 포함하지 않습니다 — 모니터링 스택 구성이 배포마다 다르고, 차트가
만든 오브젝트가 그쪽 셀렉터에 맞지 않으면 **아무것도 수집되지 않는데 오브젝트는 존재하는**
상태가 되기 때문입니다. 대신 두 형태의 설정 예시를 아래에 둡니다.

### 노출되는 지표

| 지표 | 타입 | 단위 | 어느 풀·무엇 |
|---|---|---|---|
| `cas_upload_in_flight` | gauge | 건수 | 동시 업로드 |
| `cas_upload_in_flight_bytes` | gauge | 바이트 | 인플라이트 바디 합(Content-Length 기준) |
| `cas_upload_limit` | gauge | 건수 | `maxConcurrentUploads` (`0`=무제한). **바이트 예산의 상한 게이지는 없습니다** |
| `cas_upload_rejected_total` | counter | 건수 | 건수·바이트 거절을 **함께** 셉니다. 구분하려면 위 두 게이지를 함께 보십시오 |
| `cas_blob_lock_map_entries` | gauge | 건수 | 진행 중인 쓰기가 걸린 **고유 해시 수**(대기자 포함). 이미지 `0.1.18` 이상에서 **유휴 시 `0`** |
| `cas_db_pool_connections` | gauge | 건수 | **요청 경로 풀만.** 현재값이고 max 가 아닙니다 |
| `cas_db_pool_idle_connections` | gauge | 건수 | 요청 경로 풀만 |
| `cas_db_pool_acquire_timeouts_total` | counter | 건수 | HTTP 오류 응답이 된 것만. 요청 경로 풀 + 집계 풀 + `dry_run=true` 의 GC 풀을 **합산**하며, `/_internal/health` 의 풀 타임아웃은 **세지 않습니다** |
| `cas_blob_dedup_total` | counter | 건수 | **PUT 이 기존 blob 에 맞은 횟수.** 데이터셋 중복률이 아닙니다 — 아래 참고 |
| `cas_blob_put_bytes_total` | counter | 바이트 | |
| `cas_gc_deleted_blobs_total` | counter | 건수 | **GC 가 한 번 돌아야 등록됩니다** |
| `cas_gc_freed_bytes_total` | counter | 바이트 | 〃 |
| `cas_anonymous_get_total` | counter | 건수 | **`reason`·`cause` 라벨이 붙습니다.** `reason` 은 `unsigned` · `signed_valid` · `signed_invalid`, `cause` 는 `signed_invalid` 의 원인을 한 겹 더 가릅니다(나머지 둘은 `none`). `anonymousGet` 을 끄기 전에 깨질 소비자를 세는 값입니다 (아래 참고). `reason` 은 이미지 `0.1.24`, `cause` 는 `0.1.25` 이상 |
| `cas_gc_last_ran_at_seconds{phase}` | gauge | 유닉스 초 | 그 단계를 포함한 마지막 성공 실행의 시각. **파드가 재기동해도 남습니다**(기동 시 이력에서 되살립니다). 이미지 `0.1.25` 이상 |
| `cas_gc_last_duration_ms{phase}` | gauge | ms | 마지막 실행의 단계별 소요. 재기동 뒤 첫 실행까지 값이 없습니다 |
| `cas_gc_last_reclaimed_blobs{phase}` | gauge | 건수 | 그 단계가 회수한 blob 수. `orphan`·`sweep` 에만 나갑니다. **`sweep` 쪽이 후보 등록 누락을 보는 값입니다** |
| `cas_gc_last_status` | gauge | — | `0`=성공 `1`=오류 있음 `2`=실행 중. **`gc_runs.status` 와 다릅니다** — `errors > 0` 인 실행도 `1` 입니다 |
| `cas_gc_candidates` / `cas_gc_candidate_bytes` | gauge | 건수 / 바이트 | 회수 후보 큐. GC 실행이 끝난 시점의 값이라 `orphan` 이 큐를 비운 직후를 가리킵니다 |

**라벨이 붙는 `cas_*` 는 `cas_anonymous_get_total`(`reason`·`cause`)과 `cas_gc_last_*`(`phase`) 뿐입니다.**
같은 엔드포인트에 `axum_http_requests_total` ·
`axum_http_requests_duration_seconds` · `axum_http_requests_pending` 이 함께 나오고
이쪽은 `endpoint`/`method`/`status` 라벨을 답니다(경로는 라우트 패턴으로 정규화되므로
키마다 늘지는 않습니다).

**`cas_blob_dedup_total` 을 중복률로 읽지 마십시오.** 이 카운터가 세는 것은 **PUT 경로에서
기존 blob 을 만난 횟수**이고, 다음을 세지 않습니다.

- **`CopyObject`** — 기존 blob 을 가리키는 행만 추가하므로 이 값이 움직이지 않습니다.
- **프로세스 재시작 이전분** — 프로세스 수명 카운터라 파드가 바뀌면 `0` 부터 다시 셉니다.

**데이터셋 전체의 중복률은 이 값으로 구할 수 없습니다.** 그 값은 `/_api/stats` 의
`object_count` 와 `blob_count` 로 구합니다. 둘 다 조인 없는 집계라 기본 응답에 항상
들어 있습니다 — 무거운 용량 계산은 `?sizes=true` 를 붙였을 때만 돕니다.

```
개수 기준 중복률 ≥ 1 - blob_count / object_count
```

**하한입니다.** `blob_count` 는 `blobs` 전수라 GC 가 아직 회수하지 않은 blob 을 포함하고,
`object_count` 는 live 최신 버전만 셉니다. 분모가 부풀어 있으므로 실제 중복률은 이 값
이상입니다. 콘솔이 이 카드를 `≥` 로 표시하는 이유가 그것이고, GC 대기분이 live 오브젝트보다
많으면 값이 음수가 되므로 `N/A` 로 냅니다.

모수가 맞는 값(live 오브젝트가 참조하는 고유 blob 만)은 `?sizes=true` 가 필요하고, 그쪽은
`object_versions` × `blobs` 조인이라 데이터가 커지면 `statsStatementTimeoutSecs` 에 걸릴 수
있습니다(아래 "집계 조회 격리" 절).

**풀별 분리는 없습니다** — `cas_db_pool_connections` 로는 집계 격리가 동작하는지 판정할 수
없습니다. 격리 확인은 "집계 조회 격리" 절의 방법을 쓰십시오.

### Prometheus Operator 를 쓰는 경우

`ServiceMonitor` 를 직접 만드십시오. 포트는 **이름이 `http`** 입니다(`metrics` 가 아닙니다).

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: cas-server
  namespace: <cas 네임스페이스>
  labels:
    release: <Prometheus 릴리스명>     # Prometheus 의 serviceMonitorSelector 와 맞아야 합니다
spec:
  namespaceSelector:
    matchNames: ["<cas 네임스페이스>"]
  selector:
    matchLabels:
      app.kubernetes.io/name: cas-server
      app.kubernetes.io/instance: <helm 릴리스명>
  endpoints:
    - port: http
      path: /_internal/metrics
      interval: 30s
      authorization:
        type: Bearer
        credentials:
          name: <fullname>
          key: auth-metrics-token
```

`authorization` 은 Operator `0.49` 이상입니다. 그보다 낮으면
`bearerTokenSecret: {name: <fullname>, key: auth-metrics-token}` 을 쓰십시오.

### Operator 없이 `scrape_configs` 로 수집하는 경우

**`ServiceMonitor` 오브젝트는 Operator 가 없으면 아무 일도 하지 않습니다.** CRD 만 있고
컨트롤러가 없으면 `kubectl apply` 는 성공하고 리소스는 남지만, 그것을 읽어 스크레이프
설정을 만드는 주체가 없습니다. 그 경우 아래를 Prometheus 설정에 직접 넣으십시오.

```yaml
- job_name: cas-server-metrics
  scrape_interval: 30s
  scrape_timeout: 10s
  metrics_path: /_internal/metrics
  scheme: http
  authorization:
    type: Bearer
    credentials_file: /etc/secrets/cas-metrics/auth-metrics-token
  kubernetes_sd_configs:
    - role: endpoints
      namespaces:
        names: ["<cas 네임스페이스>"]
  relabel_configs:
    - source_labels: [__meta_kubernetes_service_label_app_kubernetes_io_name]
      action: keep
      regex: cas-server
    - source_labels: [__meta_kubernetes_service_label_app_kubernetes_io_instance]
      action: keep
      regex: <helm 릴리스명>
    - source_labels: [__meta_kubernetes_endpoint_port_name]
      action: keep
      regex: http
    - source_labels: [__meta_kubernetes_namespace]
      target_label: namespace
    - source_labels: [__meta_kubernetes_service_name]
      target_label: service
    - source_labels: [__meta_kubernetes_pod_name]
      target_label: pod
```

**`authorization.credentials_file` 은 Prometheus `2.26.0` 이상입니다.** 그보다 낮으면 그 세 줄을
`bearer_token_file: /etc/secrets/cas-metrics/auth-metrics-token` 한 줄로 바꾸십시오.

**토큰은 파일로 마운트합니다.** 설정이 ConfigMap 에서 오므로 시크릿 값을 그 안에 넣을 수
없습니다. `prometheus-community/prometheus` 차트라면 이렇습니다.

```yaml
server:
  extraSecretMounts:
    - name: cas-metrics-token
      mountPath: /etc/secrets/cas-metrics
      subPath: ""
      secretName: cas-metrics-token
      readOnly: true
```

**Secret 은 네임스페이스 자원이므로 Prometheus 쪽에 복사본이 필요합니다.**

```bash
kubectl -n <prometheus 네임스페이스> create secret generic cas-metrics-token \
  --from-literal=auth-metrics-token='<sealed-secret 의 같은 값>'
```

Secret 전체를 마운트하면 파일 이름이 키 이름이 되므로 경로가
`/etc/secrets/cas-metrics/auth-metrics-token` 이 됩니다. 파일 끝의 개행은 무시됩니다.

**`role: endpoints` 디스커버리에는 `services`·`endpoints`·`pods` 에 대한 `get,list,watch`
권한이 필요합니다.** 위 차트는 `rbac.create: true` 기본값에서 이미 부여합니다.

**어노테이션 디스커버리로는 붙일 수 없습니다** — `Authorization` 헤더를 넣을 수단이 없어
401 이 됩니다. 차트는 `prometheus.io/*` 애노테이션을 붙이지 않으므로, 과거에 손으로 붙여
두었다면 제거하십시오. 남아 있으면 위 job 과 별개로 계속 401 을 냅니다.

## GC 단계와 두 CronJob

GC는 네 단계이고 `sweep` 만 `blobs` 전체를 훑습니다. 나머지 셋은 인덱스나 후보 큐로
처리되어 규모의 영향을 받지 않습니다.

| 단계 | 무엇을 | 비용 |
|---|---|---|
| `multipart` | 만료된 미완료 멀티파트의 파트 회수 | 인덱스 |
| `orphan` | 회수 후보 큐를 확인해 blob 물리 삭제 | O(삭제·덮어쓰기 건수) |
| `purge` | 보존 기간 지난 삭제 레코드 정리 | 인덱스 |
| `sweep` | `blobs` 전량 안티조인 | **O(테이블 크기)** |

기본값은 CronJob 하나가 넷을 다 도는 것입니다. `sweep` 이 오래 걸리기 시작하면 이렇게 뗍니다.

```yaml
gc:
  schedule: "0 2 * * 0"       # UTC. 주간 — multipart, orphan, purge
  phases: ""
  fullSweep:
    enabled: true
    schedule: "0 3 1 * *"     # UTC. 월간 — sweep 만. 이 값을 그대로 쓰지 말 것
```

`schedule` 은 둘 다 UTC 입니다. `0 3 1 * *` 는 UTC+9 에서 정오이고, 그 시각에 전량 스캔이
돌면 같은 인스턴스의 다른 데이터베이스 페이지 캐시까지 밀려납니다. 백업·덤프 일정과
겹치지 않는 시각으로 정하십시오.

`gc.fullSweep` 은 미뤄도 되는 Job 이 아닙니다. 같은 내용을 가리키던 마지막 두 참조가 서로
다른 키에서 동시에 지워지면 후보가 등록되지 않고, 그렇게 빠진 blob 을 찾는 경로가 `sweep`
뿐입니다.

`helm install`·`upgrade` 가 거부하는 조합 둘입니다.

- `gc.phases` 에 `orphan` 이 없다 — 큐를 비우는 경로가 그것뿐입니다.
- `fullSweep` 이 꺼져 있고 `gc.phases` 에도 `sweep` 이 없다 — 전량 스캔이 사라집니다.

회수를 아예 돌리지 않을 의도라면 `gc.enabled: false` 로 두십시오.

주기는 데이터 크기가 아니라 **회수 대상이 쌓이는 속도**로 정하십시오. 스캔 비용은 회수할
blob 이 0건이든 수천 건이든 같습니다. 판단 기준과 미루는 비용 계산은
[docs/usage.md](docs/usage.md) 의 "주기를 정하는 기준" 을 참고하십시오.

`gc.phases` 는 이미지 `0.1.20` 이상이 해석합니다. **`sweep` 은 `0.1.25` 이상**이라,
그보다 낮은 이미지에 보내면 서버가 `400` 으로 거절하고 그 Job 이 실패합니다.

## 관리 API 자격증명 (이미지 `0.1.21` 이상)

관리 평면은 `/_admin/*`(액세스 키·정책 관리)과 GC(`POST /_internal/gc`, `GET /_api/gc/*`)
둘입니다. `/_admin/*` 은 액세스 키로만 열리고, GC 는 Bearer 토큰으로도 열립니다.

| 자격증명 | `/_admin/*` | GC | 폐기 | 로그의 행위자 |
|---|---|---|---|---|
| root 액세스 키 | 열림 | 열림 | 값 교체 + 재배포 | `CASKroot` |
| 관리 정책 액세스 키 | 정책대로 | 정책대로 | 그 키만 즉시 | `key_id` |
| GC 토큰 | 닫힘 | 열림 | 값 교체 + 재배포 | `<bearer>` |

| 액션 | 여는 것 |
|---|---|
| `cas:ReadAccessKeys` | 키·정책 목록 조회, 키 단건 조회 |
| `cas:ManageAccessKeys` | 키 발급·폐기, 정책 추가·삭제 **+ 위 조회 전부** |
| `cas:ReadGc` | `GET /_api/gc/*` |
| `cas:RunGc` | `POST /_internal/gc` **+ GC 조회** |

정책의 `"*"` 는 데이터 평면 액션에만 걸립니다 — 관리 권한은 이름을 적은 정책에만 붙습니다.
정의되지 않은 액션 이름은 `400` 으로 거절합니다.

**콘솔은 토큰을 받지 않습니다.** 화면은 로그인한 키의 정책으로 열리고, 판정은
`GET /_api/whoami` 한 번입니다. 권한이 없는 화면은 탭이 표시되지 않습니다.

| 화면 | 필요한 권한 |
|---|---|
| Keys 탭 (목록) | `cas:ReadAccessKeys` 또는 `cas:ManageAccessKeys` |
| 키 발급 · revoke 버튼 | `cas:ManageAccessKeys` |
| GC 탭 · Dashboard 의 Last GC | `cas:ReadGc` 또는 `cas:RunGc` |
| GC 실행 · Dry-run 버튼 | `cas:RunGc` |

사람마다 키를 하나씩 주면 관리자를 둘 이상 둘 수 있고, 한 사람을 끊을 때 나머지가 살아
있습니다. 부트스트랩은 root 키로 합니다.

`/_admin/*` 은 **SigV4 서명으로만** 열립니다. 아래 `$SIGV4` 는 서명 헤더 묶음을 뜻하며,
손으로 만들지 말고 `awscurl` 같은 서명 도구를 쓰십시오 (`--service s3`, region 은 아무
값이나 됩니다 — 서버는 클라이언트가 선언한 값으로 서명 키를 유도합니다).

```bash
curl -X POST "$BASE/_admin/access-keys" -H "$SIGV4" \
  -H "Content-Type: application/json" -d '{"description":"alice"}'

curl -X POST "$BASE/_admin/access-keys/$KEY_ID/policies" -H "$SIGV4" \
  -H "Content-Type: application/json" -d '{"effect":"allow","action":"cas:ManageAccessKeys"}'
```

조회는 셋입니다 (이미지 `0.1.24` 이상 — 단건 조회와 `?active=` 가 그 버전부터입니다).

```bash
curl "$BASE/_admin/access-keys"              -H "$SIGV4"
curl "$BASE/_admin/access-keys?active=true"  -H "$SIGV4"
curl "$BASE/_admin/access-keys/$KEY_ID"      -H "$SIGV4"
```

**단건 조회는 폐기된 키도 `200` 으로 돌려줍니다** (`is_active: false`). `404` 는 그 `key_id`
가 없을 때뿐입니다 — 「폐기됐다」 와 「애초에 없다」 를 가르기 위한 것이라, 상위 시스템이
폐기 여부로 재발급을 판정한다면 이 구분에 기대십시오.

`?active=` 는 폐기 여부만 봅니다. **만료된 키도 폐기하지 않았으면 `active=true` 에
들어옵니다** — 만료와 폐기는 다른 상태입니다.

> **`cas:ManageAccessKeys` 는 사실상 전권입니다.** 그 키는 아무 정책이나 붙인 새 키를 만들 수
> 있으므로 데이터 전체에 접근하는 키도 만들 수 있습니다.

### 어느 자격증명을 어디에 주는가

쓰는 곳마다 필요한 만큼만 주십시오. 행위자가 로그에 남는 쪽(액세스 키)을 먼저 고려하십시오.

| 쓰는 곳 | 주는 것 |
|---|---|
| 사람 · 키 관리를 대신하는 외부 시스템 | 관리 정책 액세스 키 |
| GC CronJob | GC 토큰 (`auth-gc-token`) |
| 모니터링 스크레이프 | metrics 토큰 (`auth-metrics-token`) |
| 부트스트랩 · 비상 접근 | root 액세스 키 |

GC 토큰에는 켜기/끄기 값이 없습니다 — Secret 의 `auth-gc-token` 에 값을 넣으면 서버와
CronJob 이 둘 다 그것을 씁니다. 비면 auth 를 켠 배포에서 GC 의 bearer 경로가 닫힙니다
(`cas:RunGc` 를 가진 키의 SigV4 경로는 그대로입니다).
`useExternalSecret: false` 로 차트가 Secret 을 만드는 경우에만 `secrets.gcToken` 에 넣습니다.

**admin 토큰은 폐기됐습니다**(이미지 `0.1.24` 이상). **새 배포에서는 `auth-admin-token` 을
만들지 마십시오** — 차트 `0.1.31` 부터 기본 설치가 그 키를 만들지 않고, deployment 도
`optional` 로 참조합니다.

**이미 그 키를 들고 있으면 지우셔도 됩니다.** `0.1.30` 까지는 필수 참조라 지우면 파드가
기동하지 못했습니다. 값만 비운 채로 두어도 되고, 그 경우 서버가 무시했다고 기동 로그에
남깁니다 — sealed-secret 을 회전할 때 함께 지우는 것이 편합니다.

`gcToken` · `auth.metricsToken` 의 admin 토큰 폴백도 함께 사라졌습니다. **올리기 전에 그
둘을 채웠는지 확인하십시오** — 비어 있으면 GC 와 스크레이프가 `401` 이 됩니다. 사유와 이행
절차는 CHANGELOG `0.1.28`·`0.1.31` 을 보십시오.

NoAuth 배포(`secretMasterKey` 가 빔)에는 액세스 키가 없으므로 `gcToken` 이 GC 의 유일한
자격증명입니다. 그 모드에서 `metricsToken` 이 비면 메트릭은 무인증으로 열립니다.

## 대량 적재 중에는 GC를 끄십시오 (모든 이미지 버전)

대량 적재 중에는 `gc.enabled: false`를 권장합니다. GC는 orphan 후보마다 해시별 쓰기 락을
물리 삭제와 DB 삭제 구간 내내 쥐므로 같은 내용을 올리는 PUT이 그동안 대기하고, blob 전수
조인이 DB에 부하를 더하기 때문입니다.

**적재가 끝나면 다시 켜십시오.** 꺼 둔 동안 orphan blob이 회수되지 않아 오브젝트
스토리지 사용량이 조용히 누적됩니다.

## GC와 메모리 회수 (이미지 `0.1.17` 이하)

**이미지 `0.1.17` 이하에서는 GC 주기가 곧 서버 내부 해시별 쓰기 락 테이블의 회수
주기입니다.** 항목은 고유 해시마다 하나씩 생기고 항목당 약 190~240바이트입니다.

| `gc.enabled` | 회수 | 쌓이는 양 |
|---|---|---|
| `false` | 없음 | 파드 수명 동안 단조 증가 |
| `true` | `gc.schedule` 주기 | 그 주기만큼. 기본 주 1회면 최대 일주일치 |

**GC를 켜 뒀다고 해당 없는 항목이 아닙니다.** 2026-08 운영 사례에서 유휴 메모리 바닥값이
4.9일간 하루 330~430 MiB씩 단조 상승했고, 주 1회 주기라면 그 사이 최대 2.3~2.9 GiB가
쌓입니다. 대량 적재는 고유 해시율이 요청율과 거의 같은 구간이라 증가율이 최대가 됩니다.

선택지는 셋이고, **위로 갈수록 낫습니다.**

1. **이미지를 `0.1.18` 이상으로 올린다.** 근본 해결이고 아래 둘이 필요 없어집니다.
2. **파드를 재시작한다.** 이 테이블은 프로세스 메모리라 재시작하면 통째로 사라집니다.
   단편화까지 함께 회수되므로 회수량이 가장 큽니다. 대신 `replicaCount: 1`이라
   그동안 중단됩니다. 상승률로 한도 도달 시점을 계산해 그보다 짧은 주기로 잡으세요.
3. **중단이 곤란하면 `POST /_internal/gc?dry_run=true`를 주기 실행한다.** 이 요청은
   **blob 물리 삭제를 하지 않고 GC advisory lock도 잡지 않으면서** 그 테이블을
   회수합니다. GC를 다시 켤 필요가 없습니다.

   **다만 이 요청에는 상한이 필요합니다.**
   이 요청이 도는 읽기 전용 쿼리 둘 중 하나가 orphan 후보 COUNT인데, `blobs` ×
   `object_versions` 안티조인 전수 집계라 데이터가 커지면 디스크로 스필합니다 —
   2026-08 사고에서 임시 파일 352.8 GB를 만든 것과 같은 형태의 쿼리입니다.
   `statsStatementTimeoutSecs`는 이 쿼리를 덮지 않습니다. 같은 SQL이지만 GC 풀에서
   돌기 때문입니다.

   **그런데 그 상한인 `config.gcStatementTimeoutSecs`는 이미지 `0.1.18` 이상에서만
   동작합니다** — 이 절의 독자에게는 없는 설정이고, 넣어도 조용히 무시됩니다. 그래서
   `0.1.17` 이하에서는 PostgreSQL 쪽에서 거는 수밖에 없습니다.

   ```sql
   ALTER ROLE <cas 사용자> SET statement_timeout = '300s';
   ```

   이 방법은 GC 뿐 아니라 그 롤의 **모든** 쿼리에 걸리므로, 대용량 업로드의 메타데이터
   커밋까지 자를 수 있습니다. 그것이 곤란하면 이 선택지 대신 위 2번(재시작)을 쓰십시오.

   또 이 요청은 advisory lock도 in-flight 플래그도 잡지 않으므로 **중복 호출이 쌓일 수
   있습니다.** 이전 실행이 끝났는지 확인한 뒤 다음을 보내십시오.

   쓰기 경로와의 경합은 **"없음"이 아니라 "짧음"**입니다. 회수는 락 테이블을
   순회하는데 자료구조가 샤드로 나뉘어 있고 **한 번에 한 샤드씩** 잠급니다.
   그 순간 같은 샤드에 해당하는 해시의 쓰기만 대기하고 나머지는 진행됩니다.
   전체가 멈추지는 않습니다.

3번은 **`kubectl exec`로 실행할 수 없습니다** — 런타임 이미지(`debian:bookworm-slim`)에
`curl`도 `wget`도 없습니다. 클러스터 안에서 주기 실행하려면 `curl`이 있는 이미지의
CronJob이 필요합니다(`templates/gc-cronjob.yaml`이 참고가 됩니다 — 같은 방식으로
Secret에서 `auth-gc-token`을 주입하면 토큰이 클러스터 밖으로 나가지 않습니다).

**일회성 확인**은 포트포워드 후 로컬 `curl`로 됩니다:

```bash
NS=<namespace>
REL=cas-server     # 리소스명. 릴리스명이 'cas-server'를 포함하면 릴리스명 그대로,
                   # 아니면 '<릴리스명>-cas-server' 입니다

# 로컬 18080은 비어 있는 아무 포트나 됩니다. 원격은 서비스의 named port 'http'라
# service.port를 기본값과 다르게 두었어도 그대로 동작합니다.
# (config.port는 별개입니다 — service.targetPort와 프로브 포트가 따라오지 않으므로
#  바꾼다면 그 셋을 함께 맞춰야 합니다.)
kubectl port-forward -n "$NS" "svc/$REL" 18080:http &
TOKEN=$(kubectl get secret -n "$NS" "$REL" \
          -o jsonpath='{.data.auth-gc-token}' | base64 -d)

time curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:18080/_internal/gc?dry_run=true"
```

**주기를 정하기 전에 이 소요 시간을 재세요.** 두 가지가 합쳐진 값입니다 — 읽기 전용
쿼리 두 개(그쪽 규모에서 얼마나 걸리는지는 재 봐야 압니다)와 락 테이블 순회입니다.
무거우면 6시간 주기로도 하루 330 MiB 상승이 약 83 MiB 톱니로 줄어듭니다.

회수 건수는 cas-server 파드 로그에 남습니다 —
`GC: blob write lock 항목 회수  swept=<n> remaining=<n>` (0건이면 로그가 없습니다).

**이미지 `0.1.18` 이상은 요청이 끝날 때 즉시 회수하므로 이 완화가 전부 필요 없습니다.**
그 버전부터 `cas_blob_lock_map_entries`는 "진행 중인 쓰기 건수"를 뜻하고 유휴 시 0이며,
0으로 떨어지지 않으면 항목 유출 신호입니다.

현재 이미지 태그 확인:

```bash
kubectl get deploy "$REL" -n "$NS" \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="cas-server")].image}'; echo
```

## 집계 조회 격리 (이미지 `0.1.18` 이상)

`/_api/stats`, `/_api/buckets`, `/_api/backends` 의 blob 집계, `/_api/gc/orphan-count` 는
전 테이블 집계입니다.

`/_api/buckets/{bucket}/objects` 의 서브폴더 조회도 이미지 `0.1.23` 까지는 그랬습니다.
**`0.1.24` 부터 비용이 그 레벨의 항목 수에 비례합니다** — 하위 폴더를 subtree 째 건너뛰므로
폴더 안의 파일 수는 영향을 주지 않습니다. 그래도 계속 이 격리 풀에서 돕니다: 한 레벨의
항목이 많으면 여전히 길어질 수 있습니다.

**한 레벨의 상한이 있습니다** — 하위 폴더 10,000 개, 훑는 항목 20,000 개.

그보다 큰 레벨은 **잘리고, 응답에 그 사실이 실리지 않습니다.** `prefixes` 는 페이지를 나누지
않는 계약이라(폴더는 매 페이지 전량, 파일만 `after` 로 이어 받음) 「더 있음」을 적을 자리가
없기 때문입니다. **두 상한 모두 서버가 경고 로그를 남기므로 그쪽으로 확인하십시오.** 두 줄 다 `bucket` 과
`prefix` 를 필드로 남기므로 어느 레벨인지 바로 나옵니다.

```bash
# 걸음 상한: steps 필드가 있는 쪽
kubectl logs -n <namespace> deploy/<fullname> | grep 'steps=' | grep 상한

# 개수 상한
kubectl logs -n <namespace> deploy/<fullname> | grep '개수 상한'
```

문구 전문이 아니라 필드(`steps=`)와 짧은 조각으로 찾는 것이 안전합니다 — 문장은 다듬어질 수
있지만 필드 이름은 그대로입니다.

걸음 상한 쪽이 더 눈에 안 띕니다. **그 레벨에 직접 파일이 많으면 걸음이 파일에 먼저 소진돼
하위 폴더가 하나도 보이지 않을 수 있습니다** — 폴더 개수는 0 이라 개수 상한에는 닿지 않습니다.
파일 목록은 정상입니다.

파일 쪽이 잘리는 경우에는 위 경고가 반드시 함께 뜹니다 — `limit` 상한이 2,000 이라
10,000(폴더) + 2,001 이 20,000(걸음)보다 작고, 따라서 파일이 걸음 상한에 닿으려면 폴더 쪽이
이미 상한을 넘었어야 하기 때문입니다.

`/_api/stats` 와 `/_api/buckets` 는 **용량 계산을 기본에서 뺐습니다.** 그 둘만
`object_versions` × `blobs` 조인을 요구하기 때문이고, 한 문장에 두면 상한에 걸릴 때
조인이 없는 나머지 값까지 함께 죽습니다. 용량이 필요하면 `?sizes=true` 를 붙이십시오 —
그 요청만 무거운 쪽으로 갑니다.
데이터가 커지면 조인이 디스크로 스필하고, 2026-08 고객 환경에서 그 스필이 임시 파일
**352.8 GB** 를 만들며 적재를 **2시간 55분** 막았습니다. 파드 재시작으로 끊을 수 없었습니다.

이미지 `0.1.18` 부터 이 쿼리들은 **커넥션 1개짜리 별도 풀**에서 돕니다.

| 장치 | 값 | 역할 |
|---|---|---|
| 커넥션 1개 | 고정 | 동시성 상한. 대시보드를 몇 번 새로고침해도 DB에 도는 집계는 항상 1건 |
| `statsStatementTimeoutSecs` | `30` | PostgreSQL 이 실제로 문장을 취소하게 하는 유일한 수단 |
| `max_parallel_workers_per_gather = 0` | 고정 | `work_mem` 은 워커마다 따로 쓴다 — 워커가 붙으면 스필이 배가된다 |
| `statsWorkMemMb` | `0` | 올리면 해시 조인 배치 수가 줄어 스필이 준다. **PG 쪽 메모리**를 쓴다 |
| 캐시 60초 + single-flight | `/_api/stats` 만 | 동시 요청이 쿼리를 하나만 띄운다 |

**조회가 실패하면 `/_api/stats` 는 지난 값을 그대로 내보냅니다.** 나이 제한이 없으므로
장애가 이어지는 동안 임의로 오래된 숫자가 보일 수 있고, 화면에 그 사실이 표시되지
않습니다. 실패 직후 30초는 재질의하지 않으며(캐시된 값이 없으면 오류), 대시보드 숫자가
멈춘 것처럼 보이면 DB 쪽을 먼저 보십시오.

**다만 `?sizes=true` 요청에 용량 없는 지난 값을 주지는 않습니다.** 그 경우는 오류입니다 —
`null` 을 200 으로 돌려주면 화면이 그것을 "중복이 없다"로 읽습니다. 쿨다운도 비용 등급별로
갈라져 있어, 용량 계산이 실패해도 기본 조회는 그대로 응답합니다.

**왜 타임아웃만으로는 부족한가.** 취소된 쿼리의 커넥션은 sqlx 가 닫지 않고 유휴 풀로
반납합니다. 다음 획득자가 그 커넥션을 뽑으면 버려진 문장이 끝날 때까지 막힙니다 —
즉 타임아웃된 집계 요청 하나가 풀 커넥션 하나를 오염시킵니다. `/_internal/health` 가
요청 풀을 쓰기 때문에, 격리가 없으면 **인증 없는 GET 한 건이 파드를 Service 엔드포인트에서
밀어낼 수 있습니다.**

파드당 PostgreSQL 커넥션은 **최대** `dbMaxConnections + gcDbMaxConnections + 1` 입니다.
기본값 기준 `20 + 2 + 1 = 23`. 상시 점유가 아니라 상한입니다 — 기동 직후 실제로 열리는
것은 4개(요청 풀의 `dbMinConnections: 2` + 각 풀 1개)이고, 유휴가 이어지면 2개까지
내려갑니다. PostgreSQL `max_connections` 사이징은 이 상한으로 잡으십시오.

차트 기본값은 서버 기본값과 다릅니다 — `dbMaxConnections` 는 차트 20 / 서버 10,
`dbAcquireTimeoutSecs` 는 차트 10 / 서버 30 입니다. 차트 밖에서 같은 부등식을 쓰면
`10 + 2 + 1 = 13` 이 됩니다.

지켜야 할 부등식:

```
replicaCount × (dbMaxConnections + gcDbMaxConnections + 1) < PG max_connections
```

## 삭제와 되돌림 창

`config.softDeleteRetentionSecs` (기본 7일)는 soft-delete 된 `object_versions` **행**의
보존 기간입니다. GC 마지막 단계의 `DELETE ... WHERE deleted_at < NOW() - ...` 가 이 값을
씁니다.

**이 값은 되돌림 창이 아닙니다.** 그 문장은 행만 지우고 blob 파일은 건드리지 않습니다.
blob 물리 삭제는 GC 의 orphan 정리가 따로 하며 이 값과 무관합니다 — DELETE 가 커밋되는
순간 blob 은 orphan 후보가 되고, **다음 GC 실행에서 파일이 사라집니다.** 그때 그 해시의
soft-delete 행도 같은 트랜잭션에서 함께 지워지므로, 이 값이 실제로 관장하는 것은 그때
치우지 못한 행뿐입니다(delete marker, 그리고 다른 객체가 같은 blob 을 참조 중이라 blob 이
살아 있는 행).

**되돌림 창은 다음 GC 실행까지입니다.** 기본 스케줄이 주 1회(일요일 02:00)이므로 최대
그만큼이지만, 보장이 아닙니다 — `POST /_internal/gc` 를 수동으로 치면 즉시 닫히고,
비버저닝 버킷은 같은 키에 새 PUT 이 들어오면 그 시점에 닫힙니다. GC 가 지나간 뒤에는
blob 과 행이 함께 사라져 백업 복원 외에 방법이 없습니다. 창 안이라면 되살릴 수 있지만
DB 를 직접 고쳐야 하므로, 필요하면 GC 를 먼저 멈추고(`gc.enabled: false`) 지원팀에
문의하십시오.

실수 삭제로부터 보호하는 표준 수단은 S3 와 마찬가지로 **버킷 버저닝**입니다. 다만 한 번
켜면 끌 수 없고(`Suspended` 까지만 가능), nexus 와 연동하는 버킷이라면 이득이 크지
않습니다 — nexus 는 버전을 데이터셋 단위로 관리하고 cas 객체를 참조할 때 `versionId` 를
쓰지 않으므로(항상 최신을 읽습니다) 켜도 사용자에게 이전 버전이 보이지 않는 반면,
`object_versions` 행 누적은 그대로 옵니다.

## 오브젝트 스토리지 lifecycle 규칙 (S3 모드)

GC 가 회수하지 못하고 새는 객체가 세 자리에 있습니다. 스토리지 쪽 lifecycle 규칙이 그
마지막 방어선인데, **프리픽스마다 필요한 규칙 종류가 다릅니다.**

### 실효 프리픽스를 먼저 확인하십시오

`storage.s3.keyPrefix` 를 비워 두면 **서버가 `cas/` 를 씁니다** — 버킷 루트에 쓰는 선택지는
없습니다. 즉 차트 기본값 그대로면 실제 키는 `cas/objects/…` 입니다. 규칙을 `parts/` 에 걸면
아무것도 매치하지 않습니다. 기동 로그 첫 줄의 설정 출력에서 실제 값을 확인하십시오.

아래 표의 `{prefix}` 는 그 실효 프리픽스입니다(기본값이면 `cas/`).

### 프리픽스별 규칙

| 프리픽스 | 무엇이 들어 있나 | 저장 형태 | 걸 규칙 | 권장 TTL |
|---|---|---|---|---|
| `{prefix}objects/` | **살아 있는 blob** | 평범한 객체 + 대용량 쓰기 중의 네이티브 멀티파트 | **`AbortIncompleteMultipartUpload` 만.** `Expiration` 을 걸면 데이터가 지워집니다 | 개시 후 7일 |
| `{prefix}tmp/` | 업로드 스테이징 (아래 조건에서만 생깁니다) | 네이티브 멀티파트 + 완료 후 남은 평범한 객체 | **둘 다** | 7일 |
| `{prefix}parts/` | 멀티파트 업로드의 파트 | **평범한 객체** | **`Expiration` 만** | 7일 |

**`parts/` 에 `AbortIncompleteMultipartUpload` 를 걸면 아무것도 회수하지 않습니다.** 그 규칙은
스토리지 자신의 네이티브 멀티파트 상태에만 듣는데, cas-server 는 파트를 **평범한 객체로**
그 프리픽스 아래 씁니다. 프리픽스로 열거되는 것이 그 증거입니다.

**`tmp/` 는 스트리밍 경로에서만 씁니다.** `Content-Length` 가 `config.inlineHashLimitBytes`
(기본 256 MiB)를 넘거나 아예 없을 때(chunked)입니다. 그 밖의 `PUT` 은 최종 키에 바로 쓰므로
이 프리픽스를 거치지 않습니다. **그런 요청이 없는 배포에서는 이 아래에 아무것도 생기지
않습니다** — 규칙을 걸기 전에 실제로 무엇이 있는지 보십시오.

**`objects/` 에는 절대 `Expiration` 을 걸지 마십시오.** 살아 있는 blob 이 그 아래 있습니다.
그 프리픽스에 필요한 것은 대용량 쓰기가 중간에 죽었을 때 남는 네이티브 멀티파트 상태를
치우는 것뿐이고, 그것은 `AbortIncompleteMultipartUpload` 가 합니다 — 이 규칙은 완성된 객체를
건드리지 않습니다.

### TTL 을 7일로 두는 이유

서버는 만료된 미완료 업로드의 파트를 GC 가 정리합니다. 기준은
`config.multipartTtlSecs`(기본 86400초 = 24시간)이고, 이미지 `0.1.20` 이상에서 설정으로
바꿀 수 있습니다. 그 이하는 24시간 고정입니다.

lifecycle 은 **그 정리가 실패했을 때의 백스톱**이므로 그 값보다 넉넉해야 합니다.
`multipartTtlSecs` 를 올리셨다면 여기 TTL 도 함께 올리십시오. 너무 짧게
잡으면 진행 중인 업로드의 파트가 조립 전에 사라져 **쓰기가 5xx 로 실패합니다** — 읽기에서
데이터가 비는 형태가 아니라 쓰기 실패로 드러나므로 즉시 눈에 띕니다.

### 회수되는지 확인하는 방법

목록 API 없이, 프로덕션 쓰기 없이 확인할 수 있습니다.

```bash
# 1) 미완료 업로드 목록 — 이 응답은 PostgreSQL 에서 옵니다(스토리지 목록 API 를 타지 않음)
curl -s "http://<host>/<bucket>?uploads"

# 2) 그 uploadId 의 파트를 정확한 키로 조회 — 파트가 평범한 객체라 HEAD 가 됩니다
#    TTL 전 200, 만료 후 404 면 규칙이 집행된 것입니다
```

**규칙이 펌웨어에서 지원되는지는 넣어 본 뒤 읽어 보면 알 수 있습니다.** lifecycle 설정을
PUT 한 뒤 다시 GET 해서 그 요소가 그대로 돌아오는지 보십시오 — 지원하지 않는 어플라이언스는
거부하거나 조용히 그 요소를 빼고 저장합니다.

### GC 의 파트 정리가 실패하고 있지 않은지 함께 보십시오

GC 는 파트를 지울 때 **스토리지의 목록 API** 를 씁니다. 그 API 가 실패하는 백엔드에서는
파트 정리가 매번 실패하고, 그것이 누출의 원인일 수 있습니다. 이미지 `0.1.18` 부터 이 실패가
GC 결과에 드러납니다.

```bash
curl -s -H "Authorization: Bearer $GC_TOKEN" http://<host>/_api/gc/last-result
```

`errors` 가 0 이 아니면 그것입니다. **`status` 는 `success` 로 남으므로 `status` 가 아니라
`errors` 를 보십시오.**

## 서비스 어카운트

**`0.1.23` 까지 `values.yaml` 의 `serviceAccount` 블록은 통째로 무시됐습니다.** 어떤
템플릿도 참조하지 않아 `create: true` 로 둬도 ServiceAccount 가 만들어지지 않았고
파드에 지정되지도 않았습니다. `0.1.24` 부터 Deployment 와 GC CronJob 양쪽에 배선됩니다.

```yaml
serviceAccount:
  create: true
  name: ""                 # 비우면 fullname
  automountToken: false    # 기본값
  annotations: {}
```

| `create` | `name` | 결과 |
|---|---|---|
| `true` | `""` | fullname 으로 SA 생성 |
| `true` | `my-sa` | `my-sa` 로 SA 생성 |
| `false` | `""` | 네임스페이스의 `default` SA 사용 (생성 없음) |
| `false` | `existing-sa` | `existing-sa` 사용 (생성 없음) |

`automountToken` 은 **기본 `false`** 입니다. 이 서버는 쿠버네티스 API 를 부르지 않는데,
마운트된 토큰은 컨테이너가 뚫렸을 때 그대로 API 접근 수단이 됩니다. `auth.anonymousGet`
이 기본 `true` 이고 NodePort 로 노출되는 배포라 표면을 늘리지 않는 편이 낫습니다.

**`0.1.24` 부터 `default` SA 의 토큰 자동 마운트가 막힙니다.** 사이드카 등으로 쿠버네티스
API 를 쓰고 계셨다면 `automountToken: true` 로 되돌리세요.

IRSA / Workload Identity 를 쓰는 경우 토큰이 필요하므로 둘을 함께 설정합니다.

```yaml
serviceAccount:
  create: true
  automountToken: true
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/cas-server
```

## 릴리스 전 점검 — 선언됐는데 렌더되지 않는 키

Helm 은 쓰이지 않는 값에 오류를 내지 않습니다. 그래서 `values.yaml` 에 키를 선언하고
템플릿에서 참조하지 않으면 **설정해도 조용히 무시되고, 운영자는 고쳤다고 믿습니다.**
이 게이트가 실제로 잡은 것은 넷입니다 — cas-server 의 `config.requestTimeoutSecs`(문서가
언급하는데 미렌더)와 `serviceAccount.*`, nexus-server 의 `serviceAccount.*`, 그리고 과거
cas-server 의 `terminationGracePeriodSeconds`.

```bash
# 저장소 기준입니다 — 이 스크립트는 차트 tgz 에 들어가지 않습니다.
python scripts/check-unrendered-values.py                    # charts/ 전체
python scripts/check-unrendered-values.py charts/cas-server  # 특정 차트
```

릴리스 CI 가 `charts/` 아래 모든 차트에 이 검사를 돌리고, 미참조 키가 있으면 실패합니다.
`resources` 처럼 조상이 `toYaml` 로 통째로 소비되는 블록은 정상으로 분류합니다.

**한계**: `.Values.*` 와 템플릿만 대조하므로 **렌더된 TOML 의 서버측 키 이름 오타는
잡지 못합니다**(서버도 `deny_unknown_fields` 가 없어 조용히 무시합니다). 설정 키를
추가·변경할 때는 렌더된 ConfigMap 을 실제 바이너리에 먹여 기동 로그의 `적용된 설정`
줄로 확인하십시오.

## 레플리카 수

**`replicaCount` 는 1을 유지하세요.** 처리량이 부족하면 레플리카 대신 파드 리소스를 키웁니다.

GC의 blob 물리 삭제와 진행 중인 PUT 사이의 durability 보호가 cas-server **프로세스 내부**
per-hash 뮤텍스에 의존합니다. 파드가 둘 이상이면 이 락이 공유되지 않아, 한 파드의 GC가
다른 파드에서 커밋 직전인 blob을 참조 없음으로 오판해 물리 삭제할 수 있습니다. 그 결과
메타데이터만 남고 실체 파일이 사라진 객체가 생깁니다. GC CronJob은 Service로 요청을
보내므로 어느 한 파드에서 실행되고, 레플리카가 1개일 때만 GC와 PUT이 같은 프로세스에서
같은 뮤텍스를 잡습니다.

**롤아웃 중에도 파드가 겹치면 안 됩니다.** 그래서 `updateStrategy.type: Recreate`가
기본값입니다. 쿠버네티스 기본값인 `RollingUpdate`는 `replicas: 1`에서도
`maxSurge = ceil(0.25) = 1`, `maxUnavailable = floor(0.25) = 0`이 되어 구·신 파드가
동시에 Ready 상태가 됩니다 — 위 근거가 그 창에서 그대로 깨집니다. `helm upgrade`뿐
아니라 `kubectl rollout restart`도 마찬가지입니다.

대가는 롤아웃 중 짧은 중단입니다. `replicaCount: 1`이므로 노드 재기동만으로도 어차피
생기는 중단이고, durability를 그 대가로 사는 편이 낫다고 판단했습니다. 무중단이 더
중요해서 `RollingUpdate`로 되돌린다면 위 겹침 위험을 감수하는 것이므로 그 결정을
기록으로 남기세요.

## 헬스체크

세 프로브가 각각 다른 질문에 답합니다. **같은 엔드포인트를 돌려쓰지 마세요.**

| 프로브 | 엔드포인트 | 확인 대상 |
|--------|-----------|----------|
| `startupProbe` | `GET /_internal/live` | 기동(DB 마이그레이션 포함) 완료 여부. 성공 전까지 나머지 둘은 평가되지 않음 |
| `livenessProbe` | `GET /_internal/live` | 프로세스 응답성만. **의존성을 보지 않음** |
| `readinessProbe` | `GET /_internal/health` | **DB에 닿는지** + 백엔드 가용성. 닿지 못하면 503 (S3 모드에서 백엔드 검사는 항상 통과 — 아래 참고) |

### readinessProbe.timeoutSeconds 는 dbAcquireTimeoutSecs 보다 커야 합니다

`/_internal/health` 는 DB 커넥션을 얻지 못하면 `config.dbAcquireTimeoutSecs` 만큼 붙들려
있습니다. `timeoutSeconds` 가 그보다 짧으면 **서버가 판정을 내리기 전에 프로브가 먼저
끊깁니다.** 기본값은 `12 > 10` 으로 맞춰져 있습니다. `dbAcquireTimeoutSecs` 를 올리면
이 값도 함께 올리세요. 차트는 렌더 시점에 이 부등식을 검증하고, 어긋나면 설치가
실패합니다.

**차트 밖에서 돌리거나 `extraEnv` 로 값을 덮어쓰면 그 검증이 듣지 않습니다.** 서버는
프로브 값을 볼 수 없으므로 그 경우 아무 경고도 하지 않습니다. `CAS__READINESS_PROBE_TIMEOUT_SECS`
에 실제 프로브 값을 넣으면 서버가 기동 시 같은 부등식을 검사하고 어긋날 때만 경고합니다.


DB 가 죽은 것과 바쁜 것은 대응이 다르고, 이미지 `0.1.18` 부터 서버가 그 둘을 구분합니다.

| 상황 | 응답 | 이유 |
|---|---|---|
| DB 커넥션 풀 포화 (DB는 살아있음) | `200`, `status: "saturated"` | 프로세스는 정상 서빙 중이다 |
| DB에 못 닿음 | `503`, `status: "degraded"` | 의존성이 죽었다 |

**`storage.mode: "s3"` 에서는 백엔드 검사가 사실상 동작하지 않습니다.** S3 백엔드의
가용성 판정은 항상 참을 돌려주므로(원격 스토리지에 대한 저렴한 존재 확인 수단이 없습니다),
readiness 가 실질적으로 보는 것은 DB 뿐입니다. NFS 모드에서는 마운트 경로 존재를 실제로
확인합니다. 백엔드가 오프라인이면 `degraded`(503)가 되는 것은 NFS 모드에 해당합니다.

`replicaCount` 가 1로 고정되므로 **포화만으로 파드를 빼면 부하를 넘길 곳이 없어 열화가
전면 장애로 승격됩니다.** 다중 레플리카라면 부하를 덜어내는 의미가 있지만 여기서는
반대로 작동합니다. 2026-08 고객 환경에서 실제로 그렇게 됐습니다 — 집계 쿼리가 요청 풀
커넥션을 오염시켜 ping 이 붙들렸고, 프로브가 연속 실패해 유일한 파드가 엔드포인트에서
빠졌습니다. DB 는 죽은 게 아니라 바빴을 뿐입니다.

`livenessProbe` 를 `/_internal/health` 로 두면 안 됩니다. DB failover(보통 30~120초)나 NAS
순간 장애에 쿠버네티스가 파드를 죽이는데, 재시작으로는 외부 의존성이 복구되지 않습니다.
오히려 재기동 시 initContainer가 DB를 기다리고 CrashLoopBackOff 백오프(최대 5분)가 붙어
중단이 원래 장애보다 길어집니다. `replicaCount` 가 1이므로 그 시간이 곧 전면 중단입니다.
의존성 상태는 readiness가 판단해 Service 엔드포인트에서 빼는 것이 맞는 처리이고,
의존성이 돌아오면 파드는 그대로 복귀합니다.

`/_internal/live` 는 **cas-server 이미지 `0.1.17` 이상**에서만 제공됩니다. 이미지를 `0.1.16` 이하로
고정해 쓰는 경우 `livenessProbe.httpGet.path` 와 `startupProbe.httpGet.path` 를
`/_internal/health` 로 되돌리세요. 그러지 않으면 404가 프로브 실패로 계산되어 파드가
계속 재시작합니다.

### startupProbe 예산

DB 마이그레이션은 HTTP 리스너가 열리기 전에 수행되므로, 그동안 프로브는 반드시 실패합니다.
`startupProbe` 가 없으면 "기동 소요 > liveness 예산"인 순간 파드가 구조적으로 죽습니다
(이미지 0.1.16 최초 배포에서 `object_versions` 인덱스 생성이 114초 걸려 실제로 발생).

기본 예산은 600초입니다. 대용량 테이블에 인덱스를 추가하는 마이그레이션이 포함된
릴리스에서는 배포 전 `SELECT count(*) FROM object_versions;` 로 소요를 가늠하고 필요하면
`startupProbe.failureThreshold` 를 늘리세요. 이 예산마저 넘으면 kill → 재시도 → kill 이
반복되어 빠져나오지 못합니다.

## 업그레이드

```bash
helm repo update
helm upgrade cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

## 삭제

```bash
helm uninstall cas-server -n <namespace>
kubectl delete namespace <namespace>
```
