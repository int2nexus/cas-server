# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 **Sample → Dataset → DatasetVersion** 단위로 묶어 버전을 관리한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.14/charts/nexus-server/docs/architecture.md)
  — 도메인 모델, Version 생명주기, Annotation CoW, 스냅샷·Manifest 구조
- [사용법](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.14/charts/nexus-server/docs/usage.md)
  — 설치, Python SDK 연결, Dataset 적재·검색·seal 워크플로우, API 레퍼런스
- [변경 이력](CHANGELOG.md)
  — 버전별 동작 변경·마이그레이션·설정 키. 각 항목은 해당 GitHub Release 본문과 동일하다

## 전제

- **외부 PostgreSQL** — 접속 정보(비번 포함 DSN)는 시크릿으로 주입. 차트가 DB를 띄우지 않는다.
  **지원 범위는 14 이상이고, 자동 시험이 도는 판은 18 하나다**(`0.1.12`~). 하한 14 의 근거는 13 의
  커뮤니티 지원이 2025-11 에 끝났다는 것 하나이고, **하한인 14 는 시험한 판이 아니다.** 15·16·17 도
  시험하지 않는다. **부 버전은 고정하지 않는다** — 시험 DB 는 18 의 그때 최신 부 버전을 쓴다.
- **클러스터 내 cas-server** — CAS(파일) 백엔드.
- **시크릿 4키** (sealed-secret으로 주입): `NEXUS__DATABASE__URL`, `NEXUS__CAS__KEY_ID`, `NEXUS__CAS__SECRET`, `NEXUS__JWT__SECRET`.
  선택 키가 셋 더 있고, 쓰는 기능이 있을 때만 넣는다 — CVAT annotation 편집 세션의
  `NEXUS__CVAT__PASSWORD`, superuser의 `NEXUS__AUTH__SUPERUSER_PASSWORD`,
  지표의 `NEXUS__METRICS__TOKEN`(values 스위치가 없다 — 이 키가 곧 스위치다).
  전체 목록은 [`examples/secret.example.yaml`](examples/secret.example.yaml).
- **CVAT은 선택** — 설정하지 않아도 서버는 정상 동작한다. 세션 생성·결과 회수만 503이 되고 카탈로그·업로드·seal·조회는 영향이 없다.
- **superuser도 선택** — 설정하지 않으면 관리자를 만들 부트스트랩 수단이 없다(`users.role = admin`은 백필하지 않는다). 다만 **CVAT과 달리 반쪽 설정은 조용히 꺼지지 않고 기동을 실패시킨다**(아래 참조).

DB 마이그레이션은 바이너리에 임베드되어 **기동 시 자동 적용**된다(별도 Job 불필요). 마이그레이션이 끝나야 포트가 열리므로 그 시간은 곧 startupProbe 예산(기본 `periodSeconds 10 × failureThreshold 60` = 600초)에서 나간다 — 스키마가 바뀌는 릴리스로 올릴 때는 [CHANGELOG](CHANGELOG.md)의 해당 버전 **마이그레이션** 항목에서 예상 소요를 먼저 확인할 것. **거기 적힌 실측값은 특정 환경의 것이라 행 수로 환산해 그대로 쓸 수 없다** — 소요가 행 수에 선형인 것은 같은 하드웨어 안에서일 뿐이고 계수는 DB마다 다르다. 예산은 넉넉한 쪽으로 잡는다(모자라면 기동 실패가 반복되고, 남으면 아무 일도 일어나지 않는다). 서버는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

**한 번도 vacuum 되지 않은 대형 표**(예: `instances`)의 autovacuum 임계를 낮출 때는 값이 아니라 **순서**가 중요하다. analyze 축(`autovacuum_analyze_*`)은 임계만 걸면 되지만, vacuum 축(`autovacuum_vacuum_*`)은 **① `autovacuum_vacuum_cost_delay` 를 먼저 걸고 → ② 창을 잡아 첫 `VACUUM` 을 손으로 돌린 뒤 → ③ 임계**를 건다. 첫 vacuum 을 끝내기 전에 임계부터 걸면 visibility map 이 비어 있어 힙 전량을 읽는 대규모 vacuum 이 예고 없이 발동한다 — 수동 `VACUUM` 은 `autovacuum_vacuum_cost_delay` 를 쓰지 않으므로(기본 0) 세션에서 `SET vacuum_cost_delay` 를 먼저 걸어 I/O 를 눌러 둔다.

> **업그레이드 전에 [CHANGELOG](CHANGELOG.md)를 읽을 것.** 버전별 동작 변경·마이그레이션·롤백 하한은 그곳에만 적는다. 마이그레이션이 추가된 버전은 이전 이미지로 롤백할 수 없다.

## 설치

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

### 1) 시크릿 주입 (sealed-secret)

