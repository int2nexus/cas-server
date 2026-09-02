#!/usr/bin/env python3
"""발행되는 차트에 미치환 placeholder 가 남아 있는지 본다.

왜 필요한가. 이미지 태그와 digest 는 **차트 문서를 쓰는 시점에 아직 없다** — 서버 CI 가
이미지를 올려야 정해지는 값이다. 그래서 CHANGELOG·README·values 를 미리 써 두고
`[IMAGE_TAG]` 같은 자리표시자를 남긴 뒤 발행 직전에 채우는데, 채우는 것이 사람 손이라
빠진다.

빠지면 조용히 틀리지 않고 **밖으로 나간다.** extract-release-notes.sh 가 CHANGELOG 절을
그대로 GitHub Release 본문으로 쓰므로 도입하는 쪽이 보는 첫 화면에
`int2jieun/cas-server:[IMAGE_TAG]` 가 찍히고, README·values 는 tgz 안으로 들어간다.

## 왜 무조건 검사하지 않는가

이 저장소는 **버전을 올리지 않은 커밋도 main 에 올린다**(b8b7f3e, bf70902, bcb6548 …).
발행 전 문서를 미리 쌓아 두는 흐름이고, 그 구간에는 placeholder 가 남아 있는 것이 정상이다.
전수 검사를 걸면 그 흐름이 통째로 막힌다.

그래서 판정 기준을 **"이번 push 가 이 차트를 발행하는가"** 로 둔다.

    Chart.yaml 의 version 으로 이미 태그(<차트이름>-<버전>)가 있다  → 발행 안 됨, 건너뜀
    그 태그가 없다                                                 → cr 이 발행함, 검사함

즉 version 을 올리는 순간부터 placeholder 가 결함이 된다. 쌓는 동안은 자유롭다.
cr 의 skip_existing 과 같은 기준이라 판정이 어긋나지 않는다.

사용:
    python scripts/check-placeholders.py                     # charts/ 전체
    python scripts/check-placeholders.py charts/cas-server   # 특정 차트
종료 코드 1 = 발행될 차트에 placeholder 있음.

## 이 검사가 **덮지 않는 것** (과신하지 말 것)

1. **채운 값이 맞는지는 보지 않는다.** `[IMAGE_TAG]` 를 지난 버전 번호로 잘못 채워도
   통과한다. digest 는 사람이 Docker Hub 의 값과 대조해야 한다 —
   `curl -s https://hub.docker.com/v2/repositories/<repo>/tags/<tag>` 의 `digest` 필드다.
2. **대괄호 형태만 본다.** `TBD`, `<태그>`, `xxx` 같은 자리표시자는 이 검사 밖이다.
   새 형태를 도입하면 아래 KNOWN 에 함께 넣을 것.
3. **markdown 링크 라벨은 일부러 뺀다.** `[CHANGELOG](CHANGELOG.md)` 처럼 뒤에 `(` 나
   `[` 가 오면 링크로 보고 넘긴다. 그래서 `[FOO](bar)` 꼴의 진짜 placeholder 는 못 잡는데,
   KNOWN 에 이름이 적힌 것은 그 경우에도 잡는다.
4. **태그 조회가 로컬 git 에 의존한다.** CI 는 `fetch-depth: 0` 이라 태그가 전부 있지만,
   얕은 클론에서 돌리면 태그를 못 찾아 **모든 차트를 발행 대상으로 보고 검사한다.**
   안전한 쪽으로 틀리는 것이라 그대로 둔다.
"""
import io
import os
import re
import subprocess
import sys

import yaml

# 출력에 U+2014 같은 글자가 섞이는데 Windows 콘솔 기본값(cp949)이 그것을 인코딩하지
# 못해 UnicodeEncodeError 로 죽는다. CI(ubuntu, UTF-8)에서는 나지 않으므로 **로컬에서만
# 깨지는 실패**가 되고, 검사 결과가 아니라 검사 자체가 사라진다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 이름을 아는 자리표시자. markdown 링크 예외를 적용하지 않고 항상 잡는다.
KNOWN = ("[IMAGE_TAG]", "[IMAGE_DIGEST]")

