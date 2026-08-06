#!/usr/bin/env python3
"""CAS에 이미 올라간 이미지의 썸네일을 사후 생성한다.

썸네일은 원래 Python SDK의 `nx.upload()`가 업로드와 함께 만든다. boto3/`aws s3` 등으로
CAS에 직접 올렸다면 그 경로가 없으므로 썸네일이 비고, nexus UI가 원본으로 폴백해 로딩이
무거워진다. 이 스크립트는 업로드 수단과 무관하게 **사후에 한 번 돌리면 되는** 도구다.

키 규약 (nexus-server `src/catalog/sample.rs`, SDK `nexus/upload.py`와 동일):

    원본    {bucket}/{key}
    썸네일  {bucket}/thumb/{key}        WebP, 긴 변 256px

멱등이다 — 이미 있는 썸네일은 건너뛰므로 중단 후 다시 돌려도 안전하다.

의존성: boto3, pillow   (nexus SDK는 필요 없다)

    pip install boto3 pillow

받기:

    curl -O https://raw.githubusercontent.com/int2nexus/cas-server/main/scripts/backfill_thumbnails.py

사용:

    export CAS_URL=http://<CAS 주소>:8080
    export CAS_KEY_ID=...
    export CAS_SECRET=...

    python backfill_thumbnails.py --bucket <버킷> --dry-run    # 먼저 확인 (읽기 전용)
    python backfill_thumbnails.py --bucket <버킷> --limit 20    # 소량 시험
    python backfill_thumbnails.py --bucket <버킷>               # 전체

    python backfill_thumbnails.py --bucket <버킷> --prefix images/
    python backfill_thumbnails.py --bucket <버킷> --ca-bundle /path/corp-ca.pem

자격증명은 `CAS_KEY_ID`/`CAS_SECRET`(SDK와 같은 이름) 또는 boto3 표준
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`를 읽는다. 엔드포인트는 `--endpoint`
또는 `CAS_URL`.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

THUMB_PREFIX = "thumb/"
THUMBNAIL_MAX_EDGE = 256
THUMBNAIL_QUALITY = 80

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
        # CAS는 경로 스타일(/{bucket}/{key})이다. 가상 호스트 스타일로 서명하면 404가 난다.
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )


def list_keys(s3, bucket: str, prefix: str) -> "list[str]":
    """prefix 아래 object key를 전부 모은다(페이지네이션 처리)."""
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def make_thumbnail(data: bytes) -> "bytes | None":
    """원본 bytes → 긴 변 256px WebP. 디코딩 실패 시 None."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
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
    ap.add_argument("--bucket", required=True, help="대상 CAS 버킷")
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
    args = ap.parse_args()

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
    print(f"[1/3] 목록 조회: {args.bucket}/{prefix or '(전체)'}")
    all_keys = list_keys(s3, args.bucket, prefix)
    originals = [
        k for k in all_keys
        if not k.startswith(THUMB_PREFIX)
        and os.path.splitext(k)[1].lower() in IMAGE_EXTS
    ]
    print(f"      object {len(all_keys)}건 중 이미지 원본 {len(originals)}건")

    print(f"[2/3] 기존 썸네일 조회: {args.bucket}/{THUMB_PREFIX}{prefix}")
    have_thumb = set(list_keys(s3, args.bucket, THUMB_PREFIX + prefix))
    todo = [k for k in originals if THUMB_PREFIX + k not in have_thumb]
    print(f"      이미 있음 {len(originals) - len(todo)}건 / 생성 대상 {len(todo)}건")

    if args.limit:
        todo = todo[: args.limit]
        print(f"      --limit {args.limit} 적용 → {len(todo)}건만 처리")

    if not todo:
        print("생성할 썸네일이 없습니다.")
        return

    if args.dry_run:
        print("\n[dry-run] 아래 key에 대해 썸네일을 만들 예정입니다 (앞 20건):")
        for k in todo[:20]:
            print(f"  {k}  →  {THUMB_PREFIX}{k}")
        if len(todo) > 20:
            print(f"  … 외 {len(todo) - 20}건")
        return

    print(f"[3/3] 썸네일 생성 (workers={args.workers})")
    lock = threading.Lock()
    done = {"ok": 0, "undecodable": 0}
    errors: dict[str, str] = {}

    def one(key: str) -> None:
        body = s3.get_object(Bucket=args.bucket, Key=key)["Body"].read()
        thumb = make_thumbnail(body)
        if thumb is None:
            with lock:
                done["undecodable"] += 1
            return
        s3.put_object(
            Bucket=args.bucket, Key=THUMB_PREFIX + key,
            Body=thumb, ContentType="image/webp",
        )
        with lock:
            done["ok"] += 1

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(one, k): k for k in todo}
        for i, f in enumerate(as_completed(futures), 1):
            try:
                f.result()
            except Exception as exc:   # 건당 격리 — 하나 실패해도 나머지는 계속
                errors[futures[f]] = f"{type(exc).__name__}: {exc}"
            if i % 100 == 0 or i == len(todo):
                print(f"      {i}/{len(todo)}", flush=True)

    print(
        f"\n완료 — 생성 {done['ok']}건"
        f" / 디코딩 실패 {done['undecodable']}건"
        f" / 오류 {len(errors)}건"
    )
    if done["undecodable"]:
        print("  디코딩 실패 = pillow가 못 여는 파일(손상·미지원 포맷). 원본은 그대로 있으니")
        print("  UI는 원본으로 표시된다.")
    if errors:
        print("\n오류 (앞 10건):")
        for k, e in list(errors.items())[:10]:
            print(f"  {k}: {e}")
        print("\n같은 명령을 다시 실행하면 성공분은 건너뛰고 실패분만 재시도한다.")
        sys.exit(1)


if __name__ == "__main__":
    main()
