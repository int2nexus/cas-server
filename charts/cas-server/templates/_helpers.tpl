{{/*
storage 설정 검증 — 렌더 시점에 막는다.

왜 fail 인가. 서버는 storage_backends 가 비면 기동 시 panic 한다. 그것을 그냥
통과시키면 템플릿 오류가 CrashLoopBackOff 로 바뀌고, replicaCount: 1 +
updateStrategy: Recreate 조합에서는 전면 장애가 된다. 클러스터에 닿기 전에
읽을 수 있는 메시지로 죽는 편이 낫다.

두 가지를 본다:
1. mode 화이트리스트 — 오타("nsf")나 대소문자 불일치("NFS")는 아래 eq 비교를
   모두 빗나가 백엔드 0개로 **조용히** 렌더된다. install 도 성공하고 파드만 죽는다.
2. nfs 백엔드 목록 — mode 가 nfs 인데 목록이 비면 같은 결과다.

모든 템플릿이 이것을 첫 줄에서 부른다. 한 곳만 가드하면 helm 은 다른 템플릿에서
먼저 실패해 엉뚱한 위치를 가리킨다(0.1.23 까지 pvc.yaml:2 의 nil pointer 가 그것이었다).
*/}}
{{- define "cas-server.validateStorage" -}}
{{- $mode := .Values.storage.mode | default "" }}
{{- if not (has $mode (list "s3" "nfs")) }}
{{- fail (printf "storage.mode 가 %q 입니다. \"s3\" 또는 \"nfs\" 여야 합니다(대소문자 구분). 잘못된 값은 백엔드 0개로 렌더되어 파드가 기동 시 panic 합니다." $mode) }}
{{- end }}
{{- if eq $mode "nfs" }}
{{- if not (.Values.storage.nfs).backends }}
{{- fail "storage.mode=nfs 인데 storage.nfs.backends 가 비어 있습니다. 최소 한 개가 필요합니다:\n  storage:\n    nfs:\n      backends:\n        - id: nas1\n          name: nas1\n          mountPath: /mnt/nas1\n          storageClassName: nfs-client\n          storage: 1Ti" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
앱 이름 (nameOverride 지원)
*/}}
{{- define "cas-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
전체 리소스명: "{릴리즈명}-{앱이름}" 형식
fullnameOverride 로 완전히 대체 가능
*/}}
{{- define "cas-server.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
readinessProbe 예산 검증 — 렌더 시점에 막는다.

`/_internal/health` 는 DB 커넥션을 얻지 못하면 `config.dbAcquireTimeoutSecs` 만큼
붙들려 있다가 판정을 낸다. `readinessProbe.timeoutSeconds` 가 그보다 작거나 같으면
**kubelet 이 서버의 판정을 받기 전에 프로브를 끊는다.** 그러면 이미지 0.1.18 의
"포화(200 saturated)" 와 "단절(503 degraded)" 구분이 무의미해지고, 포화만으로도
`failureThreshold` 회 실패해 유일한 파드가 Service 에서 빠진다 — 이 릴리스가 막으려는
바로 그 결과다.

프로즈로만 적어두면 dbAcquireTimeoutSecs 를 올리는 순간 조용히 기능이 사라진다.
서버 기본값이 30 이라(차트가 10 으로 낮춰 쓴다) 차트 밖에서 돌리면 특히 그렇다.
*/}}
{{- define "cas-server.validateProbeBudget" -}}
{{- $acquire := int .Values.config.dbAcquireTimeoutSecs }}
{{- $probe   := int .Values.readinessProbe.timeoutSeconds }}
{{- if le $probe $acquire }}
{{- fail (printf "readinessProbe.timeoutSeconds(%d) 가 config.dbAcquireTimeoutSecs(%d) 보다 커야 합니다. 그러지 않으면 kubelet 이 서버의 readiness 판정을 받기 전에 프로브를 끊고, 풀 포화만으로도 파드가 Service 에서 빠집니다(replicaCount 1 이므로 전면 중단). 권장: timeoutSeconds = dbAcquireTimeoutSecs + 2" $probe $acquire) }}
{{- end }}
{{- end }}

{{/*
파드가 쓸 ServiceAccount 이름.

- create: true  → name 이 있으면 그 이름으로 만들고, 없으면 fullname 으로 만든다
- create: false → name 이 있으면 기존 그것을 쓰고, 없으면 네임스페이스의 "default"

주의: create: false + name: "" 이면 "default" SA 로 돌아가고, 그 SA 는 보통
토큰을 자동 마운트한다. 즉 **아무것도 설정하지 않은 상태가 더 느슨한 쪽**이다.
이 파드는 쿠버네티스 API 를 부르지 않으므로 create: true 로 전용 SA 를 만들고
automountToken: false 를 쓰는 편이 안전하다.
*/}}
{{- define "cas-server.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "cas-server.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
차트 레이블 (app.kubernetes.io/version 포함)
*/}}
{{- define "cas-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
공통 레이블 — 모든 리소스에 부착
*/}}
{{- define "cas-server.labels" -}}
helm.sh/chart: {{ include "cas-server.chart" . }}
{{ include "cas-server.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
셀렉터 레이블 — Deployment.spec.selector 와 Service.spec.selector 에 사용
*/}}
{{- define "cas-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cas-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
PostgreSQL 호스트 (externalDatabase.host)
*/}}
{{- define "cas-server.dbHost" -}}
{{- .Values.externalDatabase.host }}
{{- end }}

{{/*
PostgreSQL 포트
*/}}
{{- define "cas-server.dbPort" -}}
{{- .Values.externalDatabase.port | toString }}
{{- end }}

{{/*
PostgreSQL 사용자명
*/}}
{{- define "cas-server.dbUser" -}}
{{- .Values.externalDatabase.username }}
{{- end }}

{{/*
PostgreSQL 데이터베이스명
*/}}
{{- define "cas-server.dbName" -}}
{{- .Values.externalDatabase.database }}
{{- end }}

{{/*
NAS 백엔드별 PVC 이름:
- backend.pvcName 이 비어있으면 "{fullname}-{backend.id}" 자동 생성
- .root = $ (루트 컨텍스트), .backend = 백엔드 항목
*/}}
{{- define "cas-server.pvcName" -}}
{{- $root := .root }}
{{- $backend := .backend }}
{{- if $backend.pvcName }}
{{- $backend.pvcName }}
{{- else }}
{{- printf "%s-%s" (include "cas-server.fullname" $root) $backend.id | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
