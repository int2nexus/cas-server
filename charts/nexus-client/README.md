# nexus-client Helm Chart

nexus-server용 웹 UI. Caddy가 정적 파일을 서빙하고 `/api`를 nexus-server로 프록시한다.

버전별 동작 변경·마이그레이션·설정 키는 [변경 이력](CHANGELOG.md)에 있다. 각 항목은 해당
GitHub Release 본문과 동일하다.

## 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

## 설치

```bash
helm install nexus-client int2nexus/nexus-client -n <namespace> \
  --set backendUrl=http://nexus-server:80
```

- `backendUrl`은 클러스터 내 nexus-server 서비스 주소이며, Caddy가 `/api`를 이 주소로 프록시한다.
- `casUrl`은 이미지를 same-origin으로 프록시할 때만 설정한다(Caddyfile의 `/cas` 블록도 함께 활성화됨).
  보통은 비워둔다 — 백엔드가 브라우저에서 직접 접근 가능한 CAS URL을 반환하면 `<img>`로 바로 로드된다.

## 주요 values

| 키 | 기본값 | 설명 |
|---|---|---|
| `backendUrl` | `http://nexus-server:80` | `/api` 프록시 대상 |
| `casUrl` | `""` | CAS same-origin 프록시 대상(선택) |
| `casAuth.enabled` | `false` | CAS 비익명(`anonymousGet:false`) 접근 시 사이드카 SigV4 서명 활성화 |
| `casAuth.existingSecret` | `""` | CAS 키가 담긴 기존 Secret 이름. 키: `CAS_ACCESS_KEY_ID`·`CAS_SECRET_ACCESS_KEY` |
| `casAuth.region` | `cas-default` | SigV4 region |
| `service.type` / `service.nodePort` | `NodePort` / `30070` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 50m/64Mi ~ 200m/128Mi | 요청/제한 |

전체 키는 [values.yaml](values.yaml) 참조.

## CAS 이미지 인증 (SigV4)

CAS(cas-server)가 비익명(`anonymousGet: false`)이면, 브라우저 이미지 요청을 프록시하는
사이드카가 CAS 로 나갈 때 **SigV4 서명**을 붙여야 한다. cas-console **Keys 탭**에서 **GET 전용
정책 키**를 발급받아(→ `key_id` / `secret_key`) 아래처럼 주입한다.

- 서명은 **사이드카→CAS 구간에서만** 붙는다 — 브라우저는 키·서명·CAS 주소를 보지 못한다.
- 비활성(기본)이면 사이드카는 **무서명 GET** 이라 익명 배포(`anonymousGet: true`)에서만 이미지가 로드된다.

### 시크릿 주입

키를 담은 Secret 을 **먼저** 만들고(운영은 sealed-secret 권장), 차트는 `casAuth.existingSecret`
으로 그 이름만 참조한다. Secret 의 키 이름은 반드시 `CAS_ACCESS_KEY_ID` / `CAS_SECRET_ACCESS_KEY`
여야 한다.

```bash
kubectl create secret generic nexus-client-cas -n <namespace> --dry-run=client -o yaml \
  --from-literal=CAS_ACCESS_KEY_ID='<key_id>' \
  --from-literal=CAS_SECRET_ACCESS_KEY='<secret_key>' \
  | kubeseal --format yaml > sealed-nexus-client-cas.yaml
kubectl apply -f sealed-nexus-client-cas.yaml -n <namespace>

helm upgrade --install nexus-client int2nexus/nexus-client -n <namespace> \
  --set backendUrl=http://nexus-server:80 \
  --set casAuth.enabled=true \
  --set casAuth.existingSecret=nexus-client-cas
```

`casAuth.enabled=true` 인데 `existingSecret` 이 비어 있으면 렌더가 실패한다(설정 누락을 조용히
넘기지 않기 위함). region 이 `cas-default` 가 아니면 `--set casAuth.region=<region>` 을 추가한다.

## 헬스체크

Caddy가 정적 서버라 `/` GET 응답으로 liveness·readiness를 판단한다.

## 접속

```bash
# NodePort
http://<노드IP>:30070/

# 또는 port-forward
kubectl port-forward svc/nexus-client 3000:80 -n <namespace>
```

## 삭제

```bash
helm uninstall nexus-client -n <namespace>
```
