#!/usr/bin/env python3
"""values.yaml에 선언됐는데 템플릿이 참조하지 않는 키를 찾는다.

왜 필요한가. Helm은 쓰이지 않는 값에 오류를 내지 않는다. 그래서 이 부류의 결함은
**설정했는데 조용히 무시되는** 형태로 나타나고, 운영자는 고쳤다고 믿는다.
실제로 이 저장소에서 넷을 이렇게 찾았다:

  - cas-server  config.requestTimeoutSecs — README·CHANGELOG가 언급하는데 미렌더
  - cas-server  serviceAccount.*          — 블록만 있고 참조 0건
  - nexus-server serviceAccount.*         — 같은 결함 (차트 0.3.0에서 수정)
  - cas-server  terminationGracePeriodSeconds — 과거 같은 결함 (차트 0.1.22에서 수정)

주의: 부모 경로 매칭으로 판정하면 안 된다. `.Values.config`가 템플릿에 있다는 이유로
`config.requestTimeoutSecs`를 "참조됨"으로 처리하면 이 검사는 아무것도 잡지 못한다
(첫 구현이 그랬고, 뮤테이션 테스트로 드러났다).

그래서 두 단계로 본다:
  1) 정확 경로 `.Values.a.b.c`가 있으면 참조됨
  2) 없으면, 조상이 `toYaml`/`with`/`range`로 통째로 소비되는지 확인 —
     resources, nodeSelector, extraEnv 같은 블록이 그 경우다

둘 다 아니면 미참조로 보고한다.

사용:
    python scripts/check-unrendered-values.py                 # charts/ 전체
    python scripts/check-unrendered-values.py charts/cas-server  # 특정 차트
종료 코드 1 = 미참조 키 있음.

## 이 검사가 **덮지 않는 것** (과신하지 말 것)

1. **렌더된 TOML 의 서버측 키 이름은 보지 않는다.** `.Values.*` 와 템플릿만 대조하므로
   `db_min_connection = {{ .Values.config.dbMinConnections }}` 처럼 **서버 필드명에 오타가
   나면 통과한다.** `AppConfig` 에 `deny_unknown_fields` 가 없어 서버도 조용히 무시한다.
   이것이 실제로 위험한 부류이므로, 설정 키를 추가·변경할 때는 렌더된 ConfigMap 을
   **실제 바이너리에 먹여** 기동 로그의 "적용된 설정" 줄로 확인할 것.
2. **스칼라를 map/list 로 바꾸는 스키마 변경은 잡지 못한다.** 예를 들어
   `maxUploadBytesInFlight: 3221225472` 을 `{soft: ..., hard: ...}` 로 바꾸면 그 노드가
   container 가 되어 "조상 소비"로 분류되고, 템플릿은 여전히 스칼라로 다루므로 `0` 이
   렌더된다. 타입을 바꾸는 변경은 사람이 템플릿을 함께 고쳐야 한다.
3. `index .Values.config "x"` 나 `{{- $c := .Values.config }}` 같은 **간접 참조는 미참조로
   오탐한다.** 그런 형태를 도입하면 이 스크립트를 함께 손봐야 한다.
"""
import io
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML이 필요합니다: pip install pyyaml")

# Windows 기본 콘솔 코드페이지(cp949)에서는 한글·em dash 출력이 죽는다.
# 릴리스 절차용 스크립트가 인코딩 때문에 실패하면 안 되므로 명시적으로 UTF-8로 바꾼다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 조상이 "통째로 소비된다"고 인정하는 함수·액션.
#
# 이 목록이 판정의 핵심이다. 조상 경로가 템플릿에 **등장하는지**만 보면 아무것도
# 잡지 못한다 — `.Values.config`가 어딘가에 있다는 이유로 `config.requestTimeoutSecs`가
# 통과해 버린다. 실제로 첫 구현이 그랬고, 두 번째 구현도 이 목록을 정의만 해두고
# 쓰지 않아 같은 상태였다(리뷰에서 지적됨). 그러므로 참조가 **이 문맥 안에** 있는지
# 확인한다.
WHOLESALE_FUNCS = ("toYaml", "with", "range", "include", "tpl", "nindent", "toJson", "quote")

