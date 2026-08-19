# Nexus User Guide
## 1. 소개
### 1.1 Nexus

Nexus는 ML 학습 데이터를 Sample, Dataset, DatasetVersion 단위로 관리하는 ML Dataset Catalog이다.  
원본 파일(이미지 등)은 콘텐츠 주소 기반 저장소인 **cas-server(CAS)**에 보관되며, Nexus에는 해당 파일에 대한 참조 정보와 Annotation, 메타데이터, Dataset 구조 및 버전 정보가 저장된다.  
이와 같은 구조를 통해 대용량 학습 데이터를 중복 없이 관리하면서, 데이터셋 버전별 재현성과 협업을 지원한다.

### 1.2 주요 특징
Nexus는 다음과 같은 특징을 가진다.
- 원본 파일은 CAS에서 관리된다.  
원본 파일은 CAS 엔드포인트를 통한 직접 업로드 또는 SDK 메서드를 이용한 업로드 방식으로 CAS에 저장되며, Nexus에는 CAS 객체를 참조하는 정보와 메타데이터만 저장된다.
- DatasetVersion 간 Sample을 공유한다.  
새로운 DatasetVersion은 기존 버전을 Fork하여 생성할 수 있으며, 변경되지 않은 Sample은 기존 버전과 공유된다. 따라서 데이터셋 전체를 복사하지 않고도 새로운 버전을 효율적으로 관리할 수 있다.
- Annotation은 DatasetVersion 단위로 관리된다.  
동일한 Sample이라도 DatasetVersion마다 서로 다른 Annotation을 가질 수 있으며, 한 버전에서의 수정은 다른 버전에 영향을 주지 않는다.
- Seal을 통해 Immutable 버전을 생성한다.  
DatasetVersion은 Seal하여 변경이 불가능한 스냅샷으로 고정할 수 있다. Seal된 버전은 학습 및 평가에 사용되는 기준 데이터셋으로 활용되며, 동일한 데이터를 언제든지 재현할 수 있다.
- Annotation은 CVAT에서 편집할 수 있다.  
Draft 버전의 Sample을 CVAT으로 내보내 사람이 편집하고, 그 결과를 다시 Draft로 반영할 수 있다. 이미지는 Nexus를 거치지 않고 CVAT이 CAS에서 직접 받는다. 서버에 CVAT 연동이 구성된 경우에만 사용할 수 있다.

### 1.3 전체 워크플로우
![기본적인 데이터 흐름](workflow.png)

---

## 2. 설치
### 2.1 Nexus 서버 준비 (Helm)
#### 전제
- cas-server가 떠 있고, 그 접속 주소를 안다 (예: `http://cas-server:80`, 또는 외부 `https://cas.example.com`).
- 외부 PostgreSQL 접속 정보(DSN). nexus는 DB를 직접 띄우지 않는다. DB 마이그레이션은 nexus 기동 시 자동 적용된다.
- CAS 자격증명(SigV4 `key_id`/`secret`)과 JWT 시크릿.
- nexus-server는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

#### Helm repo 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```
nexus-server는 cas-server와 동일한 Helm repo를 사용한다.

#### 시크릿 주입 (sealed-secret)

