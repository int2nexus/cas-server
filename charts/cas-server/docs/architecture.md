# CAS Server 시스템 기능 명세서

<!-- ## 목차

1. [개요](#1-개요)
2. [스토리지 모델](#2-스토리지-모델)
3. [파일 생명주기](#3-파일-생명주기)
4. [스토리지 백엔드](#4-스토리지-백엔드)
5. [API 사용 가이드](#5-api-사용-가이드)
6. [에러 코드 및 대응](#6-에러-코드-및-대응)
7. [부록: 대용량 파일 업로드 (멀티파트)](#7-부록-대용량-파일-업로드-멀티파트) -->

## 1. 개요

### 1.1 시스템 소개

CAS Server는 **Content-Addressable Storage(내용 기반 주소 지정 스토리지)** 방식의 파일 스토리지 서버입니다.

파일을 이름이 아닌 **내용의 해시값**으로 식별하고, 동일한 파일은 물리적으로 단 한 번만 저장합니다. S3 호환 API를 제공하므로 기존 AWS S3 SDK·CLI를 그대로 사용할 수 있습니다.

### 1.2 핵심 특징

| 특징 | 설명 |
|------|------|
| **자동 중복 제거** | 동일 내용의 파일은 백엔드에 한 번만 저장 — 스토리지 용량 절약 |
| **콘텐츠 무결성 보장** | BLAKE3 해시로 업로드·다운로드 시 파일 손상 여부 검증 |
| **S3 호환 API** | AWS CLI, SDK, 기존 S3 연동 코드 그대로 사용 가능 |
| **다중 백엔드 지원** | 로컬 NAS 또는 S3 호환 오브젝트 스토리지를 백엔드로 사용 |
| **Zero-copy 복사** | 파일 복사 시 물리적 데이터 이동 없이 즉시 완료 |

### 1.3 전체 구성도

![전체 구성도](./images/system_spec.png)

### 1.4 용어 정의

| 용어 | 설명 |
|------|------|
| **버킷(Bucket)** | 파일을 담는 논리적 컨테이너. S3의 버킷과 동일한 개념 |
| **오브젝트(Object)** | 버킷 안의 개별 파일 항목. 키(경로 문자열)로 식별 |
| **키(Key)** | 오브젝트의 경로 식별자 (예: `images/2026/photo.jpg`) |
| **해시(Hash)** | 파일 내용을 BLAKE3 알고리즘으로 계산한 64자 16진수 문자열 |
| **블롭(Blob)** | 해시에 대응하는 실제 물리 파일. 백엔드 스토리지에 저장됨 |
| **백엔드(Backend)** | 블롭이 실제로 저장되는 물리 스토리지 (NAS 또는 S3 호환) |
| **GC(Garbage Collection)** | 삭제된 오브젝트의 블롭을 물리적으로 정리하는 주기적 작업 |

---

## 2. 스토리지 모델

### 2.1 콘텐츠 주소 저장 방식 (CAS)

일반적인 파일 스토리지는 경로(버킷 + 키)를 기준으로 파일을 저장합니다. CAS Server는 여기에 더해 **파일 내용 자체를 해시로 식별**합니다.

```
버킷: images
키:   2026/photo.jpg
해시: a3f8d2c1e7b946... (파일 내용의 BLAKE3 해시, 64자)
       └─ 실제 블롭 파일과 1:1 대응
```

- 경로(키)는 논리적 식별자이며, 물리 저장은 해시 단위로 관리됩니다.
- 같은 파일을 서로 다른 키로 올려도 블롭은 하나만 존재합니다.
- 업로드 직후 `ETag` 헤더로 해시값이 반환되므로, 클라이언트에서 무결성을 검증할 수 있습니다.


### 2.2 중복 제거 (Dedup)

동일한 내용의 파일은 물리적으로 **단 한 번만** 저장됩니다.

```
업로드 흐름:
  1. 파일 내용 → BLAKE3 해시 계산
  2. 해당 해시의 블롭이 이미 존재하는지 확인
  3a. 존재하면 → 물리 저장 없이 메타데이터만 추가  (x-cas-already-existed: true)
  3b. 없으면   → 백엔드에 블롭 저장 후 메타데이터 추가 (x-cas-already-existed: false)
```

**효과**:
- 동일 파일이 여러 버킷·키에 등록돼도 스토리지 공간을 추가로 소비하지 않습니다.
- 이미 알려진 해시는 업로드 시 `x-cas-hash` 헤더로 전달하면 물리 전송 자체를 생략할 수 있습니다.

### 2.3 버킷과 오브젝트 구조

버킷·오브젝트·키는 모두 **논리적 식별자**입니다. 실제 파일은 따로 존재하지 않으며, PostgreSQL 메타데이터 DB에 아래와 같은 형태의 레코드로 관리됩니다.

```
[PostgreSQL — 메타데이터 DB]

버킷 (Bucket): "reports"
 └─ 오브젝트 (Object)
     ├─ 키: "2026/q1.pdf"          ← 논리 경로 (이름)
     ├─ 해시: "a3f8d2..."          ← 블롭 참조 포인터 (내용 식별자)
     ├─ Content-Type, 크기, 날짜
     └─ 버전 이력 (버저닝 활성화 시)
```

해시는 파일 내용 자체가 아니라 **스토리지 백엔드에 저장된 블롭 파일을 가리키는 포인터**입니다. 서로 다른 키(이름)라도 해시가 같으면 물리 파일은 하나만 존재합니다(dedup).

```
메타데이터 DB                     스토리지 백엔드
─────────────────────────         ─────────────────────────
reports / 2026/q1.pdf             cas/objects/
  해시 = a3f8d2... ───────────▶     a3/f8/d2c1... (실제 파일)
                                              ▲
backup / old/q1.pdf                           │
  해시 = a3f8d2... ───────────────────────────┘
  (이름은 다르지만 같은 블롭 참조)
```

- 버킷은 생성·삭제·목록 조회가 가능합니다.
- 키에 `/` 구분자를 사용하면 S3의 "폴더" 구조처럼 계층적으로 관리할 수 있습니다.
- 버저닝을 활성화하면 동일 키에 파일을 덮어쓸 때 이전 버전이 보존됩니다.

### 2.4 삭제 처리 및 GC

오브젝트 삭제는 즉시 물리 삭제가 아닌 **소프트 삭제** 방식으로 동작합니다.

```
삭제 요청
  → 오브젝트에 삭제 마커 기록 (즉시 접근 불가)
  → 해당 블롭을 참조하는 오브젝트가 0개가 된 경우
      → GC 실행 시 물리 파일 삭제
```

- 삭제 후에도 다른 오브젝트가 같은 블롭을 참조하고 있으면 물리 파일은 유지됩니다.
- GC는 주기적으로 실행되며, 참조가 없는 블롭만 안전하게 삭제합니다.

---

## 3. 파일 생명주기

### 3.1 업로드

```
PUT /{버킷}/{키}
```

- `Content-Type` 헤더로 MIME 타입을 지정합니다.
- 응답에 `x-cas-hash`(BLAKE3 해시), `x-cas-already-existed`(중복 여부) 헤더가 포함됩니다.
- 해시를 미리 알고 있다면 `x-cas-hash` 요청 헤더로 전달해 검증 및 중복 건너뛰기를 활용할 수 있습니다.

**응답 예시**:
```
HTTP/1.1 200 OK
ETag: "a3f8d2c1e7b946..."
x-cas-hash: a3f8d2c1e7b946...
x-cas-already-existed: false
```

### 3.2 다운로드

```
GET /{버킷}/{키}
```

- 파일 내용을 스트리밍으로 반환합니다.
- `Range` 헤더를 사용한 부분 다운로드를 지원합니다.
- `HEAD /{버킷}/{키}` 로 파일 존재 여부·메타데이터만 확인할 수 있습니다.

**Presigned URL**:

서명된 임시 URL을 발급하면, 별도 인증 없이 제한된 시간 동안 작업을 수행할 수 있습니다. 유효 시간은 초 단위로 지정합니다.

| 용도 | 메서드 | 설명 |
|------|--------|------|
| 다운로드 링크 공유 | `GET` | AWS CLI `aws s3 presign`으로 생성 가능 |
| 클라이언트 직접 업로드 | `PUT` | SDK의 `generate_presigned_url("put_object")`로 생성 |
| 오브젝트 삭제 위임 | `DELETE` | SDK의 `generate_presigned_url("delete_object")`로 생성 |

서명은 발급 시 지정한 메서드·경로·유효기간이 포함되며, 만료 또는 메서드 불일치 시 `403 AccessDenied`를 반환합니다.

### 3.3 복사

```
PUT /{대상-버킷}/{대상-키}
x-amz-copy-source: /{원본-버킷}/{원본-키}
```

- 물리 데이터 이동 없이 메타데이터만 추가하는 **Zero-copy** 방식으로 즉시 완료됩니다.
- 원본과 사본은 동일한 블롭을 공유하며, 어느 쪽을 삭제해도 다른 쪽에 영향을 주지 않습니다.

### 3.4 삭제

```
DELETE /{버킷}/{키}
```

- 즉시 접근 불가 상태로 전환되며, 물리 삭제는 GC가 처리합니다.
- 버저닝이 활성화된 버킷에서는 삭제 마커(Delete Marker)가 추가되고 이전 버전은 보존됩니다.

---

## 4. 스토리지 백엔드

### 4.1 로컬 NAS 백엔드

NAS(Network Attached Storage)의 마운트 경로를 직접 사용하는 방식입니다.

- 블롭 파일은 해시 앞 4자를 디렉터리 계층으로 분산 저장합니다 (`ab/cd/...`).
- 파일시스템 수준의 원자적 저장으로 부분 쓰기 없이 안전하게 처리됩니다.
- NAS 연결이 끊기면 해당 백엔드를 사용하는 요청은 503으로 응답합니다.

### 4.2 S3 호환 백엔드

MinIO, Ceph RGW 등 S3 호환 오브젝트 스토리지를 백엔드로 사용합니다.

- 내부 TLS 없는 환경(내부망)에서는 HTTP 접속(`allow_http: true`)을 설정할 수 있습니다.
- 키 프리픽스(`key_prefix`)를 지정하면 하나의 S3 버킷 안에서 네임스페이스를 분리할 수 있습니다.

### 4.3 다중 백엔드 운용

같은 타입(NAS 또는 S3)의 백엔드를 여러 대 동시에 운용할 수 있습니다. NAS와 S3 혼합은 지원하지 않습니다.

**NAS 다중 구성** — 가용 공간 기준 자동 배정:
```
NAS-A  [가용 공간: 80%]  ←── 신규 업로드 우선 배정
NAS-B  [가용 공간: 45%]
NAS-C  [가용 공간: 20%]
```

**S3 다중 구성** — 엔드포인트(버킷) 단위로 등록, 요청마다 순서대로 순환(round-robin) 배정:
```
S3-main  (objectstorage-1.internal / bucket-a)  ←── 1번째 업로드
S3-sub   (objectstorage-2.internal / bucket-b)  ←── 2번째 업로드
S3-main  ...                                     ←── 3번째 업로드
```

### 4.4 백엔드 장애 시 동작

| 상황 | 동작 |
|------|------|
| 특정 NAS 연결 끊김 | 해당 NAS 관련 요청만 503 반환, 나머지 백엔드는 정상 동작 |
| 해당 NAS에만 있는 블롭 다운로드 요청 | 503 `BackendUnavailable` 반환 |
| S3 백엔드 응답 불가 | 동일하게 503 반환, 다른 S3 백엔드는 정상 동작 |
| 신규 업로드 | 정상 백엔드 중 가용 공간 최대인 곳에 저장 |

---

## 5. API 사용 가이드

CAS Server는 **AWS S3 호환 REST API**를 제공합니다. 별도 배포된 사용가이드를 통해 사용 예시를 확인할 수 있습니다. 

### 5.1 연동 방법

기존 AWS S3 클라이언트를 그대로 사용합니다. `endpoint-url`만 CAS Server 주소로 지정하면 됩니다.

**AWS CLI**:
```bash
# 파일 업로드
aws s3 cp ./report.pdf s3://documents/2026/report.pdf \
  --endpoint-url http://cas.internal:8080

# 파일 목록 조회
aws s3 ls s3://documents/ --endpoint-url http://cas.internal:8080

# Presigned URL 발급 (5분 유효)
aws s3 presign s3://documents/2026/report.pdf \
  --endpoint-url http://cas.internal:8080 --expires-in 300
```

### 5.2 인증

| 모드 | 설명 |
|------|------|
| **NoAuth** | 인증 없음, 내부망 전용 운용 시 사용 |
| **SigV4** | AWS 표준 서명(AWS4-HMAC-SHA256). Access Key + Secret Key 필요 |

SigV4 사용 시 region은 반드시 `cas-default`로 지정해야 합니다. 

```bash
aws configure set aws_access_key_id     <발급된-키-ID>
aws configure set aws_secret_access_key <발급된-시크릿>
aws configure set region                cas-default
```

### 5.3 CAS 전용 응답 헤더

S3 표준에 없는 CAS 전용 헤더가 업로드 응답에 추가됩니다.

| 헤더 | 설명 | 예시 |
|------|------|------|
| `x-cas-hash` | 저장된 파일의 BLAKE3 해시 (64자 hex) | `a3f8d2c1e7b946...` |
| `x-cas-already-existed` | 중복 블롭 여부 — `true`면 물리 저장 건너뜀 | `true` / `false` |

`x-cas-hash`를 저장해 두면, 다음 업로드 시 `x-cas-hash` **요청** 헤더로 전달해 서버가 물리 전송 없이 즉시 등록하도록 할 수 있습니다.

### 5.4 지원 API 범위

**지원**:
- 버킷: `ListBuckets`, `CreateBucket`, `DeleteBucket`, `ListObjects(V2)`, `PutBucketVersioning`
- 오브젝트: `PutObject`, `GetObject`, `HeadObject`, `DeleteObject`, `CopyObject`
- 멀티파트: `CreateMultipartUpload`, `UploadPart`, `CompleteMultipartUpload`, `AbortMultipartUpload`, `ListMultipartUploads`
- Presigned URL: `GET`, `PUT`, `DELETE` 방식

### 5.5 웹 관리 UI

`http://<서버 주소>/_ui` 에서 브라우저 기반 관리 콘솔에 접근할 수 있습니다.

| 메뉴 | 제공 기능 |
|------|-----------|
| **대시보드** | 전체 오브젝트 수·버킷 수·총 용량 요약. Last GC 결과는 Admin Token 입력 후 표시 |
| **버킷 / 오브젝트** | 버킷 목록, 오브젝트 탐색, 버전 이력 조회, 블롭 상세(해시·크기·참조 수) 확인 |
| **백엔드** | 각 스토리지 백엔드의 디스크 사용량·블롭 수 현황 |
| **GC** | Admin Token 입력 후 활성화. 고아 블롭 수 조회, 수동 GC 실행, 실행 이력 확인 |
| **액세스 키** | 키 발급·비활성화, 정책(버킷·prefix 단위 허용/거부) 관리. Admin Token 입력 필요 |

> GC 탭과 액세스 키 관리 메뉴는 Admin Token을 입력해야 활성화됩니다. 액세스 키 탭은 SigV4 인증이 활성화된 경우에만 표시됩니다.

---

## 6. 에러 코드 및 대응

모든 에러는 S3 표준 XML 형식으로 반환됩니다.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Error>
  <Code>NoSuchKey</Code>
  <Message>object not found: documents/2026/report.pdf</Message>
</Error>
```

| HTTP 상태 | 에러 코드 | 원인 및 대응 |
|-----------|-----------|--------------|
| 400 | `InvalidBucketName` | 버킷 이름 형식 오류 |
| 400 | `InvalidArgument` | 요청 파라미터 오류 |
| 401 | `InvalidSignature` | SigV4 서명 불일치 — 키·region 확인 |
| 403 | `AccessDenied` | 해당 작업 권한 없음 |
| 404 | `NoSuchBucket` | 버킷 없음 |
| 404 | `NoSuchKey` | 오브젝트 없음 |
| 404 | `NoSuchUpload` | 멀티파트 업로드 ID 없음 |
| 409 | `BucketAlreadyExists` | 이미 존재하는 버킷 이름 |
| 409 | `BucketNotEmpty` | 비어 있지 않은 버킷 삭제 시도 |
| 503 | `BackendUnavailable` | 스토리지 백엔드 접근 불가 — 운영팀 확인 필요 |

---

## 7. 부록: 대용량 파일 업로드 (멀티파트)

AWS S3 표준 멀티파트 업로드 프로토콜을 지원합니다. AWS CLI·SDK의 기본 멀티파트 임계값(통상 8 MiB)에 따라 자동으로 분할 전송됩니다.

```bash
# AWS CLI — 100 MiB 이상은 자동으로 멀티파트 전송
aws s3 cp ./large-file.bin s3://archives/large-file.bin \
  --endpoint-url http://cas.internal:8080
```

**흐름 요약**:
1. `CreateMultipartUpload` — Upload ID 발급
2. `UploadPart` — 파트별 전송 (각 파트 최소 5 MiB, 마지막 파트 제외)
3. `CompleteMultipartUpload` — 파트 조합 및 블롭 등록
4. 미완료 업로드는 `AbortMultipartUpload` 로 정리

업로드 중단 시 파트 파일이 백엔드에 남을 수 있으므로, 재시도 실패 후에는 명시적으로 Abort 호출을 권장합니다.