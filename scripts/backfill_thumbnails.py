#!/usr/bin/env python3
"""CAS에 이미 올라간 이미지의 썸네일을 사후 생성한다.

썸네일은 원래 Python SDK의 `nx.upload()`가 업로드와 함께 만든다. boto3/`aws s3` 등으로
CAS에 직접 올렸다면 그 경로가 없으므로 썸네일이 비고, nexus UI가 원본으로 폴백해 로딩이
무거워진다. 이 스크립트는 업로드 수단과 무관하게 **사후에 한 번 돌리면 되는** 도구다.

키 규약 (nexus-server `src/catalog/sample.rs`, SDK `nexus/upload.py`와 동일):

    원본    {bucket}/{key}
    썸네일  {bucket}/thumb/{key}        WebP, 긴 변 256px

멱등이다 — 이미 있는 썸네일은 건너뛰므로 중단 후 다시 돌려도 안전하다.

메모리는 **객체 수와 무관하다.** 목록을 모으지 않고 페이지 단위로 흘리며, 원본 목록과
썸네일 목록을 머지 조인해 차집합을 구한다(둘 다 사전순이고 썸네일은 `thumb/` 접두어를
공유하므로 접두어를 떼면 같은 순서가 된다). 동시 처리량도 `--workers` 의 4배로 묶여
있어 수백만 건에서도 사용량이 일정하다.

실패한 key 는 `--error-log`(기본 `backfill_thumbnails_errors.tsv`)에 한 줄씩 즉시
기록된다 — 매 실행 덮어쓰므로 **두 번 돌린 뒤에도 남아 있는 key 가 진짜 문제다.**

`--limit` 은 대상을 N건 찾는 즉시 멈춘다(전체를 훑지 않는다).

의존성: boto3, pillow   (nexus SDK는 필요 없다)

    pip install boto3 pillow

받기:

    curl -O https://raw.githubusercontent.com/int2nexus/cas-server/main/scripts/backfill_thumbnails.py

사용:

    export CAS_URL=http://<CAS 주소>:8080
    export CAS_KEY_ID=...
    export CAS_SECRET=...

    python backfill_thumbnails.py --self-test               # 네트워크 없이 내부 검증
    python backfill_thumbnails.py --bucket <버킷> --dry-run  # 대상만 세기 (읽기 전용)
    python backfill_thumbnails.py --bucket <버킷> --limit 20 # 소량 시험 (20건 찾으면 중단)
    python backfill_thumbnails.py --bucket <버킷>            # 전체

    python backfill_thumbnails.py --bucket <버킷> --prefix images/
    python backfill_thumbnails.py --bucket <버킷> --ca-bundle /path/corp-ca.pem

자격증명은 `CAS_KEY_ID`/`CAS_SECRET`(SDK와 같은 이름) 또는 boto3 표준
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`를 읽는다. 엔드포인트는 `--endpoint`
또는 `CAS_URL`.
"""
from __future__ import annotations

import argparse
import io
import itertools
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait

THUMB_PREFIX = "thumb/"
THUMBNAIL_MAX_EDGE = 256
THUMBNAIL_QUALITY = 80

# 스캔이 이 개수를 셀 때마다 진행 상황을 한 줄 찍는다. 대상이 거의 없는(=대부분
# 이미 썸네일이 있는) 버킷에서는 [2/2] 이후 완료 카운터가 오래 안 늘어 스캔이 멈춘
# 것처럼 보이는 문제가 있었다 — 이 줄이 "지금 스캔 중"이라는 증거다.
SCAN_PROGRESS_EVERY = 5000

# 썸네일을 만들 대상 확장자. 이 목록에 없으면 건너뛴다(어차피 디코딩에 실패한다).
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".gif"}


