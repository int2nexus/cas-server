# nexus-client 차트 변경 이력

각 `##` 섹션이 그대로 해당 버전의 **GitHub Release 본문**이 됩니다
(`scripts/extract-release-notes.sh` 가 발췌 → chart-releaser 가 릴리스 본문으로 사용).

`Chart.yaml` 의 `version` 을 올릴 때 이 파일 맨 위에 섹션을 함께 추가하세요.
섹션이 없으면 릴리스 워크플로가 실패합니다.

해당 사항이 없는 항목도 **"없음"이라고 적습니다** — 도입하는 쪽이 *없었다* 와 *안 썼다* 를
구별할 수 있어야 합니다. 이미지만 바뀐 릴리스라도 라우팅·프록시 계약이 유지되는지는
여기에 적혀 있어야 도입하는 쪽이 직접 시험하지 않아도 됩니다.

```markdown
## <version>

image: `jiwonkim97/nexus-client:<tag>` (변경 없음이면 그렇게 적기)

**동작 변경** — 없음
**마이그레이션** — 없음
**설정 키** — 없음
```

### 선택 라벨

세 항목은 **최소**입니다. 더 알려야 할 게 있으면 아래 라벨을 같은 모양(`**라벨** — 내용`)으로
덧붙입니다. 같은 라벨을 여러 번 써서 묶어도 됩니다.

- `**호환성**` — 요구하는 최소 appVersion·nexus-server 버전, 맞지 않을 때 벌어지는 일
- `**운영 조치**` — 이 버전 때문에 되돌리거나 새로 해야 하는 운영 작업
- `**주의**` — 버전과 무관하게 지켜야 하는 제약을 이 릴리스에서 처음 문서화한 경우

라벨 볼드 안에 수식어까지 넣지 마세요 — `**동작 변경 — 차트**` 가 아니라
`**동작 변경** — 차트` 입니다. 도입하는 쪽이 라벨을 훑어 찾기 때문에 라벨 자체가
고정된 문자열이어야 합니다.

### 마이그레이션 항목 쓰는 법

nexus-client 는 정적 파일을 서빙하는 Caddy 뿐이고 DB 가 없으므로 이 항목은 `없음` 입니다.
롤백은 `helm rollback <release> <revision>` 으로 항상 안전합니다.

단 백엔드 계약(`/api`·`/cas` 프록시 경로, `backendUrl`·`casUrl` 해석)이 바뀌면 그건
**동작 변경** 항목에 적습니다 — nexus-server 버전과 맞물리는 변경이면 필요한 최소
nexus-server 버전을 함께 씁니다.

<!-- 새 버전 섹션은 이 줄 바로 아래에, 최신이 위로 오게 추가하세요 -->

## 0.1.7

image: `jiwonkim97/nexus-client:0.1.8`

