# int2nexus-sdk 변경 이력

`int2nexus-sdk` 의 변경은 이 파일에 적습니다. 서버 이미지·차트와 따로 발행하고 따로 설치합니다.

```
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk==<버전>
```

`scripts/publish_sdk.py` 는 `sdk/pyproject.toml` 의 버전과 같은 `## <버전>` 절이 이 파일에 없으면
빌드하지 않고 멈춥니다. 최신 버전이 위로 오게 적습니다.

## 0.1.16

**`Dataset.clone` 을 서버 비동기 job 으로 전환합니다.** 신서버(nexus-server `0.1.18` 이상)에서는
복제를 `POST /datasets/{id}/versions/{version}/clone-jobs` 로 시작하고 `GET /clone-jobs/{job_id}` 로
완료까지 폴링합니다 — 복사와 실패 시 롤백을 서버가 담당해, 예전처럼 클라이언트가 `import_samples` 를
수천 번 왕복하지 않습니다(요청 1 + 폴링, 진행률 표시). 성공하면 만들어진 dataset 핸들을 반환하고,
실패·취소는 `NexusError` 입니다. **clone-job 이 없는 구서버**(그 경로가 `404`)에서는 예전의 클라이언트
반복 복제로 자동 폴백하므로 호출 방식(`ds.clone(new_name, new_version)`)은 그대로입니다.

- **동작 변경: 대상 이름의 dataset 이 이미 있으면 `409` 입니다.** `0.1.15` 까지는 이미 있으면 그
  dataset 을 재사용해 버전을 더했습니다. 서버 job 은 새 dataset 을 만들고 실패하면 통째로 롤백하는
  단위라 재사용하지 않습니다(재사용하면 실패 후 재시도가 샘플을 중복 복사합니다). 기존 dataset 에
  버전을 더하려면 그 dataset 핸들에서 `import_samples` 를 씁니다. 구서버 폴백 경로는 종전대로
  재사용합니다.
- **`clone(timeout=초)`** — 그 안에 job 이 끝나지 않으면 기다리기를 멈추고 job id 를 담은
  `NexusError` 를 던집니다. **job 을 취소하지는 않습니다**(서버에서 계속 돌 수 있으니 그 id 로 상태를
  확인합니다). 기본 `None` 은 끝날 때까지 기다립니다. 구서버 폴백 경로에는 적용되지 않습니다.
- 폴링 중 조회가 실패해도(예: `502`) 던지는 `NexusError` 에 job id 가 담깁니다 — job 은 서버에서
  계속 돌 수 있으니 그 id 로 상태를 확인합니다.
- 구서버 폴백은 **라우트가 없어서 난 `404`**(본문 없음, 또는 프록시의 HTML 오류 페이지)일 때만
  합니다. 신서버가 원본 dataset·버전이 없다고 준 `404` 는 그대로 올립니다(폴백하면 빈 대상
  dataset 만 만들고 실패해 고아가 남습니다).
- 원본 버전이 sealed 여도 복제본은 draft 로 시작합니다. 원본의 `tags`/`description` 을 복사합니다.

**CAS 서명 버그 수정 — 키에 `[` `]` 공백 등 특수문자가 있으면 CAS 요청이 `403` 으로 실패하던
문제.** SigV4 CanonicalURI 를 S3 표준(boto3 와 동일)으로 인코딩합니다. 예전에는 실제 전송 경로는
인코딩되는데 서명은 원본 경로를 써서 어긋났고, 그런 이미지를 참조하는 샘플이 `flush()` 의 CAS
확인 단계에서 전부 실패했습니다. `/` 와 비예약 문자는 보존하고 나머지는 `%XX` 로 바꿉니다
(공백·`+`·`#`·`%`·한글 포함). HEAD·GET·PUT 모두 같은 서명을 쓰므로 함께 고쳐집니다.

- 함께 바뀐 것: 이미지 참조로 **인코딩된 URL**(`https://cas/bkt/a%20b.png`, `s3://bkt/a%20b.png`)을
  넘기면 `%XX` 를 풀어 원래 key(`a b.png`)로 씁니다. 서버가 key 에 `%` 를 금지하므로 모호하지
  않습니다. 풀지 않으면 위 인코딩과 겹쳐 `%2520` 이 되어 엉뚱한 객체를 찾습니다. `backfill_dims()` 가
  샘플의 `image_url` 을 해석할 때도 같은 규칙이 적용됩니다.

