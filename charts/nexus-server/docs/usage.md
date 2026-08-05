# Nexus User Guide
## 1. 소개
### 1.1 Nexus

Nexus는 ML 학습 데이터를 Sample, Dataset, DatasetVersion 단위로 관리하는 ML Dataset Catalog이다.  
원본 파일(이미지 등)은 콘텐츠 주소 기반 저장소인 **cas-server(CAS)**에 보관되며, Nexus에는 해당 파일에 대한 참조 정보와 Annotation, 메타데이터, Dataset 구조 및 버전 정보가 저장된다.  
이와 같은 구조를 통해 대용량 학습 데이터를 중복 없이 관리하면서, 데이터셋 버전별 재현성과 협업을 지원한다.

### 1.2 주요 특징
Nexus는 다음과 같은 특징을 가진다.
- 원본 파일은 CAS에서 관리된다.  
원본 파일은 CAS 엔드포인트를 통한 직접 업로드 또는 SDK 메서드를 이용한 업로드 방식으로 CAS에 저장되며, Nexus에는 CAS 객체를 참조하는 정보와 메타데이터만 저장된다.
- DatasetVersion 간 Sample을 공유한다.  
새로운 DatasetVersion은 기존 버전을 Fork하여 생성할 수 있으며, 변경되지 않은 Sample은 기존 버전과 공유된다. 따라서 데이터셋 전체를 복사하지 않고도 새로운 버전을 효율적으로 관리할 수 있다.
- Annotation은 DatasetVersion 단위로 관리된다.  
동일한 Sample이라도 DatasetVersion마다 서로 다른 Annotation을 가질 수 있으며, 한 버전에서의 수정은 다른 버전에 영향을 주지 않는다.
- Seal을 통해 Immutable 버전을 생성한다.  
DatasetVersion은 Seal하여 변경이 불가능한 스냅샷으로 고정할 수 있다. Seal된 버전은 학습 및 평가에 사용되는 기준 데이터셋으로 활용되며, 동일한 데이터를 언제든지 재현할 수 있다.

### 1.3 전체 워크플로우
![기본적인 데이터 흐름](workflow.png)

---

## 2. 설치
### 2.1 Nexus 서버 준비 (Helm)
#### 전제
- cas-server가 떠 있고, 그 접속 주소를 안다 (예: `http://cas-server:80`, 또는 외부 `https://cas.example.com`).
- 외부 PostgreSQL 접속 정보(DSN). nexus는 DB를 직접 띄우지 않는다. DB 마이그레이션은 nexus 기동 시 자동 적용된다.
- CAS 자격증명(SigV4 `key_id`/`secret`)과 JWT 시크릿.
- nexus-server는 stateless(파일=CAS, 메타=Postgres)라 PVC가 없다.

#### Helm repo 추가

```bash
helm repo add int2nexus https://int2nexus.github.io/cas-server
helm repo update
```
nexus-server는 cas-server와 동일한 Helm repo를 사용한다.

#### 시크릿 주입 (sealed-secret)

차트는 Secret을 만들지 않고 외부 Secret을 envFrom으로 참조한다. 아래 4개의 키를 가진 Secret을 먼저 클러스터에 주입한다(kubeseal로 봉인):

```bash
kubectl create secret generic nexus-server -n <namespace> --dry-run=client -o yaml \
  --from-literal=NEXUS__DATABASE__URL='postgres://user:pass@pg-host:5432/nexus' \
  --from-literal=NEXUS__CAS__KEY_ID='<CAS key id>' \
  --from-literal=NEXUS__CAS__SECRET='<CAS secret>' \
  --from-literal=NEXUS__JWT__SECRET='<JWT 시크릿>' \
  | kubeseal --format yaml > sealed-nexus-server.yaml
kubectl apply -f sealed-nexus-server.yaml -n <namespace>
```

- `NEXUS__JWT__SECRET`은 직접 생성하는 임의의 비밀 키(로그인 JWT HS256 서명용)  
예: `openssl rand -hex 32`. 값을 바꾸면 기존 발급 토큰이 모두 무효가 된다(재로그인 필요).
- `NEXUS__CAS__KEY_ID`/`NEXUS__CAS__SECRET`은 CAS가 인정하는(write 권한 있는) 자격증명
- `NEXUS__DATABASE__URL`은 외부 Postgres DSN.