**동작 변경** — 샘플 삭제 시 explorer 캐시 페이지에서 항목을 직접 제거하지 않고 렌더 단계에서 숨깁니다. 마지막 로드 페이지 길이가 줄어 `hasNextPage=false`로 오판되는 문제를 방지하며, 삭제 직후 explorer 전체 재조회 없이 이후 스크롤 기반 추가 로드는 계속 동작합니다.
**동작 변경** — 샘플 추가·삭제 및 CVAT import 뒤 `schema`·`facet`·`histogram` 캐시를 무효화합니다. 새 라벨/필드값 또는 삭제된 값이 필터 메뉴와 분포 패널에 stale 상태로 남지 않도록 했고, 스키마에 새로 등장한 annotation 키는 기존 표시 상태를 보존하면서 자동으로 보이게 합니다.
**동작 변경** — `meta.width`/`meta.height`가 무효한 샘플은 이미지의 natural 크기를 폴백 프레임으로 사용해 렌더·다운로드를 처리합니다. 다운로드는 원본 URL이 있는 샘플만 허용하며 썸네일을 원본 대체로 사용하지 않습니다.
**동작 변경** — 이미지 URL이 없는 샘플에서 `meta.filename` basename을 public root로 임의 요청하던 POC 폴백을 제거했습니다. URL이 없으면 불필요한 404 요청을 만들지 않고 즉시 이미지 없음 상태로 처리합니다.
**동작 변경** — 샘플 목록 평탄화 결과를 메모이즈해, 필터 입력·토글 같은 무관한 렌더마다 그리드/상세뷰어 데이터가 전체 재계산되는 비용을 줄였습니다.
**마이그레이션** — 없음
**설정 키** — 없음
**호환성** — 기존 0.1.6과 동일하게 `POST /api/v1/auth/refresh`, 계정 관리 API, annotation-sessions API를 제공하는 nexus-server가 필요합니다. 날짜 기준 대신 최소 버전으로 표기합니다: **nexus-server 차트 0.2.0 / appVersion 0.1.1 이상**. 이 버전은 추가 서버 API를 요구하지 않습니다.
**주의** — 브라우저 기준 경로와 서버 기준 경로를 구분해야 합니다. 서버 기준 auth 경로는 `/api/v1/auth/...` 이지만, nexus-client Caddy의 `/api` 프록시를 거치는 브라우저 기준 요청은 `/api/api/v1/auth/...` 형태입니다. datasets/samples/explorer 등 기존 루트 계열 API는 브라우저 기준 `/api/datasets...`, `/api/samples...` 형태를 유지합니다. 기존 루트 경로를 `/api/v1`로 일괄 이전하지 않았습니다.
**주의** — 웹 UI의 이미지·썸네일 로드는 브라우저가 CAS에 직접 붙는 구조가 아니라 same-origin `/cas/image?url=...` 프록시를 경유합니다. Caddy가 `/cas/*`를 같은 컨테이너의 Node 사이드카로 넘기고, 사이드카가 CAS로 스트리밍합니다. 클라이언트 번들에 CAS 주소를 하드코딩하지 않습니다. 단, CAS 익명 GET 위협모델 자체는 cas-server/CAS 쪽 정책을 따릅니다.
**운영 조치** — nexus-client는 정적 SPA + Caddy reverse proxy + 요청 단위 `/cas/image` Node 프록시 구조라 `replicas > 1` 구성이 가능합니다. 모든 replica에 같은 `BACKEND_URL`과 `/cas` 프록시 설정을 사용하면 sticky session은 필요하지 않습니다. 다만 이미지 표시/다운로드 중 해당 파드가 죽으면 그 단일 HTTP 스트림은 실패할 수 있으므로 사용자가 재시도해야 합니다.

## 0.1.6

image: `jiwonkim97/nexus-client:0.1.7`

**동작 변경** — 세션 수명주기 자동 관리 도입: 토큰 만료 12시간 전부터 `POST /api/v1/auth/refresh` 로 선제 갱신(탭당 최대 분당 1회), 데이터 API 401 수신 시 전역 로그아웃 후 로그인 화면 이동.
**동작 변경** — CVAT 편집 세션 연동 활성화: 데이터셋 편집이 `/api` 하위 annotation-sessions 엔드포인트를 사용. `/api`·`/cas` 프록시 경로와 `backendUrl`·`casUrl` 해석 계약은 그대로.
**마이그레이션** — 없음
**설정 키** — 없음
**호환성** — nexus-server 가 `POST /api/v1/auth/refresh`, 계정 관리(`POST /api/v1/auth/password`, `DELETE /api/v1/auth/account`), annotation-sessions API 를 제공해야 함(**nexus-server 차트 0.2.0 / appVersion 0.1.1 이상**). 미제공 시 세션 자동 갱신은 로그아웃 없이 재시도만 하고, 계정 설정·CVAT 편집은 화면 에러로 표시됨.

## 0.1.5

image: `jiwonkim97/nexus-client:0.1.6`

이 버전부터 변경 이력을 남깁니다.