# `.Values.a.b.c` 와 `(.Values.a.b).c` 둘 다 잡는다.
#
# 괄호 형태를 놓치면 subtree 전체가 눈에서 사라진다. `_helpers.tpl`의
# `(.Values.storage.nfs).backends`가 그 예로, 이전 정규식은 `storage.nfs`까지만 잡아
# 그 아래 모든 키가 "조상 소비"로 분류돼 통과했다.
REF_RE = re.compile(r"\(?\.Values\.([A-Za-z0-9_.]+)\)?((?:\.[A-Za-z0-9_]+)*)")


def strip_comments(text):
    """Go 템플릿 주석과 YAML 주석 줄을 제거한다.

    정규식이 생 텍스트를 훑기 때문에, 주석 안의 `.Values.x` 도 "참조됨"으로 세어진다.
    이 템플릿들은 주석이 많아 실제 미참조 키가 그렇게 숨을 수 있다.
    """
    text = re.sub(r"\{\{-?/\*.*?\*/-?\}\}", "", text, flags=re.S)
    out = []
    for line in text.split("\n"):
        # 줄 전체가 주석인 경우만 지운다. 값 안의 `#`(색상 코드 등)을 건드리지 않는다.
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def is_container(values, path):
    """values.yaml 에서 이 경로가 map/list 인가 (= 통째로 소비될 수 있는 대상인가)."""
    node = values
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, (dict, list))


def collect_refs(text, values):
    """(정확 참조 경로 집합, 통째로 소비되는 경로 집합).

    "통째로 소비"는 두 조건을 **모두** 만족해야 인정한다.

    1. 같은 줄에 `toYaml`/`range`/`include` 등 블록을 다루는 구문이 있고
    2. values.yaml 에서 그 경로가 **map 또는 list** 다

    2번이 없으면 `{{- with .Values.config.maxUploadBytesInFlight }}` 같은 **스칼라
    가드**까지 "통째로 소비"로 분류된다. `with` 는 단순 substring 매칭이라 실제로 그런
    일이 벌어졌고, 그 결과 37개 경로가 잘못 분류됐다 — 그 아래에 새 키를 넣으면
    렌더되지 않는데도 검사를 통과했다. 스칼라는 애초에 자식이 없으므로 "조상 소비"
    판정 대상이 될 이유가 없다.
    """
    exact, wholesale = set(), set()
    for line in text.split("\n"):
        line_has_wholesale = any(f in line for f in WHOLESALE_FUNCS)
        for m in REF_RE.finditer(line):
            path = (m.group(1) + m.group(2)).rstrip(".")
            exact.add(path)
            if line_has_wholesale and is_container(values, path):
                wholesale.add(path)
    return exact, wholesale


def read_templates(templates_dir):
    """`templates/` 를 재귀적으로 읽는다.

    이전 판은 `os.listdir` 한 겹만 봐서, 템플릿을 하위 폴더로 정리한 차트에서는
    그 안의 키가 전부 미참조로 보고돼 릴리스가 막혔을 것이다.
    """
    text = ""
    for root, _dirs, files in os.walk(templates_dir):
        for name in sorted(files):
            text += io.open(os.path.join(root, name), encoding="utf-8").read() + "\n"
    return text


def leaf_paths(node, prefix=""):
    """values 트리의 리프 경로. 빈 dict/list도 리프로 본다(선언 자체가 계약이므로)."""
    if isinstance(node, dict):
        if not node:
            yield prefix
            return
        for key, value in node.items():
            child = f"{prefix}.{key}" if prefix else key
            yield from leaf_paths(value, child)
    elif isinstance(node, list):
        # 리스트 항목의 내부 키는 range 안에서 `.id` 형태로 참조되므로
        # 경로로 추적할 수 없다. 리스트 자체가 참조되는지만 본다.
        yield prefix
    else:
        yield prefix


