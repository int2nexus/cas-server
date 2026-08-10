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

## 주의사항

- 프로덕션 자격증명·values는 커밋하지 마세요. 각 차트의 `examples/`는 실제 값이 없는 예시/placeholder만
  포함합니다.
- 클라이언트 인증은 선택적입니다. cas-server의 `auth.secretMasterKey`를 설정하면 SigV4 인증이
  활성화되고, 비워두면 NoAuth 모드(인증 없음, 내부망 전용)로 동작합니다.
