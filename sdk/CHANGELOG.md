# int2nexus-sdk 변경 이력

`int2nexus-sdk` 의 변경은 이 파일에 적습니다. 서버 이미지·차트와 따로 발행하고 따로 설치합니다.

```
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk==<버전>
```

`scripts/publish_sdk.py` 는 `sdk/pyproject.toml` 의 버전과 같은 `## <버전>` 절이 이 파일에 없으면
빌드하지 않고 멈춥니다. 최신 버전이 위로 오게 적습니다.

## 0.1.27

- **`Keypoint2D`·`Keypoint3D` 의 `visibility` 는 숫자 목록이면 받습니다.** 종전에는 정수만 받아 `1.8` 같은 소수가 든 값이 `visibility must be a list of ints` 로 거부됐습니다. 이제 정수와 실수를 모두 받고 값을 바꾸지 않고 그대로 보냅니다. 불리언·문자열·`None` 이 섞이면 종전처럼 `NexusValidationError`(`visibility must be a list of numbers`)이고, 길이 검사도 같습니다. 서버는 이 값을 해석하지 않고 저장합니다. CVAT 세션은 visibility 를 「프레임 밖」·「가림」 두 플래그로만 주고받으므로, 서버 `0.1.34` 이상에서 작업자가 플래그를 바꾸지 않은 점은 소수값이 그대로 남고 플래그를 바꾸거나 새로 그린 점은 0·1·2 로 적힙니다(`0.1.33` 이하 서버는 가져올 때 소수값을 정수로 바꿉니다).

## 0.1.26

- **`ds.seal(*, if_sealed="error", wait=600.0, description=, block=True)` 와 `NexusClient.seal(..., block=True)` 는 서버가 seal 을 작업 줄에 올려 202 로 답하면 끝날 때까지 기다립니다.** nexus-server `0.1.33` 부터 동시 seal 자리가 없으면 429 대신 202(`{"job", "version"}`, `Location: /api/v1/version-jobs/{id}`)를 줍니다. `block=True` 는 `GET /api/v1/version-jobs/{id}` 를 2 초 간격으로 물어 `done` 이면 버전을 다시 읽어 sealed 버전을 돌려줍니다. 기다리는 시간은 `wait` 초가 전부이고 429 로 기다린 시간과 한 예산입니다. 넘기면 `NexusVersionJobPending`(아래)이고 seal 은 서버에서 계속 돕니다. 작업이 `failed`·`cancelled` 면 `NexusError(status_code=409, server_message=작업 오류)` 입니다. 작업 조회가 404 이면(7 일이 지나 지워짐) 버전을 다시 읽어 sealed 면 끝난 것으로 보고 아니면 409 입니다. `block=False` 는 기다리지 않고 202 본문을 그대로 돌려줍니다(`ds.seal` 은 이때 핸들의 길이 기억을 갱신하지 않습니다). 200 응답과 `0.1.32` 이하 서버(429 `seal_busy`/`seal_in_progress` 를 `Retry-After` 대로 `wait` 까지 다시 보냄)의 동작은 종전과 같습니다. `if_sealed="ignore"` 는 202 뒤 작업이 `done` 이면 sealed 버전을 돌려주고, 작업이 실패하면 예외입니다. 곧바로 돌던(200·201 을 기다리던) seal·fork 가 관리자 취소로 멈추면 `NexusError(status_code=409)` 이고 `code` 가 `"job_cancelled"` 입니다 — 버전이 draft 로 남으므로 `if_sealed="ignore"` 여도 예외입니다.
- **`ds.fork(new_version, ..., wait=600.0, block=True)`·`Dataset.load_or_create(..., fork_from=, wait=600.0, block=True)`·`NexusClient.create_version(..., wait=600.0, block=True)`** — nexus-server `0.1.33` 부터 새 버전 만들기(fork)가 작업 줄에 올라 202 를 주면 `block=True` 는 작업이 `done` 이 될 때까지 `wait` 초 안에서 기다린 뒤 draft 버전을 다시 읽어 돌려줍니다(`fork`·`load_or_create` 는 그 버전의 핸들). 넘기면 `NexusVersionJobPending`, 실패·취소는 `NexusError(status_code=409)`, 작업 조회 404 는 버전이 draft 이면 끝난 것으로 봅니다. `block=False` 면 `create_version` 은 202 본문을, `fork`·`load_or_create` 는 기다리지 않고 핸들을 돌려줍니다 — 그 버전은 준비 중일 수 있습니다. 201 과 `0.1.32` 이하 서버는 종전과 같습니다. 새 버전이 이미 있어도 `preparing` 이면 — 앞선 호출이 `NexusVersionJobPending` 으로 끝났거나 `block=False` 였던 버전 — `block=True` 인 `load_or_create`·`fork` 는 그 버전의 작업(버전 응답의 `job`)을 `wait` 초까지 기다린 뒤 draft 핸들을 돌려줍니다(실패·취소 409, 시간 초과 `NexusVersionJobPending`). `block=False` 는 기다리지 않고 핸들을 돌려주므로 그 핸들로 쓰기를 하면 서버가 409(`version_preparing`)입니다. 만들기에 실패한 버전(`failed`)을 만나면 어느 쪽이든 `NexusError(status_code=409)` 입니다. `NexusClient.wait_existing_version(dataset_id, version_row, wait=)` 가 이 대기를 합니다.
- **`nx.NexusVersionJobPending`** — `NexusError` 의 하위입니다. seal·fork 작업이 `wait` 안에 끝나지 않았을 때 나며 `job_id` 와 마지막으로 읽은 작업 dict `job`(`state`·`queue_position`·`stage`·`progress_done`/`progress_total` 등)를 싣습니다. 작업은 서버에서 계속 돌므로 `client.get_version_job(job_id)` 로 다시 확인하거나 `if_sealed="ignore"` 로 다시 호출합니다. `status_code` 는 없습니다.
- **`NexusClient.get_version_job(job_id)`** — `GET /api/v1/version-jobs/{job_id}` 로 작업 하나(`state` 는 `queued`·`running`·`done`·`failed`·`cancelled`)를 읽습니다. nexus-server `0.1.33` 부터이고, 없거나 7 일이 지나 지워졌으면 `NexusError(status_code=404)` 입니다. 연결 실패·502/503/504 는 다른 읽기와 같이 `retry_timeout` 안에서 다시 보냅니다.

## 0.1.25