차트는 Secret을 만들지 않고 외부 Secret을 envFrom으로 참조한다. 아래 4개의 키를 가진 Secret을 먼저 클러스터에 주입한다(kubeseal로 봉인). CVAT 연동을 쓰면 `NEXUS__CVAT__PASSWORD`가 5번째 키로 추가된다 — [2.2](#22-cvat-연동-선택-차트-020) 참조:

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='<CAS key id>' \
  --from-literal=NEXUS__CAS__SECRET='<CAS secret>' \
  --from-literal=NEXUS__JWT__SECRET='<JWT 시크릿>' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

- `NEXUS__JWT__SECRET`은 직접 생성하는 임의의 비밀 키(로그인 JWT HS256 서명용)  
예: `openssl rand -hex 32`. 값을 바꾸면 기존 발급 토큰이 모두 무효가 된다(재로그인 필요).
- `NEXUS__CAS__KEY_ID`/`NEXUS__CAS__SECRET`은 CAS가 인정하는(write 권한 있는) 자격증명
- `NEXUS__DATABASE__URL`은 외부 Postgres DSN.

#### 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소>      # http://cas-server:80 

# 업데이트
helm repo update
helm upgrade nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소>      # http://cas-server:80 
```

#### Python SDK 설치

```bash
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk

# 업데이트
pip install --upgrade --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk
#버전 확인
python -c "import importlib.metadata as m; print(m.version('int2nexus-sdk'))" 
```

#### 연결 설정

`nx.connect`는 로그인 후 JWT를 받아 클라이언트를 초기화한다. 계정이 없으면 등록을 먼저 실행
```python
# (최초 1회) 테스트 계정 등록 - 이미 있으면 409, 그대로 진행
import requests

NEXUS_URL = "http://<HOST>:8090"
resp = requests.post(f"{NEXUS_URL}/api/v1/auth/register", json={
"email": "<EMAIL>", "password": "<PASSWORD>", "display_name": "<NAME>",
})
print(resp.status_code, "(409 = 이미 존재, 무시 가능)")
```

설정 값의 우선순위는 **인자 > 환경변수 > 설정 파일**이다. 코드에 명시한 값이 항상 이기고, CI는 환경변수로 로컬 설정 파일을 덮을 수 있다.

**(1) 설정 파일 — 권장** (SDK 0.1.1+)

`~/.int2nexus/settings.json`파일로 저장. `nx.connect()` 로 바로 연결. 스크립트에 자격증명이 남지 않는다.

```json
{
  "nexus_url": "http://<host>:8090",
  "email": "...",
  "password": "...",
  "cas_url": "http://<host>:8080",
  "cas_key_id": "...",
  "cas_secret": "...",
  "verify": true
}
```

```python
import nexus as nx

nx.connect()
```

**(2) 인자로 직접 넘기기**

```python
import nexus as nx

nx.connect(
    nexus_url="http://<host>:8090",
    email="...", password="...",
    cas_url="http://<host>:8080",
    cas_key_id="...", cas_secret="...",
)
```

**(3) 환경변수**

환경변수가 모두 있으면 `nx.connect()`만 호출하거나 첫 API 호출 시 자동 연결된다.

```python
import os

os.environ["NEXUS_URL"] = "http://<host>:8090" # nexus-server 주소
os.environ["NEXUS_EMAIL"] = "..."              # 로그인 자격 증명
os.environ["NEXUS_PASSWORD"] = "..."           
os.environ["CAS_URL"] = "http://<host>:8080"   # cas-server 주소 
os.environ["CAS_KEY_ID"] = "..."               # CAS SigV4 서비스 계정 자격증명
os.environ["CAS_SECRET"] = "..."  

nx.connect()
```

`cas_key_id`/`cas_secret`(또는 `CAS_KEY_ID`/`CAS_SECRET`)는 CAS 업로드 서명용 키. CAS가 인정하는(해당 버킷에 write 권한 있는) 키면 동작하며, nexus 서비스 키를 공유하거나 내부 정책에 따라 개인별로 발급받은 키 사용.

#### 사내 프록시로 SSL 인증서 에러가 날 때 (SDK 0.1.1+)

사내 보안 장비가 TLS를 검사하면 `nx.connect()`가 인증서 에러로 죽는다. 아래 중 하나를 사용한다.

```bash
export REQUESTS_CA_BUNDLE=/path/to/사내-루트-CA.pem
```

```python
nx.connect(verify="/path/to/사내-루트-CA.pem")   # 검증을 유지한 채 해결 (권장)
nx.connect(verify=False)                          # 최후의 수단
```

- 설정 파일의 `"verify"` 키에 적어두면 매번 넘기지 않아도 된다. 값은 `true`/`false` 또는 **CA 번들 경로**.
- `verify=False`는 그 연결의 **중간자 공격 탐지를 포기**하는 것이다. 접속 시 한 번 경고가 뜬다.

#### 계정 관리 (SDK 0.1.2+)

`nx.connect()`가 돌려주는 클라이언트로 본인 계정을 관리한다. 되돌릴 수 없는 작업이라 `nx.` 최상위 함수로는 노출하지 않는다.

```python
client = nx.connect()
client.change_password("현재비번", "새비번123")      # 현재 비밀번호를 재확인한다
result = client.delete_account("새비번123")          # 완전 삭제 — 되돌릴 수 없다
```

- **비밀번호 변경은 새 로그인부터 적용된다.** 이미 발급된 토큰은 만료까지(기본 24시간, 배포마다 `jwt.ttlHours`로 다를 수 있다 — 아래 참조) 그대로 유효하다. 이 클라이언트 인스턴스는 계속 써도 된다.
- 설정 파일(`~/.int2nexus/settings.json`)에 비밀번호를 적어두었다면 **그 파일도 함께 고쳐야 한다** — 안 그러면 다음 `nx.connect()`가 실패한다.
- **`delete_account`는 비활성화가 아니라 삭제다.** 이메일이 풀려 같은 주소로 다시 가입할 수 있다.
- 삭제 응답의 **`released_datasets`가 0이 아니면**, 그 dataset들은 주인이 없어져 **인증된 누구나 수정·삭제할 수 있게 된다.** 팀이 쓰던 데이터라면 삭제 전에 소유자를 옮기는 편이 낫다 — 차트 0.3.0부터 superuser가 `PUT /api/v1/admin/datasets/{dataset_id}/owner`로 지정할 수 있다(아래 참조).
- 비밀번호를 잊어 로그인할 수 없는 계정은 본인이 처리할 수 없다 — 차트 0.3.0부터 superuser가 `POST /api/v1/admin/users/password-reset`으로 임시 비밀번호를 발급한다(아래 참조). superuser를 설정하지 않은 배포에서는 여전히 운영자가 DB에서 처리해야 한다.

#### superuser (차트 0.3.0+, 선택)

운영자가 `auth.superuserEmail`과 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`로 지정한 **단일 관리 계정**이다. 설정하지 않은 배포에서는 `/api/v1/admin/*`가 누구에게나 403이다. 능력은 둘뿐이고, 사용자 목록·계정 비활성화·감사 로그는 없다.

```python
import requests
h = {"Authorization": f"Bearer {su_token}"}   # superuser 계정으로 로그인한 토큰

# 1) 비밀번호를 잊은 계정 풀어주기 — 임시 비밀번호가 응답에 한 번만 실려 온다
r = requests.post(f"{base}/api/v1/admin/users/password-reset",
                  json={"email": "잠긴사람@int2.us"}, headers=h)
print(r.json()["password"])   # 어디에도 저장되지 않는다. 지금 전달할 것

# 2) dataset 소유자 지정 — 양도와 인수(주인 없는 dataset)가 같은 연산이다
requests.put(f"{base}/api/v1/admin/datasets/{dataset_id}/owner",
             json={"email": "새주인@int2.us"}, headers=h)
```

- **임시 비밀번호는 응답에 한 번만 실려 온다.** 서버 어디에도 저장되지 않으니 그 자리에서 전달하고, 받은 사람은 곧바로 `client.change_password(...)`로 바꾼다.
- **재설정해도 그 사람의 기존 토큰은 만료까지(기본 24시간, 배포마다 `jwt.ttlHours`로 다를 수 있다 — 아래 참조) 유효하다.** "잊어버림"을 푸는 도구지 "탈취 즉시 차단"이 아니다.
- **소유권 이전은 즉시 적용된다.** 소유자 검사는 요청마다 DB를 보므로 이전 소유자는 그 다음 요청부터 403이다.
- 주인 없는 dataset은 `GET /datasets`의 `owner_user_id`가 null인 것들이다. 방치해도 잠기지는 않지만 **인증된 누구나 쓸 수 있는** 상태로 남는다.
- **superuser 비밀번호를 바꾼 뒤에도 시크릿을 갱신할 필요가 없다.** `NEXUS__AUTH__SUPERUSER_PASSWORD`는 **그 계정이 없을 때 새로 만드는 용도로만** 읽힌다 — 계정이 이미 있으면 기동 시 값을 읽지도, 비교하지도 않는다. 그래서 시크릿의 값과 실제 로그인 비밀번호가 달라도 파드는 정상 기동하고, 반대로 시크릿을 바꿔 재배포해도 비밀번호는 바뀌지 않는다. 이 값을 "현재 비밀번호"가 아니라 **"계정 생성용 씨앗"**으로 보시는 편이 정확하다. 실제로 다시 쓰이는 경우는 하나뿐이다 — `auth.superuserEmail`을 **아직 가입되지 않은** 주소로 바꿔 재배포하면, 그때 이 값으로 새 계정이 만들어진다(이미 누가 쓰는 주소를 넣으면 그 계정을 채택하므로 그 사람이 superuser가 된다).
- **다만 시크릿 값을 비우지는 마십시오.** 이메일만 있고 비밀번호가 없으면(공백만 있는 경우 포함) **서버가 기동에 실패한다.** 쓰이지 않는 값이라도 8자 이상으로 남겨 두어야 하며, 기능을 끄실 때는 `auth.superuserEmail`과 이 시크릿 키를 **함께** 비우십시오.

#### 인증 관련 설정 (차트 0.3.0+)

superuser 외에도 차트 0.3.0부터 인증 관련 설정 세 가지를 helm 값으로 조정할 수 있다.

| values 키 | 기본값 | 설명 |
|---|---|---|
| `jwt.ttlHours` | 빈 값 (서버 기본 **24**) | 발급 토큰의 수명(시간). 허용 범위 **1~8760**. 이 서버는 토큰을 무효화할 수 없으므로(위 계정 관리·superuser 항목 참조) 이 값이 곧 탈취·비밀번호변경·계정삭제 이후에도 토큰이 살아있는 최대 시간이다. **범위를 벗어난 값(`0` 포함)을 주면 서버가 기동에 실패한다** — DB 연결보다 먼저 검사하므로 "0을 줬는데 조용히 24시간으로 되돌아갔다"처럼 잘못 설정한 채 넘어가는 일이 없다. 줄이면 노출 시간은 줄지만 `POST /api/v1/auth/refresh` 호출이 그만큼 잦아진다. |
| `auth.registrationEnabled` | `true` | `false`로 하면 `POST /api/v1/auth/register`만 403이 되고, 로그인·토큰 갱신·기존 계정은 영향을 받지 않는다. **끄기 전에 필요한 계정을 모두 만들어 둘 것** — 끈 뒤에는 계정을 새로 만들 방법이 없다(계정 생성 API가 register 하나뿐이라 superuser도 새 계정을 만들 수 없다). |
| `auth.docsEnabled` | `true` | `false`로 하면 `/api-docs/openapi.json`, `/swagger-ui`, `/swagger-ui/` 세 경로가 **404**가 된다(라우트 자체가 등록되지 않아서다 — 403이 아니다). 스펙은 이미 전 경로가 인증 뒤에 있으므로, 이걸로 감추는 것은 API 경로 목록뿐이다. |

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소> \
  --set jwt.ttlHours=8 \
  --set auth.registrationEnabled=false \
  --set auth.docsEnabled=false
```

### 2.2 CVAT 연동 (선택, 차트 0.2.0+)

annotation을 CVAT에서 편집하려는 경우에만 설정한다. **설정하지 않아도 nexus는 정상 동작한다** — 세션 **생성**과 **결과 회수(import)**만 503을 반환하고, 카탈로그·업로드·seal·조회는 영향을 받지 않는다.

#### CVAT 쪽 준비 (운영자 작업)

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
docker exec cvat_worker_import curl -s -o /dev/null -w '%{http_code}
'   -x http://127.0.0.1:4750 http://<CAS>/<bucket>/<object-key>
```

#### nexus 설정 (Helm)

비밀번호는 기존 Secret에 키를 하나 추가하고, 나머지는 values로 준다.

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='...' \
  --from-literal=NEXUS__CAS__KEY_ID='...' \
  --from-literal=NEXUS__CAS__SECRET='...' \
  --from-literal=NEXUS__JWT__SECRET='...' \
  --from-literal=NEXUS__CVAT__PASSWORD='<CVAT 서비스 계정 비밀번호>' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
```

```bash
helm upgrade --install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소> \
  --set cvat.baseUrl=http://cvat.example.com:8080 \
  --set cvat.user=nexus-svc
```

| values 키 | 기본값 | 설명 |
|---|---|---|
| `cvat.baseUrl` | `""` | CVAT 주소. **비우면 연동이 꺼진다** |
| `cvat.user` | `""` | CVAT 서비스 계정 |
| `cvat.organization` | `""` | CVAT organization slug (선택) |
| `cvat.projectNamePrefix` | `nexus` | 생성되는 CVAT project 이름 접두사 |
| `cvat.segmentSize` | `""` | job 분할 크기. 비우면 CVAT 기본 동작 |
| `cvat.maxSessionSamples` | `""` | 세션당 샘플 상한(서버 기본 2000) |
| `cvat.staleCreatingSecs` | `""` | 준비 중 방치된 세션 정리 기준(초, 서버 기본 1800) |

비밀번호는 values에 두지 않는다. Secret의 `NEXUS__CVAT__PASSWORD`로 주입한다.

> **호환성** — CVAT 연동에는 **appVersion 0.1.1 이상**의 이미지가 필요하다. 그 이전 이미지는 `cvat` 설정 자체를 모른다. 다만 `NEXUS__CVAT__*` 환경변수를 줘도 **기동이 깨지지는 않는다** — 모르는 설정 섹션은 무시되고 CVAT 기능만 없는 상태로 정상 기동한다(실측 확인). 차트를 먼저 올리고 이미지를 나중에 올려도 안전하다.

#### 연결 확인

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
> curl -o /dev/null -w '%{http_code}
'                      http://<CVAT-IP>:8080/api/server/about   # 404
> curl -o /dev/null -w '%{http_code}
' -H 'Host: localhost' http://<CVAT-IP>:8080/api/server/about   # 200
> ```
>
> 해결은 CVAT 쪽에서 `CVAT_HOST`를 **실제 접속 주소(IP 또는 DNS 이름)로 바꾸고** traefik·서버·UI를
> 재생성하는 것이다. nexus의 `cvat.baseUrl`만 `localhost`로 되돌려 우회하면, nexus와 CVAT이 같은
> 호스트일 때만 동작하고 세션의 `cvat_url`이 `http://localhost:8080/tasks/N`으로 만들어져
> **다른 PC의 작업자가 열 수 없다.**

#### 연결되지 않았을 때의 동작

| CVAT 상태 | 서버 기동 | 카탈로그 API | 세션 생성·회수 | 세션 목록·조회·close·delete |
|---|---|---|---|---|
| 설정 없음 | 정상 | 정상 | 503 | 정상 |
| 설정 불완전 | 정상(경고 로그) | 정상 | 503 | 정상 |
| 설정됨, CVAT 다운 | 정상 | 정상 | 세션이 `failed`가 된다 | 정상 |
| 정상 연결 | 정상 | 정상 | 정상 | 정상 |

**목록·조회·`close`·`delete`는 CVAT 없이도 동작한다.** CVAT을 호출하지 않거나(목록·조회), 호출에 실패해도 진행하기 때문이다(`delete`는 CVAT project 삭제를 건너뛰고 세션 행만 지운다). 이미 만들어진 세션을 CVAT이 죽은 뒤에도 정리할 수 있어야 하기 때문이다 — 그러지 않으면 샘플이 영구히 잠긴다.

nexus는 기동 시점에 CVAT을 호출하지 않는다. 따라서 운영 중 CVAT이 내려가도 영향은 세션 생성·회수에만 국한된다.

## 3. 핵심 흐름
### 3.1 Dataset 생성
이름으로 dataset을 찾거나 생성하고, 그 안에 지정한 version이 없으면 생성한다. 멱등 동작이며 version은 항상 명시해야 하는 필수값이다.  
생성 직후 버전은 draft 상태 — 샘플 추가/삭제, annotation 수정이 가능하다.
```python
import nexus as nx
from nexus.sample import CasRef

ds = nx.Dataset.load_or_create("my-dataset", "v0")
```

### 3.2 원본 파일 업로드

로컬 이미지를 CAS에 직접 올리고 각 파일을 가리키는 참조 `{CasRef}`를 받는다. 이후 이 참조로 샘플을 등록한다.
- 같은 파일을 다시 올려도 내용이 같으면 건너뛴다(멱등). 실패한 파일만 골라 재시도할 수 있다(같은 목록으로 재호출).  
- 같은 key에 **다른** 내용이 이미 있으면 기본은 에러(충돌)다. 의도적으로 교체하려면 `nx.upload(..., overwrite=True)`를 쓴다 — 이때 썸네일도 새 내용으로 함께 다시 만든다(안 그러면 옛 썸네일이 새 이미지에 그대로 남는다). 내용이 같으면 `overwrite` 여부와 무관하게 그대로 건너뛴다(SDK 0.1.4+).
- 이미 CAS에 올라가 있는 파일이면 이 단계를 건너뛰고, 그 파일의 CAS URL을 바로 다음 단계(nx.Sample(image=...))에 명시하여 사용할 수 있다. 다만 그렇게 하면 이미지 크기를 알 수 없어 `meta.width`/`meta.height`가 비게 된다 — 아래 [`nx.probe`](#nxprobe--업로드-없이-이미지-크기만-채우기-sdk-013)로 채운다.

```python
import json
from pathlib import Path
from dataclasses import asdict

img_dir = Path(r"...\images")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
img_paths = sorted(str(p) for p in img_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS)

# CAS key = 파일명 (prefix= 로 "prefix/파일명" 지정 가능)
refs = nx.upload(img_paths, bucket="my-bucket", workers=8)   

#대량 작업이면 refs를 JSON으로 저장해두면 재사용·재개에 좋다.
records = {path: asdict(ref) for path, ref in refs.items()}
Path("upload_refs.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
```
`CasRef` = `bucket` / `key` / `hash_hex` / `size` / `content_type` (+ `width`/`height`). 이 값을 그대로 `nx.Sample(image=ref)`에 넘긴다.  

`nx.upload`는 로컬 파일을 CAS에 올릴 때 쓰는 편의 도구일 뿐이다. 다만, `nx.upload` 과정에서 UI 로딩 최적화용 썸네일(WebP 256px,thumb/<key>)을 함께 생성한다. 업로드를 건너뛰고 CAS URL로 바로 등록하면 썸네일이 없어 UI가 원본으로 폴백한다(동작은 정상, 로딩만 무거움). 필요시 `nx.upload`를 다시 돌려 없는 썸네일만 백필할 수 있다.

#### boto3 · `aws s3` 등으로 직접 올린 경우 — 썸네일 백필

`nx.upload`를 거치지 않고 CAS에 직접 올렸다면 썸네일 생성 단계가 없다. 이미 올라간 데이터에 대해서는 아래 스크립트를 한 번 돌리면 된다. **원본 로컬 파일이 없어도 된다** — CAS에서 받아 생성한다.

```bash
pip install boto3 pillow
curl -O https://raw.githubusercontent.com/int2nexus/cas-server/main/scripts/backfill_thumbnails.py

export CAS_URL=http://<CAS 주소>:8080
export CAS_KEY_ID=... CAS_SECRET=...

python backfill_thumbnails.py --bucket <버킷> --dry-run   # 읽기 전용, 대상만 확인
python backfill_thumbnails.py --bucket <버킷>              # 실행
```

멱등이라 중단 후 다시 돌려도 안전하다(이미 있는 썸네일은 건너뛴다). `--prefix images/`로 범위를 좁히고, 사내 TLS 검사 환경이면 `--ca-bundle /path/corp-ca.pem`을 붙인다.

**수백만 건 규모에서도 그대로 쓴다.** 목록을 모으지 않고 흘려보내며 처리하므로 메모리가 객체 수와 무관하다. 실패한 key 는 `backfill_thumbnails_errors.tsv`에 한 줄씩 남고(`--error-log`로 경로 변경), 매 실행 덮어쓰므로 **두 번 돌린 뒤에도 남아 있는 key 가 진짜 문제다**(손상 파일·권한 등). 아주 큰 원본은 `--max-bytes`(기본 200MB)로 걸러 다운로드조차 하지 않는다.

> 직접 업로드를 상시 경로로 쓴다면 **적재 후 이 스크립트를 돌리는 것을 절차에 포함**해야 한다. 빠뜨리면 UI에서 원본이 그대로 로드되어 그리드가 무거워진다.

#### `nx.probe` — 업로드 없이 이미지 크기만 채우기 (sdk 0.1.3+)

업로드를 건너뛰고 CAS URL로 바로 등록하면 썸네일뿐 아니라 **이미지 크기도 빠진다.** CAS가 객체의 픽셀 크기를 알려주지 않기 때문이다(`HEAD`로 얻는 것은 hash·size·content_type뿐이다). `nx.probe`가 각 객체의 **앞부분 64KB만** 받아 이미지 헤더를 파싱해 크기를 채운다.

```python
from nexus.sample import CasRef

refs = [CasRef(bucket="my-bucket", key=f"images/{name}") for name in names]
refs = nx.probe(refs, workers=8)          # 앞부분만 range GET

ds.add([nx.Sample(r) for r in refs])
ds.flush()
```

입력은 `CasRef` 또는 `s3://`·`http(s)://` URL 문자열의 리스트다(`nx.Sample(image=)`와 같은 규칙). `nx.upload`가 돌려준 `{경로: CasRef}` dict를 그대로 넘겨도 된다(내부에서 값만 취한다). 반환은 **입력 순서를 보존한 리스트**이고 길이가 줄지 않는다 — 실패한 객체도 자리를 지키며 크기만 비어 있으므로, 호출부가 자기 파일명 목록과 zip해도 어긋나지 않는다. 이미 크기가 있는 ref는 네트워크를 타지 않아 같은 목록으로 재호출하면 실패분만 재시도된다. CAS가 Range 요청을 지원하지 않아도 동작한다(앞부분만 읽고 연결을 끊는다).

로컬 파일이 손에 있다면 네트워크를 탈 이유가 없다. 같은 파서를 직접 부르면 된다.

```python
info = nx.image_info(path.read_bytes())   # width/height/mime/channels, 헤더만 읽음 (실패 시 None)
ref = (CasRef(bucket="my-bucket", key=key, width=info.width, height=info.height)
       if info else CasRef(bucket="my-bucket", key=key))   # 모르면 키를 넣지 않는다
```

> 크기를 못 구하면 `meta`에 `width`/`height` 키를 **넣지 않는다**. `0`을 적으면 크기 facet의 range가 `min:0`으로 오염되고, CVAT이 그 값으로 정규화 좌표를 계산해 좌표가 망가진다. 키가 없으면 집계에서 조용히 빠지고, **CVAT 편집 세션 생성은 명확한 에러로 거부된다**([6.1](#61-시작-전-확인)).

#### 이미 등록된 샘플의 크기 백필 — `ds.backfill_dims` (sdk 0.1.3+)

`nx.probe`가 생기기 전에 등록된 샘플은 `meta.width`/`meta.height`가 `0`으로 들어가 있다. 그 `0`은 측정값이 아니라 SDK가 자리를 채우려고 넣은 값이고, **CVAT에서는 세션 생성은 통과한 뒤 export 단계에서 해당 인스턴스가 조용히 빠진다.** 썸네일 백필과 같은 성격의 일회성 정비다.

```python
ds = nx.Dataset.load_or_create("<dataset>", "<version>")

report = ds.backfill_dims(dry_run=True)   # 대상 규모와 실제 측정 가능 건수만 확인
report = ds.backfill_dims(workers=8)      # 적용
print(report)
# {'scanned': 12000, 'targeted': 840, 'measured': 838, 'applied': 838, 'rejected': [...]}
```

버전의 샘플을 훑어 대상을 고르고, `nx.probe`로 크기를 재고, 서버에 청크로 적용한다.

- 대상은 `meta.width`/`height`가 **없거나, `null`이거나, 0 이하**인 샘플이다. 이미 값이 있으면 건드리지 않는다.
- `dry_run=True`도 **실제로 측정까지 한다.** 쓰기만 건너뛴다 — "몇 건을 정말 잴 수 있는가"가 적용 전에 알고 싶은 전부이기 때문이다.
- image asset이 없거나 헤더를 읽지 못한 샘플은 건너뛰고 `measured`에서 빠진다.
- 서버는 **빈칸만 채우고 기록된 값은 축 단위로 거부한다.** 이미 크기가 있는 샘플을 보내면 `rejected`에 사유와 함께 돌아온다. `applied + len(rejected)`가 `measured`와 맞으므로 스크립트가 종료 코드를 정할 수 있다.
- 멱등이라 중단 후 다시 돌려도 안전하다(이미 채워진 것은 서버가 거부한다).
- sealed 버전의 샘플도 보정된다 — `samples.meta`는 seal이 얼리는 대상이 아니고([architecture.md 10.3](architecture.md#103-version-불변성)), 애초에 그 `0`은 측정된 값이 아니었다.

### 3.3 샘플 생성 & 등록

받은 ref로 `nx.Sample`을 만들어 dataset/version에 등록한다.  
저장해둔 refs를 다시 로드하는 패턴:

```python
from nexus.sample import CasRef

saved = json.loads(Path("upload_refs.json").read_text(encoding="utf-8"))
refs = {path: CasRef(**rec) for path, rec in saved.items()}

samples = [
    nx.Sample(
        image=ref,                   # CasRef (또는 http:// URL). 로컬 경로는 ValueError
        # annotation="ann.json",     # 선택: 이미지와 매핑되는 로컬 JSON 경로 / dict(inline GT) 
        # assets={"depth": depth_ref},  # 선택: image 외 추가 asset — {role: ref} 범용 dict
        # split="train", tags=[...], # 선택
    )
    for ref in refs.values()
]

ds.add(samples)                       # 등록 큐에 추가 - 단일 Sample 또는 리스트 모두
results = ds.flush(workers=8)         # 병렬 등록 → IngestResult 리스트

print("ok:", sum(r.ok for r in results), "/", len(results))
for r in (r for r in results if not r.ok):
    print("  FAIL:", r.error)
```

- `image` - `nx.upload`가 돌려준 `CasRef`, 또는 그 이미지의 CAS URL을 직접 넣는다(`http://<cas>/<bucket>/<key>`).  
- `annotation`은 Sample 등록 시점에 같이 넣는 게 자연스럽다(나중에 따로 고치는 방법은 §3.5).  
생략하면 서버가 최소한의 정보만으로 등록한다.
- `assets`는 image 외 추가 모달리티(depth map 등)를 담는 범용 dict(`{role: ref}`).  
`image`외 새 모달리티(thermal, lidar 등)가 필요하면 필드 추가 없이 이 dict에 role을 추가한다.

#### GT 파일만 있고 이미지는 이미 CAS에 있을 때

업로드를 이미 마쳤고 로컬에는 GT(JSON)만 남은 경우다. **GT의 `meta.filename`에 그 이미지의
CAS URL이 들어 있다면 이미지와 GT를 따로 짝지을 필요가 없다** — 파일명 규칙이나 확장자를
추정하지 않고 GT가 가리키는 주소를 그대로 쓴다.

```python
import json
from pathlib import Path

ann_dir = Path(r"...\annotations")

samples = []
for p in sorted(ann_dir.glob("*.json")):
    gt = json.loads(p.read_text(encoding="utf-8"))
    samples.append(nx.Sample(
        image=gt["meta"]["filename"],   # GT 안의 CAS URL을 그대로 쓴다
        annotation=gt,                   # 이미 읽었으므로 dict로 넘긴다(파일을 다시 읽지 않는다)
        # split="train", tags=[...],    # 선택
    ))

ds.add(samples)
results = ds.flush(workers=8)

print("ok:", sum(r.ok for r in results), "/", len(results))
for r in (r for r in results if not r.ok):
    print("  FAIL:", r.error)
```

**GT에 `meta`가 있으면 그 값이 그대로 쓰인다.** SDK는 `meta`가 있는 경우 어떤 필드도
수정하지 않는다. 따라서 GT가 `width`/`height`를 이미 담고 있으면 [`nx.probe`](#nxprobe--업로드-없이-이미지-크기만-채우기-sdk-013)로
크기를 채울 필요가 없다. `meta`가 **없을 때만** SDK가 최소 meta(`format_version`,
`filename`, 그리고 ref에 크기가 있으면 `width`/`height`)를 만들어 넣는다.

주의할 점 둘:

- **`meta`는 통째로 신뢰된다.** `filename`만 있고 `width`/`height`가 없는 부분 meta를 주면
  SDK가 나머지를 채워주지 않는다. 그 샘플은 크기 facet·히스토그램 집계에서 빠지고 CVAT
  편집 세션 생성이 거부된다. 크기가 없는 GT라면 [`nx.probe`](#nxprobe--업로드-없이-이미지-크기만-채우기-sdk-013)로
  ref를 채워 `image=`에 넘기거나, 등록 후 `ds.backfill_dims()`로 보정한다.
- **업로드를 건너뛰었으므로 썸네일이 없다.** UI는 원본으로 폴백하므로 동작은 정상이고
  로딩만 무겁다(§3.2 참조).

### 3.4 등록 확인
```python
samples = ds.list_samples()                        # 이 버전의 샘플 목록
sample = ds.get_sample(samples[0]["sample_id"])     # 샘플 하나의 annotation을 포함한 전체 정보

# 조건에 맞는 샘플들의 annotation을 포함한 전체 정보
everything = ds.samples()                                   # 필터 없음 → 버전 전체 샘플(자동 페이지네이션)
cars = ds.samples(label="car")                              # label이 car인 instance가 있는 샘플(전체)
trucks = ds.samples(group_key="det", label="truck")         # det 그룹 안에서만
just_these = ds.samples(sample_ids=["s1", "s2", "s3"])       # 이 sample_id들만
by_split = ds.samples(split="val", tags=["night"])  
```
`samples(sample_ids=, group_key=, label=, confidence_min=, confidence_max=, track_id=, split=, tags=, meta=, include_annotations=True)` 특정 조건 필터를 추가하여 조건에 맞는 샘플만 조회한다.  `limit`을 지정하지 않으면 커서를 자동으로 순회해 매칭 전체를 모아서 반환한다.  
매칭되는 샘플이 아주 많을 수 있는 대규모 dataset이면 `limit`없이 그냥 부를 경우 전체 데이터를 로드하느라 느려지거나 메모리를 많이 쓸 수 있다. `limit`을 명시하여 필요한 만큼만 가져오는 것을 권장한다. annotation이 필요 없는 대규모 스캔이라면 `include_annotations=False`로 경량 코어 필드만 받는 편이 훨씬 싸다.  

**`meta=` 필터는 서버 `0.1.5`부터 번들 스키마에 선언되지 않은 키도 받는다.** 그 dataset에서 실제로 관측된 값의 타입을 보고 숫자는 범위, 문자열은 값 목록, 불리언은 참/거짓으로 다룬다(선언된 필드는 선언이 우선이다). 관측된 문자열은 날짜처럼 보여도 범위가 아니라 값 목록이다. 선언에도 관측 표에도 없는 이름은 계속 400이다(오타를 빈 결과로 삼키지 않기 위한 것이다). 다만 **meta 키 이름이 `[A-Za-z0-9_]`를 벗어나면(예: `capture-time`, `카메라`) 그 필드는 필터·facet 대상이 되지 않는다** — 값은 그대로 저장되고 `ds.get_sample()`·`ds.samples()` 응답에도 보이지만 걸러낼 수는 없고 `GET .../schema` 목록에도 나타나지 않으니, 필터로 쓸 키는 영문·숫자·밑줄로 짓는다.  

직접 페이지 단위로 로드 - `after`로 다음 페이지의 시작점(이전 호출 결과의 마지막 `sample_id`)을 지정::
```python
  cursor = None
  while True:
      page = ds.samples(label="car", limit=500, after=cursor)
      ...
      if len(page) < 500:
          break
      cursor = page[-1]["sample_id"]
```

### 3.5 annotation 추가/교체

이미 등록된 샘플에 annotation만 따로 붙이거나 교체한다(재적재 없이).  
이미지 파일명(stem)으로 annotation 파일을 매핑하는 패턴:

```python
ann_dir = Path(r"...\annotations")    # 파일명 stem이 이미지와 1:1

patches = {}
for s in ds.list_samples():
    stem = Path(s["assets"]["image"]["cas_url"]).stem
    p = ann_dir / f"{stem}.json"
    if p.exists():
        patches[s["sample_id"]] = json.loads(p.read_text(encoding="utf-8"))

pres = ds.patch_annotations(patches, workers=8)   # 배치(병렬) → IngestResult 리스트
print("patched:", sum(r.ok for r in pres), "/", len(pres))
```

```python
ds.patch_annotations(sample_id, {"det": [{"id": "a", "label": "truck"}]})   # 하나씩
```
- draft 버전에서만 가능(sealed면 409). 이전 patch를 완전 교체하는 방식(누적 아님).
- 교체 단위는 group_key 단위가 아닌 샘플 전체(이 버전 한정). 기존 그룹을 유지하려면 바꾸지 않는 그룹도 `annotation_data`에 같이 넣어야 한다.  

한 그룹의 일부만 고치고 싶을 때 안전한 방법은 전체를 가져와서 필요한 부분만 바꾼 뒤 통째로 다시 보내는 것이다. 
  ```python
  full = ds.get_sample(sample_id)                          # 이 버전의 annotation 전체
  CORE = ("sample_id", "split", "tags", "created_at", "image_url", "thumbnail_url")
  annotation_data = {k: v for k, v in full.items() if k not in CORE}
                                                           # {"meta": ..., "det": [...], "seatbelt": [...]}

  for inst in annotation_data["det"]:                      # det 그룹 안 인스턴스 하나만 라벨 수정
      if inst["id"] == "a":
          inst["label"] = "truck"

  ds.patch_annotations(sample_id, annotation_data)         # seatbelt 등 나머지 그룹은 그대로 유지됨
  ```

**코어 필드를 하나라도 빠뜨리면 서버가 그것을 annotation 그룹으로 보고 버린다** — 응답의 `skipped`가 0이 아니게 되고 SDK가 경고를 낸다. 1건만 고칠 때는 아래 `get_annotation`/`save_annotation`이 더 안전하다.

**annotation 왕복 전용 메서드**(서버 `0.1.5`+, SDK `0.1.5`+): 위 패턴처럼 `get_sample()` 응답에서 `sample_id`/`split`/`tags`/`created_at`/`image_url`/`thumbnail_url` 같은 코어 필드를 직접 걸러내지 않아도, `get_annotation`/`save_annotation`이 이 버전의 annotation만 그대로 주고받는다.

```python
ann = ds.get_annotation(sample_id)                        # 이 버전의 annotation 전체 — {"meta": ..., "det": [...], ...}

for inst in ann["det"]:
    if inst["id"] == "a":
        inst["label"] = "truck"

rep = ds.save_annotation(sample_id, ann)                  # 그대로 다시 저장
# rep == {"instances": 12, "skipped": 0,
#         "skipped_reasons": {"missing_label": 0, "not_an_object": 0, "group_not_an_array": 0}}
```
- `save_annotation`은 내부적으로 `patch_annotations`와 동일하게 동작한다 — **이 버전의 인스턴스를 병합이 아니라 통째로 교체**한다. 받은 것 중 일부 그룹만 빼고 보내면 그 그룹은 사라진다(§3.5 위 패턴대로 건드리지 않는 그룹도 함께 넣어 보낼 것).
- `meta`는 버전이 아니라 샘플에 붙는다 — **모든 버전이 같은 `meta`를 공유**하므로, `get_annotation`으로 받아 그대로 `save_annotation`에 되돌리는 왕복만 해도 `meta`가 다시 쓰인다(다른 버전에서 이미 `meta`를 바꿔 뒀다면 그 값을 덮어쓰지 않도록 왕복 전에 확인할 것).
- `save_annotation`은 **서버가 버린 인스턴스 수를 담은 보고서를 반환한다.** 서버는 형식이 어긋난 원소(`label` 필드가 없는 원소, object가 아닌 원소, 값이 배열이 아닌 그룹)를 버리는데, 교체는 병합이 아니므로 **버려진 만큼 기존 인스턴스가 지워진다.** `skipped`가 0이 아니면 SDK가 `RuntimeWarning`도 함께 낸다 — 반환값을 보지 않는 스크립트에서도 유실이 드러나야 하기 때문이다. `patch_annotations`(단일·배치)도 같은 경고를 낸다.
- 구 서버(`0.1.5` 미만)나 구 SDK(`0.1.5` 미만)에는 이 메서드 자체가 없다 — 기존 `patch_annotations`/`get_sample` 조합은 그대로 쓸 수 있다. 구 서버에 새 SDK를 붙이면 `save_annotation`의 반환은 빈 dict이고 경고도 나지 않는다(서버가 보고서를 주지 않으므로 유실을 주장할 근거가 없다).
- **SDK `0.1.5`는 서버와 별도로 발행된다.** 위 §2의 업데이트 명령을 돌린 뒤 `python -c "import importlib.metadata as m; print(m.version('int2nexus-sdk'))"`로 확인하고, 아직 낮으면 인덱스에 올라오지 않은 것이다 — 그동안은 `patch_annotations`/`get_sample` 조합을 쓰거나 `GET`/`PUT` 엔드포인트를 직접 호출한다.

### 3.6 seal - 버전 잠금
검수가 끝난 draft 버전을 봉인해 불변 상태로 전환한다(draft → sealed, 단방향 - 되돌릴 수 없음). seal 시 annotation을 NDJSON 스냅샷으로 CAS에 박제하고 manifest hash를 기록한다.

```python
ds.seal()                       # 이미 sealed면 서버 409(NexusError) 전파
ds.seal(if_sealed="ignore")     # 이미 sealed면 현재 상태 그대로 반환(멱등 — 재실행 편의)
```
- seal 이후로는 해당 버전에서 샘플 추가/삭제/annotation 추가 및 버전 삭제 동작이 전부 막히고(409), to_df()로 학습 소비가 가능해진다.
- 수정하고 싶으면 새 버전으로 `fork`(§5.3) 해서 새로운 draft 버전을 만든다.

### 3.7 DataFrame 변환
`ds.to_df()`는 sealed 버전의 GT annotation 스냅샷(NDJSON)을 pandas DataFrame으로 로드한다.  
각 행 = 한 샘플 = `{sample_id, meta, <group_key>:[instances...]}`.  
seal 시 이 스냅샷은 여러 NDJSON 샤드로 나뉘어 CAS에 저장되고, nexus는 그 샤드들의 위치를 가리키는 manifest만 갖고 있다.  
`to_df()`는 nexus 서버에 manifest만 한 번 조회한 뒤, 실제 annotation 데이터(샤드 NDJSON)는 CAS에서 직접 다운로드해 DataFrame으로 조립한다 - 대량의 annotation을 읽어도 nexus 서버에 부하가 몰리지 않는다.

```python
df = ds.to_df()                              # 모든 group_key
df = ds.to_df(groups=["seatbelt", "bkp_gt"]) # 지정 그룹만
ds.to_df(path="gt.jsonl")                    # 파일로도 저장(+ df 반환) — csv/json/jsonl/parquet
for chunk in ds.to_df(chunksize=1000):       # 대규모 — 샤드 단위 스트리밍 이터레이터
    ...

import requests

for _, row in df.iterrows():
    image_bytes = requests.get(row["meta"]["filename"]).content   # 이미지는 URL로 받아옴
    instances = row.get("det", [])
    train(image_bytes, instances)
```

DataFrame에는 annotation과 이미지 경로(meta.filename)만 담기고, 이미지 바이트 자체는 안 담긴다 - 필요하면 그 경로에서 따로 받는다.  
대용량 데이터의 경우 ds.to_df(chunksize=1000)으로 한 번에 다 메모리에 올리지 않고 나눠 처리할 수 있다.

### 3.8 전체 예제
지금까지의 흐름(3.1~3.7)을 간략히 정리한다.
```python
import nexus as nx

nx.connect()

# 1. dataset 생성
ds = nx.Dataset.load_or_create("my-dataset", "v0")

# 2. 원본 파일 업로드
refs = nx.upload(["img1.png"], bucket="my-bucket", prefix="incabin")

# 3. 샘플 생성 + 등록
sample = nx.Sample(
    image=refs["img1.png"],
    annotation={"meta": {}, "det": [{"id": "a", "label": "car"}]},
    split="train",
)
ds.add(sample)
results = ds.flush()

# 4. 확인
print(ds.list_samples())

# 5. (필요하면) annotation 수정
ds.patch_annotations(results[0].sample_id, {"det": [{"id": "a", "label": "truck"}]})

# 6. 확정
ds.seal()

# 7. 학습 데이터로 사용
df = ds.to_df()
```

## 4. 데이터셋 관리
### 4.1 데이터셋 목록 조회
```python
nx.list_datasets()                              # 전체 목록
nx.list_datasets(q="incabin")                    # name/description/tags 통합 검색(부분일치)
nx.list_datasets(tags=["person-detection"])      # 태그로 필터(하나라도 포함)
nx.list_datasets(favorite=True)                  # 내 즐겨찾기만
nx.list_datasets(sort="name", order="asc")       # 정렬
```
- `q`는 `name/description/tags` 중 하나라도 부분일치하는 데이터셋을 반환한다. `name=/description=`은 개별 필드 검색
- 즐겨찾기는 `ds.favorite() / ds.unfavorite()`(멱등)로 켜고 끄고, favorite=True로 목록을 필터링한다.

### 4.2 데이터셋 정보 수정
```python
ds.update(name="my-dataset-renamed")             
ds.update(description="새 설명")                  
ds.update(name="new-name", description="새 설명") 
```
- 제공한 필드만 수정된다(둘 다 생략하면 아무 것도 안 함).  
이름을 바꾸면 이 `ds` 핸들의 내부 이름도 자동으로 같이 갱신된다.
- 다른 dataset이 이미 쓰고 있는 이름으로는 바꿀 수 없다(충돌 시 에러).
- Dataset의 소유자(생성자) 계정만 이름/설명을 바꿀 수 있다.

### 4.3 데이터셋 삭제 정책
Dataset 삭제는 버전 단위로 수행한다. `ds.delete()`로 버전을 삭제하고, 남은 버전이 하나도 없으면 Dataset도 자동으로 삭제된다. 이때 Dataset에 속한 잔여 Sample도 모두 정리되며, CAS로 Asset 삭제 요청을 보낼지는 아래 `delete_cas`가 정한다.
Dataset의 소유자(생성자)만 삭제 가능하며, sealed 버전은 삭제할 수 없다(409, 예외 없음 — 그 버전이 Dataset의 마지막 버전이어도 마찬가지다).

**CAS 원본 삭제(`delete_cas`)는 층마다 기본값이 다르다.**

- `ds.delete(...)`(SDK 고수준): `delete_cas`를 생략하면 **한 번 물어본다** — 대화형(터미널·노트북)이면 `삭제=y / 보존=N` 프롬프트가 뜨고, 입력이 불가능한 비대화형(CI·파이프)에서는 **보존(False)**으로 진행한다. 묻지 않게 하려면 `delete_cas=False`(보존) 또는 `delete_cas=True`(삭제)를 명시한다. 이 동작은 예전과 같다.
- **HTTP로 직접 호출할 때(서버 `0.1.5`부터 변경):** `?delete_cas=`를 생략하면 이제 **CAS 객체를 지우지 않는다.** 이전 버전은 지웠다. `DELETE /datasets/{id}/versions/{v}`와 `DELETE /samples/{sample_id}` 둘 다 해당한다. 지우려면 `?delete_cas=true`를 명시해야 한다.
- **SDK 저수준 `client.delete_version(...)`(SDK `0.1.5`부터 변경):** 기본값이 `delete_cas=True`에서 **`False`(보존)**로 바뀌었다. 이 함수를 직접 부르며 기본값에 기대어 용량을 회수하던 스크립트는 이제 `delete_cas=True`를 명시해야 한다.

sealed 버전이 참조하는 객체는 `delete_cas` 값과 무관하게 **항상 보존**된다(변경 없음).

`confirm`에는 **삭제할 버전 문자열**을 준다(`True`면 현재 버전). 서버가 경로의 버전과 정확히 비교해 어긋나면 400이다 — dataset 이름이 아니다.

```python
ds.delete(confirm="v0")                   # delete_cas 생략 → 대화형으로 한 번 물어본다
ds.delete(confirm="v0", delete_cas=False) # 묻지 않고 카탈로그만 삭제, CAS 원본 유지
ds.delete(confirm="v0", delete_cas=True)  # CAS로 삭제 요청까지 보냄
```

## 5. 데이터셋 버전 관리
### 5.1 Draft 버전
처음 버전 생성 시 Draft 상태이며 자유롭게 수정 가능한 작업 중 상태이다. 
이 상태에서 할 수 있는 일:
- 샘플 추가/등록, Annotation 추가, 버전 삭제
- 같은 Dataset의 다른 버전에서 샘플 재사용(재적재 없이 참조만 연결)
```python
ds.link_samples([sid1, sid2])          # 이미 존재하는 sample_id를 이 버전에 연결
ds.unlink_samples([sid1, sid2])        # 연결 해제(샘플 자체·다른 버전은 유지)
```
- 다른 Dataset의 샘플 재사용(Sample은 Dataset 범위 객체라 직접 링크가 아닌 복사)
```python
ds.import_samples(source_dataset_id, "v0", [sid1, sid2])
```
복사된 Sample은 이후 원본과 독립적으로 관리된다. `ds.samples()`로 조회한 결과를 그대로 옮기는 패턴:
```python
source = nx.Dataset.load_or_create("source-dataset", "v0")
people = source.samples(label="Person")           # 조건에 맞는 샘플 검색(전체, 자동 페이지네이션)

target = nx.Dataset.load_or_create("target-dataset", "v0")
target.import_samples(
    source.dataset_id, source.version,
    [s["sample_id"] for s in people],              # samples()의 dict에서 sample_id만 뽑는다
)
```

### 5.2 Sealed 버전
Seal 하면 그 시점 상태로 불변 스냅샷이 된다. 이후:
- 샘플 추가/삭제, Annotation 수정, 버전 삭제 불가
- `to_df()`로 소비할 수 있다.
- 수정이 필요할 경우 `fork`해서 새 Draft 버전을 생성하여 작업한다(§5.3).

### 5.3 Fork
기존 버전을 기반으로 새로운 작업용 버전을 만든다.
```python
ds_v1 = nx.Dataset.load_or_create("my-dataset", "v1", fork_from="v0")   # 전량 fork
```

> `sealed v0` --(fork_from)--> `draft v1`

fork된 버전은 원본의 샘플 구성(+ Annotation)을 그대로 이어받지만, 이후 샘플 추가/제거나 Annotation 수정은 새 버전에서 독립적으로 이루어진다(원본에 영향 없음).  
특정 샘플만 골라서 fork하고 싶으면 sample_ids=[...]를 같이 넘기거나, 조건으로 바로 고르고 싶으면 ds.fork()를 사용해 매칭되는 샘플만 담은 새 버전을 만든다:
```python
cars_v1 = ds.fork("v1", group_key="det", label="car")   # label=car인 샘플만 담은 새 버전
```
필터가 지정되지 않은 경우 위의 전량 fork와 동일하게 동작한다.

### 5.4 Clone
fork가 같은 Dataset 안에서 새 버전을 만드는 것이라면, clone은 완전히 다른 Dataset으로 통째로 복제한다.
```python
new_ds = ds.clone("my-dataset-copy", "v0")
```
- 원본을 그대로 복사해 새 dataset을 만든다(이미 있으면 그 dataset을 재사용).
- 복사 후 Draft로 시작한다 - 복제 직후 바로 이어서 patch/추가 작업이 가능하다.
- 내부적으로 import_samples를 반복 호출하는 방식이라 멱등하지 않다 - 같은 대상에 두 번 부르면 샘플이 중복 복사된다.

## 6. CVAT으로 annotation 편집 (sdk 0.1.2+)

Draft 버전의 샘플을 **CVAT으로 보내 사람이 편집**하고, 그 결과를 다시 Draft에 반영한다.
이미지는 Nexus를 거치지 않는다 - CVAT이 CAS에서 직접 받는다.

서버에 CVAT 연동이 구성되어 있어야 한다. 구성되지 않은 서버에서는 `NexusError(status_code=503)`이 발생한다.

### 6.1 시작 전 확인

| 항목 | 확인하지 않으면 |
|---|---|
| 대상 버전이 **draft** | sealed면 `NexusError(409)` |
| 내가 그 dataset의 **소유자** | `NexusError(403)` - 세션 생성은 소유자만 가능하다 |
| 서버에 CVAT 연동 구성 | `NexusError(503)` |
| CVAT이 CAS 이미지를 받을 수 있는 네트워크 | 세션이 `failed`가 되고 사유가 예외에 실린다 |
| 그 샘플을 잡고 있는 다른 세션 없음 | `NexusError(409)` - 어느 세션이 잡고 있는지 메시지에 담긴다 |

**세션 관련 작업은 모두 dataset 소유자만 할 수 있다.** 세션 생성 자체가 소유자 전용이라, 실질적으로 세션을 만든 사람과 소유자는 같은 계정이다.

`close`와 `pull`은 예외적으로 "세션을 만든 사람"에게도 열려 있는데, 이건 **소유자가 없던 시절에 만들어진 세션**이 나중에 소유자를 갖게 된 경우를 위한 안전장치다. 그런 세션을 만든 사람이 스스로 닫을 수 있게 하려는 것이고, 정상적으로 만든 세션에서는 차이가 없다.

### 6.2 세션 생성

```python
ds = nx.Dataset.load_or_create("my-dataset", version="v0")     # draft여야 한다
ids = [r["sample_id"] for r in ds.list_samples(max_samples=50)]

ses = ds.create_annotation_session(ids)     # open 될 때까지 기다렸다가 반환
print(ses.url)                              # 작업자에게 넘길 CVAT 주소
print(ses.session_id)                       # 나중에 이어받을 때 필요
```

**생성은 비동기다.** CVAT이 이미지를 모두 내려받아야 열리므로 수백 장이면 몇 분 걸린다.
바로 받아두고 나중에 기다릴 수도 있다.

```python
ses = ds.create_annotation_session(ids, wait=False)   # status == "creating"
ses.wait_open(timeout=1800)                           # 큰 세션은 넉넉히
```

데이터에 아직 없는 라벨로 새로 그리게 하려면 함께 만들어 준다.

```python
ds.create_annotation_session(ids, extra_labels=[
    {"group": "det", "label": "Face", "components": ["bounding_box"]}])
```

### 6.3 고칠 대상만 골라서 세션 만들기

세션은 `sample_ids` 목록을 받으므로 어떤 조건으로 고르든 그 결과를 그대로 넘기면 된다. 가장 흔한 것은 "특정 그룹의 특정 라벨이 붙은 샘플만 다시 손보기"다.

```python
# 'road_obj_ma' 그룹에 label이 'sedan'인 인스턴스가 있는 샘플
rows = ds.samples(group_key="road_obj_ma", label="sedan")
ids = [r["sample_id"] for r in rows]

ses = ds.create_annotation_session(ids)
print(len(ids), "개 대상 →", ses.url)
```

`group_key`/`label`/`confidence_min`/`confidence_max`/`track_id`는 **같은 인스턴스 하나**가 모두 만족해야 하는 조건이다.

```python
ds.samples(group_key="road_obj_ma", label="sedan", confidence_max=0.5)   # 신뢰도 낮은 것만
ds.samples(group_key="road_obj_ma", track_id=102)                        # 특정 track만
```

`split`/`tags`/`meta`는 인스턴스가 아니라 **샘플 자체의 속성**으로 따로 걸린다.

```python
ds.samples(group_key="road_obj_ma", label="sedan", split="train", tags=["night"])
```

세션 상한(기본 2000)을 넘으면 나눠서 만든다.

```python
for i in range(0, len(ids), 500):
    ses = ds.create_annotation_session(ids[i:i + 500], wait=False)   # 기다리지 않고 연달아
```

> 대상을 좁히면 CVAT에 보내는 이미지가 줄어 준비도 빨라진다. 다만 **한 샘플의 편집형 컴포넌트는 전부 나간다** — `label="sedan"`으로 골라도 그 샘플의 다른 인스턴스와 차선 등이 함께 보인다(그리는 화면에서 맥락이 필요하기 때문). 특정 그룹만 보이게 하려면 `groups=["road_obj_ma"]`를 함께 준다.

### 6.4 편집 결과 반영

작업자가 CVAT에서 편집한 뒤 결과를 Draft로 당겨온다.

```python
summary = ses.pull()
print(summary)
```

| 키 | 뜻 |
|---|---|
| `updated_samples` | annotation이 실제로 바뀐 샘플 수 |
| `created_instances` | CVAT에서 새로 그려 생긴 인스턴스 |
| `removed_instances` | CVAT에서 지워져 사라진 인스턴스 |
| `updated_components` | 좌표 등이 바뀐 컴포넌트 |
| `deleted_components` | 지워진 컴포넌트 |
| `warnings` | 반영되지 않은 것들의 사유 |

> **CVAT에서 반드시 `Save`(Ctrl+S)를 눌러야 한다.** 편집만 하고 저장하지 않으면 서버에 올라가지 않아 `pull()`이 전부 0을 돌려준다.

- `pull()`은 **여러 번 호출해도 안전하다.** 작업 도중에 중간중간 불러도 되고, 편집이 없으면 전부 0이다.
- `warnings`를 버리지 말 것 - "CVAT에서 지웠는데 annotation에 남아 있다"의 이유가 대개 여기 있다. 일부 샘플 반영 실패도 예외가 아니라 이 목록으로 온다.

### 6.5 종료 - `close`와 `delete`는 다르다

```python
ses.close()                 # 샘플 잠금만 풀고 CVAT project는 남긴다
ses.close(force=True)       # 미반영 편집을 버리고 닫는다 (그냥 close()는 409)
ses.delete()                # CVAT project까지 완전 삭제 - 되돌릴 수 없다
```

| | close | delete |
|---|---|---|
| 샘플 잠금 | 해제 | 해제 |
| CVAT project | **보존** | **삭제**(이미지 사본·미반영 편집까지) |
| 권한 | dataset 소유자 (+ 그 세션을 만든 사람) | **dataset 소유자만** |
| CVAT 연결 | 없어도 동작 | 없어도 동작(project 삭제만 건너뜀) |

`close()`는 아직 당겨오지 않은 편집이 있으면 `NexusError(409)`로 막는다. 먼저 `pull()`을 부르거나, 그 작업을 버릴 생각이면 `force=True`를 준다. CVAT을 조회할 수 없으면 "미반영 여부를 모름"으로 보고 막지 않는다 — CVAT이 죽었을 때 세션을 못 닫으면 샘플이 영구히 잠기기 때문이다.

### 6.6 진행 중인 세션 찾기 / 이어받기

세션은 파이썬 프로세스와 무관하게 서버에 남아 있다. 스크립트를 껐다 켜도 이어받을 수 있다.

```python
for s in nx.annotation_sessions():                  # 전역, 기본은 진행 중인 것만
    print(s.session_id, s.status, s.dataset_name, s.version, s.url)

ses = nx.annotation_session("019fd94f-...")         # id로 다시 잡기
nx.annotation_sessions(status="all", mine=True)     # 이력 포함 / 내가 만든 것만
ds.annotation_sessions()                            # 이 dataset·version의 것만
```

목록으로 만든 객체는 `has_unimported_changes`가 항상 `None`이다(세션마다 CVAT 조회가 필요해서). 필요하면 `s.refresh()` 후 읽는다.
**`None`은 '없음'이 아니라 '모름'이다.**

### 6.7 알아둘 것

- CVAT으로 나가는 컴포넌트는 `bounding_box`/`polygon`/`polyline`/`keypoint_2d` **4종뿐**이다. 3D(`cuboid_3d` 등)·classification·scalar는 편집 대상이 아니며 **그대로 보존**된다.
- 하나의 샘플은 동시에 하나의 세션에만 속할 수 있다. 겹치면 세션 생성이 거부되고, 해당 세션을 `close()`하면 풀린다.
- sealed 버전에는 세션을 만들 수 없다.
- 세션 삭제는 CVAT project를 통째로 지우므로 **회수하지 않은 편집도 함께 사라진다.**

### 6.8 전체 예제

```python
import nexus as nx
nx.connect()

ds = nx.Dataset.load_or_create("my-dataset", version="v0")
ids = [r["sample_id"] for r in ds.list_samples(max_samples=20)]

# 편집 전 annotation을 남겨둔다 - 나중에 무엇이 바뀌었는지 대조할 근거
before = {sid: ds.get_sample(sid) for sid in ids}

ses = ds.create_annotation_session(ids)
print("CVAT에서 편집하세요:", ses.url)

# --- 작업자가 CVAT UI에서 편집하고 반드시 [Save] ---

summary = ses.pull()
print(summary)

for sid in ids:
    if ds.get_sample(sid) != before[sid]:
        print("변경됨:", sid)

ses.close()
```

## 7. 에러 처리

모든 SDK 예외는 `NexusError`(및 하위 클래스 `NexusAuthError`/`NexusCasError`/`NexusIngestError`/`NexusBatchError`)를 상속한다.

```python
from nexus import NexusError

try:
    ds.delete(confirm=True)
except NexusError as e:
    if e.status_code == 409:
        print("sealed 버전이라 삭제 못 함:", e.server_message)
    elif e.status_code == 403:
        print("소유자 아님:", e.server_message)
    else:
        raise
```

- `e.status_code`(`int | None`)와 `e.server_message`(`str | None`)로 서버가 보낸 실제 에러 사유를 프로그램적으로 분기할 수 있다. `str(e)`에도 같은 내용이 포함되지만(사람이 읽는 용도), 상태코드로 분기하려면 이 두 속성을 쓴다.
- `flush`/`patch_annotations`의 배치 호출은 건당 결과를 `IngestResult(ok, sample, sample_id, error, status_code)`로 모아서 반환한다 — `strict=True`면 실패가 하나라도 있을 때 `NexusBatchError(failures=[...])`를 던진다.

#### 401과 403을 구분한다

| 코드 | 뜻 | 대응 |
|---|---|---|
| `401` | 토큰이 없거나 만료됐다 | **SDK 0.1.2+는 자동으로 다시 로그인하고 재시도한다** — 보통 이 예외를 볼 일이 없다. 그래도 401이 올라오면 자격증명 자체가 안 맞는 것이다(비밀번호가 바뀌었거나 서버 JWT 시크릿이 교체됨) |
| `403` | 로그인은 됐지만 **그 dataset의 소유자가 아니다** | 소유자에게 요청하거나, `clone()`으로 내 dataset을 만들어 작업한다 |

**조회를 포함한 모든 요청에 토큰이 필요하다.** 그리고 dataset을 바꾸는 작업 — 적재(`flush`), annotation 수정, 샘플 추가·삭제, seal, 이름 변경, 삭제 — 은 **소유자만** 할 수 있다. 소유자는 dataset을 만든 계정으로 고정된다 — 본인이 옮길 수는 없고, 차트 0.3.0+에서 superuser가 `PUT /api/v1/admin/datasets/{dataset_id}/owner`로 지정한다. 조회는 소유자가 아니어도 된다.

예외가 하나 있다. **소유자가 지정되지 않은 dataset은 누구나 바꿀 수 있다.** 소유권 도입 이전에 만들어졌거나 소유자 계정이 삭제된 경우이며, 이때는 403이 나지 않는다. 남의 dataset인 줄 알았는데 쓰기가 되면 이 경우다. 주인을 붙이려면 superuser가 위 엔드포인트로 지정한다(같은 연산이다).

`flush`는 권한 때문에 거부된 건이 있으면 조용히 넘기지 않고 예외를 던진다. 남의 dataset에 적재를 시도하다 일부만 들어가는 상황을 막기 위해서다.


## 8. 전체 API 레퍼런스
### 최상위 함수
|||
|---|---|
|`nx.connect(nexus_url=, email=, password=, cas_url=, cas_key_id=, cas_secret=)`|서버 연결|
|`nx.list_datasets(q=, name=, description=, tags=, sort=, order=, favorite=)`|dataset 목록 검색|
|`nx.upload(paths, bucket, prefix="", workers=8, overwrite=False)` → {경로: CasRef}|파일 업로드. `overwrite=True`면 같은 key에 다른 내용이 있어도 에러 대신 덮어씀(SDK 0.1.4+)|
|`nx.probe(refs, workers=8, strict=False, max_header_bytes=65536)` → [CasRef]|업로드 없이 CAS 객체의 이미지 크기만 채움(앞부분만 읽음, 순서 보존)|
|`nx.image_info(data)` → ImageInfo(width, height, mime, channels)|로컬 bytes에서 헤더만 읽어 크기 판독|
|`nx.Sample(image=, annotation=, assets=, split=, tags=)`|샘플 정의|
|`nx.CasRef(bucket, key, hash_hex=, size=, content_type=, width=, height=)`|파일 참조|
|`nx.annotation_sessions(status=, dataset_id=, mine=, limit=)`|CVAT 편집 세션 목록(전역, 기본 진행 중인 것만)|
|`nx.annotation_session(session_id)`|세션 id로 다시 잡기|

### Dataset
|||
|---|---|
|`Dataset.load_or_create(name, version, tags=, description=, fork_from=, sample_ids=)`|dataset/버전 생성 또는 조회|
|`.add(sample)` / `.flush()`|	샘플 등록|
|`.list_samples()` / `.get_sample(id)`|	조회|
|`.samples(sample_ids=, group_key=, label=, confidence_min=, confidence_max=, track_id=, split=, tags=, meta=, include_annotations=True, limit=, after=)`|	조건 조회(기본 전체, limit=주면 한 페이지). `include_annotations=False`면 annotation 없는 경량 코어만|
|`.patch_annotations(sample_id, data)`|	annotation 수정|
|`.backfill_dims(workers=8, chunk_size=500, dry_run=False)` → dict|	`meta.width/height`가 빈 샘플을 실측값으로 보정(빈칸만 채움)|
|`.sample_history(sample_id)` / `.diff(against=)`|	이력 / 비교|
|`.link_samples(ids)` / `.unlink_samples(ids)` / `.import_samples(src_dataset, src_version, ids)`|	샘플 재사용|
|`.fork(new_version, sample_ids=, group_key=, label=, ...)`|	필터링된 fork(같은 dataset)|
|`.clone(new_name, new_version)`|	통째 복제|
|`.update(name=, description=)`|	이름/설명 수정|
|`.seal()`|	버전 확정|
|`.to_df(groups=, path=, format=, chunksize=)`|	DataFrame 변환|
|`.delete(confirm=, delete_cas=)`|	버전 삭제. `confirm`은 버전 문자열(또는 `True`). `delete_cas` 미지정 시 대화형으로 한 번 묻고, 비대화형이면 CAS 원본을 유지한다([4.3](#43-데이터셋-삭제-정책))|
|`.favorite()` / `.unfavorite()`|	즐겨찾기|
|`.create_annotation_session(sample_ids, groups=, extra_labels=, wait=True, timeout=600)`|	CVAT 편집 세션 생성|
|`.annotation_sessions(status=)`|	이 dataset·version의 세션 목록|

### AnnotationSession
|||
|---|---|
|`.status` / `.url` / `.session_id`|	상태 · CVAT 주소 · 식별자|
|`.dataset_name` / `.version` / `.sample_count`|	목록에서도 채워지는 표시용 값|
|`.warnings` / `.error`|	준비 중 스킵 사유 / `failed` 사유|
|`.has_unimported_changes`|	미반영 편집 여부(**`None` = 모름**)|
|`.wait_open(timeout=600, interval=3)`|	`open`이 될 때까지 대기|
|`.refresh()`|	서버에서 다시 읽어 상태 갱신|
|`.pull()`|	CVAT 결과를 draft에 반영(멱등) → 요약 dict|
|`.close(force=False)`|	작업 종료(CVAT project 보존)|
|`.delete()`|	세션 + CVAT project 완전 삭제(소유자만)|

### 그 외
|||
|---|---|
|`client.add_tags_bulk(sample_ids, tags)` / `.remove_tags_bulk(...)`|태그 일괄 처리|
|`client.change_password(current, new)`|본인 비밀번호 변경(현재 비밀번호 재확인)|
|`client.delete_account(password)` → dict|본인 계정 **완전 삭제** — 되돌릴 수 없다|
|`NexusError`, `NexusAuthError`, `NexusCasError`, `NexusIngestError`, `NexusBatchError`|	예외 타입(`.status_code`, `.server_message`)|
|`IngestResult(ok, sample, sample_id, error, status_code)`|	배치 처리 건별 결과|
