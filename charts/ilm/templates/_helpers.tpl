{{/*
Expand the name of the chart.
*/}}
{{- define "ilm.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "ilm.fullname" -}}
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
{{- define "ilm.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ilm.labels" -}}
helm.sh/chart: {{ include "ilm.chart" . }}
{{ include "ilm.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ilm.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ilm.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "ilm.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ilm.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "ilm.registerConnectors" -}}
{{- if .Values.commonCredentialProvider.enabled }}
registerConnectors: true
{{- end}}
{{- end}}

{{/*
Return the image name
*/}}
{{- define "ilm.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the OPA
*/}}
{{- define "ilm.opa.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.opa.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the curl
*/}}
{{- define "ilm.curl.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.curl.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the kubectl
*/}}
{{- define "ilm.kubectl.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.kubectl.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image pull secret names
*/}}
{{- define "ilm.imagePullSecrets" -}}
{{- $images := list .Values.image .Values.opa.image .Values.curl.image .Values.kubectl.image }}
{{- if .Values.timeQualityMonitor }}
{{- $images = append $images .Values.timeQualityMonitor.image }}
{{- end }}
{{ include "ilm-lib.images.pullSecrets" (dict "images" $images "global" .Values.global) }}
{{- end -}}

{{/*
Return the ephemeral volume configuration
*/}}
{{- define "ilm.ephemeralVolume" -}}
{{ include "ilm-lib.volumes.ephemeral" (dict "volumes" .Values.volumes "global" .Values.global.volumes) }}
{{- end -}}

{{/*
Render init containers, if any
*/}}
{{- define "ilm.customization.initContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.initContainers .Values.initContainers) "context" $ ) }}
{{- end -}}

{{/*
Render sidecar containers, if any
*/}}
{{- define "ilm.customization.sidecarContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.sidecarContainers .Values.sidecarContainers) "context" $ ) }}
{{- end -}}

{{/*
Render additional volumes, if any
*/}}
{{- define "ilm.customization.volumes" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumes .Values.additionalVolumes) "context" $ ) }}
{{- end -}}

{{/*
Render additional volume mounts, if any
*/}}
{{- define "ilm.customization.volumeMounts" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumeMounts .Values.additionalVolumeMounts) "context" $ ) }}
{{- end -}}

{{/*
Render customized ports, if any
*/}}
{{- define "ilm.customization.ports" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalPorts .Values.additionalPorts) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables, if any
*/}}
{{- define "ilm.customization.env" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalEnv.variables .Values.additionalEnv.variables) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables from configmaps and secrets, if any
*/}}
{{- define "ilm.customization.envFrom" -}}
{{- include "ilm-lib.customizations.render.configMapEnv" ( dict "parts" (list .Values.global.additionalEnv.configMaps .Values.additionalEnv.configMaps) "context" $ ) }}
{{- include "ilm-lib.customizations.render.secretEnv" ( dict "parts" (list .Values.global.additionalEnv.secrets .Values.additionalEnv.secrets) "context" $ ) }}
{{- end -}}