차트는 Secret을 만들지 않고 외부 Secret을 `envFrom`으로 참조한다. 아래 키를 가진 Secret을 **먼저** 주입한다(앞의 넷은 필수, 뒤의 셋은 그 기능을 쓸 때만):

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='...' \
  --from-literal=NEXUS__CAS__SECRET='...' \
  --from-literal=NEXUS__JWT__SECRET='...' \
  --from-literal=NEXUS__CVAT__PASSWORD='...' \
  --from-literal=NEXUS__AUTH__SUPERUSER_PASSWORD='...' \
  --from-literal=NEXUS__METRICS__TOKEN='...' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

평문 예시: [`examples/secret.example.yaml`](examples/secret.example.yaml).
Secret 이름은 `secret.existingSecret`(비우면 릴리즈 fullname, 기본 `nexus-server`)과 일치해야 한다.

### 2) 차트 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=http://cas-server:80
```

환경별 override는 `-f values-xxx.yaml` 사용.

## 주요 values

| 키 | 기본값 | 설명 |
|---|---|---|
| `image.digest` | `""` | 채우면 `tag` 대신 이 값으로 핀한다(`repository@sha256:...`). 태그는 같은 이름으로 다시 밀릴 수 있어 무엇이 도는지 확정하지 못하므로, 고정이 필요하면 이쪽을 쓴다. 각 버전의 digest 는 [CHANGELOG](CHANGELOG.md) 의 그 버전 절 맨 위에 있다 |
| `server.port` | `8090` | 컨테이너 포트. **이 값 하나만 바꾼다** — 프로브와 `service.targetPort`는 숫자가 아니라 컨테이너 포트 이름 `http`를 가리키므로 따라온다. 숫자를 함께 박으면 오히려 어긋난다(아래 참조) |
| `cas.baseUrl` | `http://cas-server:80` | CAS(cas-server) 주소 |
| `cas.region` / `cas.defaultBucket` | `cas-default` / `data` | CAS region·기본 버킷. **버킷 이름은 S3 규칙**(소문자·숫자·`-`·`.`, 3~63자)을 따라야 한다 |
| `database.maxConnections` | `16` | 워크로드 풀 상한. 적재가 쓸 수 있는 자리는 **이 값 - 4**(조회·관리·seal 몫)이고, readiness 전용 커넥션이 이 풀 **밖에** 하나 더 붙는다(Postgres 쪽 계산은 replica당 이 값 + 1). `ingest.batchItemConcurrency`와의 불변식은 [`values.yaml`](values.yaml) 주석 |
| `ingest.admissionWaitMs` | `""` | 적재가 자리를 기다리는 상한(ms). 넘기면 대기가 아니라 **`429` + `Retry-After: 1`**. 비우면 서버 기본 3000. `0`이면 기다리지 않는다(자리가 비어 있으면 통과, 없으면 그 자리에서 `429`) |
| `secret.existingSecret` | `""` | 비밀 Secret 이름(비우면 fullname) |
| `service.type` / `service.nodePort` | `NodePort` / `30090` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 250m/256Mi ~ 1000m/1Gi | 요청/제한 |
| `cvat.baseUrl` | `""` | **비우면 CVAT 연동 꺼짐**(`NEXUS__CVAT__*` env 자체가 렌더되지 않는다) |
| `cvat.user` / `cvat.organization` | `""` / `""` | CVAT 서비스 계정, organization slug(선택) |
| `cvat.projectNamePrefix` | `nexus` | 생성되는 CVAT project 이름 접두사 |
| `cvat.segmentSize` / `cvat.maxSessionSamples` | `""` / `""` | 비우면 서버 기본값(각각 0=CVAT 기본, 2000) |
| `cvat.staleCreatingSecs` | `""` | 비우면 서버 기본값 1800초. 이 시간을 넘긴 `creating` 세션을 기동 시 `failed`로 정리 |
| `jwt.ttlHours` | `""` | 비우면 서버 기본 24시간. 허용 범위 1~8760, **벗어나면 기동 실패**(DB 연결보다 먼저 검사). 토큰을 무효화할 수 없으므로 이 값이 곧 노출 상한 |
| `auth.registrationEnabled` / `auth.docsEnabled` | `true` / `true` | 공개 회원가입 / API 문서 3경로. 각각 끄면 `register`만 403, 문서 경로는 **404**(403이 아니다) |
| `auth.approvalRequired` | `false` | `true`면 가입은 열어 둔 채 승인 전까지 아무것도 할 수 없다. 가입이 토큰 없이 `202`를 반환하므로 **가입 화면이 그것을 처리해야 한다.** 승인·대기목록 엔드포인트가 관리자 전용이라 `auth.superuserEmail`을 함께 설정해야 한다 |
| `auth.revocationCacheTtlSecs` | `""` | 비우면 서버 기본 5초. 인증이 사용자 행(역할·승인·활성)을 읽고 캐시하는 시간이며, **곧 권한 회수·계정 정지·계정 삭제가 듣기까지의 상한**이다. `0`이면 매 요청 조회(적재 처리량 20~33% 감소). 조회 자체는 끌 수 없다 |
| `auth.oidc.issuers` | `[]` | 외부 IdP 토큰을 인증 자격증명으로 받을 발급자 목록. **비우면 기능이 꺼지고 기존 동작과 같다.** 항목마다 `issuer`(필수, https) · `audience`(필수, `aud` 포함 검사) · `exchange`(기본 `false`) · `jwksUri`(선택) · `jwksAuth`(선택, `serviceaccount` — 쓰면 `serviceAccount.automountToken: true` 가 필요하다). **`audience`가 비었거나 `issuer`가 중복이면 기동 실패다.** 발급자만 설정하면 아무도 인증되지 않는다 — 신원은 `POST /api/v1/admin/oidc-identities`로 관리자가 등록한다 |
| `auth.superuserEmail` | `""` | **비우면 관리자를 만들 부트스트랩 수단이 없다.** 채우면 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`도 **반드시 함께** 있어야 한다 |
| Secret `NEXUS__METRICS__TOKEN` | (없음) | 넣으면 `GET /_internal/metrics`가 열리고 없으면 **404**다. values 스위치는 없다 — 이 차트는 Secret 전체를 `envFrom`으로 받으므로 키를 넣는 것이 곧 켜는 것 |
| `serviceAccount.automountToken` | `false` | ServiceAccount 토큰 마운트 여부. 파드 토큰에 기대는 사이드카가 있거나 `auth.oidc.issuers` 에 `jwksAuth: serviceaccount` 를 쓰면 `true` |

전체 키는 [`values.yaml`](values.yaml) 참조.

CVAT 연동은 `cvat.baseUrl`·`cvat.user`·시크릿의 `NEXUS__CVAT__PASSWORD` **셋이 다 있어야** 켜진다. 하나라도 비면 서버는 정상 기동하고 무엇이 빠졌는지 기동 로그에 남는다.

### superuser

설정으로 지정하는 관리 계정이다. 이메일은 `auth.superuserEmail`, 비밀번호는 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`(8자 이상)에 넣는다.