**annotation 을 타입 객체로 로드·편집·저장하는 경로를 더합니다** — `ds.load_sample(sample_id)`.
dict 를 손으로 조립하지 않고 `AnnotatedSample` → 그룹 → `Instance` → component(`Label`)로 다루고,
저장할 때 한 번 검증합니다.

```python
ds = nx.Dataset.load_or_create("seatbelt", version="v1",
                               group_kinds={"seatbelt_gt": "group",
                                            "SBD_HumanBbox_Detections": "container"})

s = ds.load_sample(sample_id)
s["seatbelt_gt"][0].get_component("bounding_box").rect = [0.1, 0.1, 0.4, 0.8]
s.meta["width"] = 1280
s.save()          # 검증 후 바뀐 그룹·meta 키만 보낸다
```

- **그룹 종류는 선언으로만 정해집니다.** `ds.declare_group_kinds({...})` 또는
  `load_or_create(..., group_kinds={...})` 로 그룹마다 `"group"`(한 instance 에 component 여럿) 또는
  `"container"`(행마다 component 하나, 같은 타입)를 적습니다. 행의 모양으로 추론하지 않습니다 —
  component 가 하나뿐인 병합 그룹도 있기 때문입니다. **선언하지 않은 그룹은 `RawGroup` 으로 손대지
  않고 그대로 왕복합니다.** 타입 객체로 다룰 그룹만 선언하면 됩니다.
  선언은 서버에 저장되지 않고 핸들에 있으며, 그 핸들에서 만든 `fork()`·`clone()`·서브셋
  `to_version()` 의 새 핸들에는 복사되어 이어집니다. 선언은 누적되고, 값이 `"group"`/`"container"`
  가 아니면 `ValueError` 입니다(`load_or_create(group_kinds=)` 는 dataset·버전을 만들기 **전에**
  검사합니다). `load_sample` 은 그 시점의 선언을 씁니다 — 이미 연 샘플에는 나중 선언이 반영되지
  않습니다. 선언했더라도 값이 배열이 아닌 그룹은 `RawGroup` 으로 옵니다.
- **component 타입 9종**: `Detection`(`bounding_box`)·`Keypoint2D`·`Keypoint3D`·`Classification`·
  `ScalarValue`(`value`)·`VectorValue`(`values`)·`Cuboid3D`·`Polygon`·`Polyline`. 등록되지 않은 타입은
  `Label` 로 dict 를 그대로 보존합니다.
- **새 component 는 키워드로 만듭니다** — `Detection(rect=[...], label="Person", confidence=0.9)`.
  `type` 은 클래스가 채우고, 클래스가 모르는 필드(`rct=` 같은 오타)는 그 자리에서 `TypeError` 입니다.
  `Keypoint2D`/`Keypoint3D` 는 `num_keypoints` 를 생략하면 `x` 의 길이로 채웁니다. 값이 `None` 인
  키워드는 빼고 만듭니다. 목록에 없는 필드를 담아야 하면 wire dict 를 그대로 넘기는
  `Detection({"type": "bounding_box", ...})` 형태를 씁니다.
- 클래스와 `type` 이 어긋나면(`Detection` 인데 `"type": "polygon"`) `save()` 가 거부합니다.
- **검증은 `save()` 한 곳에서만 합니다.** 로드·객체 생성·속성 대입은 검증하지 않으므로 기존 데이터가
  그대로 열립니다. 검사는 **타입만** 봅니다 — 좌표가 0~1 을 넘거나(이미지 밖) visibility 가 0~3 밖이어도
  통과합니다. 거부하는 것은 다음이 전부입니다.
  - instance: `label` 필수(문자열), `track_id` 정수·`confidence` 숫자(있으면).
  - component: `bounding_box.rect` 숫자 4개, polygon 3점·polyline 2점 이상(짝수 길이의 숫자 목록),
    classification `label` 비어 있지 않은 문자열, keypoint 는 `x`·`y`(3D 는 `z` 도) 숫자 목록의 길이가
    서로 같아야 하고 `num_keypoints` 는 있을 때만 정수이고 그 길이와 같아야 합니다(`visibility` 도
    있을 때만 같은 길이·정수),
    cuboid 의 `center`·`dimensions` 숫자 3개씩(`rotation` 은 있을 때만 숫자 9개), value·values 의 숫자.
  - 구조: container 의 행당 component 1개·동일 타입, component 자리에 단수 `Label` 만(그룹·컨테이너
    중첩 금지), 그룹 행은 `Instance` 만(`Label`·dict 를 행으로 바로 넣으면 거부), meta 는 JSON 객체.
  실패하면 `NexusValidationError` 이고 서버로 아무것도 나가지 않습니다. **검증은 보내는 그룹에만
  합니다** — 손대지 않은 그룹은 깨져 있어도 저장을 막지 않고, meta 는 바뀐 경우에만 봅니다.
