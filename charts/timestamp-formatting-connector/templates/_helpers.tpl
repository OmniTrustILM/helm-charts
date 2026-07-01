{{/*
Expand the name of the chart.
*/}}
{{- define "timestamp-formatting-connector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "timestamp-formatting-connector.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "timestamp-formatting-connector.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "timestamp-formatting-connector.labels" -}}
helm.sh/chart: {{ include "timestamp-formatting-connector.chart" . }}
{{ include "timestamp-formatting-connector.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "timestamp-formatting-connector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "timestamp-formatting-connector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "timestamp-formatting-connector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "timestamp-formatting-connector.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the image name
*/}}
{{- define "timestamp-formatting-connector.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the curl
*/}}
{{- define "timestamp-formatting-connector.curl.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.curl.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image pull secret names
*/}}
{{- define "timestamp-formatting-connector.imagePullSecrets" -}}
{{ include "ilm-lib.images.pullSecrets" (dict "images" (list .Values.image) "global" .Values.global) }}
{{- end -}}

{{/*
Render init containers, if any
*/}}
{{- define "timestamp-formatting-connector.customization.initContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.initContainers .Values.initContainers) "context" $ ) }}
{{- end -}}

{{/*
Render sidecar containers, if any
*/}}
{{- define "timestamp-formatting-connector.customization.sidecarContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.sidecarContainers .Values.sidecarContainers) "context" $ ) }}
{{- end -}}

{{/*
Render additional volumes, if any
*/}}
{{- define "timestamp-formatting-connector.customization.volumes" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumes .Values.additionalVolumes) "context" $ ) }}
{{- end -}}

{{/*
Render additional volume mounts, if any
*/}}
{{- define "timestamp-formatting-connector.customization.volumeMounts" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumeMounts .Values.additionalVolumeMounts) "context" $ ) }}
{{- end -}}

{{/*
Render customized ports, if any
*/}}
{{- define "timestamp-formatting-connector.customization.ports" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalPorts .Values.additionalPorts) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables, if any
*/}}
{{- define "timestamp-formatting-connector.customization.env" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalEnv.variables .Values.additionalEnv.variables) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables from configmaps and secrets, if any
*/}}
{{- define "timestamp-formatting-connector.customization.envFrom" -}}
{{- include "ilm-lib.customizations.render.configMapEnv" ( dict "parts" (list .Values.global.additionalEnv.configMaps .Values.additionalEnv.configMaps) "context" $ ) }}
{{- include "ilm-lib.customizations.render.secretEnv" ( dict "parts" (list .Values.global.additionalEnv.secrets .Values.additionalEnv.secrets) "context" $ ) }}
{{- end -}}

{{/*
Render customized command and arguments, if any
*/}}
{{- define "timestamp-formatting-connector.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.command "context" $) }}
{{- end -}}

{{- define "timestamp-formatting-connector.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.args "context" $) }}
{{- end -}}

{{/*
Ephemeral volume for writable /tmp (required when readOnlyRootFilesystem=true)
*/}}
{{- define "timestamp-formatting-connector.ephemeralVolume" -}}
{{ include "ilm-lib.volumes.ephemeral" (dict "volumes" .Values.volumes "global" .Values.global.volumes) }}
{{- end -}}