#### 설치

```bash
helm install nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소>      # http://cas-server:80 

# 업데이트
helm repo update
helm upgrade nexus-server int2nexus/nexus-server -n <namespace> \
  --set cas.baseUrl=<CAS 주소>      # http://cas-server:80 
```

#### Python SDK 설치

```bash
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk

# 업데이트
pip install --upgrade --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk
#버전 확인
python -c "import importlib.metadata as m; print(m.version('int2nexus-sdk'))" 
```

#### 연결 설정

`nx.connect`는 로그인 후 JWT를 받아 클라이언트를 초기화한다. 계정이 없으면 등록을 먼저 실행
```python
# (최초 1회) 테스트 계정 등록 - 이미 있으면 409, 그대로 진행
NEXUS_URL = "http://<HOST>:8090"
resp = requests.post(f"{NEXUS_URL}/api/v1/auth/register", json={
"email": "<EMAIL>", "password": "<PASSWORD>", "display_name": "<NAME>",
})
print(resp.status_code, "(409 = 이미 존재, 무시 가능)")
```

설정 값의 우선순위는 **인자 > 환경변수 > 설정 파일**이다. 코드에 명시한 값이 항상 이기고, CI는 환경변수로 로컬 설정 파일을 덮을 수 있다.

**(1) 설정 파일 — 권장** (SDK 0.1.1+)

`~/.int2nexus/settings.json`파일로 저장. `nx.connect()` 로 바로 연결. 스크립트에 자격증명이 남지 않는다.

```json
{
  "nexus_url": "http://<host>:8090",
  "email": "...",
  "password": "...",
  "cas_url": "http://<host>:8080",
  "cas_key_id": "...",
  "cas_secret": "...",
  "verify": true
}
```

```python
import nexus as nx

nx.connect()
```

**(2) 인자로 직접 넘기기**

```python
import nexus as nx

nx.connect(
    nexus_url="http://<host>:8090",
    email="...", password="...",
    cas_url="http://<host>:8080",
    cas_key_id="...", cas_secret="...",
)
```

**(3) 환경변수**

환경변수가 모두 있으면 `nx.connect()`만 호출하거나 첫 API 호출 시 자동 연결된다.

```python
import os

os.environ["NEXUS_URL"] = "http://<host>:8090" # nexus-server 주소
os.environ["NEXUS_EMAIL"] = "..."              # 로그인 자격 증명
os.environ["NEXUS_PASSWORD"] = "..."           
os.environ["CAS_URL"] = "http://<host>:8080"   # cas-server 주소 
os.environ["CAS_KEY_ID"] = "..."               # CAS SigV4 서비스 계정 자격증명
os.environ["CAS_SECRET"] = "..."  

nx.connect()
```

`cas_key_id`/`cas_secret`(또는 `CAS_KEY_ID`/`CAS_SECRET`)는 CAS 업로드 서명용 키. CAS가 인정하는(해당 버킷에 write 권한 있는) 키면 동작하며, nexus 서비스 키를 공유하거나 내부 정책에 따라 개인별로 발급받은 키 사용.

#### 사내 프록시로 SSL 인증서 에러가 날 때 (SDK 0.1.1+)

사내 보안 장비가 TLS를 검사하면 `nx.connect()`가 인증서 에러로 죽는다. 아래 중 하나를 사용한다.

```bash
export REQUESTS_CA_BUNDLE=/path/to/사내-루트-CA.pem
```

```python
nx.connect(verify="/path/to/사내-루트-CA.pem")   # 검증을 유지한 채 해결 (권장)
nx.connect(verify=False)                          # 최후의 수단
```

- 설정 파일의 `"verify"` 키에 적어두면 매번 넘기지 않아도 된다. 값은 `true`/`false` 또는 **CA 번들 경로**.
- `verify=False`는 그 연결의 **중간자 공격 탐지를 포기**하는 것이다. 접속 시 한 번 경고가 뜬다.

