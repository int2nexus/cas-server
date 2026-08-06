#!/usr/bin/env bash
# 차트별 CHANGELOG.md 에서 "현재 Chart.yaml version" 섹션만 발췌해 RELEASE_NOTES.md 로 쓴다.
#
# chart-releaser 는 release-notes-file 을 **패키징된 tgz 안**(chart.Files)에서 찾는다.
# 소스 디렉터리가 아니므로, 이 스크립트는 cr 이 패키징하기 전에 돌아야 하고
# RELEASE_NOTES.md 는 .helmignore 로 제외되면 안 된다.
# 파일을 못 찾으면 cr 은 실패하지 않고 경고 한 줄만 남긴 뒤 Chart.yaml 의 description 을
# 릴리스 본문으로 쓴다 — 조용히 회귀하므로 여기서 미리 막는다.
#
# 사용: bash scripts/extract-release-notes.sh   (레포 루트에서)

set -euo pipefail

status=0

for chart_dir in charts/*/; do
  chart_dir="${chart_dir%/}"
  name="$(basename "$chart_dir")"
  changelog="$chart_dir/CHANGELOG.md"
  notes="$chart_dir/RELEASE_NOTES.md"

  version="$(sed -n 's/^version:[[:space:]]*"\{0,1\}\([^"[:space:]]*\)"\{0,1\}[[:space:]]*$/\1/p' \
    "$chart_dir/Chart.yaml" | head -1)"

  if [ -z "$version" ]; then
    echo "::error::$name: Chart.yaml 에서 version 을 읽지 못했습니다"
    status=1
    continue
  fi

  if [ ! -f "$changelog" ]; then
    echo "::error::$name: CHANGELOG.md 가 없습니다 (릴리스 본문의 원본입니다)"
    status=1
    continue
  fi

  # "## <version>" 헤딩부터 다음 "## " 헤딩 전까지. 버전에 점이 있으므로 정규식 대신
  # 문자열 비교로 매칭한다. 헤딩 뒤에 날짜 등이 붙어도(`## 0.1.23 (2026-08-07)`) 잡힌다.
  # 마지막 `NF {p=1} p` 는 선행 빈 줄만 걷어낸다.
  awk -v h="## $version" '
    index($0, h) == 1 && (length($0) == length(h) || substr($0, length(h) + 1, 1) == " ") {
      found = 1
      next
    }
    found && /^## / { exit }
    found { print }
  ' "$changelog" | awk 'NF { p = 1 } p' > "$notes"

  if ! grep -q '[^[:space:]]' "$notes"; then
    rm -f "$notes"
    echo "::error::$name: CHANGELOG.md 에 '## $version' 섹션이 없습니다."
    echo "::error::$name: 버전을 올렸다면 변경 요약(동작 변경 / 마이그레이션 / 설정 키)을 함께 써주세요."
    status=1
    continue
  fi

  echo "$name $version — 릴리스 본문 $(grep -c '' "$notes") 줄 발췌"
done

exit "$status"
