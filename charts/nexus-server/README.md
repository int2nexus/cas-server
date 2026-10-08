# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 **Sample → Dataset → DatasetVersion** 단위로 묶어 버전을 관리한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/docs/architecture.md)
  — 도메인 모델, Version 생명주기, Annotation CoW, 스냅샷·Manifest 구조
- [사용법](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/docs/usage.md)
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
  전체 목록은 [`examples/secret.example.yaml`](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/examples/secret.example.yaml).
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

평문 예시: [`examples/secret.example.yaml`](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/examples/secret.example.yaml).
Secret 이름은 `secret.existingSecret`(비우면 릴리즈 fullname, 기본 `nexus-server`)과 일치해야 한다.

- `NEXUS__JWT__SECRET`은 직접 생성하는 임의의 비밀 키(로그인 JWT HS256 서명용)  
예: `openssl rand -hex 32`. 값을 바꾸면 기존 발급 토큰이 모두 무효가 된다(재로그인 필요).
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
| `seal.maxConcurrent` | `""` | 이 파드에서 동시에 도는 seal 의 상한(비우면 이미지 기본 `1`). 넘친 seal 은 시작하지 않고 **`429`**(`code: seal_busy`, `Retry-After: 10`). `0` 이면 기동이 실패한다. 메모리 지침(`resources`)은 seal 하나 기준이라 올리면 `limits.memory` 도 그 배수만큼 올린다. seal 하나는 풀에서 최대 둘을 예약 4(고정)에서 쓰므로 2 면 적재 포화 때 조회·관리 몫이 0 이 될 수 있다 — `database.maxConnections` 를 올려도 예약은 늘지 않는다 |
| `ingest.admissionWaitMs` | `""` | 적재가 자리를 기다리는 상한(ms). 넘기면 대기가 아니라 **`429` + `Retry-After: 1`**. 비우면 서버 기본 3000. `0`이면 기다리지 않는다(자리가 비어 있으면 통과, 없으면 그 자리에서 `429`) |
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