## 3. 핵심 흐름
### 3.1 Dataset 생성
이름으로 dataset을 찾거나 생성하고, 그 안에 지정한 version이 없으면 생성한다. 멱등 동작이며 version은 항상 명시해야 하는 필수값이다.  
생성 직후 버전은 draft 상태 — 샘플 추가/삭제, annotation 수정이 가능하다.
```python
import nexus as nx
from nexus.sample import CasRef

ds = nx.Dataset.load_or_create("my-dataset", "v0")
```

### 3.2 원본 파일 업로드

로컬 이미지를 CAS에 직접 올리고 각 파일을 가리키는 참조 `{CasRef}`를 받는다. 이후 이 참조로 샘플을 등록한다.
- 같은 파일을 다시 올려도 내용이 같으면 건너뛴다(멱등). 실패한 파일만 골라 재시도할 수 있다(같은 목록으로 재호출).  
- 이미 CAS에 올라가 있는 파일이면 이 단계를 건너뛰고, 그 파일의 CAS URL을 바로 다음 단계(nx.Sample(image=...))에 명시하여 사용할 수 있다.

```python
import json
from pathlib import Path
from dataclasses import asdict

img_dir = Path(r"...\images")
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
img_paths = sorted(str(p) for p in img_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS)

# CAS key = 파일명 (prefix= 로 "prefix/파일명" 지정 가능)
refs = nx.upload(img_paths, bucket="my-bucket", workers=8)   

#대량 작업이면 refs를 JSON으로 저장해두면 재사용·재개에 좋다.
records = {path: asdict(ref) for path, ref in refs.items()}
Path("upload_refs.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
```
`CasRef` = `bucket` / `key` / `hash_hex` / `size` / `content_type` (+ `width`/`height`). 이 값을 그대로 `nx.Sample(image=ref)`에 넘긴다.  

`nx.upload`는 로컬 파일을 CAS에 올릴 때 쓰는 편의 도구일 뿐이다. 다만, `nx.upload` 과정에서 UI 로딩 최적화용 썸네일(WebP 256px,thumb/<key>)을 함께 생성한다. 업로드를 건너뛰고 CAS URL로 바로 등록하면 썸네일이 없어 UI가 원본으로 폴백한다(동작은 정상, 로딩만 무거움). 필요시 `nx.upload`를 다시 돌려 없는 썸네일만 백필할 수 있다.

### 3.3 샘플 생성 & 등록

받은 ref로 `nx.Sample`을 만들어 dataset/version에 등록한다.  
저장해둔 refs를 다시 로드하는 패턴:

```python
from nexus.sample import CasRef

saved = json.loads(Path("upload_refs.json").read_text(encoding="utf-8"))
refs = {path: CasRef(**rec) for path, rec in saved.items()}

samples = [
    nx.Sample(
        image=ref,                   # CasRef (또는 http:// URL). 로컬 경로는 ValueError
        # annotation="ann.json",     # 선택: 이미지와 매핑되는 로컬 JSON 경로 / dict(inline GT) 
        # assets={"depth": depth_ref},  # 선택: image 외 추가 asset — {role: ref} 범용 dict
        # split="train", tags=[...], # 선택
    )
    for ref in refs.values()
]

ds.add(samples)                       # 등록 큐에 추가 - 단일 Sample 또는 리스트 모두
results = ds.flush(workers=8)         # 병렬 등록 → IngestResult 리스트

print("ok:", sum(r.ok for r in results), "/", len(results))
for r in (r for r in results if not r.ok):
    print("  FAIL:", r.error)
```

- `image` - `nx.upload`가 돌려준 `CasRef`, 또는 그 이미지의 CAS URL을 직접 넣는다(`http://<cas>/<bucket>/<key>`).  
- `annotation`은 Sample 등록 시점에 같이 넣는 게 자연스럽다(나중에 따로 고치는 방법은 §3.5).  
생략하면 서버가 최소한의 정보만으로 등록한다.
- `assets`는 image 외 추가 모달리티(depth map 등)를 담는 범용 dict(`{role: ref}`).  
`image`외 새 모달리티(thermal, lidar 등)가 필요하면 필드 추가 없이 이 dict에 role을 추가한다.