- **호환성(중요): `ds.save_annotation(sample_id, annotation, *, replace_meta=False)` 는 `meta` 를 `replace_meta=True` 일 때만 보냅니다.** 종전에는 dict 에 `meta` 가 있으면 늘 보내 `samples.meta` 를 통째로 바꿨습니다. `samples.meta` 는 버전 격리가 없어 모든 버전이 함께 보는 값이고 `get_annotation()` 결과에 늘 들어 있어, 왕복만 해도 그 사이 다른 곳에서 바꾼 meta 를 되돌렸습니다. 이제 기본은 `meta` 를 빼고 보내며(서버는 `meta` 키가 없는 PUT 에서 meta 를 건드리지 않습니다), 빼고 보냈으면 핸들당 한 번 `RuntimeWarning` 을 냅니다. **meta 를 고치려고 `save_annotation` 을 쓰던 호출은 `replace_meta=True` 를 더해야 합니다** — 더하지 않으면 경고만 나고 meta 는 바뀌지 않습니다. meta 의 키 일부만 고치려면 `merge_annotation()`·`set_values()` 를 쓰십시오. `patch_annotations()` 는 종전대로 dict 의 `meta` 를 보냅니다. 부분 저장이 없는 nexus-server `0.1.17` 이하에서 `AnnotatedSample.save()` 가 통째 PUT 으로 내려갈 때도 고친 meta 가 있을 때만 meta 를 싣습니다(종전에는 받을 때의 meta 전체를 다시 썼습니다).
- **행 모양 dict 의 저장 거부** — `save_annotation()`·`patch_annotations()`·`merge_annotation()` 은 `sample_id`·`split`·`tags`·`created_at`·`image_url`·`thumbnail_url` 가운데 하나를 배열이 아닌 값으로 가진 dict 를 보내지 않고 `NexusValidationError` 를 냅니다(`patch_annotations` 배치에서는 그 건의 실패). `get_sample()`·`samples()` 의 행을 그대로 넘기면 nexus-server `0.1.29` 이하는 그 코어 키들을 그룹으로 세어 그 버전의 그룹을 행의 그룹으로 바꿨습니다(annotation 없는 행이면 전부 지웠습니다). `0.1.30` 은 그런 요청을 400 으로 거절합니다. 그룹 값은 늘 배열이므로 `tags` 같은 이름의 그룹을 담은 `get_annotation()` 결과는 그대로 통과합니다.
- **`nx.SampleSummary`** — `ds.samples(include_annotations=False)` 의 행은 이제 `dict` 의 읽기 전용 하위 타입 `SampleSummary` 입니다. 값을 바꾸는 메서드(`row[k] = v`·`update`·`pop` 등)는 `TypeError` 이고 고쳐 쓸 사본은 `dict(row)` 로 만듭니다. **읽기 전용은 최상위 키뿐입니다** — 안쪽 `meta`(dict)·`tags`(list)는 일반 객체라 `row["meta"]["k"] = v` 는 막지 않고 원래 행을 바꿉니다(`isinstance(row["meta"], dict)`·`json.dumps(row)` 를 깨지 않으려고 감싸지 않았습니다). `dict(row)` 는 얕은 사본이므로 안쪽까지 고칠 사본은 `copy.deepcopy(dict(row))` 입니다. 저장 메서드 셋과 `AnnotatedSample.from_row()` 는 `SampleSummary` 를 받지 않습니다(`TypeError`, `patch_annotations` 배치에서는 그 건의 실패) — 그 행에는 그룹이 없어 그룹을 더해 저장하면 서버의 그 그룹을 덮습니다. **호환성:** 이 행을 제자리에서 고치던 코드는 `dict(row)` 로 사본을 만들어야 합니다. `include_annotations=True`(기본) 행은 종전대로 일반 `dict` 입니다.
- **그룹 종류의 dataset 저장** — `ds.declare_group_kinds()`·`Dataset.load_or_create(group_kinds=)` 가 그룹 종류를 dataset 에 저장하고(`PATCH /datasets/{id}/group-kinds`), `Dataset.load_or_create()`·`Dataset.open()` 이 핸들을 열 때 저장된 종류를 읽습니다(`GET`). 한 번 선언하면 그 dataset 을 여는 모든 스크립트가 같은 종류로 읽습니다. 저장하지 못하면 — 경로가 없는 nexus-server `0.1.28` 이하, 쓰기 권한이 없는 `viewer`(403), 서버가 받지 않는 키(`meta`·코어 키 `tags`·`split`·`sample_id`·`created_at`·`image_url`·`thumbnail_url`, 빈 키·앞뒤 공백·128 자 초과) — 그 핸들에만 두고 핸들당 한 번 `RuntimeWarning` 을 냅니다. 받지 않는 키는 보내지 않고 나머지 키만 저장합니다(섞어 보내면 서버가 요청 전체를 400 으로 거부합니다). 키가 256 개를 넘으면 256 개씩 나눠 보냅니다. 그 밖의 서버 오류는 `NexusError` 이고 그 요청의 키는 핸들에도 넣지 않습니다. 핸들을 열 때 저장된 종류를 읽지 못하면(재시도가 끝난 5xx·연결 실패 등) 열기를 막지 않고 `RuntimeWarning` 과 함께 저장된 선언 없이 엽니다. 서버가 준 값 중 이 SDK 가 모르는 종류는 무시합니다(그 그룹은 `RawGroup`). fork·clone·`Subset.to_version` 의 새 핸들은 저장된 종류를 읽고 그 위에 원본 핸들의 선언을 얹으며, 다시 저장하지 않습니다(fork 는 같은 dataset 이고 clone job 은 서버가 복사합니다). 핸들을 여는 데 요청이 하나 늘었습니다. `NexusClient.get_group_kinds(dataset_id)`·`patch_group_kinds(dataset_id, kinds)` 가 두 경로를 감쌉니다(값 `None` 은 그 키를 지웁니다). nexus-server `0.1.29` 부터. `load_or_create(group_kinds=)` 는 열 때 읽은 저장값과 다른 키만 보내므로 이미 같은 값이면 요청이 없고(`viewer` 가 열어도 경고가 나지 않습니다), 저장값을 읽지 못했으면 전부 보냅니다. **저장값과 다른 선언은 그 dataset 의 전역 값을 덮습니다** — 그 dataset 을 여는 다른 스크립트도 그 뒤로 그 종류로 읽습니다. `declare_group_kinds()` 는 저장 응답(저장 뒤 dataset 전체)으로 핸들을 갱신하되 그 핸들이 선언한 키는 저장하지 못해 핸들에만 둔 것까지 핸들 값이 이깁니다(열 때 읽은 값보다 핸들 선언이 이기는 것과 같은 규칙) — 롤링 교체 중 옛 파드에서 404 로 핸들에만 둔 키를 다음 선언의 응답이 다른 값으로 바꾸지 않습니다.
- **호환성: annotation 쓰기의 서버 400 은 `NexusValidationError` 입니다** — `ds.save_annotation()`·`ds.patch_annotations()`·`ds.merge_annotation()`(그리고 그것을 쓰는 `AnnotatedSample.save()`)에서 서버가 400 을 주면 일반 `NexusError` 대신 그 하위인 `NexusValidationError`(`status_code=400`, `server_message`·`code` 는 서버 응답 그대로)를 냅니다. nexus-server `0.1.30` 부터 이 경로는 파서가 버릴 그룹·원소(배열 아닌 그룹·`null`·객체 아닌 원소·문자열 `label` 없는 원소)와 공통 필드(`id`·`track_id`·`confidence`)의 타입·범위 위반을 요청 전체 400 으로 거절하고 아무것도 쓰지 않으며, 응답의 `skipped` 는 늘 0 입니다. 정수 `id`(COCO 식 `"id": 123`)·실수 `track_id`(`3.0`)·문자열 `confidence` 도 400 이고, 적재 본문을 그대로 다시 보내면서 최상위에 배열이 아닌 키(`"image_id"` 등)가 있어도 400 입니다. `nx.Instance(id=...)` 에는 문자열을 넣으십시오. SDK 가 보내기 전에 거르는 형식 오류(행 모양 dict)와 같은 예외로 잡힙니다. `NexusError` 의 하위라 `except NexusError` 와 `status_code == 400` 으로 가르던 코드는 그대로 동작하고, `except NexusValidationError` 로 SDK 쪽 거부만 잡던 코드는 서버 거절도 함께 잡습니다. `0.1.29` 이하 서버는 버릴 그룹·원소를 버리고 저장한 뒤 `skipped` 로 세며(그때는 종전대로 `RuntimeWarning`, 교체로 그만큼 기존 인스턴스가 지워진 것입니다), 공통 필드의 형식 위반은 그 필드를 값 없음으로 저장하고 경고하지 않습니다(`PATCH` 의 배열이 아닌 그룹은 그때도 400 이었습니다).
- **`ds.patch_annotations({...})` 배치의 실패 경고** — 기본 `strict=False` 에서 실패한 건이 있으면 호출당 한 번 `RuntimeWarning` 을 냅니다(실패 수, 앞 다섯 sample_id, 첫 실패의 메시지 앞 200 자). 종전에는 결과의 `ok=False` 로만 알려 반환값을 보지 않는 스크립트에서 조용히 지나갔습니다. 반환값(입력 순서의 `IngestResult` 목록)은 같고, 서버 400 은 그 건의 `status_code=400` 실패입니다. `strict=True` 는 종전대로 `NexusBatchError`, 401·403 은 종전대로 `strict` 와 무관하게 `NexusError` 입니다.
- **`Instance.from_row` 의 컴포넌트 판정** — `type` 문자열이 있는 객체만 컴포넌트이고 나머지 객체(`"attributes": {...}` 등)는 extras 로 그대로 보존합니다. 서버 스키마 관측과 같은 규칙입니다. 종전에는 객체면 모두 컴포넌트로 보아, `type` 없는 객체가 든 그룹을 고쳐 저장하면 `component missing 'type'` 으로 막혔습니다. 저장되는 JSON 은 같습니다. **호환성:** 그런 객체를 `inst.components[...]`·`inst.get_component(...)` 로 읽던 코드는 이제 `inst.extras[...]` 로 읽어야 합니다(`components` 에서는 `KeyError`·`None`).
- **호환성: `ds.distinct(field, *, fast=False, **filters)` 의 기본은 걸린 샘플을 훑습니다.** 종전에는 필터가 없는 `meta.<키>` 에서 서버 histogram 을 써서, 타입이 섞인 필드가 문자열(`"3"`·`"true"`)로 나오고 필터를 주면 원래 타입으로 나와 필터 유무로 결과가 달랐습니다. 이제 필터와 무관하게 원래 타입이고 처리 시간은 샘플 수에 비례합니다(`values()` 와 같은 읽기). `fast=True` 는 종전 histogram 경로입니다(필터가 없는 `meta.<키>` 만, 섞인 타입은 문자열).
- **`ds.sort_by(field, reverse=False, *, page_size=1000, **filters)`** — 필터에 걸린 샘플을 `field` 값 순서로 `AnnotatedSample` 로 하나씩 냅니다. 서버 정렬이 아닙니다 — `(sample_id, 값)` 만 먼저 projection 으로 모아 클라이언트에서 정렬하고 `page_size` 청크마다 본문을 받습니다(`shuffle()` 과 같은 구조, id·값 목록은 메모리에 둡니다). `field` 는 `"meta.<키>"`·`"split"`·`"sample_id"` 이고 `"tags"` 는 `ValueError` 입니다. 값이 없거나 `None` 인 샘플은 `reverse` 와 무관하게 맨 뒤이고, 같은 값끼리와 맨 뒤끼리는 `sample_id` 오름차순입니다. 값 종류(숫자·문자열·불리언)가 섞이거나 배열·객체 값이 있으면 본문을 받기 전에 `ValueError` 입니다(정수와 실수는 같은 숫자). 필터는 `iter_samples()` 와 같고 정렬 전에 적용합니다. 본 조회에는 draft 대량 읽기 표시(`x-nexus-bulk-read: 1`)가 붙습니다.
- **`ds.to_df(..., sample_fields=False)`** — `True` 면 `tags`·`split` 열을 더합니다. sealed 버전은 **seal 시점 값**입니다 — seal 이 CAS 에 쓴 메인 manifest 를 `GET .../manifest` 의 `main_manifest`(nexus-server `0.1.29` 부터, 그 이하는 `NexusError`)로 찾아 읽습니다. CAS 키에 `manifests/` 읽기 권한이 필요하고(403 이면 메시지에 적습니다), 메인 manifest 는 버전 전체를 담은 JSON 하나라 `chunksize` 여도 통째로 받습니다. 받은 본문의 BLAKE3 가 기록된 해시와 다르면 — nexus-server `0.1.23` 이하가 seal 한 버전의 이름 기반 manifest 가 같은 이름의 다른 seal 로 덮인 경우 — 열을 `None` 으로 두고 `RuntimeWarning` 을 냅니다. draft 버전은 explorer 의 지금 값입니다. 지문(`df.attrs["nexus_fingerprint"]`)은 이 열 없이 계산해 `fingerprint()` 와 같습니다. `tags`·`split` 이라는 이름의 그룹과 겹치면 받기 전에 `ValueError` 입니다 — `groups=` 가 없으면 dataset 에서 관측된 그룹 키(`/schema`)로 판정해 요청이 하나 늘고, draft·sealed 가 같은 결과입니다(`groups=` 로 그 그룹을 빼십시오). 기본(`False`)은 종전과 같고 메인 manifest 를 읽지 않습니다.
- **롤링 교체 중 옛 파드 응답의 경고 문구** — `ds.count_values()` 는 응답 헤더 `X-Nexus-Version`(nexus-server `0.1.29` 부터)으로 응답한 파드의 판을 봅니다. 헤더가 없고 정확히 500 개로 잘렸으면 nexus-server `0.1.23` 이하 파드가 옛 상한에서 자른 것으로 경고 문구에 적고, 「못 셌음」이 20 초 안에 왔으면 제한이 3 초인 옛 파드로 추정해 `NexusError` 문구에 적습니다(헤더가 있으면 새 파드라 그렇게 적지 않습니다). `ds.set_values()` 는 일괄 경로가 없어(405) 샘플별 PATCH 로 내려갈 때 호출당 한 번 `RuntimeWarning` 을 냅니다 — 그 청크는 요청 단위 전부 또는 없음이 아니라 샘플 단위로 적용되고 멈추며, 거절이 `400 meta_write_rejected` 가 아니라 `404`·`409` 입니다.
- **`ds.create_annotation_session(extra_labels=)` 의 태그 항목** — nexus-server `0.1.30` 부터 `{"type": "tag", "label": "caption", "attribute": "text", "meta_key": "caption.text"}` 를 줄 수 있습니다. 샘플 `meta` 의 한 칸(`a` 또는 `a.b`)을 CVAT 의 이미지 단위 글 속성과 왕복시킵니다. 태그 항목은 세션당 하나이고 `attribute`·`meta_key` 가 필수이며, `group`·`components`·`keypoints`·`component_key`·`instance_label` 을 함께 주면 400, 최상위 `sequence_id`·`keypoint_info` 와 `/` 가 든 `label`·`attribute` 도 400 입니다. 세션을 만들 때 meta 값이 문자열이면 그 글로, 없거나 `None`·빈 문자열이면 빈 칸으로 채우고, 문자열이 아니거나 `a.b` 의 `a` 가 객체가 아니거나 CVAT 글 상한(4,096 자)을 넘으면 채우지 않고 세션 경고만 남습니다(그런 프레임에 새로 단 태그는 가져오지 않고 close 도 막지 않습니다). 가져올 때(`session.pull()`)는 CVAT 가 저장한 직전 값(기준)과 다른 프레임만 쓰며, 기준은 가져오기마다 옮겨집니다. **태그를 두고 글을 비우면 그 키를 지우고, 태그를 지운 프레임은 변경 없음으로 두고 경고만 남깁니다**(글을 지우려면 태그를 두고 글을 비웁니다). 세션이 열린 동안 meta 가 바뀌었는데 CVAT 에서도 바꿨으면 CVAT 값이 이기고 `warnings` 에 샘플 id 가 남으며, 쓴 샘플 수는 응답의 `updated_meta_samples` 입니다(0 이면 키가 없습니다). 반영하지 못한 글 칸 편집(같은 프레임에 값이 다른 태그 둘, 그 사이 쓸 수 없는 모양이 된 자리 등)이 남으면 `force` 없는 close 가 409 이고, 그 가져오기의 `warnings` 맨 앞에 `force=True` 로 닫는 방법이 적힙니다. 세션 도중 버전에서 빠지거나 삭제된 샘플의 글 칸 편집은 버리고 `warnings` 에 남기며 close 를 막지 않습니다. 같은 세션의 가져오기가 겹치면 태그 항목 유무와 무관하게 `session.pull()` 이 409(`import_in_progress`, `NexusError`)입니다.
- **`Subset` 설명 정정** — 「sealed version 위 필터의 결정성은 annotation·tags·split 필터에 한한다」고 적고 있었습니다. `tags`·`exclude_tags` 필터는 `meta` 필터처럼 샘플마다 하나뿐인 지금 값을 보므로 sealed 버전에서도 seal 뒤의 태그 변경을 따라갑니다. 동작은 바뀌지 않았고 설명만 고쳤습니다. seal 때 태그로 거르려면 `to_df(sample_fields=True)` 의 `tags` 열을 쓰십시오.