- instance 행의 객체가 아닌 값(예: `"occluded": true`)은 component 가 아니라 원문 그대로 보존하고
  검사하지 않습니다.
- **id 는 instance 에만 있습니다.** 있으면 형식(24-hex·UUID 등)을 검사하지 않고 그대로 보존하고,
  없으면 로드·생성 때 uuid4 hex 를 채웁니다(그 그룹을 저장하면 그 id 가 서버에 기록됩니다). component
  별 id 는 없습니다. 같은 id 가 여러 그룹에 있어도 객체는 그룹마다 따로이고 편집이 서로 전파되지
  않습니다.

**FiftyOne 호환 필드 함수를 더합니다** — `AnnotatedSample` 의 `get_field` / `set_field(create=)` /
`clear_field` / `merge` / `add_labels` / `copy`, 그리고 `s["meta"]` 대입. `copy` 를 뺀 나머지는 모두
제자리 수정이고 `save()` 로 저장하며, 저장할 때는 위와 같이 바뀐 그룹·meta 키만 나갑니다.

- `clear_field` 는 `None` 이 아니라 빈 컬렉션으로 되돌립니다(`"meta"` 는 저장된 키를 전부 지웁니다).
- `merge` 는 `Instance.id` 단위로 합치고(`merge_lists=True`), 선언 안 된 그룹은 통째 교체, `meta` 는 키
  단위입니다. 가져온 값은 복사하고, 실패하면 아무것도 바꾸지 않습니다.
- `add_labels` 는 id 가 겹치면 아무것도 붙이지 않고 `ValueError` 입니다.
- `copy` 는 저장되지 않은 복사본이라 `save()` 가 실패합니다.
- 리스트 대입·`add_labels` 로 만든 새 필드는 선언된 그룹 종류를 따릅니다. **선언하지 않은 새 필드는
  다음 `load_sample` 에서 `RawGroup` 으로 돌아옵니다.**
- `Label.id`·component 단위 id 는 없고(id 는 `Instance` 에만), 그룹은 `LabelGroup`/`LabelContainer`
  두 종류입니다(FiftyOne 의 이름 붙은 컨테이너 클래스는 두지 않았습니다).

**올리기 전에 볼 것**

- **`save()` 는 바뀐 그룹과 바뀐 `meta` 키만 보냅니다.** 안 바꾼 그룹·`meta` 키는 서버가 보존하므로,
  **양쪽 모두 `save()`(서버 `0.1.18` 이상)로 저장할 때는** 두 곳에서 같은 샘플의 **다른** 그룹을
  동시에 고쳐도 서로 지우지 않습니다. 같은 그룹을 동시에 고치면 나중 저장이 이깁니다. 한쪽이
  `save_annotation`/`patch_annotations`·CVAT `pull()`이거나 옛 서버라 `save()`가 통째 교체로
  폴백한 경우는 그 저장이 오래된 스냅샷 전체를 쓰므로, 그 사이 `save()`가 쓴 다른 그룹까지
  덮어씁니다.
- 바뀐 것이 없으면 `save()` 는 요청을 보내지 않고 0 으로 채운 보고서를 돌려줍니다. 저장에 성공하면
  그 상태가 새 기준이 되어, 다음 `save()` 는 그 뒤의 변경만 보냅니다.
- `meta` 의 키를 지우려면 `del s.meta[k]` 또는 `s.meta[k] = None` 으로 씁니다.
- **`save()` 는 바뀐 `meta` 키만 보내므로 안 바꾼 `meta` 는 보내지 않습니다**(통째 교체로 폴백할
  때도 입력에 없던 `meta` 는 넣지 않습니다 — 빈 `meta` 를 보내면 서버가 저장된 meta 를 지우기
  때문입니다). meta 가 없던 샘플에 키를 넣으면 그때 보냅니다.