### 3.4 등록 확인
```python
samples = ds.list_samples()                        # 이 버전의 샘플 목록
sample = ds.get_sample(samples[0]["sample_id"])     # 샘플 하나의 annotation을 포함한 전체 정보

# 조건에 맞는 샘플들의 annotation을 포함한 전체 정보
everything = ds.samples()                                   # 필터 없음 → 버전 전체 샘플(자동 페이지네이션)
cars = ds.samples(label="car")                              # label이 car인 instance가 있는 샘플(전체)
trucks = ds.samples(group_key="det", label="truck")         # det 그룹 안에서만
just_these = ds.samples(sample_ids=["s1", "s2", "s3"])       # 이 sample_id들만
by_split = ds.samples(split="val", tags=["night"])  
```
`samples(sample_ids=, group_key=, label=, confidence_min=, confidence_max=, track_id=, split=, tags=, meta=)` 특정 조건 필터를 추가하여 조건에 맞는 샘플만 조회한다.  `limit`을 지정하지 않으면 커서를 자동으로 순회해 매칭 전체를 모아서 반환한다.  
매칭되는 샘플이 아주 많을 수 있는 대규모 dataset이면 `limit`없이 그냥 부를 경우 전체 데이터를 로드하느라 느려지거나 메모리를 많이 쓸 수 있다. `limit`을 명시하여 필요한 만큼만 가져오는 것을 권장한다.  

직접 페이지 단위로 로드 - `after`로 다음 페이지의 시작점(이전 호출 결과의 마지막 `sample_id`)을 지정::
```python
  cursor = None
  while True:
      page = ds.samples(label="car", limit=500, after=cursor)
      ...
      if len(page) < 500:
          break
      cursor = page[-1]["sample_id"]
```

### 3.5 annotation 추가/교체

이미 등록된 샘플에 annotation만 따로 붙이거나 교체한다(재적재 없이).  
이미지 파일명(stem)으로 annotation 파일을 매핑하는 패턴:

```python
ann_dir = Path(r"...\annotations")    # 파일명 stem이 이미지와 1:1

patches = {}
for s in ds.list_samples():
    stem = Path(s["assets"]["image"]["cas_url"]).stem
    p = ann_dir / f"{stem}.json"
    if p.exists():
        patches[s["sample_id"]] = json.loads(p.read_text(encoding="utf-8"))

pres = ds.patch_annotations(patches, workers=8)   # 배치(병렬) → IngestResult 리스트
print("patched:", sum(r.ok for r in pres), "/", len(pres))
```

```python
ds.patch_annotations(sample_id, {"det": [{"id": "a", "label": "truck"}]})   # 하나씩
```
- draft 버전에서만 가능(sealed면 409). 이전 patch를 완전 교체하는 방식(누적 아님).
- 교체 단위는 group_key 단위가 아닌 샘플 전체(이 버전 한정). 기존 그룹을 유지하려면 바꾸지 않는 그룹도 `annotation_data`에 같이 넣어야 한다.  

한 그룹의 일부만 고치고 싶을 때 안전한 방법은 전체를 가져와서 필요한 부분만 바꾼 뒤 통째로 다시 보내는 것이다. 
  ```python
  full = ds.get_sample(sample_id)                          # 이 버전의 annotation 전체
  annotation_data = {
      k: v for k, v in full.items()
      if k not in ("sample_id", "image_url", "thumbnail_url")
  }                                                        # {"meta": ..., "det": [...], "seatbelt": [...]}

  for inst in annotation_data["det"]:                      # det 그룹 안 인스턴스 하나만 라벨 수정
      if inst["id"] == "a":
          inst["label"] = "truck"

  ds.patch_annotations(sample_id, annotation_data)         # seatbelt 등 나머지 그룹은 그대로 유지됨
  ```

### 3.6 seal - 버전 잠금
검수가 끝난 draft 버전을 봉인해 불변 상태로 전환한다(draft → sealed, 단방향 - 되돌릴 수 없음). seal 시 annotation을 NDJSON 스냅샷으로 CAS에 박제하고 manifest hash를 기록한다.

