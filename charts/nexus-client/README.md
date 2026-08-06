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
| `service.type` / `service.nodePort` | `NodePort` / `30070` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 50m/64Mi ~ 200m/128Mi | 요청/제한 |

전체 키는 [values.yaml](values.yaml) 참조.

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
