# cas-server Helm Chart

BLAKE3 기반 CAS(Content-Addressable Storage) 서버. S3 호환 스토리지 또는 NFS를 백엔드로 사용하는
HTTP API를 제공한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/main/charts/cas-server/docs/architecture.md)
  — 스토리지 모델(CAS·dedup·GC), 백엔드 구성, S3 호환 API 명세, 에러 코드
- [사용법](https://github.com/int2nexus/cas-server/blob/main/charts/cas-server/docs/usage.md)
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
`cas-server` Secret(필수 7개 키 + 선택 1개)을 참조한다. kubeseal로 암호화해 미리 주입한다:

```bash
kubectl create secret generic cas-server \
  --namespace=<namespace> \
  --from-literal=db-password='...' \
  --from-literal=s3-access-key-id='...' \
  --from-literal=s3-secret-access-key='...' \
  --from-literal=auth-secret-master-key='...' \
  --from-literal=auth-admin-token='...' \
  --from-literal=auth-metrics-token='...' \
  --from-literal=auth-root-access-key-id='...' \
  --from-literal=auth-root-secret-key='...' \
  --dry-run=client -o yaml > /tmp/secret-plain.yaml

kubeseal --format yaml < /tmp/secret-plain.yaml > sealed-secret.yaml
rm /tmp/secret-plain.yaml
kubectl apply -f sealed-secret.yaml -n <namespace>
```

`auth-metrics-token`은 선택 항목이다. 없으면 파드는 정상 기동하고 서버가 `admin_token`으로
폴백한다 — 기존 7개 키 Secret 그대로 업그레이드해도 된다. 용도는 [메트릭 스크레이프](#메트릭-스크레이프) 참고.

`auth.secretMasterKey`를 비우면 NoAuth 모드(인증 없음, 내부망 전용)로 동작한다. 상세 절차와 값 교체
방법은 [`examples/sealed-secret.yaml`](https://github.com/int2nexus/cas-server/blob/main/charts/cas-server/examples/sealed-secret.yaml) 참고.

## 설치

```bash
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

`values-prod.yaml`은 직접 작성하거나 [`examples/values-prod.yaml`](https://github.com/int2nexus/cas-server/blob/main/charts/cas-server/examples/values-prod.yaml)을
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

## 주요 values

| 키 | 기본값 | 설명 |
|----|--------|------|
| `storage.mode` | `s3` | `s3` 또는 `nfs` |
| `externalDatabase.host` | `""` | PostgreSQL 서비스명 |
| `externalDatabase.port` | `5432` | PostgreSQL 포트 |
| `secrets.useExternalSecret` | `true` | sealed-secret으로 Secret을 미리 주입했는지 여부 |
| `auth.secretMasterKey` | (없음) | 설정 시 SigV4 인증 활성화, 비우면 NoAuth |
| `auth.metricsToken` | `""` | `GET /_internal/metrics` 전용 **읽기 전용** 토큰. 비우면 `admin_token`으로 폴백. 모니터링 스택에는 이것을 쓸 것 (아래 참고) |
| `ingress.enabled` | `false` | Ingress 활성화 |
| `config.maxUploadSizeBytes` | `10737418240` | 최대 업로드 크기 (10 GiB) |
| `config.maxUploadBytesInFlight` | `3221225472` | 동시 업로드 바디의 총 상주 바이트 상한 (3 GiB). 초과분은 `503 SlowDown`. **`0` = 무제한.** `resources.limits.memory` × 0.5 를 기준으로 함께 조정할 것 |
| `config.maxConcurrentUploads` | `96` | 동시 업로드 건수 상한. 위 바이트 예산의 보조 장치 |
| `resources.limits.memory` | `6Gi` | 2026-08-05 OOM 대응으로 올린 값. **당분간 유지할 것** — 하향 전제는 [values.yaml](values.yaml)의 `resources` 주석 참고 |
| `gc.enabled` | `true` | GC CronJob 활성화. 초기 마이그레이션 중에는 `false` 권장. **이미지 `0.1.17` 이하에서는 끄면 메모리 회수 경로도 사라진다** (아래 참고) |
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

`GET /_internal/metrics`에는 **`auth.metricsToken`을 쓰세요.** `admin_token`은
`POST /_internal/gc`(blob 물리 삭제)와 `/_admin/*`(액세스 키 관리)까지 여는 자격증명이라,
스크레이프 용도로 모니터링 스택에 배포하면 삭제 권한을 함께 넘기게 됩니다.
`metricsToken`은 이 엔드포인트에서만 통하고 다른 경로는 열지 않습니다.

`sealed-secret`에 `auth-metrics-token` 키를 추가합니다. 이 키는 **선택 항목**이고
deployment가 `optional: true`로 참조하므로, 추가하지 않아도 파드는 정상 기동합니다
(그 경우 서버가 `admin_token`으로 폴백합니다). **cas-server 이미지 `0.1.18` 이상**이
필요하며, 그 이하 이미지는 이 토큰을 무시하므로 스크레이프가 401이 됩니다.

**`metricsToken`만 채우고 `adminToken`을 비우지 마세요.** 그 조합에서는 서버가 기동을
거부합니다 — metrics만 잠기고 `POST /_internal/gc`(blob 물리 삭제)가 무인증으로 열려,
401을 보고 보호된다고 오해하게 되기 때문입니다. `replicaCount: 1`이라 기동 실패는
곧 전면 중단입니다.

**Secret을 갱신했으면 파드를 직접 재시작해야 합니다.** `secrets.useExternalSecret: true`
(기본값)에서는 Helm이 Secret 내용을 볼 수 없어 체크섬을 걸 수 없고, 따라서
`kubectl apply -f sealed-secret.yaml`만으로는 파드가 교체되지 않습니다. env는 파드
생성 시점에 주입되므로 새 토큰이 반영되지 않은 채 스크레이프만 401이 되고,
원인이 "토큰이 틀렸나"로 보입니다.

```bash
kubectl rollout restart -n <namespace> deploy/cas-server
```

업그레이드와 함께 갱신한다면 **Secret을 먼저 적용**하고 `helm upgrade`하면 파드 교체와
함께 들어가므로 별도 재시작이 필요 없습니다.

차트는 `ServiceMonitor`를 포함하지 않습니다 — 모니터링 스택 구성은 배포 측 소관입니다.

## GC와 메모리 회수 (이미지 `0.1.17` 이하)

대량 적재 중에는 `gc.enabled: false`를 권장합니다. GC의 orphan 전수 스캔과 advisory lock이
적재 경로와 경합하기 때문입니다.

**다만 이미지 `0.1.17` 이하에서는 GC 주기가 곧 서버 내부 해시별 쓰기 락 테이블의 회수
주기입니다.** 항목은 고유 해시마다 하나씩 생기고 항목당 약 180~240바이트입니다.

| `gc.enabled` | 회수 | 쌓이는 양 |
|---|---|---|
| `false` | 없음 | 파드 수명 동안 단조 증가 |
| `true` | `gc.schedule` 주기 | 그 주기만큼. 기본 주 1회면 최대 일주일치 |

**GC를 켜 뒀다고 해당 없는 항목이 아닙니다.** 2026-08 운영 사례에서 유휴 메모리 바닥값이
4.9일간 하루 330~430 MiB씩 단조 상승했고, 주 1회 주기라면 그 사이 최대 2.3~3.0 GiB가
쌓입니다. 대량 적재는 고유 해시율이 요청율과 거의 같은 구간이라 증가율이 최대가 됩니다.

선택지는 셋이고, **위로 갈수록 낫습니다.**

1. **이미지를 `0.1.18` 이상으로 올린다.** 근본 해결이고 아래 둘이 필요 없어집니다.
2. **파드를 재시작한다.** 이 테이블은 프로세스 메모리라 재시작하면 통째로 사라집니다.
   단편화까지 함께 회수되므로 회수량이 가장 큽니다. 대신 `replicaCount: 1`이라
   그동안 중단됩니다. 상승률로 한도 도달 시점을 계산해 그보다 짧은 주기로 잡으세요.
3. **중단이 곤란하면 `POST /_internal/gc?dry_run=true`를 주기 실행한다.** 이 요청은
   **blob 물리 삭제를 하지 않고 GC advisory lock도 잡지 않으면서** 그 테이블을
   회수합니다. GC를 다시 켤 필요가 없습니다. 함께 도는 것은 읽기 전용 쿼리
   두 개(orphan 후보 COUNT, 만료 멀티파트 목록)입니다.

   쓰기 경로와의 경합은 **"없음"이 아니라 "짧음"**입니다. 회수는 락 테이블을
   순회하는데 자료구조가 샤드로 나뉘어 있고 **한 번에 한 샤드씩** 잠급니다.
   그 순간 같은 샤드에 해당하는 해시의 쓰기만 대기하고 나머지는 진행됩니다.
   전체가 멈추지는 않습니다.

3번은 **`kubectl exec`로 실행할 수 없습니다** — 런타임 이미지(`debian:bookworm-slim`)에
`curl`도 `wget`도 없습니다. 클러스터 안에서 주기 실행하려면 `curl`이 있는 이미지의
CronJob이 필요합니다(`templates/gc-cronjob.yaml`이 참고가 됩니다 — 같은 방식으로
Secret에서 `auth-admin-token`을 주입하면 토큰이 클러스터 밖으로 나가지 않습니다).

**일회성 확인**은 포트포워드 후 로컬 `curl`로 됩니다:

```bash
NS=<namespace>
REL=cas-server     # helm 릴리스명. 서비스·시크릿 이름이 이것을 따릅니다

# 로컬 18080은 비어 있는 아무 포트나 됩니다. 원격은 서비스의 named port 'http'라
# config.port / service.port를 기본값과 다르게 두었어도 그대로 동작합니다.
kubectl port-forward -n "$NS" "svc/$REL" 18080:http &
TOKEN=$(kubectl get secret -n "$NS" "$REL" \
          -o jsonpath='{.data.auth-admin-token}' | base64 -d)

time curl -sS -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:18080/_internal/gc?dry_run=true"
```

**주기를 정하기 전에 이 소요 시간을 재세요.** 두 가지가 합쳐진 값입니다 — 읽기 전용
쿼리 두 개(그쪽 규모에서 얼마나 걸리는지는 재 봐야 압니다)와 락 테이블 순회입니다.
무거우면 6시간 주기로도 하루 330 MiB 상승이 약 90 MiB 톱니로 줄어듭니다.

회수 건수는 cas-server 파드 로그에 남습니다 —
`GC: blob write lock 항목 회수  swept=<n> remaining=<n>` (0건이면 로그가 없습니다).

**이미지 `0.1.18` 이상은 요청이 끝날 때 즉시 회수하므로 이 완화가 전부 필요 없습니다.**
그 버전부터 `cas_blob_lock_map_entries`는 "진행 중인 쓰기 건수"를 뜻하고 유휴 시 0이며,
0으로 떨어지지 않으면 항목 유출 신호입니다.

현재 이미지 태그 확인:

```bash
kubectl get deploy cas-server -n <namespace> -o jsonpath='{..image}{"\n"}'
```

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
| `readinessProbe` | `GET /_internal/health` | DB ping + 백엔드 가용성. 비정상이면 503 |

`livenessProbe` 를 `/_internal/health` 로 두면 안 됩니다. DB failover(보통 30~120초)나 NAS
순간 장애에 쿠버네티스가 파드를 죽이는데, 재시작으로는 외부 의존성이 복구되지 않습니다.
오히려 재기동 시 initContainer가 DB를 기다리고 CrashLoopBackOff 백오프(최대 5분)가 붙어
중단이 원래 장애보다 길어집니다. `replicaCount` 가 1이므로 그 시간이 곧 전면 중단입니다.
의존성 상태는 readiness가 판단해 Service 엔드포인트에서 빼는 것이 맞는 처리이고,
의존성이 돌아오면 파드는 그대로 복귀합니다.

`/_internal/live` 는 **cas-server 이미지 `0.1.17` 이상**에서만 제공됩니다. 이미지를 그 이하로
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
helm uninstall postgresql -n <namespace>
kubectl delete namespace <namespace>
```