def build_client(args):
    import boto3
    from botocore.config import Config

    endpoint = args.endpoint or os.environ.get("CAS_URL")
    if not endpoint:
        sys.exit("CAS 엔드포인트가 없습니다 — --endpoint 또는 CAS_URL 환경변수를 지정하세요.")

    key_id = args.key_id or os.environ.get("CAS_KEY_ID") or os.environ.get("AWS_ACCESS_KEY_ID")
    secret = args.secret or os.environ.get("CAS_SECRET") or os.environ.get("AWS_SECRET_ACCESS_KEY")
    if not key_id or not secret:
        sys.exit(
            "CAS 자격증명이 없습니다 — --key-id/--secret 또는 "
            "CAS_KEY_ID/CAS_SECRET (또는 AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY)를 지정하세요."
        )

    # TLS 검증: 기본은 켜짐. 사내 프록시가 TLS를 검사하면 --ca-bundle로 루트 CA를 주는 쪽이
    # --no-verify-ssl보다 안전하다(검증을 끄면 중간자 공격을 탐지할 수 없다).
    verify = args.ca_bundle if args.ca_bundle else (not args.no_verify_ssl)

    return boto3.client(
        "s3",
        endpoint_url=endpoint.rstrip("/"),
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        region_name=args.region,
        verify=verify,
        config=Config(
            # CAS는 경로 스타일(/{bucket}/{key})이다. 가상 호스트 스타일로 서명하면 404가 난다.
            s3={"addressing_style": "path"},
            signature_version="s3v4",
            # botocore 기본 커넥션 풀은 10. --workers 를 그보다 올리는 게 이 도구의
            # 목적(수백만 건)인데, 풀보다 워커가 많으면 urllib3가 연결을 버리고
            # 새로 맺는다 — 그 과정에서 나는 download/put 실패가 CAS 문제처럼
            # 보이는 오류 로그에 섞여, "두 번 돌린 뒤에도 남은 키가 진짜 문제다"라는
            # 절차를 흐린다. 워커 수만큼은 최소로 확보한다.
            max_pool_connections=max(args.workers, 10),
            # 몇 시간짜리 실행에서 일시적 5xx까지 오류로 잡히면 오류 로그의 신뢰도가
            # 떨어진다. 표준 재시도로 흡수한다.
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )


def iter_objects(s3, bucket: str, prefix: str):
    """prefix 아래 object를 `(key, size)` 로 흘린다. 페이지 하나분만 메모리에 둔다."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"], obj["Size"]


def iter_originals(s3, bucket: str, prefix: str):
    """썸네일 대상이 될 수 있는 원본만 흘린다 — `thumb/` 자신과 비이미지 확장자는 뺀다.

    prefix 를 주지 않으면 목록에 `thumb/...` 가 섞여 들어오는데, 걸러내도 나머지의
    정렬은 유지되므로 머지 조인의 전제가 깨지지 않는다.
    """
    for key, size in iter_objects(s3, bucket, prefix):
        if key.startswith(THUMB_PREFIX):
            continue
        if os.path.splitext(key)[1].lower() not in IMAGE_EXTS:
            continue
        yield key, size


def iter_thumb_keys(s3, bucket: str, prefix: str):
    """썸네일 목록에서 `thumb/` 를 뗀 key 를 흘린다 — 원본과 같은 순서가 된다."""
    for key, _size in iter_objects(s3, bucket, THUMB_PREFIX + prefix):
        yield key[len(THUMB_PREFIX):]


def _with_progress(stream, stats: dict, every: int = SCAN_PROGRESS_EVERY):
    """`originals` 스트림을 그대로 흘리며 `stats['scanned']` 를 세고, `every` 건마다
    진행 상황을 한 줄 찍는다(`flush=True`).

    스캔 단계가 살아있다는 증거는 이것뿐이다 — 대상 대부분이 이미 썸네일을 갖고
    있으면 완료 카운터(처리된 항목)는 수십만 건이 지나도 안 늘 수 있는데, 그동안
    스캔 자체는 계속 돌고 있다는 걸 보여줘야 "멈췄나?"와 "그냥 대상이 없다"를
    구분할 수 있다. 카운터만 두 개(scanned/skipped) 세므로 메모리는 늘지 않는다.
    """
    for item in stream:
        stats["scanned"] += 1
        if stats["scanned"] % every == 0:
            print(f"      스캔 {stats['scanned']:,}건 (건너뜀 {stats['skipped']:,}건)",
                  flush=True)
        yield item


class ErrorLog:
    """실패 키를 **즉시** 파일에 흘린다. 메모리에 쌓지 않는다.

    수백만 건에서는 실패도 수만 건이 될 수 있고, 무엇보다 몇 시간짜리 실행이 중간에
    죽어도 그때까지의 실패가 남아야 한다. 그래서 줄마다 flush 한다 — 네트워크 대기가
    지배적인 작업이라 비용은 무시할 수 있다.

    실행할 때마다 덮어쓴다. 이어붙이면 지난 실행에서 이미 해결된 키가 남아 "지금 무엇이
    문제인지"를 흐린다. 덮어쓰면 판별이 저절로 된다 — **두 번 돌린 뒤에도 남아 있는
    키가 진짜 문제다.**

    파일은 **첫 write() 에서야** 연다("w" 로 미리 열어두지 않는다). `boto3.client()`
    는 네트워크를 타지 않으므로, 만료된 자격증명이나 오타난 버킷 같은 문제는 첫 LIST
    호출에서야 드러난다 — 그 전에 파일을 미리 truncate 해두면 지난 실행이 남긴 5만
    줄짜리 실패 목록이 이번 실행이 한 줄도 쓰기 전에 죽었을 뿐인데도 사라진다. 두 번
    돌려서 비교하는 절차(위 문단)가 의지하는 게 바로 그 이전 실행의 파일이라, 이건
    조용한 데이터 손실이었다.
    """

    def __init__(self, path: str):
        self.path = path
        self.count = 0
        self._fh = None

    def write(self, key: str, reason: str, detail: str = "") -> None:
        if self._fh is None:
            self._fh = open(self.path, "w", encoding="utf-8")
        self._fh.write(f"{key}\t{reason}\t{detail}\n")
        self._fh.flush()
        self.count += 1

    def close(self, cleanup_if_empty: bool = True) -> None:
        """파일 핸들을 닫는다. 한 번도 안 열었다면(=이번 실행이 아무것도 안 썼다면)
        `cleanup_if_empty` 일 때만 지난 실행이 남긴 파일을 지운다.

        `cleanup_if_empty=True` 는 **정상 종료**(끝까지 돌았는데 실패가 0건)에만
        써야 한다 — 그건 "지난 실패가 이제 해결됐다"는 실제 결과이므로 낡은 파일을
        남겨두면 이미 고친 실패가 아직 있는 것처럼 보인다. 반대로 **중간에 죽은
        경우**(크레덴셜 오류·네트워크 장애로 첫 LIST 도 못 간 경우 등)는 아무것도
        확인한 게 없다는 뜻이라 `cleanup_if_empty=False` 로 불러 지난 파일을
        그대로 둬야 한다 — 호출부가 크래시 경로와 정상 종료 경로를 갈라 준다.
        """
        if self._fh is not None:
            self._fh.close()
        elif cleanup_if_empty and os.path.exists(self.path):
            os.remove(self.path)


def run_bounded(todo, workers: int, handle):
    """`todo` 를 흘려가며 처리하고 `handle` 의 반환값을 완료 순서대로 yield 한다.

    in-flight 를 `workers * 4` 로 묶는 것이 핵심이다. 전부 미리 제출하면 대상 수만큼
    Future 가 쌓여 워커가 8개여도 메모리는 수백만 개분이 든다. 4배는 워커가 굶지 않을
    만큼의 여유이고, 그 이상 미리 쌓아둘 이유가 없다.
    """
    max_inflight = max(workers * 4, workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        inflight = set()
        for item in todo:
            if len(inflight) >= max_inflight:
                done, inflight = wait(inflight, return_when=FIRST_COMPLETED)
                for f in done:
                    yield f.result()
            inflight.add(pool.submit(handle, item))
        while inflight:
            done, inflight = wait(inflight, return_when=FIRST_COMPLETED)
            for f in done:
                yield f.result()


def _ascending(stream, what: str):
    """오름차순 전제를 지키는지 확인하며 흘려보낸다. 역행하면 즉시 중단한다.

    머지 조인은 두 목록이 같은 순서라는 전제 위에 서 있다. 그 전제가 깨지면 결과가
    **조용히** 틀린다 — 있는 썸네일을 다시 만들거나(낭비), 없는 것을 건너뛴다(누락).
    후자는 완료 메시지가 정상으로 보여서 더 나쁘다. 비교 한 번으로 막는다.
    """
    prev = None
    for item in stream:
        key = item[0] if isinstance(item, tuple) else item
        if prev is not None and key <= prev:
            raise RuntimeError(
                f"{what} 목록이 사전순이 아니다: {prev!r} 다음에 {key!r} — "
                "머지 조인의 전제가 깨졌다. 썸네일이 조용히 누락될 수 있어 중단한다."
            )
        prev = key
        yield item


def iter_todo(originals, thumbs, stats: "dict | None" = None):
    """정렬된 두 스트림을 머지 조인해 **썸네일이 없는 원본만** 흘린다.

    `originals`는 `(key, size)` 오름차순, `thumbs`는 `thumb/` 를 뗀 key 오름차순.
    S3 목록은 UTF-8 바이너리 사전순이고 썸네일은 `thumb/` 접두어를 공유하므로,
    접두어를 떼면 원본과 같은 순서가 된다 — 그래서 집합을 들고 있지 않아도 된다.
    메모리는 객체 수와 무관하게 일정하다.

    `stats` 를 주면 이미 썸네일이 있어 건너뛴 원본 수를 `stats['skipped']` 에
    누적한다(스캔 총량은 여기서 세지 않는다 — 그건 `originals` 를 감싸는
    `_with_progress` 의 몫이다. 한 함수가 두 카운터를 다 세면 어느 스트림이 무엇을
    보장하는지 흐려진다). 키를 모으지 않고 정수만 누적하므로 메모리는 늘지 않는다.
    """
    originals = _ascending(originals, "원본")
    thumbs = _ascending(thumbs, "썸네일")
    t = next(thumbs, None)
    for key, size in originals:
        while t is not None and t < key:
            t = next(thumbs, None)
        if t == key:
            t = next(thumbs, None)
            if stats is not None:
                stats["skipped"] += 1
            continue
        yield key, size


def _self_test() -> int:
    """네트워크 없이 머지 조인을 검증한다. 실패 개수를 반환."""
    failures = []

    def check(name, ok):
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}")
        if not ok:
            failures.append(name)

    def todo(originals, thumbs):
        return [k for k, _ in iter_todo(iter(originals), iter(thumbs))]

    # 1. 썸네일이 하나도 없으면 전부 대상
    check("썸네일 없음 → 전부 대상",
          todo([("a.png", 1), ("b.png", 1)], []) == ["a.png", "b.png"])

    # 2. 일부만 있으면 없는 것만 대상
    check("일부만 있음 → 없는 것만",
          todo([("a.png", 1), ("b.png", 1), ("c.png", 1)], ["a.png", "c.png"]) == ["b.png"])

    # 3. 전부 있으면 대상 없음
    check("전부 있음 → 대상 없음",
          todo([("a.png", 1), ("b.png", 1)], ["a.png", "b.png"]) == [])

    # 4. 원본이 없는 썸네일이 섞여 있어도 나머지 판정이 흐트러지지 않는다
    #    (원본이 지워졌는데 썸네일만 남은 경우)
    check("고아 썸네일이 있어도 정상",
          todo([("b.png", 1), ("d.png", 1)], ["a.png", "b.png", "c.png"]) == ["d.png"])

    # 5. size 가 그대로 실려 나온다
    check("size 보존",
          list(iter_todo(iter([("a.png", 123)]), iter([]))) == [("a.png", 123)])

    # 8. thumb/ 키와 비이미지 확장자는 원본 목록에서 빠진다
    class _FakePaginator:
        def __init__(self, pages):
            self._pages = pages

        def paginate(self, **kwargs):
            prefix = kwargs.get("Prefix", "")
            for page in self._pages:
                yield {"Contents": [c for c in page["Contents"]
                                    if c["Key"].startswith(prefix)]}

    class _FakeS3:
        def __init__(self, keys):
            self._keys = keys

        def get_paginator(self, _name):
            return _FakePaginator([{"Contents": [{"Key": k, "Size": s}
                                                 for k, s in self._keys]}])

    s3 = _FakeS3([
        ("a.png", 10), ("b.txt", 10), ("c.jpg", 10),
        ("thumb/a.png", 5), ("thumb/c.jpg", 5),
    ])
    check("원본 필터: thumb/ 와 비이미지 제외",
          [k for k, _ in iter_originals(s3, "b", "")] == ["a.png", "c.jpg"])

    # 9. 썸네일 스트림은 thumb/ 를 떼고 원본과 같은 순서가 된다
    check("썸네일 키에서 thumb/ 제거",
          list(iter_thumb_keys(s3, "b", "")) == ["a.png", "c.jpg"])

    # 10. bounded 실행은 모든 항목을 정확히 한 번씩 처리한다
    items = [(f"k{i:04d}.png", i) for i in range(500)]
    seen = sorted(r for r in run_bounded(iter(items), 4, lambda it: it[0]))
    check("bounded 실행: 전부 한 번씩 처리",
          seen == sorted(k for k, _ in items))

    # 11. 입력이 소비보다 상한 이상 앞서 당겨지지 않는다 — 이것이 메모리를 묶는 근거다.
    #     동시 "실행" 수는 ThreadPoolExecutor 가 이미 묶으므로 그것으로는 전부 미리
    #     제출하는 구조와 구분되지 않는다. 큐에 쌓이는 양을 봐야 한다.
    pulled = {"n": 0}

    def _counting_input():
        for it in items:
            pulled["n"] += 1
            yield it

    lead = 0
    consumed = 0
    for _ in run_bounded(_counting_input(), 4, lambda it: it[0]):
        consumed += 1
        lead = max(lead, pulled["n"] - consumed)
    check("in-flight 상한 준수", lead <= 4 * 4 + 1)

    # 12. max_bytes 를 넘는 항목만 걸린다 — 같을 때는 통과(경계값)
    check("max-bytes 초과 판정",
          [is_too_large(s, 100) for s in (50, 100, 101)] == [False, False, True])

    # 6. 원본이 역행하면 즉시 중단 — 조용히 누락되는 것보다 낫다
    try:
        todo([("b.png", 1), ("a.png", 1)], [])
        check("원본 역행 → RuntimeError", False)
    except RuntimeError:
        check("원본 역행 → RuntimeError", True)

    # 7. 썸네일이 역행해도 중단
    try:
        todo([("a.png", 1), ("b.png", 1)], ["b.png", "a.png"])
        check("썸네일 역행 → RuntimeError", False)
    except RuntimeError:
        check("썸네일 역행 → RuntimeError", True)

    print(f"\nself-test: {12 - len(failures)}/12 통과")
    return len(failures)


def is_too_large(size: int, max_bytes: int) -> bool:
    """다운로드하기 전에 거를지 판정한다. 같으면 통과 — 상한은 포함이다."""
    return size > max_bytes


def make_thumbnail(data: bytes) -> "bytes | None":
    """원본 bytes → 긴 변 256px WebP. 디코딩 실패 시 None.

    JPEG는 libjpeg의 DCT 축소 디코딩을 요청한다 — 6000x4000이 750x500으로
    열려 메모리가 72MB에서 1MB 수준으로 준다. 요청 크기보다 작게 줄이지는
    않으므로 256px 썸네일 품질에는 영향이 없고, JPEG이 아니면 아무 일도 안 한다.
    """
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.draft("RGB", (THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
        img = img.convert("RGB")
        img.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=THUMBNAIL_QUALITY)
        return buf.getvalue()
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(
        description="CAS에 이미 올라간 이미지의 썸네일(thumb/<key>)을 사후 생성한다.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--bucket", help="대상 CAS 버킷")
    ap.add_argument("--prefix", default="", help="이 접두어 아래만 처리 (예: images/)")
    ap.add_argument("--endpoint", help="CAS 주소. 없으면 CAS_URL 환경변수")
    ap.add_argument("--key-id", help="CAS key id. 없으면 CAS_KEY_ID / AWS_ACCESS_KEY_ID")
    ap.add_argument("--secret", help="CAS secret. 없으면 CAS_SECRET / AWS_SECRET_ACCESS_KEY")
    ap.add_argument("--region", default=os.environ.get("CAS_REGION", "cas-default"))
    ap.add_argument("--workers", type=int, default=8, help="동시 처리 수 (기본 8)")
    ap.add_argument("--limit", type=int, help="이 개수만 처리 (시험 실행용)")
    ap.add_argument("--dry-run", action="store_true", help="무엇을 만들지만 보고하고 쓰지 않는다")
    ap.add_argument("--ca-bundle", help="TLS 검증용 CA 번들 경로 (사내 루트 CA)")
    ap.add_argument("--no-verify-ssl", action="store_true", help="TLS 검증 끄기 (최후의 수단)")
    ap.add_argument("--error-log", default="backfill_thumbnails_errors.tsv",
                    help="실패한 key 를 기록할 파일 (기본 backfill_thumbnails_errors.tsv, 매 실행 덮어씀)")
    ap.add_argument("--max-bytes", type=int, default=200 * 1024 * 1024,
                    help="이 크기를 넘는 원본은 건너뛴다 (기본 200MB). 목록 단계에서 걸러 다운로드하지 않는다")
    ap.add_argument("--self-test", action="store_true",
                    help="네트워크 없이 내부 로직만 검증하고 종료")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(1 if _self_test() else 0)

    if not args.bucket:
        sys.exit("--bucket 이 필요합니다.")

    if args.no_verify_ssl and not args.ca_bundle:
        print("경고: TLS 검증이 꺼져 있습니다 — 중간자 공격을 탐지할 수 없습니다.", file=sys.stderr)

    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("pillow가 필요합니다: pip install pillow")

    s3 = build_client(args)
    prefix = args.prefix.lstrip("/")

    # 원본 목록과 썸네일 목록을 각각 한 번씩만 훑는다. object마다 HEAD를 날리면
    # 수천 건에서 왕복이 그만큼 늘어난다 — 목록 두 번이 훨씬 싸다.
    #
    # stats 는 스캔한 원본 수(scanned)와 이미 썸네일이 있어 건너뛴 수(skipped)를
    # 정수 두 개로만 세는 카운터다 — 키를 모으지 않으므로 메모리는 늘지 않는다.
    # 대부분 이미 썸네일이 있는 버킷에서는 "생성/오류" 카운터가 오래 안 늘 수 있어,
    # 이 카운터가 없으면 스캔이 멈춘 건지 그냥 대상이 없는 건지 로그만으로 알 수 없다.
    print(f"[1/2] 대상 스캔: {args.bucket}/{prefix or '(전체)'}")
    stats = {"scanned": 0, "skipped": 0}
    originals = _with_progress(iter_originals(s3, args.bucket, prefix), stats)
    todo = iter_todo(originals, iter_thumb_keys(s3, args.bucket, prefix), stats=stats)

    if args.limit:
        todo = itertools.islice(todo, args.limit)

    if args.dry_run:
        print("\n[dry-run] 썸네일을 만들 대상 (앞 20건):")
        shown = 0
        total = 0
        for key, _size in todo:
            total += 1
            if shown < 20:
                print(f"  {key}  →  {THUMB_PREFIX}{key}")
                shown += 1
        if total > shown:
            print(f"  … 외 {total - shown:,}건")
        if args.limit and total >= args.limit:
            # islice가 --limit 에서 멈췄으므로 total은 "실제 대상 수"가 아니라
            # "--limit 이 찾아낸 수"다. 그대로 찍으면 5백만 건짜리 대상을 20건으로
            # 잘못 읽을 수 있다 — 잘림을 숨기지 않는다.
            print(f"\n대상 {total:,}건 이상 — --limit {args.limit:,} 에 걸려 멈췄습니다.")
            print("실제 전체 대상 수를 보려면 --limit 없이 다시 실행하세요.")
        else:
            print(f"\n대상 {total:,}건 (쓰기 없음)")
            if total == 0:
                if stats["scanned"] == 0:
                    print("원본을 하나도 찾지 못했습니다 — --bucket/--prefix, "
                          "확장자(IMAGE_EXTS)를 확인하세요.")
                else:
                    print(f"원본 {stats['scanned']:,}건을 스캔했고 전부 이미 썸네일이 있습니다.")
        return

    print(f"[2/2] 썸네일 생성 (workers={args.workers})")
    errors = ErrorLog(args.error_log)
    counts = {"created": 0, "undecodable": 0, "failed": 0}
    started = time.monotonic()

    def handle(item):
        key, size = item
        # 목록이 이미 크기를 알려주므로 **다운로드하기 전에** 거른다. draft가 듣지 않는
        # PNG·TIFF·BMP 대형 파일이 실제 대상이다 — 한 장이 워커 수만큼 곱해진다.
        if is_too_large(size, args.max_bytes):
            return key, "too-large", f"{size:,} bytes > --max-bytes {args.max_bytes:,}"
        try:
            body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
        except Exception as exc:
            return key, "download", f"{type(exc).__name__}: {exc}"
        thumb = make_thumbnail(body)
        if thumb is None:
            return key, "undecodable", ""
        try:
            s3.put_object(Bucket=args.bucket, Key=THUMB_PREFIX + key,
                          Body=thumb, ContentType="image/webp")
        except Exception as exc:
            return key, "put", f"{type(exc).__name__}: {exc}"
        return key, "created", ""

    try:
        for i, (key, outcome, detail) in enumerate(run_bounded(todo, args.workers, handle), 1):
            if outcome == "created":
                counts["created"] += 1
            elif outcome == "undecodable":
                counts["undecodable"] += 1
                errors.write(key, "undecodable")
            else:
                counts["failed"] += 1
                errors.write(key, outcome, detail)
            if i % 500 == 0:
                mins = (time.monotonic() - started) / 60
                print(f"      생성 {counts['created']:,} / 디코딩실패 {counts['undecodable']:,}"
                      f" / 오류 {counts['failed']:,}   (경과 {mins:.0f}분)", flush=True)
    except BaseException:
        # 크래시 경로다 — 목록/다운로드가 죽었거나 Ctrl+C 다. 이번 실행이 뭔가
        # 확인했다는 보장이 없으므로, 파일을 열지 않았다면(=한 줄도 못 썼다면)
        # 지난 실행이 남긴 실패 목록을 절대 건드리지 않는다.
        errors.close(cleanup_if_empty=False)
        raise

    # 정상 종료 — 여기 도달했다는 것 자체가 끝까지 돌았다는 뜻이다. 이번 실행이
    # 정말로 실패 0건이면 지난 실행이 남긴 낡은 실패 목록을 지운다(기본
    # cleanup_if_empty=True) — 안 지우면 이미 해결된 실패가 아직 있는 것처럼 보인다.
    errors.close()

    mins = (time.monotonic() - started) / 60
    processed = counts["created"] + counts["undecodable"] + counts["failed"]
    print(f"\n완료 — 생성 {counts['created']:,}건"
          f" / 디코딩 실패 {counts['undecodable']:,}건"
          f" / 오류 {counts['failed']:,}건"
          f" / 건너뜀(이미 썸네일 있음) {stats['skipped']:,}건   (경과 {mins:.0f}분)")
    if processed == 0:
        if stats["scanned"] == 0:
            print("원본을 하나도 찾지 못했습니다 — --bucket/--prefix, "
                  "확장자(IMAGE_EXTS)를 확인하세요.")
        else:
            print(f"원본 {stats['scanned']:,}건을 스캔했고 전부 이미 썸네일이 있습니다.")
    if errors.count:
        print(f"실패 목록: {errors.path} ({errors.count:,}줄)")
        print("같은 명령을 다시 실행하면 성공분은 건너뛰고 실패분만 재시도한다.")
        print("두 번 돌린 뒤에도 남아 있는 키가 진짜 문제다(손상 파일·권한 등).")
    if counts["undecodable"]:
        print("  디코딩 실패 = pillow 가 못 여는 파일. 원본은 그대로이므로 UI 는 원본으로 표시된다.")
    if counts["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
