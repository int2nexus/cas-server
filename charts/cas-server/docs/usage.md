# CAS 시스템 사용 예시

---

## 설치 및 배포 (Kubernetes / Helm)
cas-server 는 helm 차트를 통해 k8s 환경에 배포할 수 있습니다. 

### 1. Helm 레포 추가
cas-server 레포지토리를 등록하고 업데이트합니다.

```bash
helm repo add int2cas https://int2nexus.github.io/cas-server
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

secrets:
  dbPassword: "DB_PASSWORD" # PostgreSQL 접근 비밀번호
  s3AccessKeyId: "ACCESS_KEY"  # 백엔드 오브젝트 스토리지의 Access Key
  s3SecretAccessKey: "SECRET_KEY" # 백엔드 오브젝트 스토리지의 Secret Key

# CAS 서버 자체 인증 및 권한(SigV4) 설정
auth:
  # DB 내부 시크릿 암호화용 마스터 키 (터미널에서 `openssl rand -hex 32`로 64자 Hex 생성)
  secretMasterKey: "b396646cf0890e7db6127732e0ac614f91e1e5b7441c336dabb65c711e3eb27f"   
  adminToken: "int2cas-admin-token" # Admin API 인증용 Bearer 토큰
  rootAccessKeyId: "int2cas-root" # 최고 관리자(Superuser) Access Key ID
  rootSecretKey: "int2cas-root-secret" # 최고 관리자(Superuser) Secret Key
```

### 3. Helm 차트 설치
작성한 values-prod.yaml 파일을 적용하여 지정한 네임스페이스에 서버를 배포합니다.
```bash
# 네임스페이스가 없는 경우 생성: kubectl create namespace <namespace>
helm install cas-server int2cas/cas-server -n <namespace> -f values-prod.yaml
```

### 4. 차트 업그레이드
설정을 변경하거나 새로운 버전의 차트로 업데이트할 때 실행합니다.

```bash
helm repo update
helm upgrade cas-server int2cas/cas-server -n <namespace> -f values-prod.yaml
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

`http://cas-server:8080/_ui` 에 rootkey로 로그인하여 접속하면 Dashboard 화면이 표시됩니다. 

![UI Dashboard](./images/ui-00-login.png)

<!-- 이미지: Dashboard 탭 전체 화면 -->
![UI Dashboard](./images/ui-01-dashboard.png)

### 2. Admin token 입력

상단 입력창에 `auth.adminToken` 값을 입력하고 확인하면 **GC 탭**과 **🔑 Keys 탭**이 활성화됩니다. Dashboard의 **Last GC** 섹션도 Admin Token이 있어야 표시됩니다.

<!-- 이미지: admin token 입력창 및 확인 버튼 -->
![Admin token 입력](./images/ui-02-admin-token.png)

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

---

## AWS CLI / boto3 사용법

### 사전 설정

서버 설정의 `root_access_key_id` / `root_secret_key`로 지정한 값을 사용합니다.

```bash
aws configure set aws_access_key_id     <root_access_key_id>
aws configure set aws_secret_access_key <root_secret_key>
aws configure set region                cas-default

CAS="http://cas-server:8080" 
```

> region은 반드시 `cas-default`로 설정해야 합니다.

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url="http://cas-server:8080",
    aws_access_key_id="<root_access_key_id>",
    aws_secret_access_key="<root_secret_key>",
    region_name="cas-default",
)
```

---

## Admin API로 키 관리

웹 UI 대신 curl로 직접 발급할 수도 있습니다. 모든 Admin API 요청에는 `Authorization: Bearer <admin_token>` 헤더가 필요합니다.

```bash
ADMIN_TOKEN="values-prod.yaml의 auth.adminToken 값"
CAS="http://cas-server:8080"

# 키 발급
curl -s -X POST $CAS/_admin/access-keys \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
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

> `secret_key`는 생성 시점인 이 응답에서 단 한 번만 평문으로 노출되며, 이후 DB에는 AES-256-GCM으로 안전하게 암호화되어 저장되므로 다시 조회할 수 없습니다. 반드시 안전한 곳에 즉시 저장해 두세요.

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

```bash
HASH=$(b3sum --no-names file.bin)
curl -X PUT "$CAS/my-bucket/path/to/file.bin" \
  -H "x-cas-hash: $HASH" \
  --data-binary @file.bin
```

boto3는 임의 커스텀 헤더를 지원하지 않으므로 (`Metadata`는 `x-amz-meta-*`로 변환됨) `requests`로 직접 전송합니다.

```python
import blake3
import requests

with open("file.bin", "rb") as f:
    data = f.read()

file_hash = blake3.blake3(data).hexdigest()

resp = requests.put(
    f"{CAS}/my-bucket/path/to/file.bin",
    data=data,
    headers={"x-cas-hash": file_hash},
)
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

```bash
curl -s -X POST http://localhost:8080/_internal/gc \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# dry_run: 실제 삭제 없이 대상만 집계
curl -s -X POST "http://localhost:8080/_internal/gc?dry_run=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

GC가 이미 실행 중이면 `409 GcAlreadyRunning`이 반환됩니다.

### GC 이력 조회

```bash
# 마지막 GC 결과
curl -s http://localhost:8080/_api/gc/last-result \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 최근 20건 이력
curl -s "http://localhost:8080/_api/gc/history?limit=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 고아 블롭 수
curl -s http://localhost:8080/_api/gc/orphan-count \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 메트릭 (Prometheus)

```bash
curl -s http://localhost:8080/_internal/metrics \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 블롭 dedup 사전 확인

업로드 전 BLAKE3 해시를 미리 확인하여 이미 존재하는 blob이면 물리 전송을 생략할 수 있습니다.

```bash
HASH=$(b3sum --no-names file.bin)

# 200 OK → 이미 존재 (업로드 생략 가능)
# 404    → 신규 업로드 필요
curl -sI http://localhost:8080/_api/blobs/$HASH
```