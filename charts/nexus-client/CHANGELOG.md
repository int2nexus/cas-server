# nexus-client 차트 변경 이력

각 `##` 섹션이 그대로 해당 버전의 **GitHub Release 본문**이 됩니다
(`scripts/extract-release-notes.sh` 가 발췌 → chart-releaser 가 릴리스 본문으로 사용).

`Chart.yaml` 의 `version` 을 올릴 때 이 파일 맨 위에 섹션을 함께 추가하세요.
섹션이 없으면 릴리스 워크플로가 실패합니다.

해당 사항이 없는 항목도 **"없음"이라고 적습니다** — 도입하는 쪽이 *없었다* 와 *안 썼다* 를
구별할 수 있어야 합니다. 이미지만 바뀐 릴리스라도 라우팅·프록시 계약이 유지되는지는
여기에 적혀 있어야 도입하는 쪽이 직접 시험하지 않아도 됩니다.

```markdown
## <version>

image: `jiwonkim97/nexus-client:<tag>` (변경 없음이면 그렇게 적기)

**동작 변경** — 없음
**마이그레이션** — 없음
**설정 키** — 없음
```

### 마이그레이션 항목 쓰는 법

nexus-client 는 정적 파일을 서빙하는 Caddy 뿐이고 DB 가 없으므로 이 항목은 `없음` 입니다.
롤백은 `helm rollback <release> <revision>` 으로 항상 안전합니다.

단 백엔드 계약(`/api`·`/cas` 프록시 경로, `backendUrl`·`casUrl` 해석)이 바뀌면 그건
**동작 변경** 항목에 적습니다 — nexus-server 버전과 맞물리는 변경이면 필요한 최소
nexus-server 버전을 함께 씁니다.

<!-- 새 버전 섹션은 이 줄 바로 아래에, 최신이 위로 오게 추가하세요 -->

## 0.1.5

image: `jiwonkim97/nexus-client:0.1.6`

이 버전부터 변경 이력을 남깁니다.
