# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 **Sample → Dataset → DatasetVersion** 단위로 묶어 버전을 관리한다. (이미지: `int2jieun/nexus-server`)

## 전제

- **외부 PostgreSQL** — 접속 정보(비번 포함 DSN)는 시크릿으로 주입. 차트가 DB를 띄우지 않는다.
- **클러스터 내 cas-server** — CAS(파일) 백엔드.
- **시크릿 4키** (sealed-secret으로 주입): `NEXUS__DATABASE__URL`, `NEXUS__CAS__KEY_ID`, `NEXUS__CAS__SECRET`, `NEXUS__JWT__SECRET`.

DB 마이그레이션은 바이너리에 임베드되어 **기동 시 자동 적용**된다(별도 Job 불필요). 서버는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

## 설치

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

### 1) 시크릿 주입 (sealed-secret)

차트는 Secret을 만들지 않고 외부 Secret을 `envFrom`으로 참조한다. 아래 4키를 가진 Secret을 **먼저** 주입한다:

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='...' \
  --from-literal=NEXUS__CAS__SECRET='...' \
  --from-literal=NEXUS__JWT__SECRET='...' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

평문 예시: [`examples/secret.example.yaml`](examples/secret.example.yaml).
Secret 이름은 `secret.existingSecret`(비우면 릴리즈 fullname, 기본 `nexus-server`)과 일치해야 한다.

### 2) 차트 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set image.tag=0.0.1 \
  --set cas.baseUrl=http://cas-server:80
```

환경별 override는 `-f values-xxx.yaml` 사용.

## 주요 values

| 키 | 기본값 | 설명 |
|---|---|---|
| `image.repository` / `image.tag` | `int2jieun/nexus-server` / `0.0.1` | 서버 이미지 |
| `server.port` | `8090` | 컨테이너 포트 |
| `cas.baseUrl` | `http://cas-server:80` | CAS(cas-server) 주소 |
| `cas.region` / `cas.defaultBucket` | `cas-default` / `data` | CAS region·기본 버킷 |
| `secret.existingSecret` | `""` | 비밀 Secret 이름(비우면 fullname) |
| `service.type` / `service.nodePort` | `NodePort` / `30090` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 250m/256Mi ~ 1000m/1Gi | 요청/제한 |

전체 키는 [`values.yaml`](values.yaml) 참조.

## 헬스 체크

`GET /_internal/health` 를 liveness·readiness 프로브로 사용한다. 기동이 DB 연결·마이그레이션 성공에 게이트되므로, 200이면 정상 기동을 의미한다.

```bash
kubectl port-forward svc/nexus-server 8090:80 -n <namespace>
curl localhost:8090/_internal/health      # {"status":"ok"}
```

## 삭제

```bash
helm uninstall nexus-server -n <namespace>
kubectl delete -f sealed-nexus-server.yaml -n <namespace>   # 시크릿은 별도 정리
```
