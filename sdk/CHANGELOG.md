# int2nexus-sdk 변경 이력

`int2nexus-sdk` 의 변경은 이 파일에 적습니다. 서버 이미지·차트와 따로 발행하고 따로 설치합니다.

```
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk==<버전>
```

`scripts/publish_sdk.py` 는 `sdk/pyproject.toml` 의 버전과 같은 `## <버전>` 절이 이 파일에 없으면
빌드하지 않고 멈춥니다. 최신 버전이 위로 오게 적습니다.

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
