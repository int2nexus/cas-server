# cas-server Helm Chart

BLAKE3 기반 Content-Addressable Storage 서버의 Helm chart 레포지토리입니다.

## Helm 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 설치

### 1. PostgreSQL 먼저 설치 (필수)

cas-server에서 메타데이터 저장소로 사용하는 PostgreSQL을 bitnami/postgresql subchart 대신 별도 helm release로 설치합니다.
(bitnami가 OCI 레지스트리로 이전하면서 subchart 방식(`helm dependency`)이 정상 동작하지 않아 아래와 같이 별도 설치)

```bash
helm install postgresql oci://registry-1.docker.io/bitnamicharts/postgresql \
  --version 18.3.0 \
  -n <namespace> --create-namespace \
  --set auth.username=cas \
  --set auth.password=int2nexus \
  --set auth.database=cas_metadata \
  --set primary.persistence.storageClass=<storageClass> \
  --set primary.persistence.size=1Gi
```

### 2. cas-server 설치

```bash
helm install cas-server int2nexus/cas-server \
  -n <namespace> \
  --set externalDatabase.host=postgresql \
  --set externalDatabase.username=cas \
  --set externalDatabase.database=cas_metadata \
  --set secrets.dbPassword=int2nexus \
  --set storage.mode=nfs \
  --set storage.nfs.backends[0].id=nas-1 \
  --set storage.nfs.backends[0].mountPath=/mnt/nas1 \
  --set storage.nfs.backends[0].storageClassName=nfs-client \
  --set storage.nfs.backends[0].storage=1Ti
```

또는 values 파일 사용:

```bash
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

## values 파일 예시

### NFS 모드 (멀티 NAS)

```yaml
externalDatabase:
  host: "postgresql"
  port: 5432
  username: "cas"
  database: "cas_metadata"

secrets:
  dbPassword: "int2nexus"

storage:
  mode: "nfs"
  nfs:
    backends:
      - id: "nas-1"
        name: "nas1"
        mountPath: "/mnt/nas1"
        storageClassName: "nfs-client"
        storage: "10Ti"
      - id: "nas-2"
        name: "nas2"
        mountPath: "/mnt/nas2"
        storageClassName: "nfs-client"
        storage: "20Ti"
```

### S3 / MinIO 모드

```yaml
externalDatabase:
  host: "postgresql"
  port: 5432
  username: "cas"
  database: "cas_metadata"

secrets:
  dbPassword: "<your-password>"
  s3AccessKeyId: "<access-key>"
  s3SecretAccessKey: "<secret-key>"

storage:
  mode: "s3"
  s3:
    endpoint: "http://minio.minio-system:9000"
    bucket: "cas-blobs"
    region: "us-east-1"
    keyPrefix: "cas/"
    allowHttp: true   # MinIO TLS 없는 환경
```

### 로컬 테스트 (Docker Desktop Kubernetes)

```bash
# 1. PostgreSQL 설치
helm install postgresql oci://registry-1.docker.io/bitnamicharts/postgresql \
  --version 18.3.0 \
  -n cas-local --create-namespace \
  --set auth.username=cas \
  --set auth.password=localtest \
  --set auth.database=cas_metadata \
  --set primary.persistence.storageClass=hostpath \
  --set primary.persistence.size=1Gi

# 2. cas-server 설치
helm install cas-server int2nexus/cas-server \
  -n cas-local \
  --set externalDatabase.host=postgresql \
  --set externalDatabase.username=cas \
  --set externalDatabase.database=cas_metadata \
  --set secrets.dbPassword=localtest \
  --set storage.nfs.backends[0].id=local \
  --set storage.nfs.backends[0].mountPath=/data/cas \
  --set storage.nfs.backends[0].storageClassName=hostpath \
  --set storage.nfs.backends[0].storage=5Gi

# 3. 포트 포워딩
kubectl -n cas-local port-forward svc/cas-server 8080:80
```

## 설정 값 (values.yaml)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `image.repository` | `int2jieun/cas-server` | Docker 이미지 |
| `image.tag` | `0.1.0` | 이미지 태그 |
| `replicaCount` | `1` | NFS 모드에서는 1 권장 |
| `storage.mode` | `nfs` | `nfs` 또는 `s3` |
| `externalDatabase.host` | `""` | PostgreSQL 서비스명 |
| `externalDatabase.port` | `5432` | PostgreSQL 포트 |
| `secrets.dbPassword` | `""` | DB 비밀번호 |
| `ingress.enabled` | `false` | Ingress 활성화 |
| `config.maxUploadSizeBytes` | `10737418240` | 최대 업로드 크기 (10 GiB) |

전체 설정값은 [values.yaml](charts/cas-server/values.yaml)을 참고하세요.

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
