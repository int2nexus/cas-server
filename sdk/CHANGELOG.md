# int2nexus-sdk 변경 이력

`int2nexus-sdk` 의 변경은 이 파일에 적습니다. 서버 이미지·차트와 따로 발행하고 따로 설치합니다.

```
pip install --extra-index-url https://int2nexus.github.io/cas-server/sdk/simple/ int2nexus-sdk==<버전>
```

`scripts/publish_sdk.py` 는 `sdk/pyproject.toml` 의 버전과 같은 `## <버전>` 절이 이 파일에 없으면
빌드하지 않고 멈춥니다. 최신 버전이 위로 오게 적습니다.

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