- **부분 저장은 nexus-server `0.1.18` 이상이 필요합니다.** 그 이하 서버에서는 통째 교체로 저장합니다
  (이 경우 동시 편집 보호가 없습니다). `RuntimeWarning` 은 접속(클라이언트)당 첫 저장에서 한 번만 나고,
  그 뒤 같은 접속의 `save()` 는 경고 없이 바로 통째 교체합니다.
- **그룹 하나를 비우는 저장은 됩니다. 저장 결과 그 샘플의 인스턴스가 하나도 남지 않고 공유
  원본(base)이 있으면 서버가 409 로 거절합니다**(비우면 원본이 다시 보이기 때문입니다) — 이 버전에서
  그 샘플을 비우려면 버전에서 unlink 합니다.
- **기존 경로의 호출 방식과 반환값은 그대로입니다** — `get_sample()` 은 계속 평탄한 dict 를
  돌려주고 `get_annotation` / `save_annotation` / `patch_annotations` · 적재 경로의 시그니처와
  반환값도 같습니다. **하나 더해진 것은 경고입니다** — `save_annotation`/`patch_annotations` 에 그룹
  키가 하나도 없는 본문(`meta` 만, 또는 `{}`)을 넘기면 `RuntimeWarning` 을 냅니다(아래 서버 동작 변화
  때문에 "아무것도 안 바뀐다"가 조용히 넘어가지 않도록). **경고를 에러로 다루는 환경(`-W error`,
  pytest `filterwarnings = error`)에서는 meta 만 고치던 기존 스크립트가 멈출 수 있으니**, meta 만
  고칠 때는 `load_sample()`→`save()`(바뀐 키만 보냄)를 쓰거나 그 경고를 걸러 주십시오. 그리고
  **nexus-server `0.1.18` 이상을 상대할 때는 서버의 PUT 동작 자체가 바뀝니다**
  (SDK 를 올리지 않아도 서버가 `0.1.18` 이면 적용됩니다): 그룹 키를 하나도 안 보내면(`meta` 만
  남거나 `{}`) 이제 인스턴스가 무변경으로 남고(예전에는 전체가 지워졌습니다), 그룹을 실제로
  비우려면 빈 배열 `[]` 로 보내야 하며, 그렇게 보낸 그룹이 전부 비었는데 그 샘플에 다른 버전과
  공유하는 원본(base)이 있으면 서버가 409 를 줍니다(비우려면 버전에서 unlink). `0.1.16` 이하
  서버를 상대할 때는 예전 그대로(그룹을 하나도 안 보내도 전부 지움)입니다. `load_sample` 은
  annotation 전용 `GET` 을 쓰므로 **nexus-server `0.1.5` 이상**이 필요하고, `save()` 의 부분 저장은
  **`0.1.18` 이상**이 필요합니다(그 이하는 위처럼 통째 교체로 저장됩니다).

## 0.1.15

**외부 IdP(OIDC) 토큰으로 nexus 에 인증하는 경로를 더합니다** — `nx.connect(oidc=OidcAuth(...))`.
로봇 계정의 장수명 토큰 대신, 회전하는 짧은 OIDC 토큰을 매 요청 공급할 수 있습니다. `CasSts` 와
대칭입니다(CAS 축의 `token_file`/`token_provider` 를 nexus 인증에도 줍니다).

```python
# 쿠버네티스: kubelet 이 갈아 끼우는 projected ServiceAccount 토큰 파일.
nx = nexus.connect(oidc=nexus.OidcAuth(token_file="/var/run/secrets/tokens/nexus"))
# Keycloak 등: 코드가 유효한 토큰을 가져오는 콜러블.
nx = nexus.connect(oidc=nexus.OidcAuth(token_provider=lambda: keycloak.access_token()))
```

- 서버가 등록된 발급자의 OIDC 토큰을 요청마다 직접 Bearer 로 받습니다(교환 없이). 만료가 가까우면
  SDK 가 출처에서 다시 가져오고, 놓쳐서 `401` 이면 한 번 더 가져와 재시도합니다.
