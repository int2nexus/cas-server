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
