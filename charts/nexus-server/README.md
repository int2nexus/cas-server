# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 **Sample → Dataset → DatasetVersion** 단위로 묶어 버전을 관리한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/docs/architecture.md)
  — 도메인 모델, Version 생명주기, Annotation CoW, 스냅샷·Manifest 구조
- [사용법](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/docs/usage.md)
  — 설치, Python SDK 연결, Dataset 적재·검색·seal 워크플로우, API 레퍼런스
- [변경 이력](CHANGELOG.md)
  — 버전별 동작 변경·마이그레이션·설정 키. 각 항목은 해당 GitHub Release 본문과 동일하다

## 전제

- **외부 PostgreSQL** — 접속 정보(비번 포함 DSN)는 시크릿으로 주입. 차트가 DB를 띄우지 않는다.
  **지원 범위는 14 이상이고, 자동 시험이 도는 판은 18 하나다**. 하한 14 의 근거는 13 의
  커뮤니티 지원이 2025-11 에 끝났다는 것 하나이고, **하한인 14 는 시험한 판이 아니다.** 15·16·17 도
  시험하지 않는다. **부 버전은 고정하지 않는다** — 시험 DB 는 18 의 그때 최신 부 버전을 쓴다.
- **클러스터 내 cas-server** — CAS(파일) 백엔드.
- **시크릿 4키** (sealed-secret으로 주입): `NEXUS__DATABASE__URL`, `NEXUS__CAS__KEY_ID`, `NEXUS__CAS__SECRET`, `NEXUS__JWT__SECRET`.
  선택 키가 셋 더 있고, 쓰는 기능이 있을 때만 넣는다 — CVAT annotation 편집 세션의
  `NEXUS__CVAT__PASSWORD`, superuser의 `NEXUS__AUTH__SUPERUSER_PASSWORD`,
  지표의 `NEXUS__METRICS__TOKEN`(values 스위치가 없다 — 이 키가 곧 스위치다).
  전체 목록은 [`examples/secret.example.yaml`](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/examples/secret.example.yaml).
- **CVAT은 선택** — 설정하지 않아도 서버는 정상 동작한다. 세션 생성·계획·결과 회수만 503이 되고 카탈로그·업로드·seal·조회는 영향이 없다.
- **superuser도 선택** — 설정하지 않으면 관리자를 만들 부트스트랩 수단이 없다(`users.role = admin`은 백필하지 않는다). 다만 **CVAT과 달리 반쪽 설정은 조용히 꺼지지 않고 기동을 실패시킨다**(아래 참조).

DB 마이그레이션은 바이너리에 임베드되어 **기동 시 자동 적용**된다(별도 Job 불필요). 마이그레이션이 끝나야 포트가 열리므로 그 시간은 곧 startupProbe 예산(기본 `periodSeconds 10 × failureThreshold 60` = 600초)에서 나간다 — 스키마가 바뀌는 릴리스로 올릴 때는 [CHANGELOG](CHANGELOG.md)의 해당 버전 **마이그레이션** 항목에서 예상 소요를 먼저 확인할 것. **거기 적힌 실측값은 특정 환경의 것이라 행 수로 환산해 그대로 쓸 수 없다** — 소요가 행 수에 선형인 것은 같은 하드웨어 안에서일 뿐이고 계수는 DB마다 다르며, 행마다 JSON 을 펼치는 마이그레이션은 행 수가 아니라 행의 크기(예: meta 의 키 수와 크기)에 따라 늘어난다. 길어졌을 때의 확인과 조치는 아래 「기동 마이그레이션이 길어질 때」. 예산은 넉넉한 쪽으로 잡는다(모자라면 기동 실패가 반복되고, 남으면 아무 일도 일어나지 않는다). 서버는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

**한 번도 vacuum 되지 않은 대형 표**(예: `instances`)의 autovacuum 임계를 낮출 때는 값이 아니라 **순서**가 중요하다. analyze 축(`autovacuum_analyze_*`)은 임계만 걸면 되지만, vacuum 축(`autovacuum_vacuum_*`)은 **① `autovacuum_vacuum_cost_delay` 를 먼저 걸고 → ② 창을 잡아 첫 `VACUUM` 을 손으로 돌린 뒤 → ③ 임계**를 건다. 첫 vacuum 을 끝내기 전에 임계부터 걸면 visibility map 이 비어 있어 힙 전량을 읽는 대규모 vacuum 이 예고 없이 발동한다 — 수동 `VACUUM` 은 `autovacuum_vacuum_cost_delay` 를 쓰지 않으므로(기본 0) 세션에서 `SET vacuum_cost_delay` 를 먼저 걸어 I/O 를 눌러 둔다.