## 0.1.24

- **0.1.22 절 정정의 재정정** — 0.1.22 의 「0.1.21 절 정정」은 「태그는 스냅샷에 들어가지 않는다」고 적었는데, seal 이 CAS 에 쓰는 메인 manifest 를 빠뜨린 서술입니다. seal 시점의 `tags`·`split` 은 메인 manifest 에 샘플별로 남습니다. API 조회(`get_sample`·explorer·`iter_samples` 등)와 `to_df()` 결과에 태그 열이 없다는 것은 그대로라, 이 SDK 에서 sealed 버전의 태그는 여전히 현재 값입니다. nexus-server `0.1.29` 부터 `GET .../manifest` 의 `main_manifest` 가 메인 manifest 위치를 줍니다(이 SDK 는 아직 읽지 않습니다).
- **draft 대량 읽기 표시와 거절 문구** — annotation 을 싣고 explorer 를 페이지로 읽는 호출(draft `ds.to_df()`, `ds.fingerprint()` 의 explorer 읽기, `ds.iter_samples()`, `ds.samples()`(기본 `include_annotations=True`), `ds.shuffle()` 의 본 조회)에 헤더 `x-nexus-bulk-read: 1` 을 붙입니다. 버전 상태와 무관하게 붙이고 판정은 서버가 합니다. id·projection 만 읽는 호출(`include_annotations=False`, `values()`, `shuffle()` 의 id 수집)과 explorer 가 아닌 `Subset` 읽기에는 붙이지 않습니다. 운영자가 서버에서 draft 대량 읽기를 껐으면 draft 버전은 `403` 이고 `NexusError`(`code == "draft_bulk_read_disabled"`)의 메시지는 「운영자가 draft 대량 읽기를 껐습니다 — sealed 버전을 쓰십시오」입니다. 이 403 은 다시 보내지 않습니다. 옛 서버는 헤더를 무시하므로 동작이 같습니다. 껐을 때의 거절은 nexus-server `0.1.29` 이상입니다.

- **`nx.Mask(rle=, label=, confidence=)`** — 래스터 마스크 구성요소(`type: "mask"`)입니다. `rle` 은 COCO 압축 RLE `{"size": [높이, 너비], "counts": "<문자열>"}` 이고 `size` 는 픽셀 단위입니다. pycocotools 의 `encode` 가 주는 `bytes` `counts` 는 생성할 때 ASCII 문자열로 바꿉니다(dict 로 만들어도 같습니다). `counts` 에 정수 목록(비압축 RLE)을 주면 `validate()` 가 거부하므로 압축 문자열로 바꿔 넣으십시오. `validate()` 는 `size` 와 런 합계의 일치, 전경 픽셀 하나 이상, 넓이 5,000 만 화소 이하를 검사합니다. 이 SDK 에서 통과한 마스크는 서버가 CVAT 로 보낼 수 있는 모양입니다. CVAT 왕복은 nexus-server `0.1.29` 부터 되고, 옛 서버에도 저장은 됩니다(스키마에 없는 타입으로 취급될 뿐입니다). 디코더는 SDK 안에 있어 pycocotools 가 필요 없습니다.

- **`ds.set_assets(role, values, *, overwrite=False)`** — 이미 적재한 샘플에 에셋(예: 깊이 맵)을 붙입니다. `values` 는 `{sample_id: CAS ref}` 이고 ref 규칙은 `Sample(assets=)` 와 같습니다(`CasRef`·`s3://`·`http(s)://`, 로컬 경로와 `role="image"` 는 `ValueError`). 쓴 건수를 돌려줍니다. 이미 그 role 이 있는 샘플은 거절이고 `overwrite=True` 면 바꿉니다 — 옛 CAS 객체는 지우지 않습니다. 같은 값을 다시 보내면 거절이 아니라 변경 없음으로 세어지므로 중단된 호출을 그대로 다시 불러도 됩니다. 같은 값은 bucket·key 가 같고 ref 의 해시와 저장된 해시가 둘 다 있으면 그것까지 같은 것입니다(어느 한쪽이 없으면 bucket·key 만 봅니다) — `nx.upload(..., overwrite=True)` 로 같은 key 의 내용을 바꾼 뒤 그 `CasRef` 로 다시 붙이면 다른 값이라, `overwrite=True` 면 저장된 해시·크기를 고치고 아니면 거절입니다. 한 요청은 10,000 건 이하·본문 약 800 KB 이하로 자르고, 한 요청 안에서 하나라도 거절되면 그 요청은 아무것도 쓰지 않습니다(예외의 `code == "asset_write_rejected"`, `rejected: [{sample_id, role, reason}]`, 앞 요청들의 적용 건수 `applied`, `failed_sample_id`). sealed 버전은 `409` 이고, sealed 버전에 든 샘플의 에셋을 덮어쓰는 것도 거절됩니다. 에셋은 샘플에 붙어 있어 같은 샘플이 든 다른 버전에도 보입니다 — 버전마다 다른 에셋이 필요하면 clone 하십시오. 옛 서버에서는 `NexusError` 로 서버 판 요건을 알려 줍니다. nexus-server `0.1.29` 이상입니다.
- **`NexusClient.patch_asset_items(dataset_id, version, items, overwrite=False)`** — 위 서버 경로를 해석 없이 감쌉니다. 응답이 없는 실패는 자동으로 다시 보냅니다(같은 값이라 결과가 같습니다).
- **draft 버전의 `ds.to_df()`** — 종전에는 draft 에서 `NexusError` 였는데, 이제 explorer(`include_annotations=True`)를 1,000 행씩 읽어 seal 스냅샷과 같은 모양의 행(`sample_id`, `meta`, 그룹 키 배열)을 냅니다. explorer 에만 있는 `split`·`tags`·`created_at`·`image_url`·`thumbnail_url` 은 뺍니다. `groups=` 에 이 이름과 같은 그룹이 있으면 그 열은 `None` 입니다(explorer 행에서 그 이름은 코어 값이라 같은 이름의 그룹이 가려져 있습니다). `meta` 는 읽는 시점의 현재 값이고(sealed 는 seal 때의 사본), 읽는 동안의 편집이 섞일 수 있어 핸들당 한 번 `RuntimeWarning` 을 냅니다. `chunksize` 가 없으면 `sample_id` 오름차순으로 정렬해 sealed 와 같은 순서로 내고, `chunksize` 가 있으면 전부 모으지 않으려고 서버 순서(`sample_id` 내림차순) 그대로 청크를 흘립니다. `chunksize` 가 양수가 아니거나 `path` 와 함께 주면 서버를 부르기 전에 `ValueError` 입니다 — draft 에서 `to_df(chunksize=0)` 이 종전의 `NexusError` 에서 `ValueError` 로 바뀝니다. sealed 버전은 지금처럼 seal 스냅샷을 읽고 동작이 같습니다(`to_df()` 가 스냅샷을 읽는다는 앞선 항목들의 서술은 sealed 에 대해 그대로입니다). `chunksize` 가 없으면 결과 `df.attrs["nexus_fingerprint"]` 에 아래 지문을 싣습니다. 샘플 30 만 개(인스턴스 120 만 개) draft 버전의 `to_df()` 는 34~40 초, 같은 버전을 seal 한 뒤의 `to_df()` 는 22 초였습니다(서버·PostgreSQL 18·SDK 를 한 대 — 14 코어, 메모리 32 GB — 에서 잰 값, SDK 프로세스 메모리 증가 약 2 GB).
- **`Subset.to_df(groups=)` 의 빠진 그룹** — `groups=` 에 준 그룹이 어느 행에도 없으면 그 열을 `None` 으로 둡니다. 종전에는 열이 빠졌습니다. `ds.to_df(groups=)` 와 같은 모양입니다.
- **`ds.fingerprint(groups=None, *, source="auto")`** — 읽은 행의 지문을 `"nxfp1:" + blake3 hex` 문자열로 돌려줍니다(pandas 가 필요 없습니다). 행 순서와 키 순서를 보지 않고 `meta` 가 없는 것과 `{}` 를 같게 보므로, 같은 내용이면 출처와 무관하게 같은 값입니다. draft 에서 읽어 학습한 뒤 seal 한 버전의 지문과 견주면 읽은 내용이 seal 된 내용과 같은지 알 수 있습니다(그 사이 meta·annotation·샘플 구성이 바뀌었으면 다릅니다). `groups` 는 `to_df(groups=)` 와 같은 축약을 거친 행으로 계산합니다. `source="auto"` 는 sealed 면 seal 스냅샷, draft 면 explorer 를 읽고, `"snapshot"` 은 스냅샷만 읽어 draft 면 `NexusError`, `"explorer"` 는 sealed 에서도 explorer 를 읽습니다. sealed 의 `source="explorer"` 는 draft 경고를 내지 않습니다. explorer 의 `meta` 는 현재 값이라 seal 뒤 meta 를 고친 샘플이 있으면 스냅샷 지문과 다릅니다. 그 밖의 `source` 는 `ValueError` 입니다. 실제 CAS 를 쓴 시험 서버에서 세 버전(샘플 30 만 개 버전, 샘플 삭제·fork 뒤 annotation 교체·그룹 부분 저장·unlink·일괄 meta 쓰기를 거친 버전 둘)을 seal 한 직후 `snapshot` 과 `explorer` 지문이 같았고 행 단위 차이도 없었으며, seal 전 draft 에서 읽은 지문과도 같았습니다.
- **16 비트 그레이스케일 이미지의 썸네일** — `nx.upload` 가 만드는 썸네일이 `I;16`·`I;16L`·`I;16B`·`I;16N`·`I` 모드(깊이 맵 등)를 0 이 아닌 값의 2~98 백분위 구간을 1..255 로 선형 사상해 8 비트로 만듭니다(구간 밖은 클립, 0 은 검정 그대로). 종전에는 255 에서 잘려 mm 단위 깊이 맵이 거의 전부 흰색이었습니다. 유효값이 없으면 전부 검정이고, 구간 폭이 0 이면 유효값을 255 로 둡니다. 8 비트 이미지의 썸네일은 바뀌지 않습니다. 같은 내용을 다시 올리면 썸네일을 다시 쓰지 않으므로(`overwrite=True` 로 내용을 덮어쓴 경우만 다시 씁니다) 이미 올린 깊이 썸네일은 아래 `rewrite_thumbnails` 로 고치십시오.
- **`nx.rewrite_thumbnails(refs, *, workers=8, verbose=True)`·`ds.rewrite_thumbnails(role, **kw)`** — 이미 CAS 에 올라간 객체의 썸네일(`thumb/<key>`)을 조건 없이 다시 만들어 씁니다. 원본을 GET 해 썸네일을 만들고 기존 썸네일이 있어도 덮어쓰며 HEAD 는 하지 않습니다. `refs` 는 `CasRef` 또는 `s3://`·`http(s)://` URL 입니다. 같은 `(bucket, key)` 는 한 번만 처리합니다. 반환은 `{"written": 건수, "skipped": ["bucket/key", ...], "failed": {"bucket/key": 오류 문자열}}` 이고 키는 `"bucket/key"` 입니다 — 단 CAS 참조가 아닌 입력은 `failed` 의 키가 받은 입력 문자열(`str(입력)`)입니다. 이미지가 아니어서 썸네일을 못 만든 객체는 `skipped`, 읽기·쓰기 실패와 CAS 참조가 아닌 입력은 건당 격리되어 `failed` 에 담기며 배치를 중단하지 않습니다. `ds.rewrite_thumbnails(role)` 은 이 버전 샘플의 `role` 에셋(`assets[role]["cas_url"]`)을 모아 넘기고 그 role 이 없는 샘플은 건너뜁니다. 에셋 객체만 읽고 쓰며 카탈로그는 바꾸지 않습니다.

