# cas-server Helm Chart

BLAKE3 기반 CAS(Content-Addressable Storage) 서버. S3 호환 스토리지 또는 NFS를 백엔드로 사용하는
HTTP API를 제공한다.

## 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 시크릿 (sealed-secret) 먼저 주입

`secrets.useExternalSecret: true`(기본값)일 때 차트는 Secret을 만들지 않고, 이미 클러스터에 존재하는
`cas-server` Secret(7개 키)을 참조한다. kubeseal로 암호화해 미리 주입한다:

```bash
kubectl create secret generic cas-server \
  --namespace=<namespace> \
  --from-literal=db-password='...' \
  --from-literal=s3-access-key-id='...' \
  --from-literal=s3-secret-access-key='...' \
  --from-literal=auth-secret-master-key='...' \
  --from-literal=auth-admin-token='...' \
  --from-literal=auth-root-access-key-id='...' \
  --from-literal=auth-root-secret-key='...' \
  --dry-run=client -o yaml > /tmp/secret-plain.yaml

kubeseal --format yaml < /tmp/secret-plain.yaml > sealed-secret.yaml
rm /tmp/secret-plain.yaml
kubectl apply -f sealed-secret.yaml -n <namespace>
```

`auth.secretMasterKey`를 비우면 NoAuth 모드(인증 없음, 내부망 전용)로 동작한다. 상세 절차와 값 교체
방법은 [`examples/sealed-secret.yaml`](examples/sealed-secret.yaml) 참고.

## 설치

```bash
helm install cas-server int2nexus/cas-server -n <namespace> -f values-prod.yaml
```

`values-prod.yaml`은 직접 작성하거나 [`examples/values-prod.yaml`](examples/values-prod.yaml)을
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
| `ingress.enabled` | `false` | Ingress 활성화 |
| `config.maxUploadSizeBytes` | `10737418240` | 최대 업로드 크기 (10 GiB) |
| `gc.enabled` | `true` | GC CronJob 활성화 |

전체 설정값은 [values.yaml](values.yaml)을 참고하세요.

## 헬스체크

`GET /_internal/health` — DB ping + 스토리지 백엔드 가용성을 확인한다. 비정상이면 503 반환.

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
