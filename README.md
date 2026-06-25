# cas-server Helm Chart

BLAKE3 기반 CAS(Content-Addressable Storage) 서버의 Helm chart 레포지토리입니다.

## Helm 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 설치

```bash
helm install cas-server int2nexus/cas-server -n <namespace>
```

또는 values 파일 사용:

```bash
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

## values 파일 예시

### S3 / MinIO 모드

```yaml
externalDatabase:
  host: "postgresql"
  port: 5432
  username: "username"
  database: "database"

secrets:
  dbPassword: "<your-password>"
  s3AccessKeyId: "<access-key>"
  s3SecretAccessKey: "<secret-key>"

storage:
  mode: "s3"
  s3:
    endpoint: "storage-endpoint-url"
    bucket: "your-bucket"
    region: ""
    keyPrefix: ""
    allowHttp: true
```

## 설정 값 (values.yaml)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `image.repository` | `int2jieun/cas-server` | Docker 이미지 |
| `image.tag` | `0.1.0` | 이미지 태그 |
| `storage.mode` | `s3` | s3 호환 스토리지 |
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

---

# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 Sample→Dataset 단위로 묶어 버전을 관리합니다. (이미지: `int2jieun/nexus-server`)

## 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 시크릿 (sealed-secret) 먼저 주입

`nexus-server` Secret에 4키가 필요합니다(외부 Postgres DSN·CAS 자격증명·JWT). 비밀은 차트(values)에 두지 않고 sealed-secret으로 주입합니다:

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='...' \
  --from-literal=NEXUS__CAS__SECRET='...' \
  --from-literal=NEXUS__JWT__SECRET='...' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

평문 예시: `charts/nexus-server/examples/secret.example.yaml`.

## 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set image.tag=0.0.1 \
  --set cas.baseUrl=http://cas-server:80
```

- 외부 PostgreSQL과 cas-server가 클러스터에 있어야 합니다. DB 마이그레이션은 기동 시 자동 적용됩니다.
- 설정은 `NEXUS__` 환경변수로 주입됩니다(`values.yaml`의 `server`/`cas`, 비밀은 Secret).