## 0.1.23

- **`nx.delete_dataset(name, *, confirm_dataset_name, delete_cas=None)`·`NexusClient.delete_dataset(dataset_id, *, confirm_dataset_name, delete_cas=False)`** — dataset 을 버전째 지웁니다(nexus-server `0.1.26` 부터, 그 이하 서버는 `405`). `confirm_dataset_name` 에 dataset 의 현재 이름을 정확히 주어야 하고(틀리면 `400`), sealed 버전이 있으면 `role=admin` 만 지웁니다(아니면 `409` 이고 아무것도 지우지 않습니다). seal 이 진행 중인 버전이나 열린 CVAT 편집 세션이 있어도 `409` 이고 아무것도 지우지 않습니다. `viewer`·로봇 계정은 `403` 입니다. `delete_cas` 는 `ds.delete()` 와 같습니다 — `nx.delete_dataset` 에서 `None` 이면 대화형으로 묻고 비대화형이면 CAS 파일을 보존합니다. 버전마다 따로 지우므로 dataset 전체로는 원자적이지 않습니다. 도중에 실패했거나 응답을 받지 못했으면 다시 부르면 남은 버전부터 지우고, 이미 다 지워졌으면 `404` 입니다(서버가 받았을 수 있는 실패는 SDK 가 자동으로 다시 보내지 않습니다). `nx.delete_dataset` 은 이름이 정확히 같은 dataset 이 없으면 요청 없이 `NexusError(404)` 입니다. 반환은 `{dataset_id, versions_deleted, samples_deleted, cas_objects_deleted}` 입니다.
- **`ds.values(field)`·필터를 건 `ds.distinct(field)`·`ds.shuffle()` 의 id 수집** — nexus-server `0.1.26` 의 explorer projection(`fields`)으로 샘플마다 그 필드 값만 받습니다. 종전에는 샘플마다 meta 전체와 이미지 URL 까지 받았고, 요청 하나에 1,000 개였습니다. 이제 요청 하나에 최대 10,000 개이고, 값이 긴 필드는 서버가 페이지를 짧게(약 8 MiB 이하) 자르므로 요청 수가 그만큼 늘어납니다. 짧은 페이지를 받으면 다음 요청의 개수를 그 두 배(최소 100)로 줄이고, 꽉 찬 페이지 뒤에는 두 배로 늘립니다 — 값이 큰 필드에서 서버가 만들고 버리는 행을 줄이려는 것입니다. 서버가 마지막 페이지라고 알리면(응답 헤더 `X-Nexus-Page-End: 1`) 끝에 빈 페이지를 확인하는 요청을 보내지 않습니다. 결과(값·순서)는 종전과 같습니다. 서버가 `0.1.25` 이하면 페이지마다 응답 모양으로 알아보고 그 페이지는 종전처럼 「요청한 개수(최대 1,000)보다 짧으면 끝」으로 봅니다 — 롤링 교체 중 두 판의 파드가 번갈아 답해도 빠지는 샘플이 없습니다.
- **`NexusClient.explore_samples(..., fields=)`** — explorer projection 을 그대로 감쌉니다(nexus-server `0.1.26` 부터). 행은 `{"sample_id": .., "<필드>": 값}` 이고, **응답이 `limit` 보다 짧아도 끝이 아니므로** 빈 페이지가 올 때까지 마지막 `sample_id` 를 `cursor` 로 넘기십시오(`offset` 으로 넘기면 잘린 행을 건너뜁니다). 그 이하 서버는 `fields` 를 무시하고 행 전체를 줍니다.
- **`NexusClient.explore_samples_page(...)`** — `explore_samples` 와 같은 인자로 `(행, 마지막인가)` 를 돌려줍니다. nexus-server `0.1.26` 은 projection 의 마지막 페이지에 `X-Nexus-Page-End: 1` 을 붙이고, 이 메서드가 그것을 `True` 로 줍니다. 헤더가 없으면(옛 서버, 행 전체 explorer) `False` 이므로 빈 페이지까지 잇습니다.
- **`Dataset.load_or_create`·`nx.dataset_exists` 의 이름 조회** — nexus-server `0.1.26` 의 `name_exact`(이름 정확히 일치)로 dataset 하나만 묻습니다. 종전 `load_or_create` 는 dataset 목록 전체를 받아 이름을 비교했고, `dataset_exists` 는 부분 일치 목록을 받았습니다. 결과는 종전과 같습니다. 서버가 `0.1.25` 이하면 `name_exact` 를 무시하므로 부분 검색 `name` 을 함께 실어 받은 목록에서 이름이 같은 것을 고릅니다. 이름에 역슬래시가 들어 있으면 `name` 을 싣지 않습니다(서버의 부분 검색이 역슬래시를 이스케이프로 읽어 그 이름을 찾지 못합니다). 그런 이름은 `0.1.25` 이하 서버에서 목록 전체를 받습니다. 종전 `dataset_exists` 는 그 서버에서 역슬래시가 든 이름이 있어도 `False` 였습니다.
- **`NexusClient.list_datasets(..., name_exact=)`·`nx.list_datasets(..., name_exact=)`** — 이름이 정확히 같은(대소문자 구분) dataset 만 받습니다. nexus-server `0.1.26` 부터이고, 그 이하 서버는 이 인자를 무시해 걸러지지 않은 목록을 줍니다.
- **`ds.to_df()` 의 pandas 설치 안내** — pandas 가 없을 때의 `ImportError` 가 `pip install pandas` 를 안내합니다. 종전 안내
  `pip install 'nexus-sdk[pandas]'` 는 패키지 이름(`int2nexus-sdk`)이 다르고 `pandas` extra 도 없어 그대로 따라 하면 설치되지
  않았습니다.

## 0.1.22

**일괄 meta 쓰기, meta 필터 `exclude`·「값 없음」, `get_field_schema()` 의 int/float·배열·객체 구분, `len(ds)` 캐시, `count_values` 전수 모드를 더하고, 적재 본문에 `dataset_id` 를 싣습니다.** 새 기능은 nexus-server `0.1.24` 부터이고, 그 이하 서버에서 각 항목이 어떻게 동작하는지는 항목마다 적었습니다.