def check_chart(chart_dir):
    values_path = os.path.join(chart_dir, "values.yaml")
    templates_dir = os.path.join(chart_dir, "templates")

    values = yaml.safe_load(io.open(values_path, encoding="utf-8")) or {}

    template_text = strip_comments(read_templates(templates_dir))
    exact, wholesale = collect_refs(template_text, values)

    declared = set(leaf_paths(values))
    # 중간 노드도 선언된 것으로 본다 — 템플릿이 `.Values.resources` 처럼 블록째
    # 참조하는 경우 그것이 "선언되지 않았다"고 보고되면 안 된다.
    declared_all = set(declared)
    for path in declared:
        parts = path.split(".")
        for i in range(1, len(parts)):
            declared_all.add(".".join(parts[:i]))

    unreferenced = []
    via_ancestor = []

    for path in sorted(declared):
        if path in exact:
            continue

        # 조상이 **통째로 소비되는가.** 등장 여부가 아니라 `toYaml`/`with`/`range` 등의
        # 문맥에서 쓰였는지를 본다 — 등장 여부만 보면 이 검사는 무력해진다.
        parts = path.split(".")
        ancestor = None
        for i in range(len(parts) - 1, 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in wholesale:
                ancestor = candidate
                break

        if ancestor:
            via_ancestor.append((path, ancestor))
        else:
            unreferenced.append(path)

    # ── 반대 방향: 템플릿이 쓰는데 values.yaml 에 선언이 없는 키 ──────────────
    #
    # 같은 부류의 결함이 반대로도 생긴다. 선언이 없으면 운영자는 그 키가 있는 줄
    # 모르고, 렌더는 빈 값으로 조용히 통과한다. 이 저장소에서 실제로
    # `secrets.dbPassword` 등 세 개가 그 상태였고, `auth.adminToken` 은 불리언으로
    # 선언돼 있는데 Secret 에 자격증명으로 들어가 리터럴 "true" 가 admin 토큰이 됐다.
    undeclared = []
    for ref in sorted(exact):
        if ref in declared_all:
            continue
        # Helm 내장. 차트가 선언할 대상이 아니다.
        if ref == "global" or ref.startswith("global."):
            continue
        undeclared.append(ref)

    name = os.path.basename(os.path.normpath(chart_dir))
    print(f"── {name} ──")
    print(f"   values 리프 키 {len(declared)}개, 템플릿 참조 경로 {len(exact)}개, "
          f"조상 소비 {len(via_ancestor)}개")

    failed = False
    if unreferenced:
        failed = True
        print(f"   미참조 {len(unreferenced)}개 — values 에 있는데 템플릿이 쓰지 않습니다(설정해도 무시됨):")
        for path in unreferenced:
            print(f"     - {path}")
    if undeclared:
        failed = True
        print(f"   미선언 {len(undeclared)}개 — 템플릿이 쓰는데 values 에 없습니다(운영자가 알 수 없음):")
        for path in undeclared:
            print(f"     - {path}")

    if failed:
        return 1

    print("   양방향 모두 일치.")
    return 0


def discover_charts(root):
    """Chart.yaml 이 있는 디렉터리를 차트로 본다."""
    found = []
    for entry in sorted(os.listdir(root)):
        path = os.path.join(root, entry)
        if os.path.isfile(os.path.join(path, "Chart.yaml")):
            found.append(path)
    return found


def main(argv):
    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    if argv:
        targets = [os.path.normpath(a) for a in argv]
    else:
        charts_dir = os.path.join(repo_root, "charts")
        targets = discover_charts(charts_dir)
        if not targets:
            print(f"charts/ 에서 차트를 찾지 못했습니다: {charts_dir}")
            return 1

    failed = []
    for target in targets:
        if check_chart(target) != 0:
            failed.append(os.path.basename(target))
        print()

    if failed:
        print(f"실패: {', '.join(failed)}")
        return 1

    print(f"차트 {len(targets)}개 모두 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