# 그 밖의 [UPPER_SNAKE] 꼴. 뒤에 "(" 나 "[" 가 오면 markdown 링크 라벨이므로 뺀다.
GENERIC_RE = re.compile(r"\[[A-Z][A-Z0-9_]{2,}\](?![(\[])")

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
TEXT_EXT = {".md", ".yaml", ".yml", ".txt", ".tpl"}


def existing_tags(root):
    """저장소의 태그 집합. git 이 없거나 실패하면 빈 집합(= 전부 검사)."""
    try:
        out = subprocess.run(
            ["git", "tag", "--list"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def chart_meta(chart_dir):
    """(name, version). Chart.yaml 이 없거나 못 읽으면 (None, None)."""
    path = os.path.join(chart_dir, "Chart.yaml")
    if not os.path.isfile(path):
        return None, None
    with io.open(path, encoding="utf-8") as f:
        meta = yaml.safe_load(f) or {}
    name = meta.get("name")
    version = meta.get("version")
    return (str(name) if name else None, str(version) if version else None)


def find_hits(chart_dir):
    """[(상대경로, 줄번호, 토큰)] — 발견 순서대로."""
    hits = []
    for dirpath, dirnames, filenames in os.walk(chart_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT:
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, chart_dir).replace(os.sep, "/")
            try:
                with io.open(path, encoding="utf-8") as f:
                    lines = f.readlines()
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(lines, 1):
                found = []
                for token in KNOWN:
                    if token in line:
                        found.append(token)
                for m in GENERIC_RE.finditer(line):
                    if m.group(0) not in found:
                        found.append(m.group(0))
                for token in found:
                    hits.append((rel, i, token))
    return hits


def check_chart(chart_dir, tags):
    """0 = 통과 또는 건너뜀, 1 = placeholder 발견."""
    name, version = chart_meta(chart_dir)
    label = os.path.basename(chart_dir.rstrip(os.sep))
    print("── {} ──".format(label))

    if not name or not version:
        print("   Chart.yaml 에서 name/version 을 읽지 못해 건너뜁니다")
        return 0

    tag = "{}-{}".format(name, version)
    if tag in tags:
        print("   {} 는 이미 발행된 버전입니다 — 이번 push 는 이 차트를 발행하지 "
              "않으므로 건너뜁니다".format(tag))
        print("   (발행 전 문서를 쌓는 구간이라 placeholder 가 남아 있어도 정상입니다)")
        return 0

    hits = find_hits(chart_dir)
    if not hits:
        print("   {} 로 발행됩니다. 미치환 placeholder 없음.".format(tag))
        return 0

    print("   {} 로 발행되는데 미치환 placeholder 가 {}건 있습니다:"
          .format(tag, len(hits)))
    for rel, lineno, token in hits:
        print("     {}:{}: {}".format(rel, lineno, token))
    print("::error::{}: 위 자리를 실제 값으로 채운 뒤 다시 push 하십시오. "
          "이미지 태그와 digest 는 Docker Hub 에 올라온 값과 대조할 것.".format(label))
    return 1


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if argv:
        targets = [os.path.abspath(p) for p in argv]
    else:
        charts = os.path.join(root, "charts")
        if not os.path.isdir(charts):
            print("charts/ 디렉터리가 없습니다: {}".format(charts))
            return 1
        targets = [
            os.path.join(charts, n)
            for n in sorted(os.listdir(charts))
            if os.path.isfile(os.path.join(charts, n, "Chart.yaml"))
        ]

    tags = existing_tags(root)
    if not tags:
        print("경고: git 태그를 읽지 못했습니다. 모든 차트를 발행 대상으로 보고 "
              "검사합니다(얕은 클론이면 이 상태가 정상입니다).\n")

    status = 0
    for chart_dir in targets:
        status |= check_chart(chart_dir, tags)
        print()

    if status:
        print("미치환 placeholder 가 있습니다.")
    else:
        print("차트 {}개 모두 통과.".format(len(targets)))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