- **적재 본문의 `dataset_id`·재전송 기록 키** — `flush` 가 보내는 본문에 `dataset_id` 를 싣고, 재전송용 기록(미완 본문·`idempotency_key`)의 키를 `(dataset 이름, 버전)` 에서 `(dataset_id, 버전)` 으로 바꿉니다. nexus-server `0.1.24` 는 본문의 이름을 무시하고 id 로 찾으므로, 이름이 바뀐 dataset 에 응답을 못 받은 `flush` 를 다시 보내도 같은 기록을 찾아 `replayed` 로 끝나고, 다른 곳에서 이름이 바뀐 dataset 에도 `ds.refresh()` 없이 들어갑니다. 삭제된 dataset 의 id 면 그 항목이 `404` 로 실패하고(`flush` 결과의 실패 항목) 같은 이름으로 새로 만들지 않습니다. `nx.Dataset(client, cas, dataset_id, name, version)` 으로 직접 만든 핸들도 넘긴 `dataset_id` 를 실으므로, 그 id 가 틀리면 nexus-server `0.1.24` 에서 적재가 `404` 로 실패합니다(종전에는 이름으로 찾아 들어갔습니다). 이 효과는 **모든 파드가 `0.1.24` 로 교체된 뒤** 에 납니다. **주의:** nexus-server `0.1.23` 이하(롤링 교체 중 옛 파드 포함)는 `dataset_id` 를 읽지 않고 이름으로 찾습니다. 그래서 같은 핸들로 `ds.update(name=...)` 한 뒤 응답을 못 받은 적재를 다시 보내면 **옛 이름**의 본문이 나가 옛 이름의 dataset 이 새로 만들어집니다(그 이름이 이미 있으면 샘플이 그쪽으로 들어갑니다). 서버를 먼저 올리거나, 이름을 바꾸기 전에 `flush` 를 끝내십시오.
- **`ds.set_values("meta.<키>", {sample_id: 값})`** — 종전에는 샘플마다 요청 하나였는데, 이제 요청 하나에 최대 10,000 건을 본문 약 800 KB 이하로 묶어 씁니다(앞단 프록시의 본문 크기 상한을 넘지 않게 하려는 것입니다). 그래도 `413` 이면 그 요청을 반으로 나눠 다시 보내고, 한 건짜리가 `413` 이면 그 건에서 멈춥니다. 요청 단위로 전부 아니면 없음입니다 — 한 요청 안에서 하나라도 거절되면 그 요청은 아무것도 쓰지 않고, 앞선 요청은 되돌리지 않습니다. 거절은 `NexusError` 이고 `code == "meta_write_rejected"`, `rejected`(`[{sample_id, reason}]`, `reason` 은 `not_found`·`meta_not_object`)를 답니다. 저장된 meta 가 JSON 객체가 아닌 샘플은 이 거절(`400`)로 보고됩니다 — 종전 샘플별 경로는 같은 경우 `409` 였습니다. 예외에는 `applied`(앞서 적용된 건수)와 `failed_sample_id`(첫 거절 샘플, 거절 목록이 없으면 그 요청의 첫 샘플)가 붙습니다 — 남은 것만 다시 부르십시오. 응답을 받지 못한 실패는 자동으로 다시 보내고(같은 값이라 결과가 같습니다), 그래도 안 되면 `NexusError` 이며 그 요청의 샘플은 적용됐을 수도 있습니다. sealed 버전은 `409` 입니다. 서버가 일괄 경로를 모르면(`0.1.23` 이하, `405`) 그 호출만 종전처럼 샘플마다 보냅니다.
- **`ds.update_meta(meta, /, *, confirm=None, **필터)`** — 필터에 걸린 샘플 전부의 meta 에 같은 키들을 병합하고(값 `None` 은 그 키 삭제) `{updated, skipped_non_object_meta}` 를 돌려줍니다. `meta` 는 위치 인자 전용이고 비어 있지 않은 매핑이어야 합니다(아니면 `ValueError`). 필터는 `iter_samples` 와 같은 키워드이고(`include_annotations` 는 받지 않고 모르는 키워드는 `TypeError`), 필터를 주지 않으면 버전 전체가 대상입니다. 대상이 10,000 건을 넘으면 서버가 `409` 로 `confirm=<건수>` 를 요구합니다 — 건수는 `NexusClient.count_samples(dataset_id, version, filter, exact=True)`(`filter` 는 explorer 요청 본문 모양)가 돌려주는 `(개수, 정확한가)` 의 앞 값입니다. `sample_ids=[]` 는 서버를 부르지 않고 `{"updated": 0, "skipped_non_object_meta": 0}` 를 돌려줍니다. sealed 버전은 `409`, nexus-server `0.1.23` 이하는 `404` 입니다(샘플별로 내려가지 않습니다). 이 호출은 응답을 못 받으면 자동으로 다시 보내지 않습니다(서버에서는 적용됐을 수 있습니다) — 아주 큰 버전 전체에 쓰면 읽기 타임아웃(`NexusClient(timeout=...)`, 기본 120 초)을 넘을 수 있으니 필터로 좁히거나 `timeout` 을 늘리십시오.
- **meta 는 샘플에 붙어 있습니다** — `set_values`·`update_meta` 로 바꾼 값은 같은 샘플이 든 다른 버전의 조회에도 보입니다. sealed 버전의 seal 스냅샷(`to_df()` 가 읽는 것)은 바뀌지 않습니다.
- **`ds.get_field_schema()`** — 배열·객체 필드도 돌려줍니다(`list`·`object`·`any`, 스키마에 선언된 컨테이너 타입은 그 이름). 관측만 된 숫자 필드는 실수가 한 번이라도 들어왔으면 `float`, 정수만이면 `int` 이고, 한 번 `float` 로 관측된 필드는 값이 다시 정수만 남아도 `float` 입니다. `list` 의 원소 타입은 주지 않습니다. nexus-server `0.1.23` 이하는 종전과 같습니다(숫자는 늘 `float`, 배열·객체만 가진 필드는 없음).
- **meta 필터 `exclude`·선언 필드의 「값 없음」** — `meta={"<키>": {"type": "exclude", "value": [1]}}` 는 그 값을 가진 샘플을 빼고 **키가 없는 샘플은 남깁니다**. 숫자·불리언은 값으로 비교해 `1` 이 `1`·`1.0` 을 함께 빼고, 문자열은 텍스트로 비교합니다(`"1"` 은 숫자로 저장된 `1` 도 빼지만 `1.0` 은 빼지 않습니다). `update_meta` 같은 필터 쓰기에 걸면 그 키가 없는 샘플까지 대상입니다. `meta={"width": {"type": "ternary", "none": True}}` 는 서버 스키마에 선언된 필드에 값이 없는 샘플을 고릅니다(`0` 은 값이 있습니다). SDK 는 필터를 바꾸지 않고 보내며, nexus-server `0.1.23` 이하는 `400` 입니다.
- **`len(ds)`** — 핸들이 값을 기억합니다. sealed 버전은 서버가 seal 때 저장한 수를 읽고(`Dataset.open` 으로 열었거나 `seal()` 직후면 요청 없이 끝납니다), draft 버전은 한 번 세고 기억합니다. 이 핸들의 `flush`·`link_samples`·`unlink_samples`·`import_samples`·`seal`·`delete`·`refresh` 뒤에는 버리고 다시 셉니다(`refresh` 를 뺀 나머지는 실패해도 버리고, `refresh` 는 성공했을 때만 버립니다). **핸들 밖의 변경은 `ds.refresh()` 전까지 반영되지 않습니다** — 다른 프로세스·다른 핸들의 쓰기, 웹 화면이나 REST 로 한 샘플 삭제. 버전이 지워졌으면 `NexusError(404)` 입니다. nexus-server `0.1.23` 이하에서는 버전 조회 한 번 뒤 종전처럼 세고 기억합니다.
- **`ds.count_values(field)`** — 값 종류 100,000 개·50 초까지 셉니다(종전 500 개·3 초, nexus-server `0.1.23` 이하는 종전 그대로). 그래도 값 종류가 상한을 넘으면 `RuntimeWarning` 과 함께 개수가 큰 쪽만 오고, 제한 시간을 넘으면 `NexusError` 입니다. 숫자 meta 키는 받지 않습니다(분포는 histogram). 요청 하나가 서버의 DB 커넥션을 그 시간 동안 쥐므로 여러 필드를 동시에 부르지 마십시오. 응답을 못 받으면(읽기 타임아웃·앞단 프록시 504) 자동으로 다시 보내지 않습니다 — 서버에서 아직 세고 있을 수 있어서입니다. `NexusClient.facet_counts(..., exact=True)` 가 같은 모드입니다.
- **`NexusError.code`·`NexusError.rejected`** — 서버 오류 본문의 `code`·`rejected` 를 그대로 답니다(없으면 `None`). 생성자에 같은 이름의 키워드 인자 둘이 늘었고 기존 호출은 그대로 동작합니다.
- **`NexusClient.patch_meta_items(dataset_id, version, items)`·`NexusClient.patch_meta_by_filter(dataset_id, version, filter, meta, confirm=None)`** — `set_values`·`update_meta` 가 쓰는 서버 경로를 해석 없이 감쌉니다. 앞의 것은 응답이 없는 실패를 자동으로 다시 보내고(같은 값을 병합하므로 결과가 같습니다), 뒤의 것은 다시 보내지 않습니다. 둘 다 nexus-server `0.1.24` 부터입니다.
- **0.1.21 절 정정** — `AnnotatedSample.tags` 항목이 sealed 버전의 태그가 seal 스냅샷에 남는 것처럼 적고 있었습니다. 태그는 스냅샷에 들어가지 않아 sealed 버전에서도 언제나 현재 값입니다. 그 항목을 고쳤습니다.

## 0.1.21

**FiftyOne 식 조회·집계 메서드를 더합니다.** 서버 변경 없이 기존 경로 위에서 돕니다. nexus-server `0.1.21`·`0.1.23` 에서 실측했습니다. 쓰는 서버 경로가 처음 들어간 판은 `len(ds)` 가 `0.1.7`, `count_values`·`count_sample_tags` 가 `0.1.10`, `set_values`·admin 의 sealed 삭제가 `0.1.18` 이고, 나머지는 그보다 오래됐습니다.
필드는 서버와 같은 경로 문법입니다 — meta 는 `"meta.<키>"`, 샘플 속성은 `"tags"`·`"split"`·`"sample_id"`. FiftyOne 의 `values("x")` 는 `values("meta.x")` 로 옮깁니다.