> **업그레이드 전에 [CHANGELOG](CHANGELOG.md)를 읽을 것.** 버전별 동작 변경·마이그레이션·롤백 하한은 그곳에만 적는다. 마이그레이션이 추가된 버전은 이전 이미지로 롤백할 수 없다(수동으로 되돌릴 수 있는 경우는 아래 [되돌리기](#되돌리기)). 옛 파드와 새 파드가 함께 돌 수 없는 판은 `strategy.type=Recreate` 로 교체하라고 그 판의 절에 적는다.

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

평문 예시: [`examples/secret.example.yaml`](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/examples/secret.example.yaml).
Secret 이름은 `secret.existingSecret`(비우면 릴리즈 fullname, 기본 `nexus-server`)과 일치해야 한다.

- `NEXUS__JWT__SECRET`은 직접 생성하는 임의의 비밀 키(로그인 JWT HS256 서명용)  
예: `openssl rand -hex 32`. 값을 바꾸면 이 서버가 발급한 로그인 JWT(로그인·가입·갱신·OIDC 교환)가 모두 무효가 된다(재로그인 필요). 로봇 토큰과 외부 IdP 토큰은 영향이 없다.
- `NEXUS__CAS__KEY_ID`/`NEXUS__CAS__SECRET`은 CAS가 인정하는(write 권한 있는) 자격증명
- `NEXUS__DATABASE__URL`은 외부 Postgres DSN.

### 2) 차트 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=http://cas-server:80

# 업데이트
helm repo update
helm upgrade nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=http://cas-server:80
```

환경별 override는 `-f values-xxx.yaml` 사용.

## 주요 values

| 키 | 기본값 | 설명 |
|---|---|---|
| `image.digest` | `""` | 채우면 `tag` 대신 이 값으로 핀한다(`repository@sha256:...`). 태그는 같은 이름으로 다시 밀릴 수 있어 무엇이 도는지 확정하지 못하므로, 고정이 필요하면 이쪽을 쓴다. 각 버전의 digest 는 [CHANGELOG](CHANGELOG.md) 의 그 버전 절 맨 위에 있다 |
| `server.port` | `8090` | 컨테이너 포트. **이 값 하나만 바꾼다** — 프로브와 `service.targetPort`는 숫자가 아니라 컨테이너 포트 이름 `http`를 가리키므로 따라온다. 숫자를 함께 박으면 오히려 어긋난다(아래 참조) |
| `cas.baseUrl` | `http://cas-server:80` | CAS(cas-server) 주소 |
| `cas.region` / `cas.defaultBucket` | `cas-default` / `data` | CAS region·기본 버킷 이름. 서버는 이 이름 뒤에 `-manifests`를 붙인 버킷에 seal 스냅샷을 저장한다(이 이름 자체에는 저장하지 않는다). 붙인 이름이 **S3 규칙**(소문자·숫자·`-`·`.`, 3~63자)을 따라야 하므로 이 값은 53자 이하 |
| `database.maxConnections` | `16` | 워크로드 풀 상한. 적재가 쓸 수 있는 자리는 **이 값 - 4**(조회·관리·seal 몫)이고, readiness 전용 커넥션이 이 풀 **밖에** 하나 더 붙는다(Postgres 쪽 계산은 replica당 이 값 + 1). `ingest.batchItemConcurrency`와의 불변식은 [`values.yaml`](values.yaml) 주석 |
| `seal.maxConcurrent` | `""` | 이 파드에서 동시에 도는 버전 작업(seal 과 `fork_from` 새 버전 만들기가 함께 쓰는 자리)의 상한(비우면 이미지 기본 `1`). 자리가 없으면 요청은 **`202`** 로 [버전 작업 줄](#버전-작업-줄seal새-버전-만들기)에 서고 자리가 나는 대로 어느 파드든 돌린다. `0` 이면 기동이 실패한다. 메모리 지침(`resources`)은 작업 하나 기준이라 올리면 `limits.memory` 도 그 배수만큼 올린다. seal 하나는 풀에서 끝까지 둘(잠금 1 + 작업 1), 새 버전 만들기 하나는 하나를 쥐고(임대 갱신·진행 기록·seal 의 메인 manifest 기록으로 잠깐 셋을 더 꺼내고 파드 일꾼이 하나를 쓴다) 그 몫이 예약 4(고정)에서 나오므로 seal 둘이면 적재 포화 때 조회·관리 몫이 0 이 된다(작업마다 둘로 세어 2 이상이면 기동 로그에 경고) — `database.maxConnections` 를 올려도 예약은 늘지 않는다. 상한 2 이상에서 `database.maxConnections` 가 상한 × 3 보다 작으면 seal 들이 메인 manifest 기록용 커넥션을 서로 기다리다 실패할 수 있어 기동 로그에 그 경고도 남는다([seal 의 DB·cas 조건](#seal-의-dbcas-조건)) |
| `seal.maxAttempts` | `""` | 버전 작업 하나를 시작하는 횟수의 상한(비우면 이미지 기본 `3`). 파드가 죽거나 OOMKill 돼 끊긴 작업은 임대가 끝난 뒤 처음부터 다시 시작하고, 시작이 이 값에 이르고 또 끊기면 `failed` 로 끝난다(작업 `error` 에 시작 횟수와 상한). 레플리카 1 에서 메모리가 모자라 같은 작업이 파드를 거듭 죽이는 것을 `1` 로 막는다 — `1` 이면 파드 교체·노드 장애로 끊긴 작업도 다시 돌지 않는다. 종료 신호·잠금 실패로 줄에 돌린 작업은 세지 않는다. `1`~`3` 만 받고 그 밖(`0` 포함)이면 기동이 실패한다 |
| `ingest.admissionWaitMs` | `""` | 적재가 자리를 기다리는 상한(ms). 넘기면 대기가 아니라 **`429` + `Retry-After: 1`**. 비우면 서버 기본 3000. `0`이면 기다리지 않는다(자리가 비어 있으면 통과, 없으면 그 자리에서 `429`) |
| `explorer.draftBulkReadEnabled` | `true` | `false` 면 SDK 가 표시 헤더 `X-Nexus-Bulk-Read: 1` 을 붙인 draft 버전의 explorer 대량 읽기(draft `to_df`·`iter_samples`·`samples()`(기본 `include_annotations=True`)·`shuffle`·`sort_by`·`fingerprint`·subset `to_df`)를 **`403`**(`code: draft_bulk_read_disabled`)으로 거절한다. 웹 화면·표시 없는 클라이언트·sealed 읽기는 영향이 없다 — 협조하는 클라이언트용 운영 장치이지 보안 경계가 아니다. 서버 전체에 하나이고 파드를 다시 띄워야 반영된다. 켜 둔 채로도 표시가 붙은 draft 읽기는 요청 로그에 `bulk_read=draft`·`dataset_id`·`version`·`rows` 로 남는다. 적용 값은 `GET /api/v1/admin/config-effective` 의 `explorer.draft_bulk_read_enabled` |
| `strategy` | `{}` | Deployment 교체 방식. 비우면 쿠버네티스 기본 RollingUpdate. 옛 파드와 함께 돌 수 없는 판은 `--set strategy.type=Recreate` 로 교체한다(그 판의 CHANGELOG 에 적는다) — 옛 파드를 모두 내린 뒤 새 파드를 띄우므로 그동안 서비스가 끊긴다. Recreate 로 바꿀 때는 업그레이드 **전에** `kubectl -n <ns> patch deploy <fullname> --type=json -p '[{"op":"replace","path":"/spec/strategy/type","value":"Recreate"},{"op":"remove","path":"/spec/strategy/rollingUpdate"}]'` 로 Deployment 를 먼저 바꾸고(strategy 만 바뀌어 파드는 다시 뜨지 않는다, `remove` 만 보내면 API 서버가 기본값을 다시 채워 효과가 없다) `kubectl -n <ns> get deploy <fullname> -o jsonpath='{.spec.strategy}'` 로 확인한 뒤 같은 값으로 올린다. 차트도 Recreate 면 `rollingUpdate: null` 을 함께 렌더해 helm 3 은 patch 없이도 통과하지만, **helm 4(server-side apply)는 `spec.strategy.rollingUpdate: Forbidden` 으로 거부하므로 patch 가 필수다**(kind 에서 helm 3·4 로 확인). **`--reuse-values` 로 올리면 직전 릴리스 values 가 렌더되어 이미지가 옛 태그로 남고 파드가 다시 뜨지도 않는데 `helm history` 는 새 차트로 업그레이드 완료로 보인다**(helm 3·4 확인) — 쓰지 않거나 `--set image.tag=<새 태그>` 를 함께 주고, `--reset-then-reuse-values` 는 새 차트 기본값을 쓴다. RollingUpdate 로 되돌릴 때 helm 4 는 patch 가 `strategy.type` 을 소유해 values 에서 지우기만 하면 Recreate 가 남고 `--set strategy.type=RollingUpdate` 는 field manager 충돌로 거부된다 — `--force-conflicts --set strategy.type=RollingUpdate` 로 올리거나 `kubectl -n <ns> patch deploy <fullname> --type=merge -p '{"spec":{"strategy":{"type":"RollingUpdate"}}}'` 로 먼저 되돌린다 |
| `secret.existingSecret` | `""` | 비밀 Secret 이름(비우면 fullname) |
| `service.type` / `service.nodePort` | `NodePort` / `30090` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 250m/256Mi ~ 1000m/1Gi | 요청/제한 |
| `preStopSleepSeconds` | `5` | 파드를 종료할 때 SIGTERM 전에 기다리는 초(정수). 그동안 Service·ingress 에서 파드가 빠진다 — 서버는 SIGTERM 을 받으면 곧바로 새 연결을 닫고 진행 중인 요청만 마친다(graceful shutdown). `terminationGracePeriodSeconds`(기본 `30`)에 포함되므로 진행 중 요청에 남는 시간은 그 차이다. `0` 이면 끈다. values 에 키가 없어도 `5` 로 렌더한다 |
| `auth.superuserEmail` | `""` | **비우면 관리자를 만들 부트스트랩 수단이 없다.** 채우면 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`도 **반드시 함께** 있어야 한다([superuser](#superuser)) |
| Secret `NEXUS__METRICS__TOKEN` | (없음) | 넣으면 `GET /_internal/metrics`가 열리고 없으면 **404**다. values 스위치는 없다 — 이 차트는 Secret 전체를 `envFrom`으로 받으므로 키를 넣는 것이 곧 켜는 것 |
| `serviceAccount.automountToken` | `false` | ServiceAccount 토큰 마운트 여부. 파드 토큰에 기대는 사이드카가 있거나 `auth.oidc.issuers` 에 `jwksAuth: serviceaccount` 를 쓰면 `true` |

인증 관련 키(`jwt.*`·`auth.*`)는 [인증 설정](#인증-설정), CVAT 키(`cvat.*`)는 [CVAT 연동](#cvat-연동)에 있다. 전체 키는 [`values.yaml`](values.yaml) 참조.

## 계정과 권한 관리

### superuser

설정으로 지정하는 관리 계정이다. 이메일은 `auth.superuserEmail`, 비밀번호는 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`(8자 이상)에 넣는다.

**관리자는 둘 이상 둘 수 있다.** 관리 권한의 출처가 둘이기 때문이다 — 설정의 superuser(이 계정)와 `users.role = admin`. 후자는 superuser나 다른 `admin` 계정이 `POST /api/v1/admin/users/role`(또는 승인 시 `users/approve`)로 부여한다. `admin`은 마이그레이션이 백필하지 않으므로 **최초 한 명을 만들려면 이 설정이 필요하고**, 한 명이라도 생긴 뒤에는 설정을 비워도 그 계정들이 관리 권한을 유지한다. 감사 로그는 없다.

**CVAT과 달리 반쪽 설정은 조용히 꺼지지 않는다 — 서버가 기동에 실패한다.** 이메일만 있고 비밀번호가 없어도(공백만 있는 경우 포함), 비밀번호만 있고 이메일이 없어도 마찬가지다. 운영자가 켰다고 믿는데 실제로는 꺼져 있는 상태가 가장 나쁘고, 그 사실이 정작 필요한 순간(누군가 잠겼을 때)에야 드러나기 때문이다. **차트는 이 짝을 검사할 수 없다** — 비밀번호는 Secret에서 `envFrom`으로 들어와 템플릿에 보이지 않는다. 그래서 `helm upgrade`는 조용히 성공하고 Pod가 CrashLoop로 드러나며, 어느 쪽이 빠졌는지는 `kubectl logs`에 적힌다. 끌 때는 `auth.superuserEmail`과 시크릿 키를 **함께** 비운다.

**시크릿의 비밀번호는 계정이 없을 때 새로 만드는 데만 쓰인다.** 서버가 기동 시 그 계정이 없으면 만들고(그래야 그 주소를 아무도 선점할 수 없다), 이미 있으면 **비밀번호를 읽지도 덮지도 않는다** — 운영자가 API로 바꾼 값이 파드 재시작마다 되돌아가면 안 되기 때문이다. 그래서 비밀번호를 바꾼 뒤 시크릿을 갱신할 필요가 없고, 반대로 시크릿을 바꿔 재배포해도 로그인 비밀번호는 바뀌지 않는다. 다만 위 기동 검사 때문에 값은 8자 이상으로 남겨 둔다.

**superuser 비밀번호를 잊었다면** 시크릿을 고쳐도 소용이 없다. `auth.superuserEmail`을 **아직 가입되지 않은** 새 주소로 바꿔 재배포하면 서버가 그 주소로 계정을 새로 만들고, 그때 시크릿의 비밀번호가 쓰인다(이미 누가 쓰는 주소를 넣으면 그 계정을 채택하므로 그 사람이 superuser가 된다). 같은 주소를 유지해야 한다면 운영자가 DB에서 그 `users` 행을 직접 지운 뒤 재기동하는 방법뿐이다 — **superuser 계정은 API로 삭제할 수 없고(403), 그 이메일로는 가입할 수도 없다(409).** 계정이 사라진 창에 아무나 그 주소를 선점하면 그대로 최고 권한을 가져가기 때문이다.

**이메일을 바꿔 재배포해도 이전 계정의 관리 권한은 회수되지 않는다.** 서버가 기동 시 superuser 계정에 `role = admin`을 부여하므로, 설정에서 빠진 이전 계정은 `admin`으로 남는다. 회수하려면 새 관리자가 `POST /api/v1/admin/users/role`로 이전 계정을 강등한다.

**superuser 계정을 대상으로 삼는 관리 조작 넷은 누가 부르든 403이다** — 역할 변경(`users/role`)·정지(`users/active`)·비밀번호 재설정(`users/password-reset`)·재설정 링크 발급(`users/password-reset-links`). 유일한 부트스트랩 수단이 스스로 잠기는 것을 막기 위해서다.

### 관리 API

전부 superuser 또는 `role = admin` 계정의 토큰으로 부른다.

| 경로 | 용도 |
|---|---|
| `GET /api/v1/admin/users` | 회원 목록. `?email=`(부분검색)·`?role=`·`?kind=`(`human`/`robot`)·`?approved=`로 좁히고 `?cursor=<마지막 user_id>`·`?limit=`(기본 100, 최대 1000)으로 넘긴다. `is_superuser`가 `true`인 행은 위 403 제한이 걸리는 계정이다 |
| `POST /api/v1/admin/users` | 사람 계정 생성(만드는 순간 승인됨) |
| `POST /api/v1/admin/users/role` | 역할 변경 |
| `POST /api/v1/admin/users/active` | 계정 정지·해제 |
| `GET /api/v1/admin/users/pending` · `POST /api/v1/admin/users/approve` | 승인 대기 목록·승인(`auth.approvalRequired`가 켜진 배포) |
| `POST /api/v1/admin/users/password-reset` | 임시 비밀번호 발급 |
| `POST /api/v1/admin/users/password-reset-links` | 비밀번호 재설정 일회용 링크 토큰 발급(아래) |
| `PUT /api/v1/admin/datasets/{id}/owner` · `POST /api/v1/admin/datasets/transfer-owner` | 담당자 지정·일괄 이관 |
| `POST /api/v1/admin/robots` · `GET` | 로봇 계정 생성·목록 |
| `DELETE /api/v1/admin/robots/{user_id}` | 로봇 계정 삭제 |
| `POST /api/v1/admin/robots/{user_id}/tokens` · `GET` | 토큰 발급·목록 |
| `PATCH /api/v1/admin/robots/{user_id}/tokens/{token_id}` | 토큰 만료 앞당기기 |
| `DELETE /api/v1/admin/robots/{user_id}/tokens/{token_id}` | 토큰 폐기 |
| `POST /api/v1/admin/oidc-identities` · `GET` | OIDC 신원 `(issuer, subject)` → 계정 매핑 등록·목록. 목록은 `?user_id=`로 좁힌다 |
| `DELETE /api/v1/admin/oidc-identities/{identity_id}` | 매핑 삭제. 그 신원 하나만 막는다 |
| `GET /api/v1/admin/config-effective` | 지금 그 프로세스가 읽은 설정값([적용된 설정 확인](#적용된-설정-확인)) |

```python
import requests
h = {"Authorization": f"Bearer {admin_token}"}   # superuser 또는 role=admin 계정의 토큰

# 사람 계정 만들기 — 공개 가입을 닫아 둔 채
r = requests.post(f"{base}/api/v1/admin/users",
                  json={"email": "새사람@example.com", "role": "editor", "issue_password": True}, headers=h)
print(r.json().get("password"))   # issue_password=True 일 때만 응답에 실린다. 지금 전달할 것

# 비밀번호를 잊은 계정 풀어주기 — 임시 비밀번호가 응답에 한 번만 실려 온다
r = requests.post(f"{base}/api/v1/admin/users/password-reset",
                  json={"email": "잠긴사람@example.com"}, headers=h)
print(r.json()["password"])   # 어디에도 저장되지 않는다. 지금 전달할 것

# 역할 변경 / 계정 정지·해제
requests.post(f"{base}/api/v1/admin/users/role",
              json={"email": "동료@example.com", "role": "admin"}, headers=h)
requests.post(f"{base}/api/v1/admin/users/active",
              json={"email": "떠난사람@example.com", "active": False}, headers=h)

# 담당자 지정(담당자가 없는 dataset의 인수) / 일괄 이관(A가 담당하던 전부를 B에게)
requests.put(f"{base}/api/v1/admin/datasets/{dataset_id}/owner",
             json={"email": "새담당자@example.com"}, headers=h)
requests.post(f"{base}/api/v1/admin/datasets/transfer-owner",
              json={"from_email": "떠난사람@example.com", "to_email": "새담당자@example.com"}, headers=h)
```

- **사람 계정 만들기** — 공개 가입(`auth.registrationEnabled`)을 끈 배포에서도, 승인 대기(`auth.approvalRequired`)를 켠 배포에서도 만들 수 있고 **만든 계정은 만드는 순간 승인된다.** `role`은 `editor`/`viewer`만(`admin`은 `400` — 승격은 `users/role`). `issue_password: true`면 임시 비밀번호를 응답에 한 번만 싣고, 생략하면 **비밀번호로는 로그인할 수 없는 계정**이 된다(OIDC 신원을 붙여 쓸 사람용 — `admin/oidc-identities`로 매핑하고, 나중에 비밀번호가 필요하면 `users/password-reset`). 이미 있는 이메일·superuser 이메일은 `409`, 로봇 도메인 이메일은 `400`(로봇은 `admin/robots`).
- **임시 비밀번호는 응답에 한 번만 실려 온다.** 서버 어디에도 저장되지 않으니 그 자리에서 전달하고, 받은 사람은 곧바로 `client.change_password(...)`로 바꾼다. 재설정해도 그 사람의 기존 토큰은 만료(`jwt.ttlHours`)까지 유효하다 — "잊어버림"을 푸는 도구지 "탈취 즉시 차단"이 아니다.
- **재설정 링크는 임시 비밀번호 대신 쓰는 일회용 토큰이다.** 발급은 본문 `{"email", "expires_in_hours"}`(1~72, 필수)이고 `201` 응답에 `token` 평문이 한 번만 실린다. 사용자는 인증 없이 `POST /api/v1/auth/password-reset/inspect`(`{token}` → 이메일·만료 확인)와 `POST /api/v1/auth/password-reset/complete`(`{token, new_password}` → `204`, 로그인은 따로 한다)를 부른다. 판정 실패(없음·이미 씀·만료·대상 부적격)는 모두 `400` `reset_link_invalid` 하나이고 사유는 요청 로그의 `reset_error` 에만 남는다. 새 비밀번호가 규칙에 맞지 않으면 `code` 없는 `400` 이고 링크는 소모되지 않는다. 사용자당 살아 있는 링크는 하나이며, 다시 발급하거나 임시 비밀번호 재설정·본인 비밀번호 변경을 하면 이전 링크는 무효다. 링크를 사용자에게 전달하는 경로의 보안은 운영자 몫이다.
- **계정 정지는 삭제가 아니다.** 이메일을 계속 점유하므로 그 주소로 재가입할 수 없고, `active: true`로 해제하면 그대로 돌아온다. 정지하면 로그인이 `403 forbidden`이 되고, **이미 발급된 토큰도 캐시 수명(`auth.revocationCacheTtlSecs`, 기본 5초) 안에 막힌다.**
- **담당자 이전은 인가를 옮기지 않는다.** 이전 담당자도 계속 쓰고 지울 수 있다 — 역할이 `editor`이기 때문이다. 옮겨가는 것은 「다시 넘길 자격」 하나다. 담당자가 없는 dataset(`GET /datasets?unowned=true`)은 위험한 상태가 아니라 **인수 대기**이고, `editor` 이상이면 그대로 쓰고 지울 수 있다. 담당자가 있는 dataset을 넘기는 것은 담당자 본인이 한다([사용법 8.2](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/docs/usage.md#82-담당자-이전)).

**로그인·가입·갱신·OIDC 교환의 `200` 응답은 모두 `{ token, user_id, email }`이다** — 로그인 화면이 실어 쓰는 토큰 필드는 `token`이다. 가입이 승인 대기(`auth.approvalRequired`)면 `202`이고 타입이 다르다.

### 로봇 계정 발급

사람이 없는 워크로드(적재 잡·스케줄러·CI)용 계정이다. 쓰는 쪽은 [사용법 2.3](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.28/charts/nexus-server/docs/usage.md#23-로봇-토큰으로-연결)의 `nx.connect(robot_token=...)`로 붙는다.

계정 생성(`POST /api/v1/admin/robots`, body `{"name": "...", "role": "editor", "display_name": "..."}`, `display_name`만 선택)의 이름은 소문자·숫자·하이픈 1~48자이고 하이픈으로 시작하거나 끝날 수 없다(`400`). **이름 검사가 `role` 검사보다 먼저 돈다** — 이름이 틀린 동안에는 `role` 오류를 볼 수 없다. 로봇의 `role`은 `editor`·`viewer`뿐이고 `admin`은 `400`이다 — `admin` 로봇의 장수명 토큰은 그대로 관리 평면 전권이 되기 때문이다. 경로의 `user_id`는 정수다(UUID를 넣으면 본문 검사 전에 `400`).

토큰 발급은 `POST /api/v1/admin/robots/{user_id}/tokens`로 한다. body는 `{"label": "...", "expires_in_days": 1~365}`이고 **둘 다 필수다** — `label`을 빠뜨리면 `422`이고, 계정 생성은 이미 끝났으므로 **토큰 없는 계정이 남는다**. **평문은 발급 응답에만 한 번 실린다.** 계정 하나에 토큰을 여럿 둘 수 있어, 새 토큰을 배포하고 `last_used_at`으로 확인한 뒤 옛 토큰을 폐기하면 중단 없이 회전한다.

**만료는 앞당길 수만 있다.** `PATCH /api/v1/admin/robots/{user_id}/tokens/{token_id}` body `{"expires_at": "<RFC 3339>"}` — 현재 만료보다 빠르고 지금보다 뒤여야 하며, 연장·같은 값·과거 시각은 `400`이다.

### 인증 설정

| values 키 | 기본값 | 설명 |
|---|---|---|
| `jwt.ttlHours` | 빈 값 (서버 기본 **24**) | 발급 토큰의 수명(시간). 허용 범위 **1~8760**. 토큰 자체는 무효화할 수 없으므로 이 값이 곧 탈취·비밀번호 변경 이후에도 토큰이 살아있는 최대 시간이다(계정 삭제·정지·역할 회수는 `auth.revocationCacheTtlSecs` 안에 반영된다). **범위를 벗어난 값(`0` 포함)을 주면 서버가 기동에 실패한다**(DB 연결보다 먼저 검사). 줄이면 노출 시간은 줄지만 `POST /api/v1/auth/refresh` 호출이 그만큼 잦아진다. |
| `auth.registrationEnabled` | `true` | `false`로 하면 `POST /api/v1/auth/register`만 403이 되고, 로그인·토큰 갱신·기존 계정은 영향을 받지 않는다. 가입을 닫은 뒤에도 관리자는 사람 계정(`POST /api/v1/admin/users`)과 로봇 계정(`POST /api/v1/admin/robots`)을 만들 수 있다 — 둘 다 이 값을 보지 않는다. |
| `auth.docsEnabled` | `true` | `false`로 하면 `/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/` 세 경로가 **404**가 된다(라우트 자체가 등록되지 않는다 — 403이 아니다). 스펙은 이미 전 경로가 인증 뒤에 있으므로, 이걸로 감추는 것은 API 경로 목록뿐이다. |
| `auth.approvalRequired` | `false` | `true`로 하면 가입은 열어 둔 채 **승인 전까지 아무것도 할 수 없다.** 가입 요청은 계정을 만들되 **토큰을 주지 않고** `202`와 `{"user_id", "email", "status": "pending"}`(토큰 없음)을 반환하며, 승인 전에는 로그인·토큰 갱신이 `403`이다(본문 `pending_approval`). 승인은 `POST /api/v1/admin/users/approve`(본문에 `email`·`role` 필수), 대기 목록은 `GET /api/v1/admin/users/pending`. **켜기 전에 가입 화면이 `202`를 처리해야 하고**, 승인 엔드포인트가 관리자 전용이라 관리자(superuser 또는 `admin` 계정)가 있어야 한다. 켜기 전에 가입한 계정은 영향받지 않는다. |
| `auth.oidc.issuers` | `[]` (기능 꺼짐) | 외부 IdP가 발급한 토큰을 인증 자격증명으로 받을 발급자 목록. 항목마다 `issuer`(필수, `https://`, 토큰의 `iss`와 같아야 한다) · `audience`(필수, 토큰 `aud` **안에 있으면** 통과하는 포함 검사) · `exchange`(기본 `false`, `POST /api/v1/auth/oidc/exchange`를 이 발급자에게 여는 스위치 — 자동 회전하는 토큰에는 켜지 말 것) · `jwksUri`(선택, 발급자와 JWKS 호스트가 다를 때) · `jwksAuth`(선택, `serviceaccount` 하나만 — 파드 자신의 SA 토큰을 실어 JWKS를 읽는다. `serviceAccount.automountToken: true`가 필요하다) · `caFile`(선택, 이 발급자의 JWKS 조회에만 더해 믿을 CA 파일. [사내 CA](#사내-ca)의 `caCerts` 에 넣은 파일은 `/etc/nexus/ca/<파일 이름>`. 빈 값은 렌더 실패). **`audience`가 비었거나, `issuer`가 비-https·중복이거나, `jwksUri`가 비-https이거나, `jwksAuth`가 `serviceaccount`가 아니면 기동에 실패한다.** 목록이 비면 기능이 꺼질 뿐 기동은 정상이다. **발급자만 설정하면 아무도 인증되지 않는다** — 신원 `(issuer, subject)` → 계정 매핑을 `POST /api/v1/admin/oidc-identities`로 관리자가 등록해야 하고 자동 생성은 없다. superuser와 `role = admin` 계정에는 신원을 붙일 수 없다. 이 갈래로 온 요청은 `POST /api/v1/auth/refresh`가 `403`이다. |
| `auth.revocationCacheTtlSecs` | 빈 값 (서버 기본 **5**초) | 인증이 사용자 행(역할·승인·활성 상태)을 읽고 캐시하는 시간. **이 값이 곧 권한 회수·계정 정지·계정 삭제가 듣기까지의 상한이다.** `0`이면 매 요청 조회가 되어 즉시 반영되지만 적재 처리량이 20~33% 떨어진다(측정치). 조회 자체를 끄는 옵션은 없다. |

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소> \
  --set jwt.ttlHours=8 \
  --set auth.registrationEnabled=false \
  --set auth.docsEnabled=false
```

## 사내 CA

OIDC 발급자나 CVAT 이 사내 CA 로 서명한 https 를 쓰면 `caCerts` 에 그 CA 를 넣는다. 키가 파일 이름, 값이 PEM 이고, 비어 있지 않으면 ConfigMap 으로 만들어 `/etc/nexus/ca` 에 디렉터리째 읽기 전용으로 마운트한다(`subPath` 를 쓰지 않는다).

| values 키 | 기본값 | 설명 |
|---|---|---|
| `caCerts` | `{}` | 추가로 믿을 CA. 루트 CA 를 반드시 넣는다 — 발급 CA 한 장만으로는 검증이 루트에 닿지 않는다. 한 키에 여러 장을 넣어도 되고, 같은 CA 는 한 번만 넣어 `auth.oidc.issuers[].caFile` 과 `cvat.caFile` 이 같이 가리킨다 |

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set-file 'caCerts.sso-ca\.pem=./sso-ca.pem' \
  --set-json 'auth.oidc.issuers=[{"issuer":"https://sso.example.com/realms/x","audience":"nexus","caFile":"/etc/nexus/ca/sso-ca.pem"}]'
```

- `caFile` 이 `/etc/nexus/ca/` 아래를 가리키는데 `caCerts` 에 그 이름의 키가 없으면 렌더가 실패한다. OIDC 발급자의 빈 `caFile` 도 서버가 기동에 실패하므로 렌더에서 먼저 막는다.
- OIDC 는 JWKS 를 조회할 때마다 파일을 읽으므로 파일이 바뀌면 다음 조회부터 반영된다(ConfigMap 을 고친 뒤 kubelet 이 파일을 갱신하는 시점은 시험하지 않았다). CVAT 은 기동 때 한 번 읽어 파드를 다시 띄워야 반영되고, 못 읽으면 CVAT 연동만 꺼진다(세션 라우트 503).
- CAS(`cas.baseUrl`)가 사내 CA 서명 https 면 이 기능이 닿지 않는다. 키 이름을 해시 이름(`<주체 해시>.0`, `openssl x509 -hash -noout` 의 출력)으로 넣고 `extraEnv` 로 `SSL_CERT_DIR=/etc/nexus/ca` 를 주면 같은 ConfigMap 으로 된다.

## CVAT 연동

annotation을 CVAT에서 편집하려는 경우에만 설정한다. **설정하지 않아도 nexus는 정상 동작한다** — 세션 **생성**·**계획**·**결과 회수**(import)만 503을 반환하고, 카탈로그·업로드·seal·조회는 영향을 받지 않는다.

### CVAT 쪽 준비

nexus가 통제하지 않는 부분이라 CVAT 관리자와 함께 준비해야 한다.

| 항목 | 내용 |
|---|---|
| 서비스 계정 | nexus 가 쓸 CVAT 계정 1 개. 일반 계정이면 된다(superuser 불필요). 모든 project 를 이 계정이 소유하므로 작업자가 링크를 열려면 CVAT 관리자이거나 같은 organization(`cvat.organization`)에 있어야 한다. organization 을 쓰면 서비스 계정은 `supervisor` 이상(`worker` 면 project 생성이 `403`), 작업자는 `maintainer` 이상이어야 한다 — 링크가 task 페이지라 `worker` 는 job 에 배정돼도 열 수 없다 |
| 네트워크 도달 | **CVAT 워커 컨테이너**에서 CAS 주소로 HTTP 요청이 가능해야 한다. 이미지는 nexus를 거치지 않고 CVAT이 CAS에서 직접 받는다 |
| smokescreen 허용 | CVAT은 원격 URL 다운로드에 SSRF 가드(smokescreen)를 거친다. CAS가 사설 IP면 기본 설정에서 차단되므로 허용 대역을 지정해야 한다 |
| 이미지 읽기 권한 | nexus 는 CVAT 에 넘기는 이미지 URL 에 서버 키(`NEXUS__CAS__KEY_ID`)로 GET 서명을 붙인다(만료 `cvat.imageUrlExpirySecs`). cas 가 익명 GET 을 닫았으면(`anonymousGet: false`) 이 키에 이미지 버킷의 `GetObject` 권한이 있어야 한다. 서명한 URL 은 CVAT DB 와 워커 로그에 남는다 |

smokescreen은 CVAT 컨테이너 안에서 로컬 프록시로 동작하며, compose의 `SMOKESCREEN_OPTS` 환경변수로 허용 대상을 지정한다.

```bash
# CVAT의 .env 등에 지정한 뒤 서버·워커를 재생성한다
SMOKESCREEN_OPTS=--allow-range=10.0.0.0/8        # 또는 --allow-address=<CAS IP>

docker compose up -d --force-recreate cvat_server cvat_worker_import cvat_worker_chunks
```

**확인 방법.** 워커 안에서 프록시를 경유해 CAS 오브젝트를 실제로 받아본다. 워커에서 `curl`이 직접 성공하더라도 프록시를 거치지 않으면 의미가 없으므로, `-x`로 프록시를 명시해서 확인한다.

```bash
# 프록시 경유로 200이 나와야 한다. 407이면 smokescreen이 막고 있는 것이다.
docker exec cvat_worker_import curl -s -o /dev/null -w '%{http_code}\n' \
  -x http://127.0.0.1:4750 http://<CAS>/<bucket>/<object-key>
```

### nexus 설정

서비스 계정 비밀번호는 [시크릿](#1-시크릿-주입-sealed-secret)의 `NEXUS__CVAT__PASSWORD`로 주고(values에 두지 않는다), 나머지는 values로 준다. **`cvat.baseUrl`·`cvat.user`·비밀번호 셋이 다 있어야** 켜진다.

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소> \
  --set cvat.baseUrl=http://cvat.example.com:8080 \
  --set cvat.user=nexus-svc
```

| values 키 | 기본값 | 설명 |
|---|---|---|
| `cvat.baseUrl` | `""` | CVAT 주소. **비우면 연동이 꺼진다**. 단 시크릿에 `NEXUS__CVAT__PASSWORD`만 넣어 두면 기동 로그가 「설정 없음」이 아니라 「설정이 불완전」 경고(`missing=base_url, user`)가 된다 — 동작은 같다 |
| `cvat.user` | `""` | CVAT 서비스 계정 |
| `cvat.organization` | `""` | CVAT organization slug (선택) |
| `cvat.projectNamePrefix` | `nexus` | 생성되는 CVAT project 이름 접두사 |
| `cvat.segmentSize` | `""` | job 분할 크기. 비우면 CVAT 기본 동작(job 하나). 값을 주면 job 경계를 지나는 CVAT 트랙이 둘로 저장되어 「가져오기」에서 두 `track_id` 가 된다 — 트랙을 쓰면 비워 둔다 |
| `cvat.maxSessionSamples` | `""` | 세션당 샘플 상한(서버 기본 2000). 세션 계획 API 의 묶음 크기 상한(`session_cap`)도 이 값이다 |
| `cvat.staleCreatingSecs` | `""` | 준비 작업의 진행 기록(60 초마다)이 이 시간(초)보다 오래 멈춘 `creating` 세션을 `failed` 로 정리한다(서버 기본 1800). 각 파드가 5 분마다(기동 직후 포함) 검사하고, 다른 파드가 준비 중인 살아 있는 세션은 건드리지 않는다. 180 미만이면 180 으로 올려 쓰고 기동 로그에 경고를 남긴다(`config-effective` 에는 올린 값이 보인다) |
| `cvat.caFile` | `""` | CVAT 호출에 더해 믿을 CA 파일. 예: `/etc/nexus/ca/sso-ca.pem`([사내 CA](#사내-ca)의 `caCerts`). 못 읽으면 CVAT 연동만 꺼지고 기동은 된다. 기동 때 읽으므로 바꾸면 파드를 다시 띄워야 한다 |
| `cvat.publicUrl` | `""` | 작업자 링크(`cvat_url`) 주소. 비우면 `cvat.baseUrl`. API 는 늘 `cvat.baseUrl` 로 부른다 |
| `cvat.imageUrlExpirySecs` | `""` | CVAT 에 넘기는 presigned 이미지 URL 만료(초, 서버 기본 3600). 2100~604800 밖의 값은 범위로 깎고 기동 로그에 경고를 남긴다 |

### 연결 확인

기동 로그에 다음 중 하나가 남는다.

```
INFO  CVAT 연동 활성화 base_url=http://cvat.example.com:8080
WARN  [cvat] 설정이 불완전해 CVAT 연동을 켜지 않는다 ... missing=user, password
INFO  [cvat] 설정 없음 — annotation session 엔드포인트는 503을 반환한다
WARN  [cvat] 클라이언트를 만들지 못해 CVAT 연동을 켜지 않는다 — annotation session 엔드포인트는 503 reason=...
```

`baseUrl`/`user`/`password` 셋 중 하나라도 비면 연동을 켜지 않으며, **무엇이 빠졌는지 로그에 남는다.**

연동이 켜진 뒤 실제 동작은 세션을 하나 만들어 확인한다. 준비에 실패하면 세션 상태가 `failed`가 되고 사유가 세션의 `error`에 기록된다.

| 세션 `error` | 원인 |
|---|---|
| `CVAT login 요청 실패: ...` | CVAT이 떠 있지 않거나 주소가 틀렸다 |
| `CVAT login 실패: 401 ...` | 서비스 계정 아이디·비밀번호가 틀렸다 |
| `CVAT login 실패: 404 ...` | 그 주소에 CVAT API가 없다. **CVAT 앞단 프록시의 Host 기반 라우팅**인 경우가 많다 — 아래 참조 |
| `... likely attempt to access internal host` | smokescreen이 CAS 주소를 막고 있다 |
| `CVAT 데이터 첨부가 제한 시간 안에 ...` | 이미지 다운로드가 30분을 넘겼다. 샘플 수를 줄이거나 네트워크를 확인한다 |

`401`과 `404`를 구분해서 본다. **401은 계정 문제, 404는 주소 문제**다.

> **404가 나면서 루트(`/`)까지 404라면** CVAT 앞단 traefik이 Host 기반으로 라우팅하는데 그 규칙에
> 걸리지 않는 주소로 접근한 것이다. CVAT compose는 `CVAT_HOST` 값으로 traefik 라우터 규칙을
> 만들기 때문에, 그 값이 `localhost`인 상태에서 IP로 접근하면 traefik이 자기 기본 404
> (`404 page not found`, Go 서버 응답)를 돌려준다.
>
> ```bash
> # 확인 — Host 헤더를 바꿨을 때만 200이면 이 경우다
> curl -o /dev/null -w '%{http_code}\n'                      http://<CVAT-IP>:8080/api/server/about   # 404
> curl -o /dev/null -w '%{http_code}\n' -H 'Host: localhost' http://<CVAT-IP>:8080/api/server/about   # 200
> ```
>
> 해결은 CVAT 쪽에서 `CVAT_HOST`를 **실제 접속 주소(IP 또는 DNS 이름)로 바꾸고** traefik·서버·UI를
> 재생성하는 것이다. nexus의 `cvat.baseUrl`만 `localhost`로 되돌려 우회하면, nexus와 CVAT이 같은
> 호스트일 때만 동작하고 세션의 `cvat_url`이 `http://localhost:8080/tasks/N`으로 만들어져
> **다른 PC의 작업자가 열 수 없다.**

### 연결되지 않았을 때의 동작

| CVAT 상태 | 서버 기동 | 카탈로그 API | 세션 생성·계획·회수 | 세션 목록·조회·close·delete |
|---|---|---|---|---|
| 설정 없음 | 정상 | 정상 | 503 | 정상 |
| 설정 불완전 | 정상(경고 로그) | 정상 | 503 | 정상 |
| `cvat.caFile` 을 못 읽음 | 정상(경고 로그) | 정상 | 503 | 정상 |
| 설정됨, CVAT 다운 | 정상 | 정상 | 생성은 세션이 `failed`가 되고, 회수는 `502`(세션은 그대로). 계획은 정상 | 정상 |
| 정상 연결 | 정상 | 정상 | 정상 | 정상 |

503 의 사유는 [`config-effective`](#적용된-설정-확인)의 `cvat` 에 있다 — 설정이 없으면 `null`, 불완전하거나 `caFile` 을 못 읽었으면 `cvat.missing_fields`·`cvat.disabled_reason`.

**목록·조회·`close`·`delete`는 CVAT 없이도 동작한다.** CVAT을 호출하지 않거나(목록), 호출에 실패해도 진행하기 때문이다(조회·`close`는 미반영 편집 여부를 「모름」으로 두고, `delete`는 CVAT project 삭제를 건너뛰고 세션 행만 지운다). 이미 만들어진 세션을 CVAT이 죽은 뒤에도 정리할 수 있어야 하기 때문이다 — 그러지 않으면 샘플이 영구히 잠긴다.

nexus는 기동 시점에 CVAT을 호출하지 않는다. 따라서 운영 중 CVAT이 내려가도 영향은 세션 생성·회수에만 국한된다(계획은 CVAT을 호출하지 않는다).

## 기동 마이그레이션이 길어질 때

**기동 마이그레이션에는 스키마 변경만 둔다.** 표·열·인덱스를 만드는 것만 기동 때 하고, 기존 행을 훑어 다른 표를 채우는 일(백필)은 정합성에 필요한 것이 아니면 기동 마이그레이션에 넣지 않는다. 기동 확인 예산이 곧 마이그레이션의 시간 한도이고, 예산을 넘기면 그때까지 한 일이 버려져 처음부터 다시 돌기 때문이다. 기동에서 넘길 수 있는 행 채우기 마이그레이션은 030(meta 필드 관측의 실수 표시)과 032(sealed 버전의 샘플 수) 둘이고, 절차는 아래와 같다.

**무엇이 멈춰 있는지 보기.** 기동 10 초 뒤부터 60 초마다, 마이그레이션 잠금을 쥐었거나 기다리는 DB 세션을 한 줄씩 남긴다. 마이그레이션이 그 안에 끝나면 아무 줄도 남지 않는다.

```
마이그레이션 잠금 세션 pid=857 granted=true state="active" wait_event="" client_addr="10.0.3.17" application_name="" xact_secs=3600 query_secs=3600 query="-- meta 필드 관측에 실수 표시 행(`float`)을 채운다 — `/schema` 가 관측 전용 숫자 " blocked_by=""
마이그레이션 잠금 세션 pid=860 granted=false state="active" wait_event="advisory" client_addr="10.0.3.21" application_name="" xact_secs=10 query_secs=10 query="SELECT pg_advisory_lock($1)" blocked_by="857"
```

- `granted=true` 가 잠금을 쥔 세션이다. `query` 는 그 세션이 돌리는 질의의 앞 60 자이고, 마이그레이션 파일의 첫 줄(주석)이면 마이그레이션이 도는 중이고 `xact_secs` 가 그 마이그레이션의 소요다. `client_addr` 가 지금 떠 있는 파드가 아니면 앞서 죽은 컨테이너가 남긴 세션이다.
- `granted=false` 는 잠금을 기다리는 세션이다. 이 파드 자신도 여기 나온다.
- `blocked_by` 는 그 세션을 막고 있는 세션의 pid 다(쉼표로 여럿). 잠금을 쥔 마이그레이션 세션의 `blocked_by` 가 비어 있지 않으면 마이그레이션이 다른 세션의 표 잠금을 기다리는 중이다.

**남은 세션 막기와 정리.** 컨테이너가 죽어도 DB 는 그 세션의 질의를 계속 돌리고 잠금을 쥔 채 남는다(`client_connection_check_interval` 이 0 일 때). nexus-server 의 DB 사용자에 아래를 걸어 두면 연결이 끊긴 세션은 실행 중이든 잠금 대기 중이든 다음 확인 때 끝난다. 새로 맺는 연결부터 적용되고, 연결이 살아 있는 질의에는 영향이 없다. PostgreSQL 14 이상이고, DB 와 nexus-server 사이에 TCP 프록시·연결 풀러가 있으면 그 중계자와의 연결을 보게 되어 효과가 없을 수 있다.

```sql
ALTER ROLE <nexus-server 의 DB 사용자> SET client_connection_check_interval = '10s';
```

이미 남은 세션은 끊는다. 아래 조건은 마이그레이션 질의(파일이 주석으로 시작한다)와 마이그레이션 잠금 대기만 잡고, 서비스 중인 파드의 세션은 잡지 않는다. 살아 있는 파드의 대기 세션을 끊으면 그 컨테이너가 한 번 재시작할 뿐이다.

```sql
SELECT pid, state, wait_event, now() - query_start AS running, client_addr, left(query, 40)
FROM pg_stat_activity
WHERE datname = current_database()
  AND (query LIKE '-- %' OR query LIKE 'SELECT pg_advisory_lock(%');
-- 목록을 확인한 뒤
SELECT pg_terminate_backend(<pid>);
```

**행 채우기 마이그레이션(030·032)을 기동에서 넘기기.** 아래로 두 마이그레이션을 적용됨으로 기록하면 기동은 나머지만 적용한다. 체크섬은 이미지에 든 마이그레이션 본문의 SHA-384 이고, 한 바이트라도 다르면 이후 모든 기동이 `migration 30 was previously applied but has been modified` 로 실패하므로 그대로 옮긴다. 두 마이그레이션 파일은 이후 판에서도 바뀌지 않는다. **스키마를 만드는 다른 마이그레이션에는 이 방법을 쓰지 않는다.**

```sql
-- psql 에서 트랜잭션 블록(BEGIN) 밖에서. 030 이 도는 중이면 이것을 먼저 커밋한 뒤 위 조건으로 030 세션을 끊는다
INSERT INTO _sqlx_migrations (version, description, success, checksum, execution_time) VALUES
  (30, 'meta field float backfill', TRUE,
   decode('c7a7e6a133c90fcdad53b6848d18478dd4410982674a45f85347650964e370c0ef68af6030f66c0c2772a147bf6fb029', 'hex'), 0),
  (32, 'sealed sample count backfill', TRUE,
   decode('64a080ec3919647555e31dd1858684b15973f83c9267a3a62947ca0869846a5d21d79baff73d09b6906a5901a1fdd8bc', 'hex'), 0);
```

넘긴 동안 달라지는 것은 둘이다. 030 몫은 기존 실수 meta 필드가 `GET .../schema` 에서 `int` 로 보이는 것(그 필드에 실수 값이 새로 적재되면 `float` 가 된다), 032 몫은 기존 sealed 버전 응답에 `sample_count` 가 빠지는 것이다. 기동한 뒤 아래로 채운다. 둘 다 행을 더하기만 해 서비스 중에 돌려도 되고, `samples` 를 넓게 읽으므로 seal 과 겹치지 않는 시각을 고른다.

```sql
-- 032 몫 (한 트랜잭션)
INSERT INTO dataset_version_sample_counts (dataset_version_id, sample_count)
SELECT v.dataset_version_id, count(s.sample_id)
FROM dataset_versions v
LEFT JOIN dataset_version_samples dvs ON dvs.dataset_version_id = v.dataset_version_id
LEFT JOIN samples s ON s.sample_id = dvs.sample_id AND s.is_deleted = FALSE
WHERE v.status = 'sealed'
GROUP BY v.dataset_version_id
ORDER BY 1
ON CONFLICT DO NOTHING;

-- 030 몫 (데이터셋마다 커밋하고 n/N 을 남긴다. psql 에서 트랜잭션 블록 밖에서)
DO $$
DECLARE
  d uuid;
  n int := 0;
  total int;
BEGIN
  SELECT count(*) INTO total FROM datasets;
  FOR d IN SELECT dataset_id FROM datasets ORDER BY dataset_id LOOP
    INSERT INTO dataset_schema_meta_fields (dataset_id, field, value_type)
    SELECT DISTINCT s.dataset_id, k, v.t
    FROM samples s,
         LATERAL jsonb_object_keys(
             CASE WHEN jsonb_typeof(s.meta) = 'object' THEN s.meta ELSE '{}'::jsonb END
         ) k,
         LATERAL (VALUES
             (jsonb_typeof(s.meta->k)),
             (CASE WHEN jsonb_typeof(s.meta->k) = 'number' AND strpos(s.meta->>k, '.') > 0 THEN 'float' END)
         ) v(t)
    WHERE s.dataset_id = d
      AND s.is_deleted = FALSE
      AND v.t IS NOT NULL
      AND v.t <> 'null'
      AND k ~ '^[A-Za-z0-9_]+$'
    ORDER BY 1, 2, 3
    ON CONFLICT DO NOTHING;
    COMMIT;
    n := n + 1;
    RAISE NOTICE '030 백필 %/% dataset_id=% %', n, total, d, clock_timestamp();
  END LOOP;
END $$;
```

030 몫이 끊기면 `FROM datasets` 두 곳에 `WHERE dataset_id > '<마지막 줄의 dataset_id>'` 를 더해 이어 돌린다. 처음부터 다시 돌려도 결과는 같다.

## 되돌리기

`helm rollback` 은 차트와 이미지만 되돌리고 적용된 스키마는 그대로 둔다. nexus-server 는 기동 때 DB 의 `_sqlx_migrations` 와 이미지에 든 마이그레이션 집합을 대조해, **DB 에만 있는 마이그레이션이 있으면 기동하지 않는다**(`was previously applied but is missing in the resolved migrations`). 그래서 마이그레이션이 추가된 판에서 이전 이미지로 되돌리려면 그 마이그레이션을 손으로 걷어야 하고, 걷어도 되는지는 마이그레이션마다 다르다. 걷을 수 없으면 업그레이드 전에 떠 둔 `pg_dump` 스냅샷 복원이 유일한 수단이다. 복원은 DB 를 통째로 다시 만든다 — `pg_restore --clean --create -d postgres <덤프>`(그 DB 에 다른 접속이 없어야 하고 DB 를 지우고 만들 권한이 필요하다) 또는 `dropdb`·`createdb` 뒤 `pg_restore -d <DB>`. **`--clean` 만으로는 안 된다** — 새 마이그레이션이 만든 표는 덤프에 없어 지워지지 않고, 그 FK 때문에 그 표가 가리키는 표가 복원되지 않은 채 `_sqlx_migrations` 만 옛 상태로 돌아가 이전 이미지가 섞인 DB 위에서 오류 없이 기동한다(kind 에서 확인). 복원은 스냅샷 뒤의 모든 쓰기를 잃는다. 순서는 파드를 0 개로 내리고(아래 1) → 복원 → 이전 판 리비전으로 rollback(아래 4) → replicas 를 올리는 것이다. 새 이미지 파드가 떠 있는 채 복원하면 그 파드가 마이그레이션을 다시 적용한다.

### 038 이 적용된 DB

038(`version_jobs`·`version_job_samples`, seal·새 버전 만들기의 작업 줄)이 적용된 DB 에서 038 이전 이미지는 기동하지 않는다. 걷으면 작업 행(진행 목록·실패 사유)이 사라진다. **대기·실행 중인 작업이 있거나 `preparing`·`failed` 버전이 있으면 걷지 않는다** — 이전 이미지는 그 상태를 몰라 draft 처럼 쓰기를 받는다. 실행 중 작업은 끝나기를 기다리고, 대기 작업은 취소하고(`POST /api/v1/version-jobs/{job_id}/cancel`), `preparing`·`failed` 버전은 지운 뒤에 한다. 판정은 이 질의다(파드를 내린 뒤 참이어야 한다).

```sql
SELECT NOT EXISTS (SELECT 1 FROM version_jobs WHERE state IN ('queued', 'running'))
   AND NOT EXISTS (SELECT 1 FROM dataset_versions WHERE status IN ('preparing', 'failed'));
```

순서는 아래 035·036 절차와 같다(1 → 2 에 위 판정 → 3 → 4). 3 의 블록은 이것이다. DROP 은 외래 키가 가리키는 `datasets`·`dataset_versions`·`users` 에 AccessExclusiveLock 을 잡으므로 `lock_timeout` 을 건다.

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
DROP TABLE IF EXISTS version_job_samples;
DROP TABLE IF EXISTS version_jobs;
DELETE FROM _sqlx_migrations WHERE version = 38;
COMMIT;
```

038 과 그 앞(037·035·036)을 함께 걷을 때는 이 DROP 을 앞에 두고 `DELETE FROM _sqlx_migrations WHERE version IN (…, 38)` 로 한 트랜잭션에서 돌린다.

### 037 이 적용된 DB

037(`annotation_session_tag_baselines`, CVAT 세션의 글 칸 기준값과 `annotation_sessions` 의 가져오기 임대 칸 둘)이 적용된 DB 에서 037 이전 이미지는 기동하지 않는다. 걷으면 진행 중 세션의 글 칸 기준이 사라지므로, 태그 항목이 든 세션이 열려 있으면(`creating`·`open`) 「가져오기」하고 close 한 뒤에 한다. 순서는 아래 035·036 절차와 같다(1 → 3 → 4, 판정 2 는 없다). 3 의 블록은 이것이다.

```sql
BEGIN;
SET LOCAL lock_timeout = '3s';
DROP TABLE IF EXISTS annotation_session_tag_baselines;
ALTER TABLE annotation_sessions DROP COLUMN IF EXISTS import_lease_token, DROP COLUMN IF EXISTS import_lease_until;
DELETE FROM _sqlx_migrations WHERE version = 37;
COMMIT;
```

037 과 035·036 을 함께 걷어 035 이전 이미지로 갈 때는 아래 035·036 블록의 DROP 앞에 위 DROP·ALTER 를 넣고 `DELETE FROM _sqlx_migrations WHERE version IN (35, 36, 37)` 로 한 트랜잭션에서 돌린다(판정 2 는 그대로 한다).

### 035·036 이 적용된 DB

035(`instance_overrides`, annotation 의 그룹 단위 버전 격리 표식)·036(`dataset_group_kinds`, 그룹 종류 선언)이 적용된 DB 에서 이전 이미지는 기동하지 않는다.

**되돌려도 되는지는 이 질의 하나로 정한다.** `instance_overrides` 표가 없으면(035 가 적용되지 않은 채 끝남) 판정 없이 절차 3 으로 간다.

```sql
SELECT NOT EXISTS (SELECT 1 FROM instance_overrides);
```

- **참이 아니면 되돌리지 않는다.** 표식이 있는 샘플은 그룹 단위로 고친 샘플이고, 표식을 지우면 이전 이미지가 그 샘플을 옛 형식으로 읽어 고치지 않은 그룹이 그 버전에서 빈다. 그렇게 생긴 손상은 영구히 남는다.
- 참이면 아래 절차로 되돌릴 수 있다. 표식 없이 쓴 결과(샘플을 읽는 버전이 그 draft 하나뿐일 때 고친 것)는 이전 이미지도 바르게 읽는다.
- `dataset_group_kinds` 에 행이 있으면 그 선언은 함께 사라진다(다시 올린 뒤 다시 선언해야 한다).

**절차.** 035·036 을 적용한 이미지로 만든 CVAT 세션이 열려 있으면(`creating`·`open`) 되돌리기 전에 「가져오기」하고 close 한다 — 그 규칙으로 만든 세션을 이전 이미지가 「가져오기」했을 때의 동작은 확인하지 않았다. 판정과 DROP 사이에 새 표식이 생기지 않도록 nexus-server 파드를 먼저 내린다.

1. `kubectl -n <ns> scale deploy <fullname> --replicas=0` 으로 파드를 모두 내리고, `kubectl -n <ns> get pods -l app.kubernetes.io/instance=<릴리스>` 가 빌 때까지 기다린다. `<fullname>` 은 Deployment 이름이다 — `kubectl -n <ns> get deploy -l app.kubernetes.io/instance=<릴리스>` 로 확인한다(릴리스 이름이 `nexus-server` 를 포함하면 그 이름, 아니면 `<릴리스>-nexus-server`, `fullnameOverride` 를 주었으면 그 값).
2. 위 판정 질의가 참인지 확인한다. 참이 아니면 여기서 멈추고 `--replicas` 를 원래 값으로 되돌린다.
3. 진행 중인 seal 이 없을 때(1 을 했으면 없다) 아래를 파일로 저장해 `psql -v ON_ERROR_STOP=1 -f <파일>` 로 한 세션에서 돌린다. `ON_ERROR_STOP` 이 없으면 실패해도 psql 종료 코드가 0 이다 — 있으면 실패 때 종료 코드가 0 이 아니고, 출력 끝이 `COMMIT` 이 아니다. 실패(대개 lock timeout)하면 트랜잭션 전체가 롤백되어 두 표와 `_sqlx_migrations` 행이 그대로 남으므로 같은 명령을 다시 시도한다.

   ```sql
   BEGIN;
   SET LOCAL lock_timeout = '3s';
   DROP TABLE IF EXISTS instance_overrides;
   DROP TABLE IF EXISTS dataset_group_kinds;
   DELETE FROM _sqlx_migrations WHERE version IN (35, 36);
   COMMIT;
   ```

   `IF EXISTS` 는 035 만 적용되고 036 이 실패한 상태에서도 이 블록이 끝나게 하려는 것이다(`DELETE` 는 없는 행에도 안전하다). `lock_timeout` 을 거는 이유: DROP 은 FK 가 가리키는 `dataset_versions`·`datasets` 에 AccessExclusiveLock 을 잡는다. seal 은 도는 내내 `dataset_versions` 에 AccessShareLock 을 쥐므로, timeout 없이 기다리면 그 뒤로 그 표를 읽는 거의 모든 요청이 DROP 뒤에 줄을 선다.
4. `helm history <릴리스> -n <ns>` 에서 이전 판(차트 이전 버전, 이전 이미지)으로 배포됐던(`deployed`·`superseded`) 리비전 번호를 확인하고 `helm rollback <릴리스> <그 번호> -n <ns>` 로 띄운다. 리비전을 생략하면 바로 앞 리비전으로 가는데, 업그레이드가 한 번 거부됐다면 그것은 실패한 새 판 리비전이다. 띄운 뒤 `kubectl -n <ns> get deploy <fullname> -o jsonpath='{.spec.template.spec.containers[0].image}'` 가 이전 이미지인지 확인한다. `scale` 로 0 으로 내린 replicas 는 rollback 이 릴리스 값으로 되돌린다(kind 에서 helm 3·4 로 확인 — 그래도 0 개로 남아 있으면 `kubectl -n <ns> scale deploy <fullname> --replicas=<원래 수>`). strategy 는 helm 3 에서 RollingUpdate 로 돌아가지만 helm 4 에서는 Recreate 로 남는다(교체 때의 `kubectl patch` 가 그 필드를 소유한다). 남으면 `kubectl -n <ns> patch deploy <fullname> --type=merge -p '{"spec":{"strategy":{"type":"RollingUpdate"}}}'` 로 되돌린다(strategy 만 바뀌어 파드는 다시 뜨지 않는다). Argo CD 처럼 GitOps 로 배포하면 `helm rollback` 대신 이전 차트 버전·이미지 태그로 되돌린 매니페스트를 sync 한다(자동 sync 가 새 판으로 다시 올리지 않게 먼저 멈춘다).

이 절차를 거친 DB 에 다시 올리면 걷은 마이그레이션이 다시 적용된다.

## 스냅샷 잔여 점검(reconcile-snapshots)

`nexus-server reconcile-snapshots` 는 manifest 버킷의 `annotations/`·`manifests/` 아래 객체를 훑어, 어느 sealed 버전도 가리키지 않는 객체의 수·크기를 분류별로 보고한다. **기본은 dry-run 이라 아무것도 지우지 않고**, `--apply` 를 줄 때만 정리 대상 키를 지운다(아래 「정리」). 어느 쪽도 DB·컨테이너 파일시스템에는 쓰지 않고, 결과는 stdout 의 JSON 하나, 진행 로그는 stderr 다. HTTP 서버로 뜨지 않고 마이그레이션도 돌리지 않는다.

**분류.** 키마다 하나로 나눈다. 위에서부터 먼저 맞는 것이다.

- `recent` — 실행 시작 10 분 전 이후에 쓰인 키. 판정하지 않는다.
- `referenced` — sealed 버전의 스냅샷이 가리키는 키.
- `legacy_shard_unreferenced` — 옛 형식 샤드(`annotations/shards/{해시}.ndjson`)인데 어느 sealed 버전도 가리키지 않는 것. 정리 후보.
- `legacy_manifest_unreferenced` — 옛 형식 이름 기반 manifest 인데 어느 sealed 버전도 가리키지 않는 것. 정리 후보. 이전 서버에서 `delete_cas=false` 로 지운 sealed 버전의 manifest 도 여기 든다.
- `scoped_nonfinal` — 버전 전용 키인데 끝나지 않은 seal 의 기록만 있는 것.
- `scoped_untracked` — 버전 전용 키인데 기록이 없는 것. 지운 버전의 스냅샷이다(이전 서버는 `delete_cas=false` 로 지운 sealed 버전의 스냅샷을 남겼다 — 지금 서버는 버전 삭제가 스냅샷을 `delete_cas` 와 무관하게 지운다). 정리 후보.
- `unknown` — 위 모양 어디에도 맞지 않는 키.

분류마다 `keys`(키 수)·`key_bytes`(크기 합)·`samples`(예시 키)를 내고, 옛 형식 두 분류(`legacy_shard_unreferenced`·`legacy_manifest_unreferenced`)에는 `reclaimable_bytes_upper` 를 더 낸다(`scoped_untracked` 에는 내지 않는다). 같은 내용의 blob 을 이 버킷의 다른 분류 키가 함께 쓰면 빼고 한 번만 센 값이지만, 다른 버킷이 같은 blob 을 쓰는지는 보지 않으므로 **상한**이다. 버킷 버저닝이 켜져 있으면 삭제가 delete marker 만 남겨 이 값만큼 줄지 않는다. `referenced_missing` 은 sealed 버전이 가리키는데 버킷에 없는 키이고(스냅샷이 깨진 버전), `reference_set_complete` 가 `false` 면 옛 형식 shard manifest 를 읽지 못한 버전이 있어 `legacy_shard_unreferenced` 가 과대일 수 있다. 같은 키를 여러 sealed 버전이 가리키면 `referenced_missing` 에 버전마다 한 항목이 나온다. `other_bucket_refs` 는 옛 형식 shard manifest 가 다른 버킷을 가리킨 샤드 수(참조 집합에 넣지 않는다)이고, `caveats` 는 숫자를 읽을 때의 한계(버킷 버저닝 등)다.

**조건.**

- 이미지 교체가 끝난 뒤 돌린다. 롤링 교체 중 옛 파드가 살아 있으면 분류가 틀릴 수 있다.
- seal 이 돌지 않을 때 돌린다. 서버 컨테이너 안에서 서버와 메모리 한도를 나눠 쓴다. 실행 중 버전 삭제는 막지 않으며 그 사이의 키는 `recent`·`scoped_*` 로 빠질 뿐이다.
- 운영자에게 그 네임스페이스의 `pods/exec` 권한이 있어야 한다.

**순서.**

1. cas 정책에서 서버 키에 manifest 버킷의 `annotations/`·`manifests/` 에 대한 `ListObjects` 를 허용한다. **manifest 버킷은 values `cas.defaultBucket` 뒤에 `-manifests` 를 붙인 이름이다** — `cas.defaultBucket` 이 `data` 면 `data-manifests` 이고 `data` 자체가 아니다. 서버 키는 `GetObject` 를 이미 가진다. 권한은 shard manifest 를 읽기 전에 목록을 한 번 물어 확인한다. 권한이 없으면(cas 의 `AccessDenied`) 필요한 동작·버킷·접두사를 적고 종료 코드 1 로 끝난다. 그 밖의 403(`SignatureDoesNotMatch`·`InvalidAccessKeyId` 등 키나 시계 문제, 앞단 프록시가 낸 본문 없는 403)은 세 번 시도한 뒤 받은 응답을 그대로 적고 종료 코드 1 로 끝난다.
2. 실행한다. stdout 은 로컬 파일로, stderr 진행 로그는 터미널로 받는다. replicaCount 가 1 보다 크면 아무 파드 하나에서 한 번만 돌린다.

   ```bash
   kubectl -n <ns> exec deploy/<fullname> -- nexus-server reconcile-snapshots > reconcile-report.json
   ```

3. 1 의 허용을 회수한다. 이어서 정리(`--apply`, 아래)를 할 거면 정리를 끝낸 뒤에 회수한다 — apply 도 목록을 다시 훑는다.

옵션 — `--samples <N>`(분류마다 예시 키 수, 기본 20), `--concurrency <N>`(shard manifest 동시 읽기 수이자 `--apply` 의 동시 삭제 수, 기본 8), `--apply --confirm <n> --bucket <이름>`(아래 「정리」), `--help`(사용법과 종료 코드 표). dry-run 의 종료 코드는 정상이면 0(`reference_set_complete=false` 도 0)이고, 인자가 틀렸을 때(모르는 인자, `--concurrency 0` 등)·목록 권한이 없을 때·목록이나 shard manifest 를 세 번 시도해도 못 읽을 때·DB 오류·버전 전용 키 기록 표가 없는 DB 면 1 이며 이유는 stderr 의 마지막 줄에 있다. apply 의 2·3·4 는 아래 「정리」에 있다.

**읽는 양과 소요.** 목록은 키 1 만 개당 요청 하나, 본문은 옛 형식 sealed 버전마다 shard manifest 하나만 읽고 HEAD 는 쓰지 않는다. DB 는 읽기 전용 트랜잭션 하나로 한 번 읽는다. 합성 데이터로 잰 메모리 증가분과 소요는 아래와 같다(키 1 만 개 목록 응답을 주는 시험용 cas 스텁, Windows, 키는 버전마다 100 개). 소요는 대부분 스텁의 목록 응답이라 실제 cas 에서는 다르다.

| 키 구성 | 10 만 키 | 100 만 키 |
|---|---|---|
| 옛 형식 키 | 22 MB · 0.9 초 | 137 MB · 70 초 |
| 버전 전용 키 | 38 MB · 0.8 초 | 377 MB · 79 초 |

버전 전용 샤드는 기본 설정(`annotationShardSize` 10,000)에서 sealed 샘플 1 만 개당 하나다. 실제 cas(키 10 개)에 대고 잰 프로세스 전체 최고 메모리는 14 MB 였다.

**별도 키를 쓰려면** 그 키에 manifest 버킷 `annotations/`·`manifests/` 의 `ListObjects` 와 `annotations/` 의 `GetObject`(옛 형식 shard manifest 를 읽는다)를 허용하고, nexus Secret 에 `NEXUS_RECONCILE_CAS_KEY_ID`·`NEXUS_RECONCILE_CAS_SECRET` 로 더해 파드를 다시 띄운 뒤 2 를 한다. 둘 중 하나만 있으면 종료 코드 1 이다. 명령줄로 넘기지 않는다(셸 이력·프로세스 목록에 남는다).

**exec 를 쓸 수 없으면** 같은 이미지·같은 Secret(`envFrom` — DB 주소와 cas 키)·같은 ServiceAccount·Deployment 와 같은 cas 좌표 `env` 셋(`NEXUS__CAS__BASE_URL`·`NEXUS__CAS__REGION`·`NEXUS__CAS__DEFAULT_BUCKET` — 이미지에 설정 파일이 없어 하나라도 빠지면 설정을 읽지 못해 종료 코드 1)으로 Job 을 만들고 `args: ["reconcile-snapshots"]` 를 준다. 서버 포트·호스트와 JWT 비밀은 읽지 않는다. NetworkPolicy 가 라벨로 DB·cas 접근을 가르면 그 라벨도 맞춰야 한다 — 이 경로는 차트가 보장하지 않는다.

**정리(`--apply`).** 정리 후보 세 분류 — `scoped_untracked`, `legacy_shard_unreferenced`(`reference_set_complete` 가 `true` 일 때만), `legacy_manifest_unreferenced`(dataset 이름이 UUID 모양이면 그 이름으로 만든 옛 키가 살아 있는 버전의 manifest 일 수 있어, 키의 dataset 자리가 이 DB 의 dataset 이름과 같으면 남긴다 — 결과의 `legacy_manifest_name_like`) — 를 지운다. 결과 JSON 의 `delete_targets` 가 지울 키 수다. **전제: 그 manifest 버킷을 쓰는 nexus DB 가 하나일 때만 한다** — 다른 nexus 가 같은 버킷을 쓰면 그쪽의 살아 있는 스냅샷이 잔여로 분류되어 지워진다. 키를 지워도 같은 내용을 가리키는 다른 키는 그대로이고, 공간은 그 내용을 쓰는 키가 모두 지워질 때만 cas GC 가 돌려준다(옛 형식 두 분류는 `reclaimable_bytes_upper` 가 그 상한이다).

1. 위 「순서」의 1·2 대로 dry-run 을 돌려 `delete_targets` 와 `bucket` 을 본다(목록 허용은 아직 회수하지 않는다).
2. 실행하는 cas 키에 manifest 버킷 `annotations/`·`manifests/` 의 `DeleteObject` 가 있는지 확인한다(서버 키는 버전 삭제에 쓰므로 이미 있어야 한다. 대조용으로 받은 별도 키는 없을 수 있다).
3. 같은 방법으로 `--apply` 를 준다. 수와 버킷은 1 의 결과에서 옮긴다.

   ```bash
   kubectl -n <ns> exec deploy/<fullname> -- nexus-server reconcile-snapshots --apply --confirm <delete_targets> --bucket <bucket> > reconcile-apply.json
   ```

4. 「순서」 1 의 목록 허용(별도 키면 그 키에 준 `DeleteObject` 도)을 회수한다.

`--confirm` 이 지울 키 수와 다르면 **하나도 지우지 않고** 결과 JSON 을 낸 뒤 종료 코드 2 로 끝난다 — dry-run 과 apply 사이에 버전이 지워지거나(옛 형식 sealed 버전을 지우면 그 버전만 쓰던 공유 샤드가 참조를 잃어 대상이 된다), dry-run 때 쓴 지 10 분이 안 돼 `recent` 였던 키가 apply 때 그 컷을 넘기면 수가 달라진다. 그 경우 apply 결과의 `delete_targets` 를 보고 다시 준다. `--bucket` 이 설정의 manifest 버킷과 다르면 DB·cas 에 닿기 전에 종료 코드 1 이다. 지울 때마다 stderr 에 키·분류·결과 한 줄이 남는다(끊겨도 무엇을 지웠는지 남는다). 지우지 못한 키가 남으면 결과의 `apply.failed`(분류별 수)·`apply.failed_keys`(최대 20 개 표본 — 전체는 stderr 의 `result=failed` 줄)와 함께 종료 코드 3 이고, 다시 돌리면 남은 것만 대상이다 — dry-run 을 다시 돌려 새 `delete_targets` 를 `--confirm` 에 준다(처음 값을 그대로 주면 종료 코드 2, 종료 코드 4 뒤 권한을 열고 다시 돌릴 때도 같다). cas 가 삭제를 403(`AccessDenied`)으로 거부하면 새 삭제를 멈추고 그때까지의 결과를 낸 뒤 종료 코드 4 다 — 결과의 `apply.deleted`·`apply.failed`(분류별 수의 합)와 `forbidden_count`(거부된 키 수)·`not_started`(보내지 않은 키 수)를 더하면 `delete_targets` 다. 종료 코드가 여럿 해당하면 4 → 3 → 2 순으로 앞의 것이다.

## annotation 버전 행 정리(compact-instances)

`nexus-server compact-instances` 는 `instances` 표에 쌓인 버전별 복사본을 정리한다. HTTP 서버로 뜨지 않고 마이그레이션도 돌리지 않으며, DB(`database.url`)에만 접속한다. 먼저 옛 형식(버전 행은 있고 그룹 표식이 없는 샘플·버전)을 그룹 표식 형식으로 바꾸고, 읽기 규칙이 읽지 않는 버전 행(표식이 있는 샘플·버전에서 표식이 없는 그룹의 버전 행)을 지운다. 그 뒤 하는 일은 셋이다.

1. 공유 행과 내용이 같은 버전 행 복사본을 지운다(그룹 단위 비교).
2. 읽는 버전이 하나뿐이고 그 버전에 링크된 샘플의 버전 행을 공유 행으로 옮긴다. sealed 버전도 포함한다.
3. 그 샘플을 읽는 버전 모두가 따로 쓴 그룹의 공유 행(아무 버전도 읽지 않는 행)을 지운다.

공유 행(적재 때 쓴 annotation — 버전이 하나뿐일 때의 annotation 쓰기로 고쳐졌을 수 있다)을 지우는 것은 2 와 3 이고 대상 샘플이 갈린다. 둘은 끌 수 있다 — 끈 단계는 하지 않을 뿐이라, 나중에 기본값으로 다시 돌리면 남겨 둔 상태를 그대로 처리한다.

| 단계 | 대상 샘플 | 지우는 공유 행 | 끄는 옵션 |
|---|---|---|---|
| 2 옮기기 | 읽는 버전이 하나이고 링크된 샘플 | 그 버전이 따로 쓴 그룹의 공유 행 | `--no-move` 또는 `--keep-shared` |
| 3 읽히지 않는 공유 행 | 읽는 버전이 둘 이상이고 링크된 샘플 | 그 버전들이 모두 따로 쓴 그룹의 공유 행 | `--keep-shared` |

`--keep-shared` 로 돌리면 공유 행을 하나도 지우지 않고, 1 의 복사본과 읽기 규칙이 읽지 않는 버전 행만 지운다.

**되돌릴 수 없다.** 기본은 쓰지 않는 dry-run 이다. `--apply` 는 `--dataset <id>` 하나 또는 `--all` 과 `--undo-log <dir>` 를 함께 요구한다.

**결과.**

- 각 버전이 읽는 annotation 내용과 seal 스냅샷은 바뀌지 않는다. 다만 1 로 지운 복사본 대신 공유 행이 보이므로 `GET /instances?dataset_version_id=` 의 `instance_id` 가 바뀐다(sealed 포함). 이 경로는 `instance_id` 순 페이지 넘김이라 정리와 겹친 순회는 행을 놓치거나 두 번 받을 수 있다.
- 버전을 주지 않은 `GET /instances`(저장된 행 그대로)는 행 수와 내용이 바뀐다.
- 2 를 거친 샘플을 fork 없이 다른 버전에 링크하면 적재 때 값이 아니라 옮긴 버전의 값을 보고, 3 을 거친 샘플은 그 그룹이 비어 보인다. 2·3 이 지우는 공유 행은 undo 기록에만 남는다. 공유 행을 남겨야 하는 dataset 은 `--exclude-dataset` 으로 빼거나 `--keep-shared` 로 돌린다.
- **디스크는 줄지 않는다.** 지운 행 자리는 `VACUUM` 뒤 표 안에서 다시 쓰이는 공간이 될 뿐이고, 실행하는 동안에는 WAL·`VACUUM` 전의 지운 행·2 가 쓰는 새 행과 인덱스 항목만큼 늘어난다. 파일을 줄이려면 `pg_repack`(표 크기만큼의 여유 공간), 인덱스 단위 `REINDEX INDEX CONCURRENTLY`(인덱스 하나 크기의 여유), 또는 그 표를 쓸 수 없는 `VACUUM FULL` 이 필요하고 이 명령은 하지 않는다.

**조건.**

- 백업(`pg_dump` 또는 PITR 기준점)을 확보한 뒤, 서버를 이 이미지로 올린 뒤에, 교체·되돌리기 중이 아닐 때 실행한다. dry-run 도 DB 의 마이그레이션이 이 바이너리와 같은지 먼저 대조해, 다르면 시작하지 않는다(마이그레이션이 같은 판끼리는 이 대조가 서버의 판을 가리지 않으므로 서버를 올리는 것은 운영자가 지킨다). 이전 이미지의 fork 는 정리 대상 형식을 새로 만든다.
- DB 에 직접 접속한다. `--apply` 는 동시 실행을 세션 advisory lock 으로 막으므로 pgbouncer transaction 모드를 거치면 그 잠금이 성립하지 않는다.
- `--apply` 는 복제본이면 시작하지 않고, 비활성 복제 슬롯이 있으면 `--allow-inactive-slots` 없이는 시작하지 않는다. dry-run 은 환경 변수 `NEXUS_COMPACT_DATABASE_URL` 로 복제본을 가리킬 수 있다. 복제본에서는 `--all` 의 행 수 어림(`instance_rows_before`)을 통계 대신 `pg_class.reltuples` 로 내고, `ANALYZE` 전이면 `null` 이다.

**순서.**

1. 백업.
2. dry-run — 지울 행·옮길 행·영구히 사라지는 행 수를 센다. 출력의 `samples_scanned`·`samples_changed`·`equal_version_rows_deleted`·`invisible_version_rows_deleted`·`rows_moved_to_shared`·`shared_rows_deleted`(2 몫 `shared_rows_deleted_by_move`, 3 몫 `shared_rows_deleted_unread`)·`undo_rows_full` 에 아래 단위 비용을 곱해 소요·WAL·undo 를 어림한다. 소요 단가는 후보(버전 행이나 표식이 있는) 샘플 기준이라, 후보 없는 샘플도 세는 `samples_scanned` 를 곱하면 위쪽 어림, `samples_changed` 를 곱하면 아래쪽 어림이다. 단계를 끌 실행이면 같은 옵션으로 dry-run 한다(끈 단계는 세지 않는다).
3. 작은 dataset 하나를 primary 에서 dry-run 한 뒤 `--apply --dataset <id> --undo-log <dir>` → 결과 확인. 두 실행의 소요 비율(결과 JSON 의 시각은 초 단위라 몇 분 걸리는 dataset 을 고르거나 진행 줄 `tx_ms` 의 합으로 비교한다), 진행 줄의 WAL, undo 디렉터리 크기가 이 환경의 단가다(apply 뒤에 dry-run 하면 정리된 상태를 세어 비율이 틀린다).
4. `--apply --all --undo-log <dir>`.
5. 끝난 뒤 `ANALYZE instances`.

**옵션.** `--help` 가 사용법과 종료 코드 표를 낸다. `--resume <dataset_id>:<sample_id>`, `--batch <n>`(시작 배치, 기본 100 샘플. 배치 하나가 1 초를 넘으면 다음 배치를 절반으로 줄이고(최소 10, 시작 값이 그보다 작으면 시작 값), 꽉 찬 배치가 0.25 초 안에 끝나기를 세 번 이어 하면 두 배로 늘려 시작 값까지 돌아간다. 후보를 찾는 훑기는 배치 크기와 따로 한 번에 1,000 샘플(`--batch` 가 더 크면 그 값)이다), `--undo-timeout-ms <n>`(기본 5000 — 배치마다 undo 기록의 쓰기·fsync 를 기다리는 상한. 넘으면 그 배치를 롤백해 잠금을 놓고 `aborted.reason = undo_write_timeout` 으로 멈춘다. 느린 저장소면 올려 `--resume` 한다), `--sleep-ms <n>`(기본 0, 배치 사이 쉬는 시간 — 시간당 WAL 은 낮추지만 총량은 같다), `--verify-sealed <k>`(기본 3, 0 이면 끔 — `--apply` 에서 sealed 버전 k 개의 annotation 내용을 시작과 끝에 해시해 대조. 고른 버전을 통째로 두 번 읽어 소요가 버전 크기에 비례하므로, 큰 sealed 버전이 든 범위는 작은 dataset 에서 확인한 뒤 0 으로 돌릴 수 있다), `--allow-inactive-slots`, `--no-move`·`--keep-shared`(위 표), `--exclude-dataset <id>`(`--all` 에서 그 dataset 을 뺀다, 여러 번 줄 수 있다. 없는 id 이거나 `--resume` 의 dataset 이 들어 있거나 `--dataset` 과 함께 주면 시작하지 않는다), `--undo-segment-mb <n>`(기본 256, undo 기록 파일 하나의 크기 기준).

**출력과 종료 코드.** 결과 JSON 은 stdout, 진행 줄(배치마다 소요·WAL 바이트·undo 기록 소요 `undo_ms`·배치 크기·그 배치에서 읽은 annotation 원문 바이트 `components_bytes`·dry-run 이 그 배치를 다시 읽었는지 `retried`)은 stderr 다. 메모리 최고점은 배치 하나의 `components_bytes` 에 비례하므로, 큰 배치가 있는 dataset 은 `--batch` 를 줄여 따로 돌린다. 결과 JSON 에는 종료 코드(`exit_code`)·undo 기록 소요(`undo_write_ms_max`·`undo_write_ms_total`)·끈 단계(`steps_disabled`)·뺀 dataset(`excluded_datasets`)이 함께 실린다. 종료 코드는 0 정상, 1 시작 전 오류(인자·접속·관문, 결과 JSON 없음), 2 중단(`aborted`), 3 sealed 해시 불일치, 5 계획 자기 검증 실패(`skipped.self_check` 가 0 이 아님 — 판정 결함의 신호라 **dry-run 도 5 로 끝나며, 5 면 다음 단계로 넘어가지 않는다**), 4 신호로 중단, 130 두 번째 신호로 즉시 종료(결과 JSON 없음)다. 여럿 해당하면 2 → 3 → 5 → 4 순으로 앞의 것이다. `--verify-sealed` 가 고른 sealed 버전이 실행 중에 지워지면 그 버전은 `deleted: true` 로 싣고 불일치로 세지 않는다. 해시는 annotation 원문(소수 표기까지)을 대상으로 한다. SIGTERM 을 받으면 진행 중 배치를 마치고 멈춰 `resume_at` 을 내고, 그 값으로 `--resume` 한다. 끝낸 배치가 없이 멈추면 `resume_at` 은 이번 실행에 준 `--resume` 값(주지 않았으면 `null`)이다. `null` 이면 처음부터 다시 돌린다(`--resume` 에 그대로 넘기지 않는다). 훑은 수(`samples_scanned`)는 끝낸 배치와 후보 없이 넘긴 샘플을 센다(멈춘 배치는 세지 않고 다음 실행이 다시 훑는다). **dry-run 은 복제 충돌(SQLSTATE 40001)과 연결 끊김을 만나면 다시 접속해 같은 배치를 시도마다 절반씩 줄인 묶음(1/2·1/4·1/8)으로 나눠 세 번까지 다시 읽고**, 그래도 실패하면 `aborted.reason` 을 `replica_conflict`·`connection_lost` 로 내고 멈춘다. 후보 목록 훑기와 실행 중의 마이그레이션 대조도 같은 횟수로 다시 읽는다(묶음은 나누지 않는다). 다시 읽기 전에, 복제본이면 받은 WAL 을 모두 재생할 때까지(받은 위치와 재생 위치가 같아질 때까지) 최대 5 분 기다린다 — `max_standby_streaming_delay` 는 질의 하나의 시간이 아니라 받은 WAL 을 재생하는 데 허용하는 시간이고 복제본이 따라잡았을 때만 다시 시작되어, 밀린 채로 다시 읽으면 바로 다시 취소되기 때문이다. 5 분 안에 따라잡지 못하거나 재생 위치를 가릴 수 없으면 그대로 다시 읽는다. 쉬거나 기다리는 동안 SIGTERM 을 받으면 종료 코드 4 로 멈추고 `resume_at` 을 낸다. 다시 시도한 배치의 진행 줄 소요(`tx_ms`)는 성공한 시도의 읽기·판정만 재고(쉼·재접속·기다린 시간은 빠진다) `retried: true` 가 붙으며, 그 배치 다음은 소요와 무관하게 배치 크기가 절반으로 줄고 빠른 배치가 이어지면 다시 늘어난다. 복제본이 idle 세션을 끊은 경우는 클라이언트에 SQLSTATE 가 오지 않아 `connection_lost` 로 나온다. `--apply` 는 다시 시도하지 않는다. 교착·`lock_timeout`·`statement_timeout` 등으로 세 번 다시 시도해도 실패한 배치는 멈추지 않고 `skipped.conflict` 로 세고 넘어가므로(종료 코드는 그대로), 그 값이 0 이 아니면 그만큼 처리하지 않은 것이라 stderr 경고 줄에 남은 그 범위를 다시 돌린다. 결과 JSON 의 `server_version` 은 이 도구 바이너리의 판이다.

**undo 기록.** 영구히 사라지는 행(아무 버전도 읽지 않는 버전 행, 3 의 공유 행, 2 로 옮기기 전에 지우는 적재 원본)은 내용 전체를, 같은 내용이 DB 에 남는 행(1 의 복사본, 2 로 옮긴 행, 그룹 표식)은 키만 배치마다 커밋 전에 기록한다. 자동 되돌리기는 없고 수작업 복구·조사용이다. 실행마다 파일은 두 종류다.

- 기록 파일 `<run_id>-<세그먼트 6 자리>.ndjson.gz` — 바꾸는 배치마다 gzip 멤버 하나를 이어 쓰고, 파일이 `--undo-segment-mb`(기본 256 MiB)를 넘으면 다음 배치부터 새 파일이다. 멤버의 첫 줄(`run`·`batch`·`xid`)이 그 배치 트랜잭션의 xid 를 담는다.
- 색인 `<run_id>.index.ndjson`(압축하지 않음) — 배치마다 두 줄이다. 멤버를 디스크에 내린 뒤·DB 를 바꾸기 전에 위치 줄(`batch`·`file`·`offset`·`len`·`xid`), 커밋 뒤에 `{"batch":…,"committed":true}`.

**복구에 쓰는 기록은 색인으로 고른다.** 기록 파일에는 롤백된 시도의 멤버도 남는다(같은 배치의 재시도, 시간 초과로 늦게 끝난 기록) — `zcat <파일>` 로 전부 읽는 것은 조사용이고, 그대로 되살리면 실제로 지우지 않은 행까지 되살린다. 복구는 다음 순서다.

1. 배치마다 색인의 **마지막** 위치 줄만 쓴다(앞의 위치 줄은 롤백된 시도다).
2. 그 배치에 committed 줄이 있으면 커밋됐다. 없으면 롤백됐다고 단정하지 않는다 — 커밋 직후 죽었을 수 있다. 위치 줄의 xid 를 `SELECT pg_xact_status('<xid>'::xid8)` 로 가려 `committed` 일 때만 쓴다. 이 함수는 DB 가 트랜잭션 상태 기록을 지우기 전까지만 답하므로 **실행이 끝나거나 멈춘 직후에** 가린다.
3. 멤버는 `tail -c +$((offset+1)) <file> | head -c <len> | zcat` 으로 읽는다. 기록 도중 죽어 파일 끝이 잘려도 잘리는 것은 마지막 멤버뿐이다.

위치 줄이 없는 배치는 DB 를 바꾸지 않았다. 색인의 마지막 줄이 줄바꿈 없이 깨져 있으면(쓰는 도중 끝남) 그 줄은 무시한다 — 위치 줄이면 위치 줄이 없는 배치와 같고, committed 줄이면 2 의 xid 로 가린다. undo 볼륨 크기는 작은 dataset apply 의 실측으로 정한다.

**단위 비용**(PostgreSQL 18.6 합성 데이터, 샘플당 53.5 행).

| 항목 | 값 |
|---|---|
| apply 소요 | 후보 샘플당 3.7 ms(읽는 버전 하나) ~ 5.0 ms(둘) — 측정 데이터는 모든 샘플이 후보였다 |
| dry-run 소요 | 후보 샘플당 0.62 ms |
| WAL(정리 몫) | 대부분(행 약 400 B 에서 약 85 %, 1 KB 넘는 행에서 95 % 이상)이 지운 행이 있던 힙 페이지의 전체 페이지 기록(FPI, 페이지마다 약 8 KB 하나)이라, 바뀐 샘플 수나 지운 행 수가 아니라 **지울 행이 든 페이지 수**를 따른다(옮기기 없음). 지울 행끼리 페이지를 채웠으면 지운 행 하나에 그 행의 저장 크기(`pg_column_size(i.*)`)의 약 1.1 ~ 1.3 배(행 391 B 에서 1.2 ~ 1.3 배, 1,415 B 에서 1.08 배)이고, 지울 행과 남는 행이 한 페이지에 반씩 섞였으면 약 2.2 배다 — 한 페이지에 지울 행이 적을수록 커져 하나뿐이면 행당 약 8 KB 다. 샘플당 지운 행이 12 에서 25 로 늘면 WAL 도 두 배였고, 길게 돌려도 행당 값은 줄지 않는다. data checksums 나 `wal_log_hints` 가 켜진 DB 에서는 실행 중 체크포인트가 끼면 늘어난다 — 이미 지운 페이지를 체크포인트 뒤에 다시 읽으며 힌트 비트를 세울 때 페이지 기록(`FPI_FOR_HINT`)이 한 번 더 남기 때문이다(실행 중간에 한 번 끼었을 때 약 33 %, 둘 다 꺼진 DB 에서는 0.5 %). 옮긴 행은 하나에 약 2.6 KB 를 더한다. autovacuum 이 겹치면 서버 전체는 약 2 배. 진행 줄의 `wal_bytes` 는 서버 전체 WAL 위치의 차라 같은 시간의 다른 쓰기도 들어간다 |
| undo(gzip) | 바뀐 샘플당 약 750 B. 풀면 내용 전체 기록 행당 약 557 B |

WAL 은 `equal_version_rows_deleted`(와 그 밖에 지우는 행 수) × 지울 행의 평균 크기 × 1.1 ~ 1.3 을 하한으로 어림하고, 버전 행이 든 페이지에 다른 행이 섞여 있으면 그만큼 올린다(버전 행이 반이면 약 2 배). 평균 크기(첫 질의)와 섞인 정도(둘째 질의의 `version_share` — 버전 행이 든 페이지에서 버전 행의 비율, 1 에 가까우면 하한)는 표본으로 본다(복제본에서 돌려도 된다). 버전 행이 모두 지워지는 것은 아니므로 `version_share` 는 지울 행 비율의 상한이다. 체크포인트 몫이 붙는지는 `SHOW data_checksums`·`SHOW wal_log_hints` 로 본다.

```sql
SELECT avg(pg_column_size(i.*)) FROM instances i TABLESAMPLE SYSTEM (0.1) WHERE i.dataset_version_id IS NOT NULL;

SELECT round(avg(v::numeric / n), 2) AS version_share, sum(v) AS sampled_version_rows
  FROM (SELECT count(*) AS n, count(*) FILTER (WHERE dataset_version_id IS NOT NULL) AS v
          FROM instances TABLESAMPLE SYSTEM (0.1) GROUP BY (ctid::text::point)[0]) p
 WHERE v > 0;
```

**실행 중.** 진행 줄의 WAL 바이트·`pg_stat_replication` 의 복제 지연·남은 디스크를 보고, 크면 멈춘 뒤 `--sleep-ms` 를 올려 `--resume` 한다. `VACUUM` 은 autovacuum 에 맡기는 것이 기본이다. 손으로 돌리면 `n_dead_tup` 이 커졌을 때 한 번에 하나만, 쓰기가 적은 시간에 돌린다. 정리가 잡고 있는 샘플을 겨냥한 annotation 쓰기는 그 배치가 끝날 때까지 기다린다(배치 100 에서 p99 약 340 ms).

**Job 예시.** 파드 exec 가 아니라 Job 으로 돌린다. 같은 이미지(서버와 마이그레이션이 같은 판의 도구 이미지를 따로 지정할 수 있는지는 CHANGELOG 의 **호환성**)·같은 Secret 을 쓰고, undo 기록은 서버 데이터와 다른 PVC 에 둔다.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nexus-compact-instances
spec:
  backoffLimit: 0            # 자동 재시도는 처음부터 다시 돈다 — 실패하면 resume_at 으로 손으로 잇는다
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 120   # 배치 하나(진행 줄 tx_ms) + --sleep-ms 보다 길게
      securityContext:
        fsGroup: 10001                     # 이미지의 실행 사용자(uid 10001)가 undo 볼륨에 쓸 수 있게
        fsGroupChangePolicy: OnRootMismatch  # 다시 띄울 때마다 undo 파일 전체의 소유권을 다시 바꾸지 않게
      containers:
        - name: compact
          image: <Deployment 와 같은 이미지(digest)>
          args: ["compact-instances", "--apply", "--all", "--undo-log", "/undo"]
          env:                                 # 설정은 DB 주소(Secret)만 읽는다
            - name: NO_COLOR               # 진행 줄에 색 제어 문자를 섞지 않는다(로그 grep 용)
              value: "1"
          envFrom:
            - secretRef:
                name: <nexus-server Secret>   # NEXUS__DATABASE__URL 을 담은 Secret
          volumeMounts:
            - name: undo
              mountPath: /undo
      volumes:
        - name: undo
          persistentVolumeClaim:
            claimName: <undo 기록용 PVC>
```

**설정은 DB 주소(`NEXUS__DATABASE__URL`, Secret)만 읽는다** — 서버 포트·cas 좌표 같은 다른 설정이 없어도 시작한다. dry-run 은 `args: ["compact-instances"]` 이고 undo 볼륨이 필요 없다(`NEXUS_COMPACT_DATABASE_URL` 로 복제본을 가리킬 수 있다). fsGroup 을 지원하지 않는 볼륨(NFS 등)이면 디렉터리 소유자를 10001 로 맞춰 둔다 — 쓸 수 없으면 시작할 때 종료 코드 1 로 아무것도 쓰지 않고 멈춘다.

**멈추기와 이어 돌리기.** 멈출 때는 `kubectl -n <ns> exec <pod> -- sh -c 'kill -TERM 1'` 로 신호를 보낸다(이미지에 `kill` 실행 파일이 없어 셸의 내장 명령을 쓴다) — pod 가 남아 `kubectl logs` 로 결과 JSON 의 `resume_at` 을 읽을 수 있다. Job 이나 pod 를 지우면 로그도 함께 사라진다(로그 수집기가 없을 때). 신호는 배치 사이(와 dry-run 재시도의 쉼·대기 중)에서만 보므로 `--sleep-ms` 휴식 중이면 휴식이 끝난 뒤, 시작 때 sealed 해시를 계산하는 중이면 그 계산이 끝난 뒤 멈춘다. 유예가 끝나 강제 종료돼 결과 JSON 이 없으면 마지막 `정리 진행` 줄의 `dataset_id` 와 `last_sample` 로 `--resume <dataset_id>:<last_sample>` 을 만든다. 작은 dataset 으로 먼저 확인할 때는 sealed 버전이 있는 것을 고른다 — 없으면 `verify_sealed.versions` 가 비고 대조가 일어나지 않는다. 배포 도구가 자동 sync 로 Job 을 다시 만들지 않게 하고, 로그(stdout 결과 JSON·stderr 진행 줄)를 Job 이 끝난 뒤에도 남게 한다. NetworkPolicy 가 라벨로 DB 접근을 가르면 그 라벨도 맞춘다.

## 샘플 삭제 확인 인덱스(deleted-sample-index)

`nexus-server deleted-sample-index` 는 포함 인덱스 `idx_samples_id_deleted ON samples (sample_id) INCLUDE (is_deleted)` 를 점검하고 만든다. 개수·목록 경로(facet 개수, explorer 개수와 일괄 쓰기의 `confirm` 비교, subset 해소, 버전 샘플 수, seal 의 샘플 수 기록, dataset·버전 통계)는 샘플마다 지워졌는지(`is_deleted`)를 보려고 `samples` 힙을 읽는데, 이 인덱스가 있으면 플래너가 인덱스만 읽어 판정한다. **서버의 문장은 바뀌지 않는다** — 인덱스가 생기면 그때부터 쓰이고 파드를 다시 띄울 필요가 없으며, 인덱스가 없어도 결과는 같다(느릴 뿐이다). HTTP 서버로 뜨지 않고 마이그레이션도 돌리지 않으며 DB(`database.url`)에만 접속한다. 서버는 기동 때 `삭제 확인 인덱스 상태 state="absent" index="idx_samples_id_deleted"` 모양의 한 줄을 남긴다(`state` 는 `absent`·`invalid`·`valid`·`building`·`mismatched`, 값에 따옴표가 붙는다).

**효과는 `samples` 의 all-visible 비율에 따라 달라진다.** visibility map 비트가 꺼진 페이지(적재 뒤 아직 vacuum 되지 않은 페이지, `meta`·`tags`·삭제 UPDATE 를 받은 페이지)는 인덱스만 읽는 스캔도 힙을 다시 읽는다. 점검 출력의 `table.relallvisible / table.relpages` 가 그 비율의 어림이다. 큰 표는 기본 autovacuum 문턱이 높아 비율이 낮게 머물 수 있으므로 `samples` 에 표 단위 문턱(`autovacuum_vacuum_insert_scale_factor`·`autovacuum_vacuum_scale_factor`·`autovacuum_analyze_scale_factor`)을 낮춰 두는 것을 함께 검토한다.

**만들기의 비용.** 표 전체를 두 번 읽는다(`CREATE INDEX CONCURRENTLY`). 그동안 적재·조회는 막히지 않는다. 인덱스 크기는 행 수에 비례한다(샘플 200 만 행에 약 80 MB). 적재 한 행마다 인덱스 삽입이 하나 늘고, `is_deleted` 가 인덱스 열이 되므로 샘플 삭제 UPDATE 는 HOT 이 될 수 없다(삭제 한 건마다 모든 인덱스에 항목이 들어간다).

**조건.**

- **만드는 동안 그 DB 전체에서 vacuum 이 dead tuple 을 치우지 못한다** — 만들기가 스냅샷을 쥐어 xmin 지평선을 묶는다. `compact-instances --apply` 와 겹쳐 돌리지 않는다(그쪽이 지운 행이 그동안 남는다).
- 앞선 트랜잭션이 끝나기를 기다리는 단계가 있다 — 주 서버의 긴 문장·REPEATABLE READ 트랜잭션(`pg_dump` 등)이 있으면 그 단계에서 선다. 복제본의 질의와 `hot_standby_feedback` 은 기다리게 하지 않는다. 점검 출력의 `oldest_xmin` 을 보고 시작한다.
- `--apply` 는 복제본이면 시작하지 않는다. 동시 실행을 세션 advisory lock 으로 막으므로 pgbouncer transaction 모드를 거치면 그 잠금이 성립하지 않는다. `samples` 에 vacuum·ANALYZE 같은 표 잠금(`ShareUpdateExclusiveLock`)을 쥔 다른 세션이 있으면 시작하지 않는다 — anti-wraparound vacuum 은 기다리는 쪽이 있어도 물러나지 않아 만들기가 그 뒤에 몇 시간 설 수 있다. 이 판정은 권한에 따라 가려지는 진행 뷰가 아니라 잠금으로 한다.
- 여러 nexus 가 함께 쓰는 DB 에는 `--apply` 하지 않는다(그 DB 를 쓰는 다른 서버의 계획도 바뀐다).

**순서.**

1. 점검(`args: ["deleted-sample-index"]`) — 상태·`relallvisible / relpages`·진행 중 vacuum·`oldest_xmin`.
2. 쓰기가 적은 시간, vacuum 직후에(체크섬이나 `wal_log_hints` 가 켜져 있으면 두 번 읽으며 hint bit 를 세운 페이지가 WAL 을 늘린다) `--apply`.
3. 기동 로그의 상태 줄 또는 다시 점검해 `valid` 를 확인한다.

**옵션과 종료 코드.** 인자는 `--apply` 하나이고 `--help` 가 사용법·운영 안내·종료 코드 표를 낸다. 결과 JSON(`state_before`·`state_after`·`reason`·`index_bytes`·`table`·`leftover_invalid`·`vacuum`·`oldest_xmin`·`indcheckxmin`·`elapsed_ms`)은 stdout, 진행 줄(5 초마다 `phase`·블록 진행)은 stderr 다. 종료 코드는 0 정상(점검을 마침·만듦·이미 유효함), 1 결과 JSON 없이 끝남(인자·접속·복제본 거부 또는 도중 DB 오류), 2 아무것도 하지 않았거나 만들지 못함, 4 신호로 만들기를 취소함이다. 2 의 사유(`reason`)는 다음과 같다.

| `reason` | 뜻 | 할 일 |
|---|---|---|
| `lock_held` | 다른 실행이 진행 중 | 그 실행이 끝난 뒤 점검 |
| `mismatched` | 같은 이름의 다른 정의(다른 표·열·정렬 방향·opclass 등) | 손대지 않는다 — 그 인덱스를 확인해 지운 뒤 다시 |
| `building` | INVALID 인덱스가 있고 다른 세션이 `samples` 에 표 잠금을 쥠(누가 만드는 중이거나 vacuum·ANALYZE 중) | 끝난 뒤 다시 |
| `vacuum_in_progress` | 다른 세션이 `samples` 에 표 잠금을 쥠(vacuum·ANALYZE 등) | 끝난 뒤 다시 |
| `table_lock_busy` | 실패해 남은 INVALID 인덱스를 3 초 안에 지우지 못함 — `samples` 를 쓰는 3 초 넘는 문장·트랜잭션이 있다 | 한가한 때 다시(인덱스는 INVALID 그대로 남아 다시 해도 안전하다) |
| `create_failed` | 만들기 실패 | stderr 의 오류를 보고 다시 — 남은 INVALID 는 다음 `--apply` 가 정리 |
| `not_valid_after_create` | 만든 뒤에도 유효하지 않음 | 점검 출력 확인 |

SIGTERM 을 받으면 진행 중인 만들기를 취소하고 4 로 끝난다. 남은 INVALID 인덱스는 다음 `--apply` 가 정리한다. 실패해 남은 INVALID 인덱스도 쓰기 비용은 들므로 오래 두지 않는다. 비동시 `DROP INDEX` 로 손으로 지우지 않는다(`samples` 에 AccessExclusiveLock) — 지워야 하면 `DROP INDEX CONCURRENTLY idx_samples_id_deleted`.

**Job 예시.** 설정은 DB 주소(`NEXUS__DATABASE__URL`, Secret)만 읽는다. 볼륨은 필요 없다.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nexus-deleted-sample-index
spec:
  backoffLimit: 0            # 실패하면 사유(reason)를 보고 손으로 다시 돌린다
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 60   # 신호를 받으면 만들기를 취소하고 끝낸다
      containers:
        - name: index
          image: <Deployment 와 같은 이미지(digest)>
          args: ["deleted-sample-index", "--apply"]
          env:
            - name: NO_COLOR
              value: "1"
          envFrom:
            - secretRef:
                name: <nexus-server Secret>   # NEXUS__DATABASE__URL 을 담은 Secret
```

만들기는 표 크기에 따라 몇 시간 걸릴 수 있다. Job 에 `activeDeadlineSeconds` 를 걸면 그 시간에 신호를 받아 취소된다. 로그(stdout 결과 JSON·stderr 진행 줄)를 Job 이 끝난 뒤에도 남게 한다.

## 버전 작업 줄(seal·새 버전 만들기)

seal(`POST /datasets/{id}/versions/{v}/seal`)과 `fork_from` 이 있는 새 버전 만들기(`POST /datasets/{id}/versions`, 저장된 필터의 `POST /subsets/{id}/version` 포함)는 DB 에 하나인 작업 줄(`version_jobs`)을 지난다. 빈 버전 만들기와 clone job 은 줄 밖이다.

- **응답.** 줄이 비었고 그 파드에 자리(`seal.maxConcurrent`)가 있으면 끝까지 돌고 seal 은 `200` + sealed 버전, 새 버전 만들기는 `201` + draft 버전이다. 아니면 **`202`** + `{"job": {...}, "version": {...}}` + `Location: /api/v1/version-jobs/{job_id}` 이다(`job.queue_position` 은 1 부터). 같은 버전에 대기·실행 중인 작업이 있으면 그 작업을 `202` 로 돌려준다. 이미 sealed 인 버전의 seal 은 `409` `already_sealed`.
- **돌리는 쪽.** 각 파드가 자리가 날 때와 5 초마다 줄 맨 앞(요청 순서)을 집는다. 도는 작업은 120 초 임대를 30 초마다 늘리고, 파드가 죽어 임대가 끝나면 다른 파드가 처음부터 다시 돌린다 — 시작이 `seal.maxAttempts`(기본 3)에 이른 뒤 또 끊기면 다시 돌지 않고 `failed` 다(`job.error` 에 시작 횟수와 상한). 같은 버전의 앞선 실행이 잠금을 쥐고 있어 시작하지 못한 작업은 시도로 세지 않고 줄로 돌리고 그 파드가 15 초 건너뛴다(그동안은 줄이 비지 않아 새 요청이 자리가 있어도 `202`). 종료 신호를 받은 파드는 더 집지 않고, 신호를 받은 즉시와 요청을 다 비운 뒤 돌리던 작업을 시도로 세지 않고 줄로 돌린다. 작업 행은 파드 이름(`HOSTNAME`)으로 주인을 가린다.
- **버전 상태.** 새 버전 만들기가 대기·실행 중인 버전은 `preparing`, 실패·취소된 버전은 `failed` 다. 둘 다 목록에 보이고 적재·링크·링크 해제·annotation·meta·에셋 붙이기·seal·fork 원본·clone job 원본·CVAT 세션·샘플 가져오기 대상과 원본이 `409`(`code: version_preparing`)다. 실패 사유는 버전 응답의 `job.error` 이고 응답 본문과 같은 문구다(DB·내부 오류는 `database error`·`internal error`, 원문은 서버 로그에만. CAS 오류는 응답 본문과 달리 `cas error` 만 적는다). `failed` 는 지울 수 있고, 대기·실행 중인 작업이 있는 `preparing` 버전(과 그것이 든 dataset)은 작업을 취소한 뒤 지운다. 대기 중인 seal 의 대상은 draft 그대로라 그 사이의 적재·수정도 seal 에 들어간다.
- **진행 목록.** `GET /api/v1/version-jobs`(`state`·`since`(끝난 작업에만, 기본 24 시간 전)·`cursor`·`limit`(1~1000, 기본 100), 최근 요청 먼저)와 `GET /api/v1/version-jobs/{job_id}` 이고 viewer 도 본다. 항목은 데이터셋·버전 이름과 id, 종류(`seal`·`fork`), 상태(`queued`·`running`·`done`·`failed`·`cancelled`), 대기 순번, 요청한 사람의 이메일(요청한 본인과 관리자에게만), 요청·시작·끝 시각, 파드, 단계·`progress_done`/`progress_total`, 오류, 취소 요청 여부다. 끝난 작업은 7 일 뒤 지워진다. 버전 응답에도 그 버전의 작업 요약 `job`(`job_id`·`kind`·`state`·`queue_position`·`requested_at`·`error`)이 붙는다(draft·`preparing` 은 대기·실행 중일 때만, `failed` 는 마지막 작업). `job.requested_at` 은 진행 목록의 같은 필드와 같은 값이다. draft 버전의 `seal_in_progress`·`seal_started_at` 은 실행 중인 seal 작업에서 온다 — seal 을 돌리던 파드가 죽으면 임대가 끝날 때까지(최대 약 2 분) 진행 중으로 보인다.
- **단계.** 같은 단계 안의 진행은 2 초 간격으로 묶어 기록한다(단계가 바뀌면 바로). 로그 `버전 작업 진행` 줄에도 같은 값이 남는다.

  | 종류 | 단계(순서대로) | `progress_done` / `progress_total` |
  |---|---|---|
  | seal | `shards` | 올린 샤드 수 / 시작 때 센 버전 샘플 수 ÷ 샤드 크기 올림(도중 적재로 늘 수 있다) |
  | seal | `shard_manifest` | 앞 단계 값을 이어받는다 |
  | seal | `main_manifest` | 메인 manifest 에 쓴 샘플 수 / 버전 샘플 수 × 2 — 같은 스냅샷을 두 번 읽으므로(해시를 정하는 1 차, cas 로 보내는 2 차) 1 차가 끝나면 절반이다. 같은 버전 재시도에서 이미 올라간 내용이면 2 차 없이 끝까지 찬다 |
  | seal | `finalize` | 앞 단계 값을 이어받는다 |
  | fork | `link` | 없음 |
  | fork | `copy` → `finalize` | annotation 을 복제한 샘플 수 / 복제할 샘플 수(원본 버전에 버전 전용 annotation 이 있는 샘플 — `sample_ids` 를 주면 그중 고른 샘플). `finalize` 는 이어받아 두 값이 같다 |

- **취소.** `POST /api/v1/version-jobs/{job_id}/cancel`(`editor` 이상, 로봇은 `403`). 대기 작업은 요청한 사람 또는 관리자(설정 superuser·`role=admin`)가 취소하고 그 자리에서 `cancelled` 다(새 버전 만들기면 버전이 `failed`). 실행 중 작업은 관리자만 취소하고, 같은 파드면 곧바로, 다른 파드면 30 초 안에 멈춘다 — 다만 그때 DB 문장 하나를 실행 중이면 그 문장이 끝난 뒤에 멈춘다(서버가 기다리기를 그만둬도 PostgreSQL 은 받은 문장을 끝까지 돌린다). 새 버전 만들기의 `link` 단계는 원본의 링크 전체를 문장 하나로 옮기므로 큰 버전이면 그 시간만큼 늦다. 멈춘 seal 은 버전이 draft 로 남고 이미 올린 스냅샷 객체를 지운다. 멈추기 직전에 끝났으면 작업은 `done` 이다. 응답은 `202` + 작업이고, 끝난 작업은 `409`(`code: job_not_cancellable`)다. 바로 돌던 작업이 취소되면 그 요청은 `409`(`code: job_cancelled`, `작업이 취소되었습니다`)로 끝난다.
- **SDK.** `202` 를 기다리는 SDK 를 함께 쓴다 — 기다리지 않는 SDK 는 `202` 본문을 끝난 결과로 받는다(변경 이력의 해당 판 **운영 조치**).

## seal 의 DB·cas 조건

seal 은 메인 manifest(샘플마다 에셋 참조를 적은 객체)를 `REPEATABLE READ READ ONLY` 트랜잭션 하나의 서버측 커서로 1,000 행씩 두 번 읽는다 — 1 차는 해시만 계산해 객체 키를 정하고, 2 차는 같은 스냅샷을 되감아 cas 로 흘려 올린다. 샤드는 샘플 1,000 개씩 읽는다. 그래서 메모리가 버전의 샘플 수와 무관하고, 대신 아래 조건이 붙는다.

- **메인 manifest 는 `Content-Length` 없는 chunked PUT 이다**(cas `0.1.4`·`0.1.8`·`0.1.12`·`0.1.15`·`0.1.16`·`0.1.35` 가 바이트 그대로 받는 것을 확인했다). nexus 와 cas 사이에 프록시가 있으면 chunked 요청 본문을 받아야 하고, 요청 본문을 모아 두었다 보내는 프록시면 응답을 기다리는 시간이 그만큼 길어진다(서버는 본문을 다 보낸 뒤 `300 초 + 1 초/MiB` 까지 기다린다).
- **DB 역할의 `idle_in_transaction_session_timeout` 은 5 분 이상이거나 `0` 이어야 한다.** 스냅샷 커넥션은 `FETCH` 사이·기록·cas 확인 동안 `idle in transaction` 이고, 끊기면 그 seal 이 실패한다(잠금 커넥션은 끊겨도 seal 이 끝까지 가는 것과 다르다). 스냅샷 트랜잭션의 문장(`DECLARE`·`FETCH`·`MOVE`)에는 서버가 `statement_timeout` 300 초를 건다 — 첫 `FETCH` 가 버전 전체를 정렬하므로 큰 버전에서 수 초~수십 초 걸린다.
- **스냅샷이 열린 동안** `samples`·`dataset_version_samples`·`sample_assets` 에 AccessShareLock 을 쥐고 DB 전체의 vacuum 지평선을 붙든다. 그 시간은 두 패스 + cas 로 보내는 시간이다(로컬 측정 150 만 샘플 12.8 초, cas 가 느리면 그만큼 길다). 그동안 `deleted-sample-index --apply`(`CREATE INDEX CONCURRENTLY`)는 기다리고, 그 표를 바꾸는 마이그레이션이 든 판으로 올리면 기동이 seal 이 끝날 때까지 늦는다.
- **seal 도중의 쓰기는 한 샤드 안에서 섞일 수 있다.** 샤드 하나의 샘플·annotation 을 묶음마다 다른 문장으로 읽기 때문이다. seal 하는 버전에 쓰지 않는 것이 전제다(서버가 막지는 않는다).
- **커넥션.** 메인 manifest 단계의 seal 은 잠금·스냅샷 둘을 쥔 채 객체 기록용 셋째를 꺼낸다. `seal.maxConcurrent` 가 2 이상이고 `database.maxConnections` 가 그 3 배보다 작으면 seal 들이 셋째를 서로 기다리다 기록 시한(약 30 초) 뒤 실패할 수 있어 기동 로그에 경고가 남는다.

**메모리.** 한도를 정하는 것은 seal 이 한 번에 읽는 **샘플 1,000 개 묶음**의 annotation·meta 크기(B)다. values 의 `resources` 주석의 식 `limits.memory ≥ (64 MiB + 80 × B) × seal.maxConcurrent + 512 MiB` 를 쓴다. 샤드 객체 크기로 잡으면 샘플이 1 만 개보다 적은 버전에서 모자란다(샤드가 작아도 1,000 개 묶음을 여러 번 디코드한 몫이 남는다). B 는 아래 질의로 어림한다(측정 데이터에서 무거운 annotation 은 실제의 1.0~1.2 배, 샘플당 box 하나는 0.4 배 — 그 몫은 고정 몫 안이다). sealed 여부와 무관하게 쓴다.

```sql
-- :vid = 버전 id. sample_id 순으로 연속한 샘플 1,000 개 묶음 중 가장 큰 것의 meta + annotation 구성요소 텍스트(MiB).
WITH s AS (
  SELECT dvs.sample_id, (row_number() OVER (ORDER BY dvs.sample_id) - 1) / 1000 AS batch
  FROM dataset_version_samples dvs JOIN samples x ON x.sample_id = dvs.sample_id
  WHERE dvs.dataset_version_id = :'vid' AND NOT x.is_deleted)
SELECT batch,
       round((sum(coalesce(octet_length(x.meta::text), 0)) + sum(coalesce(i.bytes, 0))) / 1048576.0, 1) AS approx_mib
FROM s JOIN samples x ON x.sample_id = s.sample_id
LEFT JOIN LATERAL (SELECT sum(octet_length(components::text)) AS bytes FROM instances i
                   WHERE i.sample_id = s.sample_id
                     AND (i.dataset_version_id IS NULL OR i.dataset_version_id = :'vid')) i ON true
GROUP BY batch ORDER BY approx_mib DESC LIMIT 1;
```

## 헬스 체크와 지표

프로브는 셋으로 갈린다. `GET /_internal/live`(의존성을 조회하지 않는 프로세스 응답성 확인)를 startup·liveness에, `GET /_internal/health`(DB ping)를 readiness에 쓴다. liveness를 `/_internal/health`로 두면 DB failover(보통 30~120초) 중에 파드가 kill되는데, 재시작으로는 외부 의존성이 복구되지 않아 중단이 원래 장애보다 길어진다.

```bash
kubectl port-forward svc/nexus-server 8090:80 -n <namespace>
curl localhost:8090/_internal/health      # {"status":"ok","db":true}
```

**readiness는 워크로드와 커넥션 풀을 나눠 쓴다.** `/_internal/health`는 크기 1의 전용 풀로 ping하므로 적재가 워크로드 풀을 전부 써도 200이다. 그래서 **readiness 실패는 「DB에 못 닿는다」만 뜻하고**, 「앱이 바쁘다」로는 파드가 서비스에서 빠지지 않는다. 앱이 커넥션을 못 받고 있는지는 아래 `nexus_db_pool_acquire_timeouts_total`로 본다.

`live`와 `health` 두 경로는 프로브가 자격증명 없이 호출해야 하므로 인증이 면제된다. 그 밖의 면제 경로는 `POST /api/v1/auth/register`·`POST /api/v1/auth/login`, 재설정 링크의 `POST /api/v1/auth/password-reset/inspect`·`/complete`(링크 토큰이 자격증명), API 문서 경로(`/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/`)뿐이며, 문서 경로는 `auth.docsEnabled: false`로 끄면 404가 된다. **데이터 API는 조회를 포함해 전부 토큰이 필요하다.**

### 지표

`GET /_internal/metrics`는 Prometheus 텍스트를 낸다. **인증이 면제되지 않는다** — 시크릿의 `NEXUS__METRICS__TOKEN`을 bearer로 받고, 비어 있으면 경로 자체가 404다. 스크레이퍼는 로그인할 수 없고 JWT를 쓰게 하면 모니터링 스택이 카탈로그 전체를 읽는 계정을 들고 있어야 해서 토큰을 따로 뒀다. 스크레이프마다 DB 집계 한 왕복이 워크로드 풀에서 나가므로 15초보다 촘촘한 주기는 권하지 않는다. 설정 여부는 [`config-effective`](#적용된-설정-확인)의 `metrics.token_set`으로 확인한다.

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" localhost:8090/_internal/metrics
```

| 묶음 | 지표 | 쓰는 법 |
|---|---|---|
| DB 풀 | `nexus_db_pool_connections` · `_idle_connections` · `_acquire_timeouts_total` | **`_acquire_timeouts_total`이 오르기 시작하는 순간이 풀 포화의 시작점이다** — readiness는 전용 커넥션을 쓰므로 그 상황에서도 계속 200이고, 이 카운터가 유일한 신호다 |
| 적재 유입 제어 | `nexus_ingest_permits_total` · `_available` · `nexus_ingest_rejected_total` | |
| 로봇 토큰 | `nexus_robot_tokens_active` · `_expiring_soon` · `nexus_robot_token_min_expires_in_seconds` · `nexus_robot_accounts_without_active_token` | 이 넷과 `nexus_version_jobs_queued` 만 DB를 조회한다(각각 한 왕복, 250ms 제한 — 줄 길이는 `nexus_metrics_db_stats_ok` 에 들지 않는다). 조회가 실패하거나 제한을 넘겨도 **사라지지 않고 직전 값으로 남으므로**(기동 후 한 번도 못 읽었으면 처음부터 없다), 알림에는 `and nexus_metrics_db_stats_ok == 1`을 함께 건다. `min_expires_in_seconds`는 활성 토큰이 없을 때 `+Inf`라 `< 임계값` 경보가 저절로 풀린다 |
| seal·버전 작업 자리 | `nexus_seal_permits_total` · `_available` | 파드당 동시 버전 작업(seal·새 버전 만들기) 자리와 빈 자리. **total − available 이 그 파드에서 지금 도는 작업 수다** — 요청과 떨어져 도는 작업은 `axum_http_requests_pending` 에 잡히지 않으므로 이 둘로만 보인다 |
| 버전 작업 줄 | `nexus_version_jobs_queued` · `nexus_version_jobs_total`(라벨 `kind` = `seal`·`fork`, `result` = `done`·`failed`·`cancelled`) · `nexus_version_job_wait_seconds`(히스토그램, `kind`) · `nexus_version_job_duration_seconds`(히스토그램, `kind`·`result`) | 줄에 선 작업 수(DB 전체 값이라 파드마다 같고, 조회가 실패하면 직전 값이 남는다)·끝난 작업 수(여섯 다 `0` 부터)·요청부터 시작까지·시작부터 끝까지. 히스토그램 구간은 seal 소요와 같고 첫 작업이 끝나야 나온다. 대기 중에 취소된 작업은 수만 센다 |
| 도는 버전 작업 | `nexus_version_job_stage`(라벨 `kind`·`dataset_version_id`·`stage`, 값 `1`) · `nexus_version_job_progress_ratio`(라벨 `kind`·`dataset_version_id`) | 그 파드에서 지금 도는 작업마다 지금 단계와 끝낸 비율(위 「단계」 표의 `progress_done ÷ progress_total`, 0~1 — 전체 수가 없거나 0 이면 비율 시리즈가 없다). 이름은 진행 목록에서 버전 id 로 찾는다. **끝난 작업과 지난 단계의 시리즈는 다음 스크레이프에 나오지 않는다**(스크레이프마다 도는 작업에서 읽어 쓴다). 시리즈 수는 파드마다 대략 `seal.maxConcurrent` × 2 이고(seal 은 자리를 놓은 뒤 잔여 정리를 마칠 때까지 시리즈가 남아, 그동안 다음 작업이 돌면 잠깐 하나 더 나온다), 도는 작업이 없으면 둘 다 없다 |
| 삭제 정리 | `nexus_cas_delete_failures_total`(라벨 `kind` = `asset`·`thumbnail`·`snapshot`) | 삭제와 seal 잔여 정리에서 지우지 못하고 남긴 객체 누적. 셋 다 `0` 부터 나온다. **`asset`·`thumbnail` 은 다시 정리되지 않는다.** 버전 삭제에서 오른 `snapshot` 은 [스냅샷 잔여 점검](#스냅샷-잔여-점검reconcile-snapshots)의 `--apply` 로 지우고, seal 잔여 정리에서 오른 `snapshot` 은 그 버전을 지울 때 다시 지운다 — bucket·key 는 대개 같은 시각의 로그 `CAS object 삭제 실패`·`CAS 썸네일 삭제 실패`·`스냅샷 객체 CAS 삭제 실패` 줄에 있다(버전 삭제 뒤 정리 판정 자체가 DB 오류로 실패한 경우는 `삭제 뒤 CAS 정리 판정 실패` 줄에 dataset_id·version 만 남는다) |
| seal 결과 | `nexus_seal_total`(라벨 `result` = `completed`·`failed`) · `nexus_seal_duration_seconds`(히스토그램, 같은 라벨) | 끝난 seal 의 수와 소요. 요청이 끊긴 seal·대기했다 일꾼이 돌린 seal 도 끝날 때 기록하므로 앞단 프록시의 읽기 타임아웃을 소요 분포에 맞춰 정한다. `already_sealed` 거절과 잠금을 못 잡아 줄로 돌린 작업은 세지 않는다. 히스토그램은 첫 seal 이 끝나야 나온다 |
| 끊긴 요청 | `nexus_http_requests_cancelled_total`(라벨 `method`·`endpoint`) | 응답 전에 클라이언트나 프록시가 연결을 끊은 요청 누적. `endpoint` 는 아래 HTTP 요청 지표와 같은 규칙이다. 첫 끊김이 생겨야 나온다 |
| annotation 쓰기 | `nexus_annotation_instance_writes_total`(라벨 `mode` = `direct`·`group`·`legacy_converted`·`unchanged`) | 그룹을 보낸 annotation 쓰기(PUT·PATCH·CVAT 가져오기)를 커밋 뒤 샘플마다 한 번 센다. 넷 다 `0` 부터 나온다. `direct` 는 샘플을 읽는 버전이 그 draft 하나라 공유 행을 고친 쓰기, `group` 은 바뀐 그룹만 버전 전용으로 쓴 쓰기, `legacy_converted` 는 옛 형식 샘플을 첫 쓰기에서 그룹 단위로 바꾼 쓰기, `unchanged` 는 바뀐 그룹이 없어 인스턴스를 쓰지 않은 것이다 |
| 할당자 | `nexus_jemalloc_allocated_bytes` · `_resident_bytes` | `resident − allocated` 가 대략 할당자가 붙든 몫이라, 메모리가 오를 때 할당자가 쥔 것인지 애플리케이션이 쥔 것인지를 가른다 |
| 집계 성공 | `nexus_metrics_db_stats_ok` | 이번 스크레이프에서 위 넷을 실제로 읽었으면 `1`, 못 읽었으면 `0` |
| HTTP 요청 | `axum_http_requests_total`(라벨 `method`·`status`·`endpoint`) · `axum_http_requests_duration_seconds`(히스토그램, 같은 라벨) · `axum_http_requests_pending`(`method`·`endpoint`) | 이름·라벨 키·지연 구간이 cas-server와 같다 |

**HTTP 요청 지표의 `endpoint`는 요청 경로가 아니라 라우트 템플릿이다**(`/datasets/{dataset_id}`) — dataset id마다 시리즈가 생기지 않는다. 어느 라우트에도 매칭되지 않은 요청은 `unmatched` 하나로 모이고(cas-server는 이 경우 요청 경로를 적는다), 프로브·스크레이프 경로도 함께 세어진다. 응답 전에 끊긴 요청은 요청 수·지연에 잡히지 않는다(위 `nexus_http_requests_cancelled_total` 과 로그의 `요청이 취소됐다` 줄로 본다. seal·새 버전 만들기는 끊겨도 계속 돌며, 위 seal·버전 작업 지표로 본다). 엔드포인트 하나만 5xx인 결함은 이렇게 본다.

```promql
sum by (endpoint) (rate(axum_http_requests_total{status=~"5.."}[5m]))
```

### 적용된 설정 확인

`GET /api/v1/admin/config-effective`(관리자 전용)는 지금 그 프로세스가 **읽은 값**을 돌려준다 — 차트 렌더 결과가 아니므로 `extraEnv` 오버라이드도 드러난다.

```python
requests.get(f"{base}/api/v1/admin/config-effective", headers=h).json()
# {"server": {...},
#  "database": {"url": "postgres://nexus:<redacted>@db-host:5432/nexus", "max_connections": 16},
#  "jwt": {"secret": "<set>", "ttl_hours": 24},
#  "auth": {"superuser_email": "<set>", "approval_required": false,
#           "revocation_cache_ttl_secs": 5, ...},
#  "cvat": null,
#  "seal": {"max_concurrent": 1}, ...}
```

**이것이 필요한 이유는 오타가 조용히 삼켜지기 때문이다.** 서버는 모르는 설정 키를 오류로 만들지 않는다 — `NEXUS__JWT__TTLHOURS`처럼 한 글자 틀린 env는 무시되고 기본값으로 기동한다. 경고도 없고 기동도 정상이라, 의도한 값이 실제로 걸렸는지 확인할 방법이 이 응답뿐이다.

비밀값은 값이 아니라 `<set>`/`<unset>`으로만 나오고 `database.url`은 비밀번호만 가려진다(호스트·DB명은 남는다). **`superuser_email`도 주소가 아니라 `<set>`/`<unset>`이다** — 이 서버는 이메일이 곧 권한이라 주소를 아는 것이 표적을 아는 것과 같다. 그 값이 필요하면 기동 로그를 본다.

## `server.port`를 바꿀 때

`server.port` **하나만** 바꾸면 된다.

```bash
helm upgrade ... --set server.port=9000
```

컨테이너 포트, 앱이 듣는 포트(`NEXUS__SERVER__PORT`), Service의 `targetPort`, 세 프로브(startup·liveness·readiness)가 모두 이 값을 따라간다. 뒤의 넷은 숫자가 아니라 **컨테이너 포트 이름 `http` 를** 가리키기 때문이다.

`values-xxx.yaml`에서 프로브나 `service.targetPort`를 직접 override할 때 숫자를 박지 말 것 — `server.port`와 어긋나면 앱은 새 포트에서 도는데 kubelet은 옛 포트를 찔러 **Pod가 영영 Ready가 되지 않는다.** 컨테이너 로그에는 아무 이상이 없어 원인을 찾기 어렵다.

## 삭제

```bash
helm uninstall nexus-server -n <namespace>
kubectl delete -f sealed-nexus-server.yaml -n <namespace>   # 시크릿은 별도 정리
```
