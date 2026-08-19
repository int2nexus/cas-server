# nexus-server Helm Chart

ML 학습 데이터 카탈로그 서버. cas-server 위에서 파일을 **Sample → Dataset → DatasetVersion** 단위로 묶어 버전을 관리한다.

## 문서

- [아키텍처](https://github.com/int2nexus/cas-server/blob/main/charts/nexus-server/docs/architecture.md)
  — 도메인 모델, Version 생명주기, Annotation CoW, 스냅샷·Manifest 구조
- [사용법](https://github.com/int2nexus/cas-server/blob/main/charts/nexus-server/docs/usage.md)
  — 설치, Python SDK 연결, Dataset 적재·검색·seal 워크플로우, API 레퍼런스
- [변경 이력](CHANGELOG.md)
  — 버전별 동작 변경·마이그레이션·설정 키. 각 항목은 해당 GitHub Release 본문과 동일하다

## 전제

- **외부 PostgreSQL** — 접속 정보(비번 포함 DSN)는 시크릿으로 주입. 차트가 DB를 띄우지 않는다.
- **클러스터 내 cas-server** — CAS(파일) 백엔드.
- **시크릿 4키** (sealed-secret으로 주입): `NEXUS__DATABASE__URL`, `NEXUS__CAS__KEY_ID`, `NEXUS__CAS__SECRET`, `NEXUS__JWT__SECRET`.
  CVAT annotation 편집 세션을 쓰면 `NEXUS__CVAT__PASSWORD`가 **5번째 키**로 추가된다(선택).
  superuser를 쓰면 `NEXUS__AUTH__SUPERUSER_PASSWORD`가 **6번째 키**로 추가된다(선택).
- **CVAT은 선택** — 설정하지 않아도 서버는 정상 동작한다. 세션 생성·결과 회수만 503이 되고 카탈로그·업로드·seal·조회는 영향이 없다.
- **superuser도 선택** — 설정하지 않으면 `/api/v1/admin/*`가 누구에게나 403일 뿐 나머지는 영향이 없다. 다만 **CVAT과 달리 반쪽 설정은 조용히 꺼지지 않고 기동을 실패시킨다**(아래 참조).

DB 마이그레이션은 바이너리에 임베드되어 **기동 시 자동 적용**된다(별도 Job 불필요). 서버는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

> **appVersion 0.1.1은 파괴적 변경을 포함한다** — 조회를 포함한 **모든 API가 인증을 요구**하고, dataset을 바꾸는 요청은 **소유자만** 통과한다. 업그레이드 전에 [CHANGELOG](CHANGELOG.md)의 0.2.0 항목을 반드시 읽을 것.

## 설치

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

### 1) 시크릿 주입 (sealed-secret)

차트는 Secret을 만들지 않고 외부 Secret을 `envFrom`으로 참조한다. 아래 키를 가진 Secret을 **먼저** 주입한다(마지막 CVAT 줄은 연동을 쓸 때만):

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='...' \
  --from-literal=NEXUS__CAS__SECRET='...' \
  --from-literal=NEXUS__JWT__SECRET='...' \
  --from-literal=NEXUS__CVAT__PASSWORD='...' \
  --from-literal=NEXUS__AUTH__SUPERUSER_PASSWORD='...' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

평문 예시: [`examples/secret.example.yaml`](examples/secret.example.yaml).
Secret 이름은 `secret.existingSecret`(비우면 릴리즈 fullname, 기본 `nexus-server`)과 일치해야 한다.

### 2) 차트 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=http://cas-server:80
```

환경별 override는 `-f values-xxx.yaml` 사용.

## 주요 values

| 키 | 기본값 | 설명 |
|---|---|---|
| `server.port` | `8090` | 컨테이너 포트. **바꿀 때 프로브·`service.targetPort`도 함께 바꿀 것**(아래 참조) |
| `cas.baseUrl` | `http://cas-server:80` | CAS(cas-server) 주소 |
| `cas.region` / `cas.defaultBucket` | `cas-default` / `data` | CAS region·기본 버킷. **버킷 이름은 S3 규칙**(소문자·숫자·`-`·`.`, 3~63자)을 따라야 한다 |
| `database.maxConnections` | `16` | 커넥션 풀 상한. `ingest.batchItemConcurrency`와의 불변식은 [`values.yaml`](values.yaml) 주석 참조 |
| `secret.existingSecret` | `""` | 비밀 Secret 이름(비우면 fullname) |
| `service.type` / `service.nodePort` | `NodePort` / `30090` | 서비스 노출 |
| `ingress.enabled` | `false` | Ingress 사용 여부 |
| `resources` | 250m/256Mi ~ 1000m/1Gi | 요청/제한 |
| `cvat.baseUrl` | `""` | **비우면 CVAT 연동 꺼짐**(`NEXUS__CVAT__*` env 자체가 렌더되지 않는다) |
| `cvat.user` / `cvat.organization` | `""` / `""` | CVAT 서비스 계정, organization slug(선택) |
| `cvat.projectNamePrefix` | `nexus` | 생성되는 CVAT project 이름 접두사 |
| `cvat.segmentSize` / `cvat.maxSessionSamples` | `""` / `""` | 비우면 서버 기본값(각각 0=CVAT 기본, 2000) |
| `cvat.staleCreatingSecs` | `""` | 비우면 서버 기본값 1800초. 이 시간을 넘긴 `creating` 세션을 기동 시 `failed`로 정리 |
| `auth.superuserEmail` | `""` | **비우면 superuser 기능 꺼짐.** 채우면 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`도 **반드시 함께** 있어야 한다 |

전체 키는 [`values.yaml`](values.yaml) 참조.

CVAT 연동은 `cvat.baseUrl`·`cvat.user`·시크릿의 `NEXUS__CVAT__PASSWORD` **셋이 다 있어야** 켜진다. 하나라도 비면 서버는 정상 기동하고 무엇이 빠졌는지 기동 로그에 남는다.

### superuser

비밀번호를 잊어 로그인할 수 없는 계정을 풀어주고, dataset 소유자를 지정하는 단일 관리 계정이다. 이메일은 `auth.superuserEmail`, 비밀번호는 시크릿의 `NEXUS__AUTH__SUPERUSER_PASSWORD`(8자 이상)에 넣는다.

**CVAT과 달리 반쪽 설정은 조용히 꺼지지 않는다 — 서버가 기동에 실패한다.** 일부러 그렇게 만들었다: 운영자가 켰다고 믿는데 실제로는 꺼져 있는 상태가 가장 나쁘고, 그 사실이 정작 필요한 순간(누군가 잠겼을 때)에야 드러나기 때문이다. **차트는 이 짝을 검사할 수 없다** — 비밀번호는 Secret에서 `envFrom`으로 들어와 템플릿에 보이지 않는다. 그래서 `helm upgrade`는 조용히 성공하고 Pod가 CrashLoop로 드러나며, 어느 쪽이 빠졌는지는 `kubectl logs`에 적힌다.

**끌 때도 두 곳을 함께 비운다.** `auth.superuserEmail`만 지우고 Secret에 비밀번호를 남겨두면 "비밀번호만 있는" 상태가 되어 역시 기동에 실패한다.

**여기 적은 비밀번호는 최초 계정 생성 때만 쓰인다.** 서버가 기동 시 그 계정이 없으면 만들고(그래야 그 주소를 아무도 선점할 수 없다), 이미 있으면 **비밀번호를 덮지 않는다** — 운영자가 API로 바꾼 값이 파드 재시작마다 되돌아가면 안 되기 때문이다. 나중에 이 env를 바꿔도 로그인 비밀번호는 바뀌지 않는다(자주 나오는 오해다). 잊었다면 Secret을 고치는 게 아니라 그 계정을 지우고 다시 기동해야 한다.

권한은 토큰이 아니라 **이 설정값**으로 판정하므로, 이메일을 바꿔 재배포하면 즉시 회수된다 — 토큰을 무효화할 수 없는 이 서버에서 유일한 예외다. 능력은 비밀번호 재설정(`POST /api/v1/admin/users/password-reset`)과 dataset 소유자 지정(`PUT /api/v1/admin/datasets/{dataset_id}/owner`) 둘뿐이고, 사용자 목록·계정 비활성화·감사 로그는 없다.

## 헬스 체크

프로브는 셋으로 갈린다. `GET /_internal/live`(의존성을 조회하지 않는 프로세스 응답성 확인)를 startup·liveness에, `GET /_internal/health`(DB ping)를 readiness에 쓴다. liveness를 `/_internal/health`로 두면 DB failover(보통 30~120초) 중에 파드가 kill되는데, 재시작으로는 외부 의존성이 복구되지 않아 중단이 원래 장애보다 길어진다 — 자세한 배경은 [CHANGELOG](CHANGELOG.md) 0.3.0 참조.

```bash
kubectl port-forward svc/nexus-server 8090:80 -n <namespace>
curl localhost:8090/_internal/health      # {"status":"ok","db":true}
```

이 두 경로만 인증이 면제된다(프로브가 자격증명 없이 호출해야 하므로). 나머지 API는 조회를 포함해 전부 토큰이 필요하다.

### `server.port`를 바꿀 때

`server.port` **하나만** 바꾸면 된다.

```bash
helm upgrade ... --set server.port=9000
```

컨테이너 포트, 앱이 듣는 포트(`NEXUS__SERVER__PORT`), Service의 `targetPort`, 두 프로브가 모두 이 값을 따라간다. 뒤의 셋은 숫자가 아니라 **컨테이너 포트 이름 `http`**를 가리키기 때문이다.

`values-xxx.yaml`에서 프로브나 `service.targetPort`를 직접 override할 때 숫자를 박지 말 것 — `server.port`와 어긋나면 앱은 새 포트에서 도는데 kubelet은 옛 포트를 찔러 **Pod가 영영 Ready가 되지 않는다.** 컨테이너 로그에는 아무 이상이 없어 원인을 찾기 어렵다.

## 삭제

```bash
helm uninstall nexus-server -n <namespace>
kubectl delete -f sealed-nexus-server.yaml -n <namespace>   # 시크릿은 별도 정리
```