- **`ds.iter_samples(*, page_size=1000, **필터)`** — `AnnotatedSample` 을 하나씩 내는 제너레이터입니다. annotation 을 항상 전부 싣고, 받은 샘플의 `meta`·`tags`·그룹을 고친 뒤 `save()` 하면 바뀐 것만 저장됩니다. 그룹은 `ds.declare_group_kinds()`(또는 `load_or_create(group_kinds=)`)로 선언한 것만 타입 객체가 되고 나머지는 원본 그대로 왕복합니다. 필터는 `ds.samples()` 와 같은 키워드(`split`·`tags`·`exclude_tags`·`meta`·`group_key`·`label`·`confidence_min`/`max`·`track_id`·`sample_ids`)이고 `include_annotations` 는 받지 않습니다 — annotation 없이 만든 샘플에 그룹을 넣고 저장하면 서버의 그 그룹이 통째로 교체되기 때문입니다(가벼운 순회는 `values()` 나 `ds.samples(include_annotations=False)`). 서버에는 `page_size` 만큼씩 꺼낼 때 묻고, 순서는 `sample_id` 내림차순입니다. `page_size` 는 1~1000 정수만 받고 그 밖은 `ValueError`, 모르는 필터 키워드와 `include_annotations` 는 `TypeError` 입니다 — 제너레이터라서 이 오류는 호출할 때가 아니라 첫 샘플을 꺼낼 때 납니다. 「바뀐 것만 저장」은 nexus-server `0.1.18` 이상이고, 그보다 옛 서버에서는 `RuntimeWarning` 과 함께 annotation 통째 교체로 저장합니다(종전 `load_sample()` 과 같습니다).
- **`AnnotatedSample.tags`·`AnnotatedSample.split`** — `iter_samples`·`shuffle`·`ds.load_sample()` 로 받은 샘플은 태그(고칠 수 있는 리스트)와 split(읽기 전용)을 듭니다. `save()` 는 바뀐 그룹·meta 를 저장한 뒤 더해진 태그를 붙이고 빠진 태그를 뗍니다(순서만 바뀐 것은 변경이 아닙니다). 태그를 바꿨는데 핸들의 버전이 sealed 면 아무것도 보내지 않고 `NexusError(409)` 입니다(sealed 라는 답은 핸들이 기억해 다시 묻지 않습니다). 샘플이 그 사이 삭제됐으면 `NexusError(404)` 입니다. 태그를 바꾼 `save()` 뒤에는 `s.tags` 가 서버에 저장된 값(중복 없음, 서버가 정한 순서)으로 바뀝니다 — 서버는 기존 태그 뒤에 새 태그를 붙이지만, 새 태그가 여럿이면 그들끼리의 순서는 넣은 순서와 다를 수 있습니다. 태그를 모두 떼려면 `s.tags = []` 로 두십시오 — `None` 은 `NexusValidationError` 입니다. 두 저장은 한 트랜잭션이 아니어서 태그 단계가 실패하면 meta·그룹은 이미 저장된 상태이고, 다시 `save()` 하면 태그만 보냅니다. **meta 와 태그는 샘플에 붙어 있어** 같은 샘플을 공유하는 다른 버전(sealed 포함)의 조회에도 바뀐 값이 보입니다. meta 는 seal 스냅샷(`to_df()` 가 읽는 것)에 seal 때 값이 남지만, `to_df()` 결과에는 태그 열이 없어 sealed 버전의 태그는 언제나 현재 값입니다.
- **`ds.load_sample(sample_id)`** — 샘플 단건 조회로 바꿔 `tags`·`split` 까지 읽습니다. annotation 은 종전과 같지만, 그룹 이름이 `sample_id`·`split`·`tags`·`created_at`·`image_url`·`thumbnail_url` 중 하나와 같으면 그 그룹은 서버 응답에서 그 이름의 필드에 가려 보이지 않습니다(`iter_samples`·`shuffle` 도 같습니다). 이 SDK 는 그런 그룹을 건드리지 않습니다 — nexus-server `0.1.18` 미만이라 통째 교체로 저장할 때도 서버에 저장된 값을 읽어 그대로 함께 보냅니다(이 읽기는 `0.1.5` 이상이 필요합니다).
- **`ds.name`** — dataset 이름. 핸들이 아는 이름이라 이 핸들의 `update(name=)` 과 `ds.refresh()` 가 갱신합니다.
- **`ds.refresh()`** — `dataset_id` 로 dataset 을 다시 읽어 `ds.name` 을 갱신하고 핸들을 돌려줍니다. 다른 곳에서 이름이 바뀌었을 때 씁니다. dataset 이 없으면 `NexusError(404)` 입니다.
- **`len(ds)`** — 버전의 샘플 수(필터 없는 정확한 수)를 서버에 묻습니다. **`bool(ds)` 는 항상 `True`** 이고 서버를 부르지 않습니다 — 빈 버전의 핸들도 `if ds:` 에서 참입니다.
- **`ds.values(field, **필터)`** — 샘플마다 값 하나를 `sample_id` 내림차순 리스트로 돌려줍니다. 키가 없으면 `None`, `"tags"` 는 리스트입니다. `field` 는 `"meta.<키>"`·`"tags"`·`"split"`·`"sample_id"` 만 받고 그 밖은 `ValueError` 입니다. 필터는 `iter_samples` 와 같습니다.
- **`ds.distinct(field, **필터)`** — 정렬된 고유 값 리스트입니다(`field` 규칙은 `values` 와 같습니다). 필터가 있으면 걸린 샘플을 훑어 모읍니다(값 분포 조회는 필터를 받지 않습니다). `None` 은 빼고 배열 값은 원소를 펼치며, 객체 값이 있으면 `ValueError`, 값이 없는 키는 `[]` 입니다. 숫자는 숫자 순서로 정렬되고 `1` 과 `1.0` 은 하나입니다. 필터 없이 부를 때 스칼라 타입이 둘 이상 섞인 `meta` 필드(문자열·숫자·불리언 중 둘 이상)는 값이 모두 문자열(`"3"`·`"true"`)로 나옵니다. 값이 `None` 이거나 빈 리스트인 필터 인자는 필터로 치지 않습니다.
- **`ds.count_values(field)`** — `{값: 샘플 수}`(인스턴스 수가 아닙니다). `field` 는 `"tags"`·`"meta.<문자열·불리언 키>"`·`"group_key"`·`"<그룹>.label"`·`"<그룹>.component.type"` 이고 그 밖은 서버가 `400` 입니다. 키는 서버가 준 문자열입니다(불리언은 `"true"`/`"false"`). 값 종류가 500 을 넘으면 개수가 큰 쪽만 오고 `RuntimeWarning` 을 냅니다. 서버가 제한 시간 안에 못 세면 0 건으로 돌려주지 않고 `NexusError` 를 냅니다.
- **`ds.count_sample_tags()`** — 샘플 태그별 샘플 수. `count_values("tags")` 와 같습니다.
- **`ds.get_field_schema()`** — `{"meta.<키>": 타입 문자열}`. dataset 에서 관측된 키만 담고 버전과 무관합니다(다른 버전에서만 쓰인 키도 나옵니다). 관측만 된 숫자 필드는 정수여도 `"float"` 이고, 배열·객체만 관측된 필드는 빠집니다(서버 쪽 과제, 일정 미정).
- **`ds.tags`·`ds.add_tag(*tags)`·`ds.remove_tag(*tags)`** — dataset 태그를 읽고 더하고 뺍니다. `ds.tags` 는 부를 때마다 서버에서 읽는 **튜플**이라 `ds.tags.append(t)` 는 `AttributeError` 입니다(리스트였다면 아무 일도 안 하고 지나갑니다). `add_tag`/`remove_tag` 는 갱신된 태그 튜플을 돌려주고, 인자가 없거나 리스트 하나를 넘기면(`add_tag(["a", "b"])`) 요청 전에 `ValueError` 입니다 — `add_tag("a", "b")` 또는 `add_tag(*리스트)` 로 부르십시오.
- **`ds.set_values("meta.<키>", {sample_id: 값})`** — 샘플마다 meta 키 하나를 씁니다. 값 `None` 은 그 키를 지우고 다른 meta 키는 그대로 둡니다. 적용한 건수를 돌려줍니다. 샘플마다 요청 하나이고 일괄 트랜잭션이 아닙니다 — 실패하면 그 자리에서 멈추고, 올라오는 예외의 `applied`(앞서 적용된 건수 — 되돌리지 않습니다)와 `failed_sample_id` 로 알려 줍니다. 서버 오류는 `NexusError`(인증 오류면 `NexusAuthError` 그대로)이고, 응답을 못 받은 실패(읽기 타임아웃 등)도 `NexusError` 입니다 — 그때 실패한 샘플은 적용됐을 수도 있습니다(다시 보내도 결과가 같습니다). 그 밖의 예외는 종류를 바꾸지 않고 두 속성만 붙습니다. sealed 버전은 첫 건의 `409` 에서 멈춥니다. `field` 는 `"meta.<키>"` 만 받습니다.
- **`ds.shuffle(*, seed=None, page_size=1000, **필터)`** — 필터에 걸린 샘플을 섞은 순서로 `AnnotatedSample` 로 하나씩 내는 제너레이터입니다. 같은 `seed` 와 같은 데이터면 같은 순서입니다. `sample_id` 를 먼저 모아 섞은 뒤 `page_size` 개씩 본문을 받으므로 id 목록은 메모리에 둡니다. 도중에 지워진 샘플은 건너뜁니다. 필터 규칙은 `iter_samples` 와 같습니다(`include_annotations` 를 받지 않습니다).
- **`nx.dataset_exists(name)`** — 그 이름의 dataset 이 있으면 `True`. 이름이 정확히 같은 것만 셉니다(부분 일치는 `False`).
- **`ds.delete(..., confirm_dataset_name=)`·`NexusClient.delete_version(..., confirm_dataset_name=)`** — `role=admin` 은 sealed 버전도 데이터셋 이름을 정확히 주면 삭제됩니다(틀리거나 빠지면 `400`, nexus-server `0.1.18` 이상). 비-admin 은 종전대로 `409` 입니다. 인자를 주지 않으면 요청이 종전과 같습니다. 「sealed 는 예외 없이 삭제 불가」라던 독스트링도 고쳤습니다.
- **`NexusClient` 저수준 메서드** — `version_stats`·`facet_values`·`facet_counts`·`histogram`·`version_schema`·`add_dataset_tags`·`remove_dataset_tags`. 서버 경로를 그대로 감싸고 응답 JSON 을 해석 없이 돌려줍니다.

## 0.1.20

**seal 이 서버의 동시 seal 상한에 걸리면 기다렸다 다시 보냅니다.** nexus-server `0.1.21` 부터 파드마다 동시에 도는 seal 의
수에 상한이 있고(`code: seal_busy`), 같은 버전의 seal 이 이미 진행 중이면 어느 파드든 거절합니다(`code: seal_in_progress`).
두 경우 모두 seal 을 시작하지 않고 `429` 와 `Retry-After: 10` 으로 돌아오므로 다시 보내도 중복 seal 이 생기지 않습니다.
`seal_in_progress` 를 기다린 끝에는 보통 앞 seal 이 끝나 `409 already_sealed` 가 옵니다(`if_sealed="ignore"` 면 그 버전을 돌려줍니다).

