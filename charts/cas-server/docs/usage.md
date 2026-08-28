# CAS 시스템 사용 예시

---

## 설치 및 배포 (Kubernetes / Helm)
cas-server 는 helm 차트를 통해 k8s 환경에 배포할 수 있습니다.

### 1. Helm 레포 추가
cas-server 레포지토리를 등록하고 업데이트합니다.

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

### 2. values-prod.yaml 작성
운영 환경에 맞는 설정 값을 YAML 파일로 생성하여 기본 차트 설정을 오버라이드합니다.

```yaml
# values-prod.yaml

# 백엔드 오브젝트 스토리지 정보
storage:
  mode: "s3"
  s3:
    endpoint: "http://objectStorage.internal:9000"
    bucket: "cas-objects"
    region: "local"
    keyPrefix: "cas/"
    allowHttp: true # 내부망 등 TLS가 없는 오브젝트 스토리지 환경인 경우 true

# 메타데이터 관리를 위한 PostgreSQL 정보 (운영 환경에서는 외부 관리형 DB 권장)
externalDatabase:
  host: "postgres.internal"
  port: 5432
  username: "cas"
  database: "cas_metadata"

# 자격증명. useExternalSecret: false 로 두면 차트가 Secret 을 직접 만든다.
# 기본값은 true 이고, 그 경우 클러스터에 미리 만들어 둔 Secret(sealed-secret 등)을
# 참조하며 아래 값들은 읽히지 않는다 — 그 방식은 README 의
# "시크릿 (sealed-secret) 먼저 주입" 절을 따를 것.
secrets:
  useExternalSecret: false

  dbPassword: "DB_PASSWORD" # PostgreSQL 접근 비밀번호
  s3AccessKeyId: "ACCESS_KEY"  # 백엔드 오브젝트 스토리지의 Access Key
  s3SecretAccessKey: "SECRET_KEY" # 백엔드 오브젝트 스토리지의 Secret Key

  # DB 내부 시크릿 암호화용 마스터 키. 비우면 인증이 꺼진 NoAuth 모드로 뜬다.
  secretMasterKey: "<openssl rand -hex 32 의 출력(64자 Hex)>"
  rootAccessKeyId: "int2cas-root"             # 최고 관리자 Access Key ID. auth 를 켜면 필수
  rootSecretKey: "<최고 관리자 Secret Key>"    # auth 를 켜면 필수
  gcToken: "<GC CronJob 용 Bearer 토큰>"       # 비우면 GC 의 Bearer 경로가 닫힌다

# CAS 서버 인증 동작 설정.
auth:
  anonymousGet: true # GET/HEAD 를 인증 없이 허용. 신뢰 네트워크가 아니면 false
                     # (끄기 전에 cas_anonymous_get_total 을 볼 것 — 아래 메트릭 절)
  metricsToken: "<스크레이프용 Bearer 토큰>"  # GET /_internal/metrics 를 여는 유일한 수단
```

### 3. Helm 차트 설치
작성한 values-prod.yaml 파일을 적용하여 지정한 네임스페이스에 서버를 배포합니다.
```bash
# 네임스페이스가 없는 경우 생성: kubectl create namespace <namespace>
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

### 4. 차트 업그레이드
설정을 변경하거나 새로운 버전의 차트로 업데이트할 때 실행합니다.

```bash
helm repo update
helm upgrade cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

### 5. 리소스 제거
배포된 CAS 서버와 관련 리소스를 완전히 삭제합니다.

```bash
# Helm 릴리스 삭제
helm uninstall cas-server -n <namespace>
# (선택 사항) 네임스페이스 전체 삭제 시
kubectl delete namespace <namespace>
```

---

## 웹 UI로 키 관리 (`/_ui`)

API 호출 없이 브라우저에서 액세스 키를 발급하고 정책을 관리할 수 있습니다.

### 1. UI 접속

`/_ui` 에 root 키로 로그인하면 Dashboard 화면이 표시됩니다.

**경로는 `/_ui` 입니다. 뒤에 슬래시를 붙인 `/_ui/` 는 `404` 입니다.** 리버스 프록시나
Ingress 에서 경로를 재작성한다면 슬래시가 붙지 않게 하십시오.

브라우저에서 열려면 접근 경로를 하나 만들어야 합니다.

> **먼저 읽으십시오.** `/_api/*` 는 SigV4 인증을 요구합니다(이미지 `0.1.21` 이상).
> 콘솔 표면에서 무인증으로 열려 있는 것은 `/_ui` 와 `/_api/auth-mode` 둘뿐이고,
> `config.consoleEnabled: false` 로 콘솔 전체를 끌 수 있습니다. 그 밖에 무인증인 것은
> 프로브용 `/_internal/health` 와 `/_internal/live` 입니다.
> `auth.anonymousGet: true` 여도 예약 경로 넷
> (`_api`·`_ui`·`_internal`·`_admin`)은 익명 대상이 아닙니다 — 익명 허용은 데이터 평면
> `GET`/`HEAD /{bucket}/{key}` 뿐입니다.
>
> Service 기본값 `NodePort` 는 표면을 **클러스터의 모든 노드 x 30080** 으로 만들고, 파드가
> 없는 노드 IP 에서도 응답합니다. **신뢰 네트워크 밖이라면 `service.type: ClusterIP` 로 두고
> 포트포워드나 인증 프록시를 쓰십시오.** 차트 README 의 "노출 주의" 절에 자세히 적었습니다.