- `email`/`password`·`robot_token` 과는 함께 줄 수 없습니다(`ValueError`) — 셋 다 로그인을
  대체합니다. `cas_sts`(CAS 축)와는 함께 씁니다.
- 이 경로에는 `refresh`·비밀번호 변경·계정 삭제가 없습니다(서버가 OIDC 요청에 `403`). 신원은
  관리자가 `POST /api/v1/admin/oidc-identities` 로 명시 등록합니다.
- **부가 기능입니다** — 정적 키·로봇 토큰·STS 경로는 그대로입니다. 올리지 않아도 동작이 바뀌지
  않습니다.

## 0.1.14

**호환성(중요): CAS 자격증명을 nexus 에서 자동으로 받아 오지 않습니다.**

nexus 가 CAS 자격증명을 발급하지 않게 되면서(브로커 경로 폐지) SDK 도 요청하지 않습니다.
**자격증명 없이 `nx.connect()` 하던 설치본은 이 판으로 올리십시오** — 발급 경로를 지운 서버 판에서는
`0.1.13` 이하가 접속에 실패합니다. 이 판은 브로커를 쓰던 서버와 걷어낸 서버 양쪽에서 동작합니다.

**올리기 전에 볼 것**

- **설정 파일(`~/.int2nexus/settings.json`)에 자동 발급으로 깔린 `cas_key_id`/`cas_secret` 가 있으면
  바꾸십시오.** 그 값은 `0.1.13` 이하가 만료 시 스스로 갱신해 주던 것인데 이제 갱신 경로가 없습니다.
  두 값이 다 있으므로 **접속 시점에는 경고가 나지 않고**, 만료된 뒤 첫 CAS 호출에서 `403` 으로
  드러납니다. CAS 운영자에게 받은 키로 바꾸거나 STS 모드로 옮기십시오.
- **`CAS_KEY_ID` 나 `CAS_SECRET` 중 한쪽만 설정한 배포는 동작이 달라집니다.** `0.1.13` 이하는 이때
  발급이 일어나 두 값이 함께 채워져 요청이 서명됐습니다. 이제는 경고가 뜨고 **서명 없이 나갑니다.**
- **기본 region 이 아닌 배포는 `cas_region`(또는 `CAS_REGION`)을 직접 주십시오.** 발급 응답이 이 값을
  채워 주던 경로가 없어졌습니다. 틀리면 서명이 맞지 않아 계속 `403` 입니다.

**변경**

- `nx.connect()` 가 `POST /api/v1/auth/cas-credentials` 를 부르지 않습니다. 자격증명은 인자 ·
  환경변수(`CAS_KEY_ID`/`CAS_SECRET`) · 설정 파일 중 하나로 직접 주거나, 스스로 갱신하는 STS 모드
  (`cas_sts=CasSts(token_file=...)`, `0.1.12`+)를 쓰십시오.
- **자격증명이 하나도 없으면 경고합니다.** 접속 자체는 그대로 되고 CAS 요청이 서명 없이 나갑니다 —
  CAS 가 익명 읽기를 허용하지 않는 배포에서는 첫 CAS 호출이 `403` 입니다. 이전 판은 이 자리에서
  자동 발급을 받았으므로 조용히 넘어갔습니다.
- **`403` 에 자격증명을 갈아 끼우지 않습니다.** 갱신할 곳이 없습니다. 만료 · 폐기된 정적 키는 새 값을
  주어야 풀리고, 에러 메시지가 그것을 짚습니다(이전 문구는 「`cas_key_id` 없이 `nx.connect()` 를 불러
  SDK 가 발급 · 갱신하게 하라」였는데, 되지 않는 일을 시키는 안내였습니다). 스스로 갱신하는 것은 STS
  모드뿐이고 그쪽은 그대로입니다.
- **`NexusClient.issue_cas_credentials()` 를 제거했습니다.** 남겨 두면 지금은 `503`, 서버가 경로를
  지운 뒤에는 `404` 만 내는 메서드가 됩니다.
- **`CasClient` 의 `on_forbidden` 인자를 제거했습니다.** `CasClient` 를 직접 만들어 쓰는 코드가
  그 인자를 주면 `TypeError` 입니다.