{{/*
Render customized command and arguments, if any
*/}}
{{- define "ilm.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.command "context" $) }}
{{- end -}}

{{- define "ilm.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.args "context" $) }}
{{- end -}}

{{- define "ilm.curl.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.curl.image.command "context" $) }}
{{- end -}}

{{- define "ilm.curl.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.curl.image.args "context" $) }}
{{- end -}}

{{- define "ilm.kubectl.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.kubectl.image.command "context" $) }}
{{- end -}}

{{- define "ilm.kubectl.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.kubectl.image.args "context" $) }}
{{- end -}}

{{- define "ilm.opa.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.opa.image.command "context" $) }}
{{- end -}}

{{- define "ilm.opa.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.opa.image.args "context" $) }}
{{- end -}}

{{/*
Return the image name of the time-quality-monitor
*/}}
{{- define "ilm.timeQualityMonitor.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.timeQualityMonitor.image "global" .Values.global) }}
{{- end -}}

{{- define "ilm.timeQualityMonitor.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.timeQualityMonitor.image.command "context" $) }}
{{- end -}}

{{- define "ilm.timeQualityMonitor.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.timeQualityMonitor.image.args "context" $) }}
{{- end -}}

{{/*
Return true when the umbrella chart should use the in-cluster provisioning
RabbitMQ subchart instead of an externally configured provisioning API.
*/}}
{{- define "ilm.provisioning.useLocalSubchart" -}}
{{- if and (not .Values.global.provisioning.apiUrl) .Values.provisioningRabbitMq.enabled -}}true{{- end -}}
{{- end -}}

{{/*
Init container for provisioning per-instance AMQP queue.
Rendered when proxy support is enabled and either the in-cluster bootstrap
service or an external provisioning API is configured.
Calls POST /api/v1/queues on the provisioning API with retry loop.
*/}}
{{- define "ilm.initContainer.provisionQueue" -}}
{{- $localProvisioningApi := eq (include "ilm.provisioning.useLocalSubchart" .) "true" }}
{{- if and .Values.global.proxy.enabled (or .Values.provisioningRabbitMq.enabled .Values.global.provisioning.apiUrl) }}
- name: provision-instance-queue
  image: {{ include "ilm.curl.image" . }}
  imagePullPolicy: {{ .Values.curl.image.pullPolicy }}
  {{- if .Values.curl.image.securityContext }}
  securityContext: {{- .Values.curl.image.securityContext | toYaml | nindent 4 }}
  {{- end }}
  {{- if .Values.curl.image.resources }}
  resources: {{- toYaml .Values.curl.image.resources | nindent 4 }}
  {{- end }}
  env:
    - name: PROVISIONING_API_URL
      {{- if .Values.global.provisioning.apiUrl }}
      value: {{ .Values.global.provisioning.apiUrl | quote }}
      {{- else }}
      value: {{ printf "http://provisioning-rabbitmq-service:%s" (toString .Values.provisioningRabbitMq.service.port) | quote }}
      {{- end }}
    {{- if and $localProvisioningApi .Values.provisioningRabbitMq.bootstrap.security.enabled }}
    - name: PROVISIONING_API_KEY
      valueFrom:
        secretKeyRef:
          name: provisioning-rabbitmq-secret
          key: securityApiKey
    {{- else if and (not $localProvisioningApi) .Values.global.provisioning.apiKey }}
    - name: PROVISIONING_API_KEY
      valueFrom:
        secretKeyRef:
          name: provisioning-secret
          key: provisioningApiKey
    {{- end }}
  command:
    - /bin/sh
    - -c
    - |
      HOSTNAME=$(hostname)
      until
        if [ -n "${PROVISIONING_API_KEY:-}" ]; then
          curl -sf -X POST "${PROVISIONING_API_URL}/api/v1/queues" \
            -H "Content-Type: application/json" \
            -H "X-API-Key: ${PROVISIONING_API_KEY}" \
            -d "{
              \"name\": \"${HOSTNAME}\",
              \"exchange\": \"ilm-proxy\",
              \"routingKey\": \"proxymessage.*.${HOSTNAME}\",
              \"properties\": { \"x-expires\": 1800000 }
            }"
        else
          curl -sf -X POST "${PROVISIONING_API_URL}/api/v1/queues" \
            -H "Content-Type: application/json" \
            -d "{
              \"name\": \"${HOSTNAME}\",
              \"exchange\": \"ilm-proxy\",
              \"routingKey\": \"proxymessage.*.${HOSTNAME}\",
              \"properties\": { \"x-expires\": 1800000 }
            }"
        fi
      do
        echo "Waiting for provisioning API at ${PROVISIONING_API_URL}..."
        sleep 5
      done
      echo "Instance queue provisioned for ${HOSTNAME}"
{{- end }}
{{- end -}}