```python
ds.seal()                       # 이미 sealed면 서버 409(NexusError) 전파
ds.seal(if_sealed="ignore")     # 이미 sealed면 현재 상태 그대로 반환(멱등 — 재실행 편의)
```
- seal 이후로는 해당 버전에서 샘플 추가/삭제/annotation 추가 및 버전 삭제 동작이 전부 막히고(409), to_df()로 학습 소비가 가능해진다.
- 수정하고 싶으면 새 버전으로 `fork`(§5.3) 해서 새로운 draft 버전을 만든다.

### 3.7 DataFrame 변환
`ds.to_df()`는 sealed 버전의 GT annotation 스냅샷(NDJSON)을 pandas DataFrame으로 로드한다.  
각 행 = 한 샘플 = `{sample_id, meta, <group_key>:[instances...]}`.  
seal 시 이 스냅샷은 여러 NDJSON 샤드로 나뉘어 CAS에 저장되고, nexus는 그 샤드들의 위치를 가리키는 manifest만 갖고 있다.  
`to_df()`는 nexus 서버에 manifest만 한 번 조회한 뒤, 실제 annotation 데이터(샤드 NDJSON)는 CAS에서 직접 다운로드해 DataFrame으로 조립한다 - 대량의 annotation을 읽어도 nexus 서버에 부하가 몰리지 않는다.

```python
df = ds.to_df()                              # 모든 group_key
df = ds.to_df(groups=["seatbelt", "bkp_gt"]) # 지정 그룹만
ds.to_df(path="gt.jsonl")                    # 파일로도 저장(+ df 반환) — csv/json/jsonl/parquet
for chunk in ds.to_df(chunksize=1000):       # 대규모 — 샤드 단위 스트리밍 이터레이터
    ...

import requests

for _, row in df.iterrows():
    image_bytes = requests.get(row["meta"]["filename"]).content   # 이미지는 URL로 받아옴
    instances = row.get("det", [])
    train(image_bytes, instances)
```

DataFrame에는 annotation과 이미지 경로(meta.filename)만 담기고, 이미지 바이트 자체는 안 담긴다 - 필요하면 그 경로에서 따로 받는다.  
대용량 데이터의 경우 ds.to_df(chunksize=1000)으로 한 번에 다 메모리에 올리지 않고 나눠 처리할 수 있다.

### 3.8 전체 예제
지금까지의 흐름(3.1~3.7)을 간략히 정리한다.
```python
import nexus as nx

nx.connect()

# 1. dataset 생성
ds = nx.Dataset.load_or_create("my-dataset", "v0")

# 2. 원본 파일 업로드
refs = nx.upload(["img1.png"], bucket="my-bucket", prefix="incabin")

# 3. 샘플 생성 + 등록
sample = nx.Sample(
    image=refs["img1.png"],
    annotation={"meta": {}, "det": [{"id": "a", "label": "car"}]},
    split="train",
)
ds.add(sample)
results = ds.flush()

# 4. 확인
print(ds.list_samples())

# 5. (필요하면) annotation 수정
ds.patch_annotations(results[0].sample_id, {"det": [{"id": "a", "label": "truck"}]})

# 6. 확정
ds.seal()

# 7. 학습 데이터로 사용
df = ds.to_df()
```

## 4. 데이터셋 관리
### 4.1 데이터셋 목록 조회
```python
nx.list_datasets()                              # 전체 목록
nx.list_datasets(q="incabin")                    # name/description/tags 통합 검색(부분일치)
nx.list_datasets(tags=["person-detection"])      # 태그로 필터(하나라도 포함)
nx.list_datasets(favorite=True)                  # 내 즐겨찾기만
nx.list_datasets(sort="name", order="asc")       # 정렬
```
- `q`는 `name/description/tags` 중 하나라도 부분일치하는 데이터셋을 반환한다. `name=/description=`은 개별 필드 검색
- 즐겨찾기는 `ds.favorite() / ds.unfavorite()`(멱등)로 켜고 끄고, favorite=True로 목록을 필터링한다.

