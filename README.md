# int2nexus Helm Charts & SDK

[![cas-server](https://img.shields.io/github/v/release/int2nexus/cas-server?filter=cas-server-*&label=cas-server)](https://github.com/int2nexus/cas-server/releases)
[![nexus-server](https://img.shields.io/github/v/release/int2nexus/cas-server?filter=nexus-server-*&label=nexus-server)](https://github.com/int2nexus/cas-server/releases)
[![nexus-client](https://img.shields.io/github/v/release/int2nexus/cas-server?filter=nexus-client-*&label=nexus-client)](https://github.com/int2nexus/cas-server/releases)
[![python-sdk](https://img.shields.io/endpoint?url=https%3A%2F%2Fint2nexus.github.io%2Fcas-server%2Fsdk%2Fbadge.json)](https://int2nexus.github.io/cas-server/sdk/simple/int2nexus-sdk/)

BLAKE3 기반 CAS(Content-Addressable Storage) 서버와 이를 사용하는 nexus 데이터 카탈로그 스택을
Kubernetes에 배포하기 위한 Helm chart 레포입니다. Python SDK도 이 레포(GitHub Pages)를 통해
배포됩니다. 애플리케이션 소스코드는 포함되지 않으며, Docker 이미지는 외부에서 빌드됩니다.

## 차트

| 차트 | 설명 |
|---|---|
| [cas-server](charts/cas-server/README.md) | BLAKE3 기반 CAS 서버 (S3/NFS 백엔드) |
| [nexus-server](charts/nexus-server/README.md) | ML 학습 데이터 카탈로그 서버 (cas-server 위 Sample→Dataset 버전 관리) |
| [nexus-client](charts/nexus-client/README.md) | nexus-server 웹 UI |

설치/values/시크릿 주입 방법 등 상세 내용은 각 차트 README를 참고하세요.

## Helm 레포 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```

```bash
helm install cas-server int2nexus/cas-server -n <namespace>
helm install nexus-server int2nexus/nexus-server -n <namespace>
helm install nexus-client int2nexus/nexus-client -n <namespace>
```

시크릿 주입, values 오버라이드 등 배포 전 준비 사항은 차트별 README를 따르세요.

## SDK 설치 (Python)

int2nexus SDK는 wheel/sdist 파일로 이 레포의 GitHub Pages(`sdk/simple/`, PEP 503 simple index)에
게시됩니다:

```bash
pip install int2nexus-sdk --index-url https://int2nexus.github.io/cas-server/sdk/simple/
```

## 릴리즈 방법

`main` 브랜치에 push하면 GitHub Actions(`release.yaml`)가 `helm/chart-releaser-action`을 통해 자동으로
GitHub Releases와 `index.yaml`을 업데이트합니다. 새 버전을 릴리즈하려면 각 차트의 `Chart.yaml`의
`version`/`appVersion`과 `values.yaml`의 `image.tag`를 함께 맞춰 커밋합니다. 릴리즈 태그가
`<차트명>-<version>` 형식으로 생성되므로 위 cas-server/nexus-server/nexus-client 배지는 자동으로
최신 버전을 반영합니다.

python-sdk는 GitHub Releases 태그가 없는 별도 배포 경로(`sdk/simple/` PEP 503 인덱스)라 위 셋과
방식이 다릅니다. `scripts/publish_sdk.py`가 인덱스를 만들면서 `sdk/badge.json`도 함께 쓰고, 배지는
그 파일을 읽습니다(shields.io endpoint) — **발행하면 배지가 따라오므로 손댈 것이 없습니다.**

### 릴리즈 게이트 — 선언됐는데 렌더되지 않는 키

`release.yaml`이 `scripts/check-unrendered-values.py`를 돌립니다. `charts/` 아래 모든 차트의
`values.yaml` 리프 키를 템플릿 참조와 대조하고, 미참조 키가 있으면 **릴리즈를 실패시킵니다.**

Helm은 쓰이지 않는 값에 오류를 내지 않습니다. 그래서 이 부류의 결함은 "설정했는데 조용히
무시되는" 형태로 나타나고, 운영자는 고쳤다고 믿습니다. 이 저장소에서 넷을 그렇게 찾았습니다 —
cas-server의 `config.requestTimeoutSecs`·`serviceAccount.*`, nexus-server의 `serviceAccount.*`,
과거 cas-server의 `terminationGracePeriodSeconds`.

```bash
python scripts/check-unrendered-values.py                    # charts/ 전체
python scripts/check-unrendered-values.py charts/cas-server  # 특정 차트
```

새 values 키를 추가할 때는 커밋 전에 로컬에서 한 번 돌리세요. `resources`처럼 조상이
`toYaml`로 통째로 소비되는 블록은 정상으로 분류하므로 예외 처리가 필요 없습니다.

**이 검사는 `.Values.*`와 템플릿만 대조합니다 — 렌더된 TOML의 서버측 키 이름은 보지
않습니다.** `db_min_connection = ...`처럼 서버 필드명에 오타가 나면 통과하고, 서버도
조용히 무시합니다. 설정 키를 추가·변경할 때는 렌더된 ConfigMap을 실제 바이너리에 먹여
기동 로그의 `적용된 설정` 줄로 확인하세요. 다른 한계는 스크립트 docstring에 있습니다.

## 주의사항

- 프로덕션 자격증명·values는 커밋하지 마세요. 각 차트의 `examples/`는 실제 값이 없는 예시/placeholder만
  포함합니다.
- 클라이언트 인증은 선택적입니다. cas-server의 `auth.secretMasterKey`를 설정하면 SigV4 인증이
  활성화되고, 비워두면 NoAuth 모드(인증 없음, 내부망 전용)로 동작합니다.
