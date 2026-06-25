{{/* 앱 이름 */}}
{{- define "nexus-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* 전체 리소스명 */}}
{{- define "nexus-server.fullname" -}}
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

{{/* 차트 레이블 */}}
{{- define "nexus-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* 공통 레이블 */}}
{{- define "nexus-server.labels" -}}
helm.sh/chart: {{ include "nexus-server.chart" . }}
{{ include "nexus-server.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* 셀렉터 레이블 */}}
{{- define "nexus-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nexus-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* 비밀 Secret 이름 (existingSecret 비우면 fullname) */}}
{{- define "nexus-server.secretName" -}}
{{- if .Values.secret.existingSecret }}{{ .Values.secret.existingSecret }}{{- else }}{{ include "nexus-server.fullname" . }}{{- end }}
{{- end }}