### 4.2 데이터셋 정보 수정
```python
ds.update(name="my-dataset-renamed")             
ds.update(description="새 설명")                  
ds.update(name="new-name", description="새 설명") 
```
- 제공한 필드만 수정된다(둘 다 생략하면 아무 것도 안 함).  
이름을 바꾸면 이 `ds` 핸들의 내부 이름도 자동으로 같이 갱신된다.
- 다른 dataset이 이미 쓰고 있는 이름으로는 바꿀 수 없다(충돌 시 에러).
- Dataset의 소유자(생성자) 계정만 이름/설명을 바꿀 수 있다.

### 4.3 데이터셋 삭제 정책
Dataset 삭제는 버전 단위로 수행한다. `ds.delete()`로 버전을 삭제하고, 남은 버전이 하나도 없으면 Dataset도 자동으로 삭제된다. 이때 Dataset에 속한 잔여 Sample도 모두 정리되며 필요 시 CAS로 Asset 삭제 요청을 보내 CAS에서 Asset이 정리될 수 있도록 한다. 
Dataset의 소유자(생성자)만 삭제 가능하며, sealed 버전은 삭제할 수 없다.

## 5. 데이터셋 버전 관리
### 5.1 Draft 버전
처음 버전 생성 시 Draft 상태이며 자유롭게 수정 가능한 작업 중 상태이다. 
이 상태에서 할 수 있는 일:
- 샘플 추가/등록, Annotation 추가, 버전 삭제
- 같은 Dataset의 다른 버전에서 샘플 재사용(재적재 없이 참조만 연결)
```python
ds.link_samples([sid1, sid2])          # 이미 존재하는 sample_id를 이 버전에 연결
ds.unlink_samples([sid1, sid2])        # 연결 해제(샘플 자체·다른 버전은 유지)
```
- 다른 Dataset의 샘플 재사용(Sample은 Dataset 범위 객체라 직접 링크가 아닌 복사)
```python
ds.import_samples(source_dataset_id, "v0", [sid1, sid2])
```
복사된 Sample은 이후 원본과 독립적으로 관리된다. `ds.samples()`로 조회한 결과를 그대로 옮기는 패턴:
```python
source = nx.Dataset.load_or_create("source-dataset", "v0")
people = source.samples(label="Person")           # 조건에 맞는 샘플 검색(전체, 자동 페이지네이션)

target = nx.Dataset.load_or_create("target-dataset", "v0")
target.import_samples(
    source.dataset_id, source.version,
    [s["sample_id"] for s in people],              # samples()의 dict에서 sample_id만 뽑는다
)
```

### 5.2 Sealed 버전
Seal 하면 그 시점 상태로 불변 스냅샷이 된다. 이후:
- 샘플 추가/삭제, Annotation 수정, 버전 삭제 불가
- `to_df()`로 소비할 수 있다.
- 수정이 필요할 경우 `fork`해서 새 Draft 버전을 생성하여 작업한다(§5.3).

### 5.3 Fork
기존 버전을 기반으로 새로운 작업용 버전을 만든다.
```python
ds_v1 = nx.Dataset.load_or_create("my-dataset", "v1", fork_from="v0")   # 전량 fork
sealed v1 --(fork_from)--> draft v2
```
fork된 버전은 원본의 샘플 구성(+ Annotation)을 그대로 이어받지만, 이후 샘플 추가/제거나 Annotation 수정은 새 버전에서 독립적으로 이루어진다(원본에 영향 없음).  
특정 샘플만 골라서 fork하고 싶으면 sample_ids=[...]를 같이 넘기거나, 조건으로 바로 고르고 싶으면 ds.fork()를 사용해 매칭되는 샘플만 담은 새 버전을 만든다:
```python
cars_v1 = ds.fork("v1", group_key="det", label="car")   # label=car인 샘플만 담은 새 버전
```
필터가 지정되지 않은 경우 위의 전량 fork와 동일하게 동작한다.

