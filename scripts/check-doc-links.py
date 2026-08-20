#!/usr/bin/env python3
"""차트 문서 링크가 가리키는 릴리스 태그가 Chart.yaml 의 version 과 맞는지 본다.

왜 필요한가. `docs/` 는 Helm 릴리즈 Secret 1MB 한도 때문에 `.helmignore` 로 패키지에서
빠진다. 그래서 패키지 안의 README·values·NOTES 는 문서를 **밖으로 링크**할 수밖에 없고,
그 링크가 `main` 을 가리키면 `0.3.3` 을 손에 든 사람이 그 뒤에 바뀐 문서를 읽는다.
nexus-server 차트 0.3.3 에서 링크를 `blob/nexus-server-0.3.3/...` 로 고정한 이유가 그것이다.

고정하는 순간 새 부담이 생긴다 — **릴리스마다 손으로 버전을 올려야 한다.** 안 올리면
`main` 을 가리킬 때보다 덜 틀리지만 여전히 틀리고, 조용히 틀린다. 이 검사가 그 자리를 막는다.

판정은 하나뿐이다: 링크에 `<차트이름>-<버전>` 형태의 태그가 있으면 그 버전이 같은 차트의
`Chart.yaml` version 과 같아야 한다.

사용:
    python scripts/check-doc-links.py                  # charts/ 전체
    python scripts/check-doc-links.py charts/nexus-server   # 특정 차트
종료 코드 1 = 어긋난 링크 있음.

## 이 검사가 **덮지 않는 것** (과신하지 말 것)

1. **`main` 링크는 오류로 보지 않는다.** 차트마다 방침이 다를 수 있어(고정하지 않기로 한
   차트도 있다) 이미 고정한 링크만 검사한다. 뒤집으면, **한 번도 고정하지 않은 차트는 이
   검사의 보호를 전혀 받지 못한다.** 고정할 생각이라면 한 곳이라도 고정해야 감시가 시작된다.
2. **링크가 실제로 열리는지는 보지 않는다.** 태그는 chart-releaser 가 merge 이후에 만들므로,
   릴리스 직전에는 올바른 링크도 404 다. 이 검사는 문자열 대조이지 도달성 확인이 아니다.
3. **다른 차트를 가리키는 링크는 그 차트 기준으로 본다.** nexus-server 문서가
   `cas-server-0.1.26` 을 가리키면 cas-server 의 Chart.yaml 과 대조한다 — 남의 차트 버전을
   내 차트 버전으로 판정하지 않기 위해서다. 그 차트가 저장소에 없으면 건너뛴다.
"""
import io
import os
import re
import sys

import yaml

# 예: .../blob/nexus-server-0.3.3/charts/... 또는 raw.githubusercontent.com/.../nexus-server-0.3.3/...
TAG_RE = re.compile(r"(?<![\w-])([a-z][a-z0-9-]*?)-(\d+\.\d+\.\d+)(?=/)")

SKIP_DIRS = {".git", "node_modules"}
TEXT_EXT = {".md", ".yaml", ".yml", ".txt", ".tpl"}


def chart_versions(root):
    """charts/<name>/Chart.yaml 에서 {차트이름: version} 을 모은다."""
    out = {}
    charts = os.path.join(root, "charts")
    if not os.path.isdir(charts):
        return out
    for name in sorted(os.listdir(charts)):
        path = os.path.join(charts, name, "Chart.yaml")
        if not os.path.isfile(path):
            continue
        with io.open(path, encoding="utf-8") as f:
            meta = yaml.safe_load(f) or {}
        if meta.get("name") and meta.get("version"):
            out[str(meta["name"])] = str(meta["version"])
    return out


def scan_file(path, versions):
    """한 파일에서 어긋난 링크를 찾아 (줄번호, 줄, 차트, 링크버전, 기대버전) 로 돌려준다."""
    bad = []
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            for chart, ver in TAG_RE.findall(line):
                expected = versions.get(chart)
                if expected is None:
                    continue  # 이 저장소의 차트가 아니다 — 판정하지 않는다
                if ver != expected:
                    bad.append((lineno, line.rstrip(), chart, ver, expected))
    return bad


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    versions = chart_versions(root)
    if not versions:
        print("charts/ 아래에서 Chart.yaml 을 찾지 못했다", file=sys.stderr)
        return 1

    targets = argv[1:] or [os.path.join(root, "charts")]
    findings = []
    for target in targets:
        target = target if os.path.isabs(target) else os.path.join(root, target)
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1] not in TEXT_EXT:
                    continue
                path = os.path.join(dirpath, fn)
                for item in scan_file(path, versions):
                    findings.append((os.path.relpath(path, root),) + item)

    if not findings:
        print("문서 링크의 릴리스 태그가 Chart.yaml version 과 모두 일치한다")
        return 0

    print("Chart.yaml version 과 어긋나는 문서 링크:\n")
    for rel, lineno, line, chart, ver, expected in findings:
        print(f"  {rel}:{lineno}")
        print(f"    링크: {chart}-{ver}   기대: {chart}-{expected}")
        print(f"    {line.strip()[:120]}")
        print()
    print(f"{len(findings)}건. 링크의 태그를 올리거나 Chart.yaml version 을 확인할 것.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