포트포워드가 가장 안전합니다. `NodePort` 를 그대로 쓰는 경우에는
`http://<노드IP>:30080/_ui` 입니다.

```bash
kubectl port-forward -n <namespace> svc/cas-server 8080:http
# http://localhost:8080/_ui
```

`ingress.enabled: true` 로 두셨다면 `https://<ingress.host>/_ui` 입니다.


![UI Dashboard](./images/ui-00-login.png)

<!-- 이미지: Dashboard 탭 전체 화면 -->
![UI Dashboard](./images/ui-01-dashboard.png)

### 2. 화면과 권한

**콘솔은 토큰을 받지 않습니다.** 화면은 로그인한 키의 SigV4 서명으로 열리고, 무엇을 보일지는
`GET /_api/whoami` 한 번으로 정합니다.

| 화면 | 필요한 권한 |
|---|---|
| Keys 탭 (목록) | `cas:ReadAccessKeys` 또는 `cas:ManageAccessKeys` |
| 키 발급 · revoke 버튼 | `cas:ManageAccessKeys` |
| GC 탭 · Dashboard 의 Last GC | `cas:ReadGc` 또는 `cas:RunGc` |
| GC 실행 · Dry-run 버튼 | `cas:RunGc` |

root 키는 전부 열립니다. 권한이 없는 화면은 탭이 표시되지 않습니다.

`secrets.gcToken` 과 `auth.metricsToken` 은 GC CronJob 과 스크레이프 용입니다 — 콘솔은
어느 쪽도 쓰지 않습니다.

### 3. 새 키 발급

Keys 탭에서 설명(description)과 선택적 만료일을 입력하고 발급 버튼을 클릭합니다. 만료일 설정이 없는 경우 영구 유효합니다.

<!-- 이미지: 키 발급 폼 (description 입력, 만료일 선택, 발급 버튼) -->
![새 키 발급](./images/ui-03-create-key.png)

발급 직후 `key_id`와 `secret_key`가 표시됩니다. **이 화면에서만 확인할 수 있으므로 반드시 복사해 두세요.**

<!-- 이미지: 발급 결과 (key_id, secret_key 표시) -->
![발급 결과](./images/ui-04-key-created.png)

### 4. 정책 추가

키 목록에서 해당 키의 정책 추가 폼에 effect / action / bucket / prefix 를 입력하고 추가합니다.

<!-- 이미지: 정책 추가 폼 및 적용된 정책 태그 목록 -->
![정책 추가](./images/ui-05-add-policy.png)

`action` 에 쓸 수 있는 이름과 `bucket`·`prefix` 가 걸리는 범위는 아래 "5. 액션 목록" 에
정리했습니다.

**root 키는 폐기할 수 없습니다** — `DELETE /_admin/access-keys/<root>` 는 `403` 입니다.
auth 를 켠 배포에서 root 는 필수 부트스트랩 신원이라, 비활성으로 만들면 관리 평면 접근 수단이
통째로 사라질 수 있기 때문입니다.

### 5. 액션 목록

정책에 쓸 수 있는 이름은 **아래 열다섯 개와 `"*"` 가 전부**입니다. 다른 문자열은 `400`
입니다 — `PutObjekt` 같은 오타가 아무것에도 걸리지 않는 정책이 되지 않게 하려는 것입니다.
`cas:*` 처럼 관리 액션에 와일드카드를 적는 것도 거절합니다.

| 평면 | 액션 |
|---|---|
| 데이터 | `ListBuckets` · `CreateBucket` · `DeleteBucket` · `ListObjects` |
| | `GetObject` · `PutObject` · `DeleteObject` |
| | `CreateMultipartUpload` · `UploadPart` · `CompleteMultipartUpload` · `AbortMultipartUpload` |
| 관리 | `cas:ReadAccessKeys` · `cas:ManageAccessKeys` · `cas:ReadGc` · `cas:RunGc` |

**`"*"` 는 데이터 평면 액션 열한 개에만 걸립니다.** 관리 액션 넷은 이름을 명시한 정책에만
붙습니다 — 그러지 않으면 `*` 로 발급된 키 전부가 키 발급·GC 실행 권한을 얻게 됩니다.

**넓은 쪽이 좁은 쪽을 포함합니다.** `cas:ManageAccessKeys` 만 준 키도 키 목록이 보이고,
`cas:RunGc` 만 준 키도 GC 조회가 됩니다. 거꾸로는 성립하지 않습니다 — `cas:ReadAccessKeys`
만 준 키는 발급·폐기를 못 하므로 감사·대조 전용 자격증명으로 쓸 수 있습니다.

#### 어떤 API 가 어느 액션으로 판정되는가

넷은 자기 이름의 액션이 없습니다(굵게). **인가를 건너뛰는 것이 아니라 다른 액션으로
판정되며, 그 판정은 요청 처리보다 먼저 일어납니다.**