**관리자는 둘 이상 둘 수 있다.** 관리 권한의 출처가 둘이기 때문이다 — 설정의 superuser(이 계정)와 `users.role = admin`. 후자는 superuser가 `POST /api/v1/admin/users/role`로 부여한다. `admin`은 마이그레이션이 백필하지 않으므로 **최초 한 명을 만들려면 이 설정이 필요하고**, 한 명이라도 생긴 뒤에는 설정을 비워도 그 계정들이 관리 권한을 유지한다.

**CVAT과 달리 반쪽 설정은 조용히 꺼지지 않는다 — 서버가 기동에 실패한다.** 일부러 그렇게 만들었다: 운영자가 켰다고 믿는데 실제로는 꺼져 있는 상태가 가장 나쁘고, 그 사실이 정작 필요한 순간(누군가 잠겼을 때)에야 드러나기 때문이다. **차트는 이 짝을 검사할 수 없다** — 비밀번호는 Secret에서 `envFrom`으로 들어와 템플릿에 보이지 않는다. 그래서 `helm upgrade`는 조용히 성공하고 Pod가 CrashLoop로 드러나며, 어느 쪽이 빠졌는지는 `kubectl logs`에 적힌다.

**끌 때도 두 곳을 함께 비운다.** `auth.superuserEmail`만 지우고 Secret에 비밀번호를 남겨두면 "비밀번호만 있는" 상태가 되어 역시 기동에 실패한다.

**여기 적은 비밀번호는 최초 계정 생성 때만 쓰인다.** 서버가 기동 시 그 계정이 없으면 만들고(그래야 그 주소를 아무도 선점할 수 없다), 이미 있으면 **비밀번호를 덮지 않는다** — 운영자가 API로 바꾼 값이 파드 재시작마다 되돌아가면 안 되기 때문이다. 나중에 이 env를 바꿔도 로그인 비밀번호는 바뀌지 않는다(자주 나오는 오해다). 잊었다면 Secret을 고쳐도 소용이 없다 — `auth.superuserEmail`을 **아직 가입되지 않은** 새 주소로 바꿔 재배포하면 서버가 그 주소로 계정을 새로 만들고, 그때는 Secret의 비밀번호가 그대로 쓰인다. 같은 주소를 유지해야 한다면 운영자가 DB에서 그 `users` 행을 직접 지운 뒤 재기동하는 방법뿐이다 — **superuser 계정은 API로 삭제할 수 없고(403), 그 이메일로는 가입할 수도 없다(409).** 계정이 사라진 창에 아무나 그 주소를 선점하면 그대로 최고 권한을 가져가기 때문이다.