**superuser 계정을 대상으로 삼는 관리 조작 셋은 누가 부르든 403이다** — 역할 변경(`users/role`)·정지(`users/active`)·비밀번호 재설정(`users/password-reset`). 유일한 부트스트랩 수단이 스스로 잠기는 것을 막기 위해서다.

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
- **계정 정지는 삭제가 아니다.** 이메일을 계속 점유하므로 그 주소로 재가입할 수 없고, `active: true`로 해제하면 그대로 돌아온다. 정지하면 로그인이 `403 forbidden`이 되고, **이미 발급된 토큰도 캐시 수명(`auth.revocationCacheTtlSecs`, 기본 5초) 안에 막힌다.**
- **담당자 이전은 인가를 옮기지 않는다.** 이전 담당자도 계속 쓰고 지울 수 있다 — 역할이 `editor`이기 때문이다. 옮겨가는 것은 「다시 넘길 자격」 하나다. 담당자가 없는 dataset(`GET /datasets?unowned=true`)은 위험한 상태가 아니라 **인수 대기**이고, `editor` 이상이면 그대로 쓰고 지울 수 있다. 담당자가 있는 dataset을 넘기는 것은 담당자 본인이 한다([사용법 8.2](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/docs/usage.md#82-담당자-이전)).

**로그인·가입·갱신·OIDC 교환의 `200` 응답은 모두 `{ token, user_id, email }`이다** — 로그인 화면이 실어 쓰는 토큰 필드는 `token`이다. 가입이 승인 대기(`auth.approvalRequired`)면 `202`이고 타입이 다르다.

### 로봇 계정 발급

사람이 없는 워크로드(적재 잡·스케줄러·CI)용 계정이다. 쓰는 쪽은 [사용법 2.3](https://github.com/int2nexus/cas-server/blob/nexus-server-0.3.18/charts/nexus-server/docs/usage.md#23-로봇-토큰으로-연결)의 `nx.connect(robot_token=...)`로 붙는다.

계정 생성(`POST /api/v1/admin/robots`, body `{"name": "...", "role": "editor", "display_name": "..."}`, `display_name`만 선택)의 이름은 소문자·숫자·하이픈 1~48자이고 하이픈으로 시작하거나 끝날 수 없다(`400`). **이름 검사가 `role` 검사보다 먼저 돈다** — 이름이 틀린 동안에는 `role` 오류를 볼 수 없다. 로봇의 `role`은 `editor`·`viewer`뿐이고 `admin`은 `400`이다 — `admin` 로봇의 장수명 토큰은 그대로 관리 평면 전권이 되기 때문이다. 경로의 `user_id`는 정수다(UUID를 넣으면 본문 검사 전에 `400`).

토큰 발급은 `POST /api/v1/admin/robots/{user_id}/tokens`로 한다. body는 `{"label": "...", "expires_in_days": 1~365}`이고 **둘 다 필수다** — `label`을 빠뜨리면 `422`이고, 계정 생성은 이미 끝났으므로 **토큰 없는 계정이 남는다**. **평문은 발급 응답에만 한 번 실린다.** 계정 하나에 토큰을 여럿 둘 수 있어, 새 토큰을 배포하고 `last_used_at`으로 확인한 뒤 옛 토큰을 폐기하면 중단 없이 회전한다.

**만료는 앞당길 수만 있다.** `PATCH /api/v1/admin/robots/{user_id}/tokens/{token_id}` body `{"expires_at": "<RFC 3339>"}` — 현재 만료보다 빠르고 지금보다 뒤여야 하며, 연장·같은 값·과거 시각은 `400`이다.

### 인증 설정

| values 키 | 기본값 | 설명 |
|---|---|---|
| `jwt.ttlHours` | 빈 값 (서버 기본 **24**) | 발급 토큰의 수명(시간). 허용 범위 **1~8760**. 토큰 자체는 무효화할 수 없으므로 이 값이 곧 탈취·비밀번호 변경 이후에도 토큰이 살아있는 최대 시간이다(계정 삭제·정지·역할 회수는 `auth.revocationCacheTtlSecs` 안에 반영된다). **범위를 벗어난 값(`0` 포함)을 주면 서버가 기동에 실패한다**(DB 연결보다 먼저 검사). 줄이면 노출 시간은 줄지만 `POST /api/v1/auth/refresh` 호출이 그만큼 잦아진다. |
| `auth.registrationEnabled` | `true` | `false`로 하면 `POST /api/v1/auth/register`만 403이 되고, 로그인·토큰 갱신·기존 계정은 영향을 받지 않는다. 가입을 닫은 뒤에도 관리자는 사람 계정(`POST /api/v1/admin/users`)과 로봇 계정(`POST /api/v1/admin/robots`)을 만들 수 있다 — 둘 다 이 값을 보지 않는다. |
| `auth.docsEnabled` | `true` | `false`로 하면 `/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/` 세 경로가 **404**가 된다(라우트 자체가 등록되지 않는다 — 403이 아니다). 스펙은 이미 전 경로가 인증 뒤에 있으므로, 이걸로 감추는 것은 API 경로 목록뿐이다. |
| `auth.approvalRequired` | `false` | `true`로 하면 가입은 열어 둔 채 **승인 전까지 아무것도 할 수 없다.** 가입 요청은 계정을 만들되 **토큰을 주지 않고** `202`와 `{"status": "pending"}`을 반환하며, 승인 전에는 로그인·토큰 갱신이 `403`이다(본문 `pending_approval`). 승인은 `POST /api/v1/admin/users/approve`(본문에 `email`·`role` 필수), 대기 목록은 `GET /api/v1/admin/users/pending`. **켜기 전에 가입 화면이 `202`를 처리해야 하고**, 승인 엔드포인트가 관리자 전용이라 관리자(superuser 또는 `admin` 계정)가 있어야 한다. 켜기 전에 가입한 계정은 영향받지 않는다. |
| `auth.oidc.issuers` | `[]` (기능 꺼짐) | 외부 IdP가 발급한 토큰을 인증 자격증명으로 받을 발급자 목록. 항목마다 `issuer`(필수, `https://`, 토큰의 `iss`와 같아야 한다) · `audience`(필수, 토큰 `aud` **안에 있으면** 통과하는 포함 검사) · `exchange`(기본 `false`, `POST /api/v1/auth/oidc/exchange`를 이 발급자에게 여는 스위치 — 자동 회전하는 토큰에는 켜지 말 것) · `jwksUri`(선택, 발급자와 JWKS 호스트가 다를 때) · `jwksAuth`(선택, `serviceaccount` 하나만 — 파드 자신의 SA 토큰을 실어 JWKS를 읽는다. `serviceAccount.automountToken: true`가 필요하다). **`audience`가 비었거나, `issuer`가 비-https·중복이거나, `jwksUri`가 비-https이거나, `jwksAuth`가 `serviceaccount`가 아니면 기동에 실패한다.** 목록이 비면 기능이 꺼질 뿐 기동은 정상이다. **발급자만 설정하면 아무도 인증되지 않는다** — 신원 `(issuer, subject)` → 계정 매핑을 `POST /api/v1/admin/oidc-identities`로 관리자가 등록해야 하고 자동 생성은 없다. superuser와 `role = admin` 계정에는 신원을 붙일 수 없다. 이 갈래로 온 요청은 `POST /api/v1/auth/refresh`가 `403`이다. |
| `auth.revocationCacheTtlSecs` | 빈 값 (서버 기본 **5**초) | 인증이 사용자 행(역할·승인·활성 상태)을 읽고 캐시하는 시간. **이 값이 곧 권한 회수·계정 정지·계정 삭제가 듣기까지의 상한이다.** `0`이면 매 요청 조회가 되어 즉시 반영되지만 적재 처리량이 20~33% 떨어진다(측정치). 조회 자체를 끄는 옵션은 없다. |

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소> \
  --set jwt.ttlHours=8 \
  --set auth.registrationEnabled=false \
  --set auth.docsEnabled=false
```

## CVAT 연동

annotation을 CVAT에서 편집하려는 경우에만 설정한다. **설정하지 않아도 nexus는 정상 동작한다** — 세션 **생성**과 **결과 회수(import)**만 503을 반환하고, 카탈로그·업로드·seal·조회는 영향을 받지 않는다.

### CVAT 쪽 준비

nexus가 통제하지 않는 부분이라 CVAT 관리자와 함께 준비해야 한다.

| 항목 | 내용 |
|---|---|
| 서비스 계정 | nexus가 사용할 CVAT 계정 1개. `docker exec -it cvat_server python manage.py createsuperuser` 로 생성한다. 모든 CVAT project를 이 계정이 소유하므로 일반 작업자 계정과 분리한다 |
| 네트워크 도달 | **CVAT 워커 컨테이너**에서 CAS 주소로 HTTP 요청이 가능해야 한다. 이미지는 nexus를 거치지 않고 CVAT이 CAS에서 직접 받는다 |
| smokescreen 허용 | CVAT은 원격 URL 다운로드에 SSRF 가드(smokescreen)를 거친다. CAS가 사설 IP면 기본 설정에서 차단되므로 허용 대역을 지정해야 한다 |

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
| `cvat.segmentSize` | `""` | job 분할 크기. 비우면 CVAT 기본 동작 |
| `cvat.maxSessionSamples` | `""` | 세션당 샘플 상한(서버 기본 2000) |
| `cvat.staleCreatingSecs` | `""` | 준비 작업의 진행 기록(60 초마다)이 이 시간(초)보다 오래 멈춘 `creating` 세션을 `failed` 로 정리한다(서버 기본 1800). 각 파드가 5 분마다(기동 직후 포함) 검사하고, 다른 파드가 준비 중인 살아 있는 세션은 건드리지 않는다. 180 미만이면 180 으로 올려 쓰고 기동 로그에 경고를 남긴다(`config-effective` 에는 올린 값이 보인다). 이미지 `0.1.21`~ |

### 연결 확인

기동 로그에 다음 중 하나가 남는다.

```
INFO  CVAT 연동 활성화 base_url=http://cvat.example.com:8080
WARN  [cvat] 설정이 불완전해 CVAT 연동을 켜지 않는다 ... missing=user, password
INFO  [cvat] 설정 없음 — annotation session 엔드포인트는 503을 반환한다
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

| CVAT 상태 | 서버 기동 | 카탈로그 API | 세션 생성·회수 | 세션 목록·조회·close·delete |
|---|---|---|---|---|
| 설정 없음 | 정상 | 정상 | 503 | 정상 |
| 설정 불완전 | 정상(경고 로그) | 정상 | 503 | 정상 |
| 설정됨, CVAT 다운 | 정상 | 정상 | 세션이 `failed`가 된다 | 정상 |
| 정상 연결 | 정상 | 정상 | 정상 | 정상 |

**목록·조회·`close`·`delete`는 CVAT 없이도 동작한다.** CVAT을 호출하지 않거나(목록), 호출에 실패해도 진행하기 때문이다(조회·`close`는 미반영 편집 여부를 「모름」으로 두고, `delete`는 CVAT project 삭제를 건너뛰고 세션 행만 지운다). 이미 만들어진 세션을 CVAT이 죽은 뒤에도 정리할 수 있어야 하기 때문이다 — 그러지 않으면 샘플이 영구히 잠긴다.

nexus는 기동 시점에 CVAT을 호출하지 않는다. 따라서 운영 중 CVAT이 내려가도 영향은 세션 생성·회수에만 국한된다.

## 헬스 체크와 지표

프로브는 셋으로 갈린다. `GET /_internal/live`(의존성을 조회하지 않는 프로세스 응답성 확인)를 startup·liveness에, `GET /_internal/health`(DB ping)를 readiness에 쓴다. liveness를 `/_internal/health`로 두면 DB failover(보통 30~120초) 중에 파드가 kill되는데, 재시작으로는 외부 의존성이 복구되지 않아 중단이 원래 장애보다 길어진다.

```bash
kubectl port-forward svc/nexus-server 8090:80 -n <namespace>
curl localhost:8090/_internal/health      # {"status":"ok","db":true}
```

**readiness는 워크로드와 커넥션 풀을 나눠 쓴다.** `/_internal/health`는 크기 1의 전용 풀로 ping하므로 적재가 워크로드 풀을 전부 써도 200이다. 그래서 **readiness 실패는 「DB에 못 닿는다」만 뜻하고**, 「앱이 바쁘다」로는 파드가 서비스에서 빠지지 않는다. 앱이 커넥션을 못 받고 있는지는 아래 `nexus_db_pool_acquire_timeouts_total`로 본다.

`live`와 `health` 두 경로는 프로브가 자격증명 없이 호출해야 하므로 인증이 면제된다. 그 밖의 면제 경로는 `POST /api/v1/auth/register`·`POST /api/v1/auth/login`과 API 문서 경로(`/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/`)뿐이며, 문서 경로는 `auth.docsEnabled: false`로 끄면 404가 된다. **데이터 API는 조회를 포함해 전부 토큰이 필요하다.**

### 지표

`GET /_internal/metrics`는 Prometheus 텍스트를 낸다. **인증이 면제되지 않는다** — 시크릿의 `NEXUS__METRICS__TOKEN`을 bearer로 받고, 비어 있으면 경로 자체가 404다. 스크레이퍼는 로그인할 수 없고 JWT를 쓰게 하면 모니터링 스택이 카탈로그 전체를 읽는 계정을 들고 있어야 해서 토큰을 따로 뒀다. 스크레이프마다 DB 집계 한 왕복이 워크로드 풀에서 나가므로 15초보다 촘촘한 주기는 권하지 않는다. 설정 여부는 [`config-effective`](#적용된-설정-확인)의 `metrics.token_set`으로 확인한다.

```bash
curl -H "Authorization: Bearer $METRICS_TOKEN" localhost:8090/_internal/metrics
```

| 묶음 | 지표 | 쓰는 법 |
|---|---|---|
| DB 풀 | `nexus_db_pool_connections` · `_idle_connections` · `_acquire_timeouts_total` | **`_acquire_timeouts_total`이 오르기 시작하는 순간이 풀 포화의 시작점이다** — readiness는 전용 커넥션을 쓰므로 그 상황에서도 계속 200이고, 이 카운터가 유일한 신호다 |
| 적재 유입 제어 | `nexus_ingest_permits_total` · `_available` · `nexus_ingest_rejected_total` | |
| 로봇 토큰 | `nexus_robot_tokens_active` · `_expiring_soon` · `nexus_robot_token_min_expires_in_seconds` · `nexus_robot_accounts_without_active_token` | 이 넷만 DB를 조회한다(250ms 제한). 조회가 실패하거나 제한을 넘겨도 **사라지지 않고 직전 값으로 남으므로**(기동 후 한 번도 못 읽었으면 처음부터 없다), 알림에는 `and nexus_metrics_db_stats_ok == 1`을 함께 건다. `min_expires_in_seconds`는 활성 토큰이 없을 때 `+Inf`라 `< 임계값` 경보가 저절로 풀린다 |
| seal | `nexus_seal_permits_total` · `_available` | 파드당 동시 seal 자리와 빈 자리. **total − available 이 지금 도는 seal 수다** — 연결이 끊긴 seal 은 `axum_http_requests_pending` 에 잡히지 않으므로 진행 중인 seal 은 이 둘로만 보인다 |
| 삭제 정리 | `nexus_cas_delete_failures_total`(라벨 `kind` = `asset`·`thumbnail`·`snapshot`) | 삭제의 CAS 정리에서 지우지 못하고 남긴 객체 누적. 셋 다 `0` 부터 나온다. **오르면 그 객체는 다시 정리되지 않는다** — bucket·key 는 같은 시각의 로그 `CAS object 삭제 실패`·`CAS 썸네일 삭제 실패`·`sealed manifest CAS 삭제 실패` 줄에 있다 |
| 할당자 | `nexus_jemalloc_allocated_bytes` · `_resident_bytes` | `resident − allocated` 가 대략 할당자가 붙든 몫이라, 메모리가 오를 때 할당자가 쥔 것인지 애플리케이션이 쥔 것인지를 가른다 |
| 집계 성공 | `nexus_metrics_db_stats_ok` | 이번 스크레이프에서 위 넷을 실제로 읽었으면 `1`, 못 읽었으면 `0` |
| HTTP 요청 | `axum_http_requests_total`(라벨 `method`·`status`·`endpoint`) · `axum_http_requests_duration_seconds`(히스토그램, 같은 라벨) · `axum_http_requests_pending`(`method`·`endpoint`) | 이름·라벨 키·지연 구간이 cas-server와 같다 |

**HTTP 요청 지표의 `endpoint`는 요청 경로가 아니라 라우트 템플릿이다**(`/datasets/{dataset_id}`) — dataset id마다 시리즈가 생기지 않는다. 어느 라우트에도 매칭되지 않은 요청은 `unmatched` 하나로 모이고(cas-server는 이 경우 요청 경로를 적는다), 프로브·스크레이프 경로도 함께 세어진다. 응답 전에 끊긴 요청은 요청 수·지연에 잡히지 않는다(로그의 `요청이 취소됐다` 줄로 본다. seal 은 끊겨도 계속 돌며, 위 seal 지표로 본다). 엔드포인트 하나만 5xx인 결함은 이렇게 본다.

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

컨테이너 포트, 앱이 듣는 포트(`NEXUS__SERVER__PORT`), Service의 `targetPort`, 세 프로브(startup·liveness·readiness)가 모두 이 값을 따라간다. 뒤의 넷은 숫자가 아니라 **컨테이너 포트 이름 `http`**를 가리키기 때문이다.

`values-xxx.yaml`에서 프로브나 `service.targetPort`를 직접 override할 때 숫자를 박지 말 것 — `server.port`와 어긋나면 앱은 새 포트에서 도는데 kubelet은 옛 포트를 찔러 **Pod가 영영 Ready가 되지 않는다.** 컨테이너 로그에는 아무 이상이 없어 원인을 찾기 어렵다.

## 삭제

```bash
helm uninstall nexus-server -n <namespace>
kubectl delete -f sealed-nexus-server.yaml -n <namespace>   # 시크릿은 별도 정리
```