| API | 요청 | 판정 액션 |
|---|---|---|
| `ListBuckets` | `GET /` | `ListBuckets` |
| `CreateBucket` | `PUT /{bucket}` | `CreateBucket` |
| **`PutBucketVersioning`** | `PUT /{bucket}?versioning` | `CreateBucket` |
| `DeleteBucket` | `DELETE /{bucket}` | `DeleteBucket` |
| `ListObjects(V2)` · `ListObjectVersions` | `GET /{bucket}` | `ListObjects` |
| **`ListMultipartUploads`** | `GET /{bucket}?uploads` | `ListObjects` |
| `GetObject` | `GET /{bucket}/{key}` | `GetObject` |
| **`HeadObject`** | `HEAD /{bucket}/{key}` | `GetObject` |
| `PutObject` | `PUT /{bucket}/{key}` | `PutObject` |
| **`CopyObject`** | `PUT` + `x-amz-copy-source` | `PutObject`(대상) **+** `GetObject`(소스) |
| `DeleteObject` | `DELETE /{bucket}/{key}` | `DeleteObject` |
| `CreateMultipartUpload` | `POST /{bucket}/{key}?uploads` | `CreateMultipartUpload` |
| `UploadPart` | `PUT ...?partNumber=&uploadId=` | `UploadPart` |
| `CompleteMultipartUpload` | `POST ...?uploadId=` | `CompleteMultipartUpload` |
| `AbortMultipartUpload` | `DELETE ...?uploadId=` | `AbortMultipartUpload` |
| Presigned URL | `GET` · `PUT` · `DELETE` | 각각 `GetObject` · `PutObject` · `DeleteObject` |

**`GetObject` 만 부여한 키는 `CopyObject` 로 쓸 수 없습니다** — 대상에 `PutObject` 가
필요합니다. 버저닝도 바꿀 수 없고(`CreateBucket` 필요) 멀티파트 목록도 볼 수
없습니다(`ListObjects` 필요). 그런 키는 읽기 전용으로 운용하셔도 됩니다.

#### `bucket` · `prefix` 가 걸리는 깊이

액션마다 다릅니다. 정책을 좁힐 때 여기서 어긋납니다.

| 대상 | 해당 액션 | `bucket` | `prefix` |
|---|---|---|---|
| 서비스 | `ListBuckets` | **`"*"` 여야만 통과** | 보지 않음 |
| 버킷 | `CreateBucket` · `DeleteBucket` · `ListObjects` | 이름 일치 또는 `"*"` | **보지 않음** |
| 오브젝트 | 나머지 전부 | 이름 일치 또는 `"*"` | `key` 의 접두사 또는 `"*"` |
| 관리 | 관리 액션 4개 | 보지 않음 | 보지 않음 |

조용히 어긋나는 자리가 둘입니다.

- **`ListBuckets` 는 버킷을 지정한 정책으로 열리지 않습니다.** 버킷 목록은 특정 버킷의
  자원이 아니므로 `bucket: "images"` 정책이 걸리지 않습니다. 버킷 목록이 필요한 소비자에게는
  `{"action": "ListBuckets", "bucket": "*"}` 를 따로 주십시오.
- **`ListObjects` 에는 `prefix` 가 걸리지 않습니다.**
  `{"action": "ListObjects", "bucket": "images", "prefix": "upload/"}` 로 발급해도 그 키는
  `images` 버킷 **전체**를 나열합니다. prefix 로 좁혀지는 것은 오브젝트 액션뿐입니다.
  목록을 실제로 가리려면 버킷을 나누셔야 합니다.

---

## AWS CLI / boto3 사용법

### 사전 설정

서버 설정의 `root_access_key_id` / `root_secret_key`로 지정한 값을 사용합니다.

```bash
aws configure set aws_access_key_id     <root_access_key_id>
aws configure set aws_secret_access_key <root_secret_key>
aws configure set region                cas-default

CAS="http://cas-server:80"
```