**이메일을 바꿔 재배포해도 이전 계정의 관리 권한은 회수되지 않는다.** 서버가 기동 시 superuser 계정에 `role = admin`을 부여하므로, 설정에서 빠진 이전 계정은 `admin`으로 남는다. 회수하려면 새 관리자가 `POST /api/v1/admin/users/role`로 이전 계정을 강등한다. **superuser 계정을 대상으로 삼는 관리 조작 셋은 누가 부르든 403이다** — `POST /api/v1/admin/users/role`(역할 변경)·`.../active`(정지)·`.../password-reset`(비밀번호 재설정). 호출자가 superuser 본인이든 `role = admin`이든 같다.

관리 엔드포인트, 로봇 계정, OIDC 신원 매핑 등 계정 관리 API는 [사용법 §2.1 superuser](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.14/charts/nexus-server/docs/usage.md#superuser-차트-030-선택)에, 인가 정책의 근거는 [아키텍처 10장](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.14/charts/nexus-server/docs/architecture.md)에 있다.

## 헬스 체크

프로브는 셋으로 갈린다. `GET /_internal/live`(의존성을 조회하지 않는 프로세스 응답성 확인)를 startup·liveness에, `GET /_internal/health`(DB ping)를 readiness에 쓴다. liveness를 `/_internal/health`로 두면 DB failover(보통 30~120초) 중에 파드가 kill되는데, 재시작으로는 외부 의존성이 복구되지 않아 중단이 원래 장애보다 길어진다 — 자세한 배경은 [CHANGELOG](CHANGELOG.md) 0.3.0 참조.

```bash
kubectl port-forward svc/nexus-server 8090:80 -n <namespace>
curl localhost:8090/_internal/health      # {"status":"ok","db":true}
```

**readiness는 워크로드와 커넥션 풀을 나눠 쓴다**. `/_internal/health`는 크기 1의 전용 풀로 ping하므로 적재가 워크로드 풀을 전부 써도 200이다. 그래서 **readiness 실패는 「DB에 못 닿는다」만 뜻하고**, 「앱이 바쁘다」는 더 이상 파드를 서비스에서 빼지 않는다. 앱이 커넥션을 못 받고 있는지는 readiness가 아니라 `nexus_db_pool_acquire_timeouts_total` 지표로 본다.

`GET /_internal/metrics`는 **인증이 면제되지 않는다.** 시크릿의 `NEXUS__METRICS__TOKEN`을 bearer로 받고, 비어 있으면 경로 자체가 404다. 스크레이퍼는 로그인할 수 없고 JWT를 쓰게 하면 모니터링 스택이 카탈로그 전체를 읽는 계정을 들고 있어야 해서 토큰을 따로 뒀다. 스크레이프마다 DB 집계 한 왕복이 워크로드 풀에서 나가므로 15초보다 촘촘한 주기는 권하지 않는다. 설정 여부는 `GET /api/v1/admin/config-effective`의 `metrics.token_set`으로 확인한다.

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" localhost:8090/_internal/metrics
```

내는 지표의 목록과 알림에 쓰는 법은 [사용법 §2.1 superuser](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.14/charts/nexus-server/docs/usage.md#superuser-차트-030-선택)의 「지표를 보려면」에 있다.

`live`와 `health` 두 경로는 프로브가 자격증명 없이 호출해야 하므로 인증이 면제된다. 그 밖의 면제 경로는 `POST /api/v1/auth/register`·`POST /api/v1/auth/login`과 API 문서 경로(`/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/`)뿐이며, 문서 경로는 `auth.docsEnabled: false`로 끄면 404가 된다. **데이터 API는 조회를 포함해 전부 토큰이 필요하다.**

### `server.port`를 바꿀 때

`server.port` **하나만** 바꾸면 된다.

```bash
helm upgrade ... --set server.port=9000
```

컨테이너 포트, 앱이 듣는 포트(`NEXUS__SERVER__PORT`), Service의 `targetPort`, 두 프로브가 모두 이 값을 따라간다. 뒤의 셋은 숫자가 아니라 **컨테이너 포트 이름 `http`**를 가리키기 때문이다.

`values-xxx.yaml`에서 프로브나 `service.targetPort`를 직접 override할 때 숫자를 박지 말 것 — `server.port`와 어긋나면 앱은 새 포트에서 도는데 kubelet은 옛 포트를 찔러 **Pod가 영영 Ready가 되지 않는다.** 컨테이너 로그에는 아무 이상이 없어 원인을 찾기 어렵다.

## 삭제

```bash
helm uninstall nexus-server -n <namespace>
kubectl delete -f sealed-nexus-server.yaml -n <namespace>   # 시크릿은 별도 정리
```