- `nx.connect(save_cas_credentials=...)` 인자는 시그니처 호환을 위해 남아 있지만 아무 일도 하지
  않습니다. `True` 로 주면 경고합니다(STS 모드에서도 경고합니다) — 그 값을 켜 둔 코드는 자격증명이
  파일에 남는 것을 전제하고 있으므로 조용히 무시하지 않습니다.
- 「서버에 CAS 관리 자격증명이 구성되지 않아…」로 시작하던 `503` 안내 문구를 걷었습니다. 그 상태를
  만드는 설정이 서버에서 없어졌습니다.

**필요한 서버 버전** — 없습니다. 이 판은 어떤 nexus 판과도 동작합니다.

## 0.1.13

**변경**

- **서명을 요구하는 CAS 에서 `Dataset.to_df()` 가 `403` 이던 것을 고쳤습니다.** annotation 스냅샷(manifest 와 샤드 NDJSON)을 CAS 자격증명으로 서명해 받습니다. `0.1.12` 이하는 서명 없이 받아, 익명 읽기를 받지 않는 CAS 에서는 seal 은 성공하고 `to_df()` 만 `403`(메시지 「nexus는 CAS 익명 읽기를 전제로 하므로 버킷 정책을 확인하세요」)이었습니다. **CAS 버킷을 익명 읽기로 열 필요는 없습니다** — nexus 가 발급하는 CAS 자격증명은 역할과 무관하게 읽기(`GetObject`)를 갖습니다.
- annotation 을 CAS URL(`s3://`·`http(s)://`)로 넘긴 `Sample` 도 같은 원인으로 `flush` 에서 `403` 이었습니다. 같이 고쳤습니다.
- 스냅샷 URL 의 호스트는 쓰지 않고 `nx.connect` 의 `cas_url` 로 받습니다. 서버의 `cas.baseUrl` 이 클러스터 내부 주소여도 클러스터 밖에서 `to_df()` 를 부를 수 있습니다. 두 주소가 다르면 에러 메시지에 둘 다 나옵니다.
- 받은 스냅샷을 seal 때 기록된 BLAKE3 해시와 대조하고, 다르면 `NexusError` 입니다. 해시가 기록되지 않은 버전은 대조하지 않습니다.
- **동작 변경: 해시가 맞지 않는 버전의 `to_df()` 는 이제 실패합니다.** `0.1.12` 이하는 대조하지 않았으므로, seal 뒤 그 CAS 키의 객체가 다른 내용으로 바뀐 버전에서는 박제된 것과 다른 스냅샷을 에러 없이 돌려줬습니다. 이제 그런 버전은 `해시가 seal 때 기록된 값과 다릅니다` 로 멈추고, 메시지에 기대값·실제값·요청한 URL 이 나옵니다. 우회하는 옵션은 두지 않았습니다 — 받은 데이터가 그 버전이라는 보장이 없기 때문입니다.
- `Dataset` 을 CAS 클라이언트 없이(`cas=None`) 직접 만들었으면 `to_df()` 와 CAS URL annotation 적재가 `NexusError`(`CAS 클라이언트가 없어 …`)로 실패합니다. `0.1.12` 이하의 `to_df()` 는 CAS 클라이언트를 쓰지 않아 이 경우에도 동작했습니다. `nx.connect()` 나 `Dataset.load_or_create()` 로 만든 핸들은 해당하지 않습니다.
- 스냅샷을 받다가 `403` 이면 CAS 의 거부 사유(정책 거부 `AccessDenied`, 폐기·만료 `InvalidAccessKeyId`)가 메시지에 붙습니다.
- CAS 자격증명 없이 접속했으면 종전처럼 서명 없이 요청합니다.

위 변경 말고는 `0.1.12` 와 같습니다.

**필요한 서버 버전**

```
기능                          nexus-server           cas-server
to_df 서명 · 해시 대조          무관                   무관
그 밖의 기능                   SDK 0.1.12 와 같음      SDK 0.1.12 와 같음
```

## 0.1.12 이하

`0.1.12` 이하의 변경은 [nexus-server 차트 CHANGELOG](https://github.com/int2nexus/cas-server/blob/main/charts/nexus-server/CHANGELOG.md) 에 서버 릴리스와 함께 적혀 있습니다. 모든 버전에 노트가 있지는 않습니다 — `0.0.1`~`0.0.4`·`0.1.0`·`0.1.6`·`0.1.7` 은 그곳에도 언급이 없습니다.