> region 은 아무 값이나 됩니다. 서버가 클라이언트의 선언 값으로 서명 키를 유도하므로,
> 지정하지 않아 SDK 기본값(boto3 는 `us-east-1`)이 들어가도 그대로 동작합니다.
> 예시의 `cas-default` 는 관례일 뿐입니다.

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="http://cas-server:80",
    aws_access_key_id="<root_access_key_id>",
    aws_secret_access_key="<root_secret_key>",
    region_name="cas-default",   # 임의 값 가능. 생략하면 boto3 기본값이 쓰이고 그것도 동작합니다
)
```

---

## Admin API로 키 관리

웹 UI 대신 명령줄로 직접 발급할 수도 있습니다. `/_admin/*` 을 여는 자격증명은 **SigV4
신원 둘뿐입니다.** Bearer 토큰으로 열리는 경로가 없으므로 `gcToken` 으로도 열리지 않습니다.

| 자격증명 | 필요한 것 |
|---|---|
| root 키 | 관리 평면 전권. 조작이 `key_id=<root>` 로 기록됨 |
| 관리 정책 키 | 발급·폐기·정책 변경은 `cas:ManageAccessKeys`, 조회는 `cas:ReadAccessKeys` 또는 `cas:ManageAccessKeys`. 조작이 그 `key_id` 로 기록됨 |

**서명을 손으로 만들지 말고 서명 도구를 쓰십시오.** 아래는
[`awscurl`](https://github.com/okigan/awscurl) 예시입니다 — `--service` 는 `s3`,
`--region` 은 아무 값이나 됩니다.

```bash
# 키 발급 — root 키 또는 cas:ManageAccessKeys 를 가진 키로 서명
awscurl --service s3 --region cas-default \
  --access_key "$KEY_ID" --secret_key "$SECRET" \
  -X POST "$CAS/_admin/access-keys" \
  -H "Content-Type: application/json" \
  -d '{"description": "my-service-key"}'
```

```json
{
  "key_id": "CASKa1b2c3...",
  "secret_key": "sk-deadbeef...",
  "created_at": "2026-05-18T00:00:00Z"
}
```

> `secret_key` 는 이 응답에서 한 번만 평문으로 나옵니다. DB 에는 AES-256-GCM 으로 암호화해
> 저장하므로 다시 조회할 수 없습니다. 즉시 안전한 곳에 옮겨 두십시오.

조회·정책 변경 등 나머지 `/_admin/*` 호출과 각 응답의 계약(`?active=` 필터, 폐기된 키의
단건 조회, 시각 형식)은 차트 README 의 "관리 API 자격증명" 절에 있습니다.

`/_admin/*` 은 **auth 를 켠 배포에만 존재합니다.** NoAuth 배포에는 액세스 키라는 개념이
없어 이 경로가 마운트되지 않습니다.

---

## 버킷

### 버킷 목록 조회

```bash
aws s3api list-buckets --endpoint-url $CAS
```

```python
resp = s3.list_buckets()
for b in resp["Buckets"]:
    print(b["Name"], b["CreationDate"])
```

### 버킷 생성

```bash
aws s3api create-bucket --bucket my-bucket --endpoint-url $CAS
```

```python
s3.create_bucket(Bucket="my-bucket")
```

### 버킷 삭제

```bash
aws s3api delete-bucket --bucket my-bucket --endpoint-url $CAS
```

```python
s3.delete_bucket(Bucket="my-bucket")
```

### 오브젝트 목록 조회

```bash
aws s3api list-objects-v2 --bucket my-bucket --endpoint-url $CAS

# 접두사 필터
aws s3api list-objects-v2 --bucket my-bucket --prefix logs/ --endpoint-url $CAS
```

```python
resp = s3.list_objects_v2(Bucket="my-bucket", Prefix="logs/")
for obj in resp.get("Contents", []):
    print(obj["Key"], obj["Size"])
```

`--max-keys 0` 은 빈 목록을 돌려줍니다 — `IsTruncated` 는 `false` 이고 이어받을 커서도
없습니다. 0건을 요청했으므로 「더 있음」 을 참으로 두지 않습니다. 콘솔 API
`GET /_api/buckets/{bucket}/objects` 의 `limit=0` 도 같습니다(`has_more: false`,
`next_after: null`).

---

## 오브젝트

### 업로드

```bash
aws s3api put-object \
    --bucket my-bucket \
    --key path/to/file.bin \
    --body ./file.bin \
    --endpoint-url $CAS

# aws s3 cp 도 동일하게 동작
aws s3 cp ./file.bin s3://my-bucket/path/to/file.bin --endpoint-url $CAS
```

```python
# 파일 업로드
s3.upload_file("file.bin", "my-bucket", "path/to/file.bin")

# 바이트 직접 업로드
s3.put_object(
    Bucket="my-bucket",
    Key="path/to/file.bin",
    Body=b"hello world",
    ContentType="text/plain",
)
```

dedup 여부는 응답 헤더 `x-cas-already-existed`로 확인할 수 있습니다.

```python
resp = s3.put_object(
    Bucket="my-bucket",
    Key="path/to/file.bin",
    Body=open("file.bin", "rb"),
)
print(resp["ResponseMetadata"]["HTTPHeaders"].get("x-cas-already-existed"))
# "true"  → 동일 파일이 이미 존재 (디스크 저장 생략됨)
# "false" → 신규 저장
```

### 업로드 최적화 — x-cas-hash 헤더

파일의 BLAKE3 hash를 미리 알고 있는 경우 `x-cas-hash` 헤더로 전달하면,
중복 파일일 때 body를 전송하지 않고 즉시 완료됩니다.

이것도 평범한 `PutObject` 입니다 — **`auth.anonymousGet` 은 `GET`/`HEAD` 에만 걸리므로 이
요청은 서명해야 합니다.** `curl` 은 `--aws-sigv4` 로 직접 서명할 수 있습니다(curl `7.75`
이상).

```bash
HASH=$(b3sum --no-names file.bin)

curl -X PUT "$CAS/my-bucket/path/to/file.bin" \
  --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  -H "x-cas-hash: $HASH" \
  --data-binary @file.bin
```

boto3 는 `put_object` 인자로 임의 헤더를 받지 않습니다 (`Metadata` 는 `x-amz-meta-*` 로
변환됩니다). 서명 직전 이벤트에 훅을 걸어 헤더를 넣습니다.

```python
import blake3

with open("file.bin", "rb") as f:
    data = f.read()

file_hash = blake3.blake3(data).hexdigest()

def add_cas_hash(request, **kwargs):
    request.headers.add_header("x-cas-hash", file_hash)

s3.meta.events.register_first("before-sign.s3.PutObject", add_cas_hash)
s3.put_object(Bucket="my-bucket", Key="path/to/file.bin", Body=data)
s3.meta.events.unregister("before-sign.s3.PutObject", add_cas_hash)
```

### 다운로드

```bash
aws s3api get-object \
    --bucket my-bucket \
    --key path/to/file.bin \
    output.bin \
    --endpoint-url $CAS

# aws s3 cp 도 동일하게 동작
aws s3 cp s3://my-bucket/path/to/file.bin ./output.bin --endpoint-url $CAS
```

```python
# 파일로 저장
s3.download_file("my-bucket", "path/to/file.bin", "output.bin")

# 메모리로 읽기
resp = s3.get_object(Bucket="my-bucket", Key="path/to/file.bin")
data = resp["Body"].read()
```

### Range 다운로드 (부분 다운로드)

```bash
aws s3api get-object \
    --bucket my-bucket \
    --key path/to/file.bin \
    --range "bytes=0-1023" \
    output_part.bin \
    --endpoint-url $CAS
```

```python
resp = s3.get_object(
    Bucket="my-bucket",
    Key="path/to/file.bin",
    Range="bytes=0-1023",
)
chunk = resp["Body"].read()  # 1024 bytes
```

### 메타데이터 조회

```bash
aws s3api head-object \
    --bucket my-bucket \
    --key path/to/file.bin \
    --endpoint-url $CAS
```

```python
resp = s3.head_object(Bucket="my-bucket", Key="path/to/file.bin")
print(resp["ContentLength"])
print(resp["ETag"])          # BLAKE3 hash (double-quoted)
```

### 복사 (zero-copy)

blob 파일 이동 없이 메타데이터만 추가됩니다.

```bash
aws s3api copy-object \
    --bucket dst-bucket \
    --key new/path/file.bin \
    --copy-source my-bucket/path/to/file.bin \
    --endpoint-url $CAS
```

```python
s3.copy_object(
    Bucket="dst-bucket",
    Key="new/path/file.bin",
    CopySource={"Bucket": "my-bucket", "Key": "path/to/file.bin"},
)
```

### 삭제

```bash
aws s3api delete-object \
    --bucket my-bucket \
    --key path/to/file.bin \
    --endpoint-url $CAS
```

```python
s3.delete_object(Bucket="my-bucket", Key="path/to/file.bin")
```

> 삭제는 소프트 삭제(soft-delete)입니다. 물리 파일은 GC 실행 시 제거됩니다.

---

## Presigned URL

인증 없이 일시적으로 접근 가능한 URL을 생성합니다.

```bash
# 기본값 3600초, --expires-in으로 조정 가능
aws s3 presign s3://my-bucket/path/to/file.bin \
    --endpoint-url $CAS \
    --expires-in 300
```

```python
url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": "my-bucket", "Key": "path/to/file.bin"},
    ExpiresIn=300,
)
print(url)

# 생성된 URL은 인증 없이 접근 가능
import requests
resp = requests.get(url)
```

---

## 멀티파트 업로드

boto3는 `upload_file` / `upload_fileobj`가 파일 크기에 따라 자동으로 멀티파트를 사용합니다 (기본 임계값 8 MiB).

```python
from boto3.s3.transfer import TransferConfig

config = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,   # 8 MiB 이상이면 멀티파트
    multipart_chunksize=8 * 1024 * 1024,   # 파트 크기
)

s3.upload_file(
    "large_file.bin",
    "my-bucket",
    "large_file.bin",
    Config=config,
)
```

수동으로 제어할 경우:

```python
# 1. 시작
resp = s3.create_multipart_upload(Bucket="my-bucket", Key="large.bin")
upload_id = resp["UploadId"]

parts = []
try:
    # 2. 파트 업로드
    for i, chunk in enumerate(read_chunks("large.bin"), start=1):
        part = s3.upload_part(
            Bucket="my-bucket",
            Key="large.bin",
            UploadId=upload_id,
            PartNumber=i,
            Body=chunk,
        )
        parts.append({"PartNumber": i, "ETag": part["ETag"]})

    # 3. 완료
    s3.complete_multipart_upload(
        Bucket="my-bucket",
        Key="large.bin",
        UploadId=upload_id,
        MultipartUpload={"Parts": parts},
    )
except Exception:
    # 4. 실패 시 취소
    s3.abort_multipart_upload(
        Bucket="my-bucket", Key="large.bin", UploadId=upload_id
    )
    raise
```

```python
def read_chunks(path, size=8 * 1024 * 1024):
    with open(path, "rb") as f:
        while chunk := f.read(size):
            yield chunk
```

---

## aws s3 sync

```bash
# 로컬 디렉토리 → 버킷 동기화
aws s3 sync ./data s3://my-bucket/data/ --endpoint-url $CAS

# 버킷 → 로컬 디렉토리
aws s3 sync s3://my-bucket/data/ ./data --endpoint-url $CAS
```

---

## 내부 API

### 헬스체크

인증 없이 접근 가능합니다.

```bash
curl http://localhost:8080/_internal/health
```

### GC 수동 트리거

GC 경로(`POST /_internal/gc`, `GET /_api/gc/*`)를 여는 자격증명은 둘입니다.

| 자격증명 | 형태 | 비고 |
|---|---|---|
| `secrets.gcToken` | `Authorization: Bearer <gc_token>` | GC 전용. `/_admin/*`·메트릭은 열리지 않음 |
| `cas:RunGc` · `cas:ReadGc` 정책 키 (또는 root) | SigV4 서명 | 조작이 `key_id` 로 기록됨 |

GC CronJob 처럼 blob 회수만 필요한 주체에는 `gcToken` 을 주십시오. Secret 의 `auth-gc-token`
키에 값이 있는지가 그대로 스위치이고, 서버와 CronJob 이 같은 키를 읽습니다.

```bash
# GC 전용 토큰 (권장)
curl -s -X POST http://localhost:8080/_internal/gc \
  -H "Authorization: Bearer $GC_TOKEN"

# 또는 cas:RunGc 를 가진 키 / root 키의 SigV4 서명
curl -s -X POST --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  http://localhost:8080/_internal/gc

# dry_run: 실제 삭제 없이 대상만 집계
curl -s -X POST --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  "http://localhost:8080/_internal/gc?dry_run=true"
```

조회(`GET /_api/gc/*`)에는 `cas:ReadGc` 로 충분하고, 실행에는 `cas:RunGc` 가 필요합니다.

GC가 이미 실행 중이면 `409 GcAlreadyRunning`이 반환됩니다.

#### 단계를 나눠 실행하기

> 이미지 `0.1.20` 이상이 필요합니다. 그 이하는 `phases` 를 무시하고 세 단계를 모두
> 실행합니다 — 요청은 성공하므로 로그의 `phases` 필드로 적용 여부를 확인하십시오.

GC는 세 단계로 나뉘며 비용이 크게 다릅니다. 아래는 blobs 200만 / object_versions 358만
환경에서 GC를 실제로 돌려 완료 로그의 `ms_*` 필드로 받은 값입니다.

| 단계 | 하는 일 | `ms_*` |
|---|---|---|
| `multipart` | 만료된 미완료 멀티파트 업로드의 파트 회수 | 2~5 |
| `orphan` | 참조가 사라진 blob 물리 삭제 | **13,729** |
| `purge` | 보존 기간이 지난 soft-delete 레코드 삭제 | 213~319 |

`multipart,purge` 편성은 324 ms, 전 단계는 13.9초가 걸렸습니다 — 43배 차이입니다.

`orphan`만 blob 테이블 전체를 훑기 때문에 데이터가 늘어나는 만큼 실행 시간이 함께
늘어납니다. 나머지 두 단계는 인덱스로 처리되어 규모의 영향을 받지 않습니다.

`phases` 파라미터로 이번 실행에서 돌 단계를 고를 수 있습니다. 생략하면 세 단계 모두
실행합니다.

```bash
# 주간 작업: 저렴한 단계만
curl -s -X POST "http://localhost:8080/_internal/gc?phases=multipart,purge" \
  -H "Authorization: Bearer $GC_TOKEN"

# 월간 작업: 전체
curl -s -X POST http://localhost:8080/_internal/gc \
  -H "Authorization: Bearer $GC_TOKEN"
```

`orphan`을 미루면 회수가 그만큼 늦어질 뿐 데이터가 사라지지는 않습니다. 회수 대상 blob은
다음 스캔까지 디스크에 남아 있으므로, 주기를 늘린 만큼 용량 여유를 두고 잡으십시오.

##### 주기를 정하는 기준

**스캔 비용은 회수 대상 개수와 무관합니다.** 회수할 blob이 0건이어도 4건이어도 테이블
전체를 훑는 시간은 같습니다. 그래서 주기는 데이터 크기가 아니라 **회수 대상이 쌓이는
속도**로 정하는 것이 맞습니다.

회수 대상 blob은 마지막 참조가 사라질 때 생깁니다 — 객체 삭제, 그리고 같은 키를 다른
내용으로 덮어쓰는 경우입니다. **삭제와 덮어쓰기가 드문 환경이라면 자주 훑을 이유가
없습니다.** 매주 몇 분을 들여 몇 건을 회수하는 것보다, 한 달에 한 번 같은 시간을 들여
같은 몇 건을 회수하는 편이 낫습니다.

과거 실행 이력으로 판단하십시오.

```bash
curl -s "http://localhost:8080/_api/gc/history" -H "Authorization: Bearer $GC_TOKEN"
```

`deleted_blobs`가 매번 한 자릿수라면 전수 스캔을 그 빈도로 돌릴 이유가 없습니다. 월 1회
또는 분기 1회로 늦추십시오. 반대로 매번 수천 건씩 회수되고 있다면 지금 주기를 유지하는
편이 낫습니다 — 미룬 만큼 디스크에 남습니다.

미루는 비용은 이렇게 어림합니다.

```
남아 있을 용량 = (한 주기당 평균 deleted_blobs) x (평균 blob 크기) x (늘린 배수)
```

주당 4건, blob 하나가 5 MB, 주 1회를 월 1회로 늦춘다면 약 80 MB가 더 남아 있게 됩니다.
이 값이 용량 여유에 비해 작다면 늦추는 편이 이득입니다.

> `dry_run=true`로 회수 대상 수를 먼저 확인하는 방법은 이 판단에 쓰지 마십시오.
> 그 조회도 같은 전수 스캔을 돕니다 — 알아보려고 비용을 그대로 치르게 됩니다.
> 이미 지나간 실행 이력을 보는 편이 공짜입니다.

정의되지 않은 단계 이름은 `400`으로 거절합니다. 조용히 무시하면 오타 하나로 의도한
단계가 빠진 채 성공한 것처럼 보이기 때문입니다.

실행된 단계는 완료 로그의 `phases` 필드에 남습니다. `deleted_blobs=0`이 회수할 대상이
없어서인지 해당 단계를 돌리지 않아서인지 이 필드로 구분할 수 있습니다.

Helm으로 배포하셨다면 `gc.phases`와 `gc.fullSweep`으로 두 개의 CronJob을 나눌 수 있습니다.
설정 방법은 차트 README의 "GC가 오래 걸린다면 단계를 나누십시오"를 참고하십시오.

#### `GET /_api/whoami`

호출한 자격증명이 관리 평면에서 무엇을 할 수 있는지 돌려줍니다. 콘솔이 화면을 구성하는
근거이고, 서버 인가 미들웨어와 같은 판정기로 계산합니다.

```bash
curl -s --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  "http://localhost:8080/_api/whoami"
```

```json
{
  "key_id": "CASKroot",
  "is_root": true,
  "can": {
    "read_access_keys": true,
    "manage_access_keys": true,
    "read_gc": true,
    "run_gc": true
  }
}
```

**각 값은 정책 원장이 아니라 실제로 열리는 것을 답합니다.** 위 "액션 목록" 절의 포함 관계가
그대로 반영되므로, `cas:ManageAccessKeys` 만 가진 키도 `read_access_keys` 가 `true` 이고
`cas:RunGc` 만 가진 키도 `read_gc` 가 `true` 입니다.

`action: "*"` 정책은 관리 평면에 걸리지 않으므로 그런 키는 넷 다 `false` 입니다.

#### `GET /_api/config-effective`

지금 이 프로세스에 적용된 설정을 돌려줍니다. 기동 첫 줄 로그와 같은 내용이지만, **로그 보존
창이 짧은 배포에서는 그 줄을 나중에 볼 수 없습니다.** 차트 렌더 결과가 아니라 프로세스가 읽은
값이라 `extraEnv` 오버라이드도 여기 드러납니다.

```bash
curl -s --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  "http://localhost:8080/_api/config-effective"
```

아래는 발췌입니다 — 실제 응답에는 `config.*` 로 넘긴 값이 전부 들어 있습니다.

```json
{
  "db_url": "postgresql://postgres:***@pg/cas",
  "multipart_ttl_secs": 86400,
  "console_enabled": true,
  "auth": { "secret_master_key": "<set>", "metrics_token": "<set>",
            "gc_token": "<set>", "anonymous_get": true },
  "storage_backends": [
    { "id": "s3-1", "backend_type": "s3", "endpoint": null,
      "access_key_id": "<set>", "secret_access_key": "<set>" }
  ]
}
```

**자격증명은 값으로 나가지 않습니다.** `<set>`/`<unset>` 만 나가고, `db_url` 의 비밀번호는
가려집니다.

**백엔드 스토리지 주소(`endpoint`)는 관리 주체에게만 채웁니다** — root 키 또는
`cas:ManageAccessKeys` 를 가진 키. `/_api/backends` 와 같은 기준이고, 그 밖의 키에는
`null` 로 나갑니다.

이미지 `0.1.21` 이상입니다.

### 미완료 멀티파트 만료 기준

GC가 미완료 멀티파트 업로드를 만료로 보는 기준은 `config.multipartTtlSecs`(기본 86400초 =
24시간)입니다. 이미지 `0.1.20` 이상에서만 동작하며, 그 이하는 24시간 고정입니다.

파트 정리 경로가 실제로 도는지 확인하려면 업로드를 만들고 중단한 뒤 만료를 기다려야 하는데,
24시간이면 GC 주기까지 더해 확인에 한 주가 걸립니다. **시험 환경에서** 이 값을 몇 분으로
줄이면 즉시 판정할 수 있습니다.

> **운영에서는 줄이지 마십시오.** 진행 중인 업로드의 파트가 조립 전에 회수되면 그 업로드가
> `5xx`로 실패합니다. 큰 파일을 올리는 클라이언트가 먼저 깨집니다.

### 웹 콘솔 끄기

콘솔(`/_ui`)과 그 조회 API(`/_api/*`)를 쓰지 않는다면 `config.consoleEnabled: false`로
아예 마운트하지 않을 수 있습니다. 이미지 `0.1.20` 이상에서만 동작합니다.

인증을 거는 것보다 표면 자체를 없애는 편이 확실합니다 — 특히 서비스가 `NodePort`로
노드 IP에 직접 열려 있는 경우입니다.

끄면 `/_ui`, `/_api/auth-mode`, `/_api/stats`, `/_api/buckets`, `/_api/backends`,
`/_api/blobs/{hash}`, `/_api/whoami`, `/_api/config-effective` 에 핸들러가 붙지 않습니다.
응답 코드는 인증 설정에 따라 갈립니다 —
인증이 꺼져 있으면 `404`, 켜져 있으면 인증 미들웨어가 라우팅보다 먼저 걸러 `403`입니다.
**어느 쪽이든 유효한 자격증명으로도 응답하지 않습니다.**

`/_api/gc/*`와 `/_internal/*`은 별도 라우터에 있어 남으므로 **GC CronJob은 그대로
동작합니다.**

### GC 이력 조회

```bash
# 마지막 GC 결과
curl -s http://localhost:8080/_api/gc/last-result \
  -H "Authorization: Bearer $GC_TOKEN"

# 이력. limit 은 기본 20, 상한 90 입니다. 오프셋·커서는 없으므로
# 90 건을 넘는 이력은 이 API 로 뜰 수 없습니다.
curl -s "http://localhost:8080/_api/gc/history?limit=90" \
  -H "Authorization: Bearer $GC_TOKEN"

# 고아 블롭 수
curl -s http://localhost:8080/_api/gc/orphan-count \
  -H "Authorization: Bearer $GC_TOKEN"
```

### 메트릭 (Prometheus)

```bash
curl -s http://localhost:8080/_internal/metrics \
  -H "Authorization: Bearer $METRICS_TOKEN"
```

**이 경로를 여는 것은 `auth.metricsToken` 하나입니다.** 이 토큰은 이 엔드포인트에서만
통하고 다른 어떤 경로도 열지 않으므로, 모니터링 스택에 배포해도 넘어가는 권한이 없습니다.

**이 경로에는 SigV4 분기가 없습니다.** 액세스 키로는 열리지 않고 root 키로도 `401`입니다.
관리 평면에서 유일한 예외입니다.

**`metricsToken` 이 비면** auth 를 켠 배포에서는 `/_admin/*`·GC 와 같이 `401` 로 닫히고
(이미지 `0.1.24` 이상), NoAuth 배포에서는 무인증으로 열립니다. 후자는 기동 시 경고가 뜹니다.

**노출되는 지표는 `cas_*` 13종입니다.** 타입·단위와 각 값이 무엇을 보는지(특히
`cas_db_pool_*` 가 어느 풀을 보고하는지)는 차트 README 의 "메트릭 스크레이프" 절에 표로
정리했습니다. `cas_anonymous_get_total` 하나만 라벨(`reason`)을 답니다. 같은 엔드포인트에
`axum_http_*` 3종이 함께 나오고 이쪽은 라벨을 답니다.

먼저 볼 값 셋만 여기 적습니다.

| 지표 | 정상 | 어긋나면 |
|---|---|---|
| `cas_blob_lock_map_entries` | **유휴 시 `0`** | 0으로 안 떨어지면 항목 회수가 동작하지 않는 것입니다 |
| `cas_db_pool_idle_connections` | 부하 중에도 `0` 이 지속되지 않음 | `connections` 가 max 인데 `idle` 이 0 으로 지속되면 풀 포화입니다 |
| `cas_db_pool_acquire_timeouts_total` | 증가하지 않음 | 증가하면 포화가 실제 실패로 이어진 것입니다(`503`) |

#### `anonymousGet` 을 끄기 전에 — `cas_anonymous_get_total`

`auth.anonymousGet: true` 인 동안 익명으로 통과한 읽기를 `reason` 라벨로 셉니다(이미지
`0.1.24` 이상). 세 값 모두 지금은 `200` 이고, 이 계수가 판정을 바꾸지는 않습니다.

| `reason` | 요청 | `anonymousGet: false` 로 내리면 |
|---|---|---|
| `unsigned` | 서명이 없음 | `403` |
| `signed_valid` | 유효한 키로 서명함 | 그대로 통과 (정책에 `GetObject` 가 있어야 함) |
| `signed_invalid` | 서명이 있으나 검증 실패 | `403` |

`unsigned` 와 `signed_invalid` 가 끄는 순간 깨질 소비자입니다. **둘 다 늘지 않는 기간을
확인한 뒤에 내리십시오.** `false` 로 두면 이 카운터는 늘지 않습니다.

### 스크레이프 배선

**Prometheus Operator 가 있으면** `ServiceMonitor` 를, **없으면** `scrape_configs` 를 직접
씁니다. `ServiceMonitor` 오브젝트는 Operator 가 없으면 CRD 가 있어도 아무 일도 하지 않습니다.
양쪽 예시와 토큰 파일 마운트 방법은 차트 README 의 "메트릭 스크레이프" 절에 있습니다.

배선할 때 틀리기 쉬운 값 셋입니다.

- 포트는 **이름이 `http`** 입니다(`metrics` 가 아니고, 숫자 `8080` 도 아닙니다).
- 경로는 `/_internal/metrics` 입니다.
- Secret 은 네임스페이스 자원이라 **Prometheus 쪽 네임스페이스에 복사본이 필요합니다.**
  키 이름은 `auth-metrics-token` 입니다.

### 블롭 dedup 사전 확인

업로드 전 BLAKE3 해시를 미리 확인하여 이미 존재하는 blob이면 물리 전송을 생략할 수 있습니다.

`/_api/blobs/{hash}` 는 콘솔 경로라 **유효한 키의 SigV4 서명이 필요합니다.** 대응하는 정책
액션은 없으므로 데이터 전용 키로도 열립니다. `config.consoleEnabled: false` 인 배포에는 이
경로가 없습니다.

```bash
HASH=$(b3sum --no-names file.bin)

# 200 OK → 이미 존재 (업로드 생략 가능)
# 404    → 신규 업로드 필요
curl -sI --aws-sigv4 "aws:amz:cas-default:s3" --user "$KEY_ID:$SECRET" \
  "http://localhost:8080/_api/blobs/$HASH"
```

`HEAD` 는 존재 여부만 돌려주고, 같은 경로의 `GET` 은 blob 상세를 JSON 으로 돌려줍니다.