### 5.4 Clone
fork가 같은 Dataset 안에서 새 버전을 만드는 것이라면, clone은 완전히 다른 Dataset으로 통째로 복제한다.
```python
new_ds = ds.clone("my-dataset-copy", "v0")
```
- 원본을 그대로 복사해 새 dataset을 만든다(이미 있으면 그 dataset을 재사용).
- 복사 후 Draft로 시작한다 - 복제 직후 바로 이어서 patch/추가 작업이 가능하다.
- 내부적으로 import_samples를 반복 호출하는 방식이라 멱등하지 않다 - 같은 대상에 두 번 부르면 샘플이 중복 복사된다.

## 6. 에러 처리

모든 SDK 예외는 `NexusError`(및 하위 클래스 `NexusAuthError`/`NexusCasError`/`NexusIngestError`/`NexusBatchError`)를 상속한다.

```python
from nexus import NexusError

try:
    ds.delete(confirm=True)
except NexusError as e:
    if e.status_code == 409:
        print("sealed 버전이라 삭제 못 함:", e.server_message)
    elif e.status_code == 403:
        print("소유자 아님:", e.server_message)
    else:
        raise
```

- `e.status_code`(`int | None`)와 `e.server_message`(`str | None`)로 서버가 보낸 실제 에러 사유를 프로그램적으로 분기할 수 있다. `str(e)`에도 같은 내용이 포함되지만(사람이 읽는 용도), 상태코드로 분기하려면 이 두 속성을 쓴다.
- `flush`/`patch_annotations`의 배치 호출은 건당 결과를 `IngestResult(ok, sample, sample_id, error)`로 모아서 반환한다 — `strict=True`면 실패가 하나라도 있을 때 `NexusBatchError(failures=[...])`를 던진다.


## 7. 전체 API 레퍼런스
### 최상위 함수
|||
|---|---|
|`nx.connect(nexus_url=, email=, password=, cas_url=, cas_key_id=, cas_secret=)`|서버 연결|
|`nx.list_datasets(q=, name=, description=, tags=, sort=, order=, favorite=)`|dataset 목록 검색|
|`nx.upload(paths, bucket, prefix="", workers=8)` → {경로: CasRef}|파일 업로드|
|`nx.Sample(image=, annotation=, assets=, split=, tags=)`|샘플 정의|
|`nx.CasRef(bucket, key, hash_hex=, size=, content_type=)`|파일 참조|

### Dataset
|||
|---|---|
|`Dataset.load_or_create(name, version, tags=, description=, fork_from=, sample_ids=)`|dataset/버전 생성 또는 조회|
|`.add(sample)` / `.flush()`|	샘플 등록|
|`.list_samples()` / `.get_sample(id)`|	조회|
|`.samples(sample_ids=, group_key=, label=, confidence_min=, confidence_max=, track_id=, split=, tags=, meta=, limit=, after=)`|	조건 조회(기본 전체, limit=주면 한 페이지)|
|`.patch_annotations(sample_id, data)`|	annotation 수정|
|`.sample_history(sample_id)` / `.diff(against=)`|	이력 / 비교|
|`.link_samples(ids)` / `.unlink_samples(ids)` / `.import_samples(src_dataset, src_version, ids)`|	샘플 재사용|
|`.fork(new_version, sample_ids=, group_key=, label=, ...)`|	필터링된 fork(같은 dataset)|
|`.clone(new_name, new_version)`|	통째 복제|
|`.update(name=, description=)`|	이름/설명 수정|
|`.seal()`|	버전 확정|
|`.to_df(groups=, path=, format=, chunksize=)`|	DataFrame 변환|
|`.delete(confirm=, delete_cas=)`|	버전 삭제|
|`.favorite()` / `.unfavorite()`|	즐겨찾기|

### 그 외
|||
|---|---|
|`client.add_tags_bulk(sample_ids, tags)` / `.remove_tags_bulk(...)`|태그 일괄 처리|
|`NexusError`, `NexusAuthError`, `NexusCasError`, `NexusIngestError`, `NexusBatchError`|	예외 타입(`.status_code`, `.server_message`)|
|`IngestResult(ok, sample, sample_id, error)`|	배치 처리 건별 결과|