- **`ds.seal(wait=)`·`NexusClient.seal(..., wait=)`** — 그 `429` 를 기다리는 최대 초. 기본 600. `Retry-After` 보다 일찍
  다시 보내지 않고, `Retry-After` 가 15 초 이하면 다시 묻는 간격은 최대 15 초(지터 포함 22.5 초)입니다. 넘기면 `NexusError(status_code=429)`. `0` 이면
  기다리지 않고, 0 이상의 유한한 숫자가 아니면(음수·`nan`·`inf`·`bool`·`None`·문자열) `ValueError`. 기다린 시간만 세고 seal 자체의 소요는 세지 않습니다(그쪽은 `timeout` 입니다).
  기다리는 도중 서버 교체로 연결이 끊겨 다시 보내도(`retry_timeout`) 기다린 합은 이어서 세므로 `wait` 를 넘기지 않습니다.
- **seal 도중 읽기 타임아웃은 실패가 아닙니다.** 서버 `0.1.21` 의 seal 은 연결이 끊겨도 끝까지 계속되고 SDK 는 이 타임아웃(기본 120 초)을 다시 보내지 않으므로, `if_sealed="ignore"` 로 다시 호출하거나 버전 상태를 확인하십시오.
- **버전 설명** — `ds.seal(description=)`(seal 과 함께 기록, `None` 은 지움)·`ds.set_description(text)`(sealed 버전도 됨, `None`·`""` 은 지움)·`ds.description`(부를 때마다 서버에서 읽음)·`NexusClient.update_version`. 서버 `0.1.21` 이 필요합니다 — `0.1.20` 이하 서버는 seal 본문을 무시해 설명이 저장되지 않고, `set_description` 의 PATCH 는 `405` 입니다. `description` 을 주지 않으면 seal 은 종전처럼 본문 없이 나갑니다. `if_sealed="ignore"` 로 불렀는데 이미 sealed 인 버전이면 준 `description` 은 적용되지 않습니다 — 그때는 `ds.set_description()` 을 쓰십시오.
- **`seal(wait=)` 는 `numpy` 정수·`fractions.Fraction` 같은 `numbers.Real` 도 받습니다.** 유한한 0 이상 값이면 되고 `bool`·`nan`·`inf`·음수·`None`·문자열은 종전대로 `ValueError` 입니다.
- **seal 밖의 429 는 그대로입니다.** `/ingest/batch` 등은 종전처럼 8 회까지만 다시 보냅니다(`Retry-After: 1` 이면 약 90~140 초). `0.1.19` 이하도
  seal 의 `429` 를 이 8 회로 다시 보내므로(seal 의 `Retry-After: 10` 이면 약 126~189 초), 앞의 seal 이 그보다 길면 `429` 로 끝납니다.
- **`ds.seal(if_sealed="ignore")` 가 sealed 가 아닌 버전을 돌려주지 않습니다.** 종전에는 `409` 면 무엇이든 「이미 sealed」로
  보고 버전을 조회해 돌려줬습니다. 서버는 seal 저장 위치가 다른 sealed 버전과 겹칠 때(`a/b` 와 `a_b`)도 `409` 를 내고, 그때
  버전은 `draft` 입니다. 이제 조회한 버전이 `sealed` 일 때만 돌려주고, 아니면(그 사이 버전이 지워진 경우 포함) 원래의 `409` 를 올립니다.

## 0.1.19

**서버 부재(연결 실패·502·503·504)를 기다렸다 다시 보냅니다.** cas-server·nexus-server 를 교체하는 동안(수십 초~2 분)
적재가 실패로 끝나지 않고 이어집니다. nexus-server `0.1.20` 과 함께 쓸 때 `/ingest/batch` 재전송도 중복 없이 됩니다.

- **`retry_timeout`** — 한 요청이 **첫 실패부터** 기다리는 초. 기본 120. `nx.connect(retry_timeout=)`, 환경변수
  `NEXUS_RETRY_TIMEOUT`, 설정 파일 키 `retry_timeout`(우선순위 인자 > 환경변수 > 파일). `0` 이면 끕니다(0.1.18 동작).
  `CasClient(...)`·`NexusClient(...)` 를 직접 만들어도 환경변수를 읽습니다. 숫자가 아니면 `ValueError`.
- **다시 보내는 것.** 요청이 서버에 닿지 않은 실패(연결 거부·연결 타임아웃·DNS)는 모든 요청을. 처리됐을지 모르는 실패
  (응답 도중 끊김·읽기 타임아웃·프록시의 502·503·504, nexus 가 낸 502)는 다시 보내도 결과가 같은 요청만 — `GET`·`HEAD`,
  annotation·subset·즐겨찾기 `PUT`, `buckets/ensure`, explorer·facet 개수 `POST`, 그리고 `/ingest`·`/ingest/batch`
  (서버가 `X-Nexus-Idempotency` 를 알렸고 모든 item 에 키가 있을 때만). nexus 가 스스로 낸 503·504(CVAT·OIDC 미구성 등)는
  다시 보내지 않습니다. 401 재로그인·429 백오프는 그대로이고 nexus 요청의 429 는 부재 시간을 먹지 않습니다(CAS 는 아래). 응답 본문을 읽다 끊긴 경우
(`ChunkedEncodingError`)도 처리됐을지 모르는 실패라 안전한 요청만 다시 보냅니다. TLS·인증서 오류
  (`SSLError`)는 서버 부재가 아니라 다시 보내지 않습니다(CAS 는 종전처럼 3 회까지만). `nx.connect()` 의 첫 로그인은
  기다리지 않습니다 — 적재 도중의 요청만 기다립니다.
- **CAS.** `CasClient.put`·`nx.upload`·`head`·`get` 이 같은 상한을 씁니다. `flush` 가 CAS 를 부르는 호출도 여기에
  들어갑니다 — bucket·key·hash·size·content_type 다섯 값이 다 있지 않은 ref(CAS URL, `{bucket, key}` 만 있는 ref,
  `meta.filename` 으로 가리킨 이미지)에 보내는 `HEAD`, CAS ref 로 넘긴 annotation 의 `GET`, 그리고 `nx.probe` 의 범위
  `GET` 입니다. 그래서 이미지를 CAS URL 로 넘기는 적재도 cas-server 교체 동안 등록이 멈추지 않고 기다렸다가 이어집니다.
  `HEAD` 404(객체 없음)는 다시 보내지 않고 곧바로 실패합니다. STS 모드는 쓸 수 있는 임시 자격증명이 없을 때만 STS 를
  같은 상한까지 기다립니다(남은 수명이 60 초보다 길면 종전처럼 캐시를 씁니다). **CAS(`DeadlineRetry`)의 429·503 대기는
`retry_timeout` 예산을 먹고**, 서버가 준 `Retry-After` 도 예산에 맞춰 자르지 않습니다. CAS 500 은 예산 전체 동안 다시
보냅니다(대상은 종전과 같고 이제 시간으로 묶입니다).
- **멱등 키.** `flush` 가 item 마다 `idempotency_key`(UUID)를 싣습니다. 키는 `Sample` 이 `(dataset, version)` 마다 들고,
  성공하면 지웁니다 — 성공한 `Sample` 을 **다음 `flush`** 에 다시 넣으면 0.1.18 처럼 새 샘플이 생깁니다. 같은 `flush` 에
  같은 객체를 두 번 넣으면 같은 키가 두 번 가서 샘플 1 개 + `replayed` 1 건이 됩니다. 응답을 못 받고 끝난 샘플은 처음 보낸
  본문을 기억해 두었다가 다음 `flush` 에서 **그대로** 다시 보냅니다(그 사이 `Sample` 내용을 바꿔도 기억한 본문이 갑니다 —
  내용을 바꾸려면 새 `Sample` 을 만드십시오). 서버가 기존 결과를 돌려주면 `IngestResult.replayed` 가 `True` 이고 성공으로
  셉니다. 요약 줄에 `replayed N` 이 붙습니다.
- **실패한 샘플을 다시 보내는 법.** `flush` 는 실패한 샘플을 큐에 되돌려 놓지 않습니다. 직접 다시 넣으십시오 —
  `ds.add([r.sample for r in results if not r.ok])`. 키와 기억한 본문은 **같은 `Sample` 객체**가 들고 있어서, 새
  `Sample` 을 만들면 새 키가 되어 중복될 수 있습니다. 이 상태는 프로세스 메모리에만 있어 프로세스를 재시작하면
  사라집니다. `copy.copy`·`copy.deepcopy`·`dataclasses.replace` 로 만든 복제본은 키·본문 없이 새 샘플로 시작합니다.
- **수정: 생성한 뒤 바꾼 `Sample` 이 반영됩니다.** 생성한 뒤 `Sample` 의 `image`·`assets`·`annotation` 을 바꾸면(다시 대입하거나
  `s.assets["depth"] = ref` 처럼 그 자리에서 바꾸면) 0.1.18 까지는 `flush` 가 생성 때의 값을 보냈습니다. 이제 `flush` 가 그때의
  값을 씁니다. 생성 뒤에 로컬 경로를 대입하면 그 샘플은 준비 단계에서 실패로 드러납니다. 위의 기억한 본문은 이 경우에도
  나중 수정보다 우선합니다.
- **애매한 실패와 재전송 사이에 `ds.update(name=...)` 로 dataset 이름을 바꾸지 마십시오.** 키는 `(dataset 이름, version)`
  마다 따로 두므로, 이름을 바꾼 핸들로 다시 넣으면 기억한 본문이 쓰이지 않고 새 키로 나갑니다. 처음 요청이 이미
  커밋됐다면 그 샘플은 조용히 중복됩니다. 이름을 바꾸기 전에 다시 보내십시오.
- **서버에 `ingest.verify_assets=true` 이면** cas-server 를 교체하는 동안 새 item 은 여전히 실패합니다(서버 자신의
  CAS HEAD 에는 재시도가 없어 502 로 item 이 실패하고, SDK 는 이를 확정 item 오류로 봅니다). 이미 기록된 키만 CAS 없이
  재전송됩니다. 기본값(false)은 영향이 없습니다.
- **`NexusClient.ingest_batch`·`ingest` 를 직접 부르면 키가 붙지 않습니다.** 재전송을 원하면 item 마다 `idempotency_key` 를
  넣으십시오.

