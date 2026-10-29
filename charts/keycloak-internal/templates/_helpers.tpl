{{/*
Expand the name of the chart.
*/}}
{{- define "keycloak-internal.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "keycloak-internal.fullname" -}}
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
{{- define "keycloak-internal.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "keycloak-internal.labels" -}}
helm.sh/chart: {{ include "keycloak-internal.chart" . }}
{{ include "keycloak-internal.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "keycloak-internal.selectorLabels" -}}
app.kubernetes.io/name: {{ include "keycloak-internal.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "keycloak-internal.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "keycloak-internal.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the image name
*/}}
{{- define "keycloak-internal.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the theme container
*/}}
{{- define "keycloak-internal.theme.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.theme.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image name of the curl
*/}}
{{- define "keycloak-internal.curl.image" -}}
{{ include "ilm-lib.images.image" (dict "image" .Values.curl.image "global" .Values.global) }}
{{- end -}}

{{/*
Return the image pull secret names
*/}}
{{- define "keycloak-internal.imagePullSecrets" -}}
{{ include "ilm-lib.images.pullSecrets" (dict "images" (list .Values.image) "global" .Values.global) }}
{{- end -}}

{{/*
Retun the ephemeral volume configuration
*/}}
{{- define "keycloak-internal.ephemeralVolume" -}}
{{ include "ilm-lib.volumes.ephemeral" (dict "volumes" .Values.volumes "global" .Values.global.volumes) }}
{{- end -}}

{{/*
Render init containers, if any
*/}}
{{- define "keycloak-internal.customization.initContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.initContainers .Values.initContainers) "context" $ ) }}
{{- end -}}

{{/*
Render sidecar containers, if any
*/}}
{{- define "keycloak-internal.customization.sidecarContainers" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.sidecarContainers .Values.sidecarContainers) "context" $ ) }}
{{- end -}}

{{/*
Render additional volumes, if any
*/}}
{{- define "keycloak-internal.customization.volumes" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumes .Values.additionalVolumes) "context" $ ) }}
{{- end -}}

{{/*
Render additional volume mounts, if any
*/}}
{{- define "keycloak-internal.customization.volumeMounts" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalVolumeMounts .Values.additionalVolumeMounts) "context" $ ) }}
{{- end -}}

{{/*
Render customized ports, if any
*/}}
{{- define "keycloak-internal.customization.ports" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalPorts .Values.additionalPorts) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables, if any
*/}}
{{- define "keycloak-internal.customization.env" -}}
{{- include "ilm-lib.customizations.render.yaml" ( dict "parts" (list .Values.global.additionalEnv.variables .Values.additionalEnv.variables) "context" $ ) }}
{{- end -}}

{{/*
Render customized environment variables from configmaps and secrets, if any
*/}}
{{- define "keycloak-internal.customization.envFrom" -}}
{{- include "ilm-lib.customizations.render.configMapEnv" ( dict "parts" (list .Values.global.additionalEnv.configMaps .Values.additionalEnv.configMaps) "context" $ ) }}
{{- include "ilm-lib.customizations.render.secretEnv" ( dict "parts" (list .Values.global.additionalEnv.secrets .Values.additionalEnv.secrets) "context" $ ) }}
{{- end -}}

{{/*
Render customized command and arguments, if any
*/}}
{{- define "keycloak-internal.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.command "context" $) }}
{{- end -}}

{{- define "keycloak-internal.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.image.args "context" $) }}
{{- end -}}

{{- define "keycloak-internal.theme.image.command" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.theme.image.command "context" $) }}
{{- end -}}

{{- define "keycloak-internal.theme.image.args" -}}
{{- include "ilm-lib.tplvalues.render" (dict "value" .Values.theme.image.args "context" $) }}
{{- end -}}

{{/*
The ILM realm to import, as JSON text. With MCP enabled in managed mode, the lists of MCP's objects in
realms/mcp-objects.json are appended to the realm's, and ilm-mcp-upstream receives copies of the ilm client's Username
and Groups mappers, so that a token exchanged for MCP carries the claims of ILM's own tokens.
*/}}
{{- define "keycloak-internal.realm" -}}
{{- $text := tpl (.Files.Get "realms/ilm-2.18.0_realm.json") . -}}
{{- if not (and .Values.global.mcp.enabled (eq .Values.global.mcp.identity.mode "managed")) -}}
{{- $text -}}
{{- else -}}
{{- $realm := fromJson $text -}}
{{- $objects := fromJson (tpl (.Files.Get "realms/mcp-objects.json") .) -}}
{{- $mappers := list -}}
{{- range $realm.clients -}}
{{- if eq .clientId "ilm" -}}
{{- range .protocolMappers -}}
{{- if has .name (list "Username" "Groups") -}}
{{- $mappers = append $mappers (omit . "id") -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- range $objects.clientScopes -}}
{{- if eq .name "ilm-mcp-upstream" -}}
{{- $_ := set . "protocolMappers" (concat .protocolMappers $mappers) -}}
{{- end -}}
{{- end -}}
{{- $_ := set $realm "adminPermissionsEnabled" $objects.adminPermissionsEnabled -}}
{{- range $key := list "defaultOptionalClientScopes" "clientScopes" "clients" "groups" -}}
{{- with get $objects $key -}}
{{- $_ := set $realm $key (concat (get $realm $key) .) -}}
{{- end -}}
{{- end -}}
{{- $_ := set $realm.clientProfiles "profiles" (concat $realm.clientProfiles.profiles $objects.clientProfiles.profiles) -}}
{{- $_ := set $realm.clientPolicies "policies" (concat $realm.clientPolicies.policies $objects.clientPolicies.policies) -}}
{{- /* Starts with a line break, as the realm file does: the ConfigMap trims the one before this text. */ -}}
{{- printf "\n%s" (toPrettyJson $realm) -}}
{{- end -}}
{{- end -}}
