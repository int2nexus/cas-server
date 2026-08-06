# cas-server 차트 변경 이력

각 `##` 섹션이 그대로 해당 버전의 **GitHub Release 본문**이 됩니다
(`scripts/extract-release-notes.sh` 가 발췌 → chart-releaser 가 릴리스 본문으로 사용).

`Chart.yaml` 의 `version` 을 올릴 때 이 파일 맨 위에 섹션을 함께 추가하세요.
섹션이 없으면 릴리스 워크플로가 실패합니다.

해당 사항이 없는 항목도 **"없음"이라고 적습니다** — 도입하는 쪽이 *없었다* 와 *안 썼다* 를
구별할 수 있어야 합니다.

```markdown
## <version>

image: `int2jieun/cas-server:<tag>` (변경 없음이면 그렇게 적기)

**동작 변경** — 없음
**마이그레이션** — 없음
**설정 키** — 없음
```

## 0.1.22

image: `int2jieun/cas-server:0.1.16`

이 버전부터 변경 이력을 남깁니다.