**호환성.** nexus-server `0.1.19` 이하는 `idempotency_key` 를 무시하고 `X-Nexus-Idempotency` 를 내지 않으므로, 그 서버에서는
`/ingest/batch` 를 다시 보내지 않습니다(0.1.18 과 같게 실패로 돌려줍니다). 그 서버에서 실패한 샘플을 다시 넣으면 이미
커밋된 것이 중복될 수 있습니다 — 옛 서버는 키로 가려내지 못합니다. **nexus-server 를 `0.1.20` 으로 올리는 교체 한
번은 적재를 멈추십시오** — 옛 파드와 새 파드가 섞인 동안 재전송이 옛 파드로 가면 중복됩니다. nexus-server `0.1.19`
이하는 `X-Request-Id` 도 내지 않아, 그 서버가 스스로 낸 503(예: CVAT 미구성)도 프록시가 낸 것으로 보고 안전한 요청은
`retry_timeout` 동안 기다린 뒤 실패합니다.

**의존성.** `urllib3>=1.26` 을 명시합니다(CAS 재시도가 1.26 에 들어온 `Retry(other=)` 를 씁니다). `requests>=2.31` 이
허용하던 1.25 이하가 설치된 환경은 이 판을 설치할 때 urllib3 가 올라갑니다.

```
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk==0.1.19
```

## 0.1.18

**id 로 기존 dataset 버전을 여는 `Dataset.open` 과, 접속된 CAS 클라이언트를 얻는 `nx.cas_client()` 를
더합니다.** 기존 호출의 동작이 달라지는 것은 아래 쿼리 붙은 URL(「수정 — CAS URL」의 첫 항목)과
「동작 변경 — `flush`·`patch_annotations`」 둘입니다.

- **`nx.Dataset.open(dataset_id, version, *, client=None, cas=None)`** — 아무것도 만들지 않습니다.
  dataset 이나 버전이 없으면 `NexusError`(`status_code=404`)입니다. `load_or_create` 는 이름으로 찾고
  없으면 만들므로, 읽기만 하는 워커(`to_df()` 등)는 이쪽을 쓰십시오. 핸들에 읽기 전용 제한은 없고,
  쓰기 권한은 서버의 역할 판정이 정합니다. `client`/`cas` 를 둘 다 주지 않으면 `nx.connect()` 의
  접속을 씁니다(접속 전이면 자동 접속). 한쪽만 주면 나머지는 이미 `connect()` 된 것에서만 채우고,
  없으면 `ValueError` 입니다(자동 접속으로 다른 서버의 것과 짝지어지지 않게).
- **`nx.cas_client()`** — 현재 접속의 `CasClient` 를 돌려줍니다(접속 전이면 자동 접속). 비공개 전역
  `nexus._cas` 를 읽던 코드는 이것으로 옮기십시오.
- **`nx.CasClient` · `nx.NexusClient` 를 공개 목록(`nexus.__all__`)에 올립니다.** 두 클래스는 전부터
  최상위에서 import 됐고, 이번 판부터 공개 API 로 약속합니다.

**수정 — CAS URL 의 key 에 `#` · `?` 가 있으면 그 앞에서 key 가 잘리던 문제.** `Sample(image=<URL>)`
처럼 `http(s)://` URL 을 참조로 넘기면 `#` 뒤를 fragment, `?` 뒤를 query 로 떼어내, 없는 객체를
`HEAD` 해 `flush()` 가 실패했습니다(`0.1.16` 의 특수문자 수정 범위 밖이었습니다). 이제 호스트 뒤의
경로 전체를 bucket/key 로 씁니다 — `s3://` 와 같은 방식입니다. `#` `?` `;` 는 key 에 남고 요청
경로에서 `%23` `%3F` `%3B` 로 인코딩됩니다. `%XX` 는 전과 같이 풀어서 원래 key 로 씁니다.
같은 파싱을 쓰는 `backfill_dims()`(서버가 준 `image_url`)와 annotation `meta.filename` 참조도 함께
고쳐집니다.

- **쿼리가 붙은 URL 은 이제 참조로 쓸 수 없습니다.** presigned URL 이나 브라우저에서 복사한
  `https://cas/b/k.png?X-Amz-Signature=...` 처럼 쿼리가 붙은 URL 은 `0.1.17` 까지 쿼리를 버리고
  읽었지만, 이제 쿼리까지 key 로 보아 없는 객체를 가리킵니다. 쿼리를 떼고 넘기거나 `CasRef`·`s3://`
  를 쓰십시오.

**서버 `0.1.19` 의 인코딩된 객체 URL 을 읽습니다.** 서버 `0.1.19` 부터 `image_url`·`thumbnail_url`·
manifest 의 `cas_url` 이 key 를 인코딩해 줍니다. `to_df()` 가 스냅샷 URL 에서 key 를 되읽을 때 이제
한 번 풀어 씁니다. 옛 서버가 준 인코딩되지 않은 URL 도 그대로 읽습니다.

- **호환성(중요): 서버를 `0.1.19` 로 올리면 SDK 도 `0.1.18` 로 올리십시오.** 버전 이름에 영숫자와
  `-_.~` `/` 밖의 문자(한글·공백·괄호·`+` 등)가 있는 sealed 버전은 서버 `0.1.19` 와 SDK
  `0.1.16`·`0.1.17` 조합에서 `to_df()` 가 실패합니다("annotation 스냅샷 manifest을(를) CAS에서 받지
  못했습니다(404)"). 버전 이름이 스냅샷 key 에 들어가는데, 옛 SDK 가 서버가 인코딩한 URL 을 한 번
  더 인코딩하기 때문입니다. 버전 이름이 영숫자와 `-_.~` 만이면(`v1`, `v1.0` 등) 영향이 없습니다.
  (`/` 는 스냅샷 key 에서 `_` 로 바뀌어 이 문제와는 무관하지만, `/` 가 든 버전은 옛 SDK 에서 원래
  조회·seal 이 되지 않습니다 — 아래 버전 경로 수정.)

**수정 — 버전 이름에 `#` · `?` · `/` 가 있으면 다른 버전으로 요청이 가던 문제.** SDK 가 버전 이름을
요청 경로에 인코딩 없이 넣어, `v1#x` 는 `#` 뒤가 떨어져 `v1` 로 요청했고(`v1` 이 있으면 그 버전의
응답을 받았습니다) `release/2026` 은 없는 경로로 갔습니다. 이제 버전 이름을 경로 한 조각으로
인코딩합니다. 영숫자·공백·한글만 쓰는 버전 이름은 전과 같은 요청이 나갑니다.

**동작 변경 — `flush`·`patch_annotations`.**

- **결과가 입력 순서로 옵니다.** `0.1.17` 까지는 병렬 처리가 끝난 순서로 모아, 준비 단계(CAS
  `HEAD`) 실패가 목록 맨 앞에 왔고 적재 청크도 끝난 순서대로 섞였습니다. 결과를 입력 순서로 맞추던
  코드는 엉뚱한 샘플과 짝지어졌습니다. 이제 둘 다 입력 순서로 정렬해 돌려주고, `IngestResult` 에
  입력에서의 위치 `index` 를 더했습니다(`flush` 는 호출 시점 큐, `patch_annotations` 는 넘긴 항목).
- **`flush` 준비 단계에서 CAS 가 401/403 을 내면 아무것도 적재하지 않고 `NexusCasError` 를
  올립니다.** 한 건이라도 있으면 배치 전체가 멈춥니다. 예외 문구는 CAS 자격증명·정책 문제라고
  적고, 큐는 그대로 남으므로 고친 뒤 같은 핸들에서 다시 `flush()` 하면 됩니다. `0.1.17` 까지는
  CAS `HEAD` 의 403 이 `status_code` 없이 건별 실패로만 남았고, annotation 을 CAS 에서 받다 난 403 은
  나머지를 적재한 뒤 nexus 역할 문제라는 틀린 문구로 예외가 됐습니다. 나머지를 적재한 뒤 예외를
  올리지 않는 이유는, 그러면 이미 등록된 건의 `sample_id` 가 예외와 함께 사라져 재시도가 중복
  적재가 되기 때문입니다.

**`NexusCasError` 가 HTTP 상태코드를 싣습니다.** CAS `HEAD`·범위 `GET`·`PUT` 실패와 STS 발급
실패, STS 모드의 리다이렉트 거부가 `status_code`(와 `server_message`)를 채웁니다(`GET` 은 전부터
채웠습니다). `flush` 의 "CAS object 없음"(`HEAD` 404)은 `404` 입니다. 그래서 `IngestResult.status_code` 로
403(영구)·404(없음)·5xx(일시)를 가를 수 있습니다. HTTP 응답이 없는 실패는 여전히 `None` 입니다 —
연결 실패는 `NexusCasError` 가 아니라 requests 예외(`ConnectionError` 등) 그대로 올라오고, SDK 가
스스로 판정한 오류(입력 검증, 업로드 key 충돌)는 `NexusCasError` 이되 `status_code` 가 없습니다.

## 0.1.17

**annotation 객체 모델의 instance id — 빈 id 도 채우고, 형식을 UUID v4 로 맞춥니다.**

- **id 가 없거나 빈 문자열인 행에 UUID v4(하이픈 형식 `8-4-4-4-12`, GT spec 형식)를 붙입니다.**
  `0.1.16` 은 id 키가 없을 때만 하이픈 없는 32 자리 hex 를 붙였습니다. 서버는 id 없이 적재된 행을
  빈 문자열로 돌려주므로, `0.1.16` 으로 `load_sample()` 한 그런 행들은 모두 id 가 `""` 로 남아 서로
  구분되지 않았고, id 로 행을 가르는 `merge()`·`add_labels()`·CVAT 왕복이 그 행들을 하나로 취급했습니다.
  채운 id 는 로드 기준에 포함되므로 **그 그룹을 고쳐 저장할 때만** 서버에 기록됩니다 — 손대지 않은
  그룹은 그대로입니다. 이미 id 가 있는 행은 형식과 무관하게 그대로 보존합니다.
- **`save()` 가 보내는 그룹 안에 같은 id 가 두 번 이상 있으면 거부합니다**(`NexusValidationError`,
  메시지에 중복 id). GT spec 4 장 「모든 객체의 id 는 그룹 내에서 유일해야 한다」의 구조 규칙이고,
  중복이면 id 로 행을 가르는 `merge()`·`add_labels()`·CVAT 왕복이 그중 한 행만 다룹니다. 로드와
  손대지 않은 그룹은 검사하지 않으므로 중복이 있는 그룹도 열고 읽을 수 있고, 고쳐 저장할 때만 중복
  행의 id 를 먼저 정리해야 합니다(그룹이 다르면 같은 id 는 정상입니다 — 같은 대상을 잇는 값입니다).
  id 형식은 여전히 검사하지 않습니다.

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
