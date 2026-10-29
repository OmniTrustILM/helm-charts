{{/*
Return the kong api gateway configuration for the given environment.
The optional "clientCertHeader" names the client certificate header that the MCP route removes
(ssl-client-cert by default).

Example:
{{ include "api-gateway-kong.yaml" ( dict "global" .Values.global "apiGateway" .Values ) }}
*/}}
{{- define "api-gateway-kong.config.yml" -}}
{{- if .apiGateway.config.custom }}
{{ .apiGateway.config.custom }}
{{- else }}
_format_version: '2.1'
_transform: true
services:
  # Core service for the backend API
  - name: core
    host: {{ .apiGateway.backend.core.service.name }}
    port: {{ .apiGateway.backend.core.service.port }}
    protocol: http
    routes:
      - name: protocols_route
        strip_path: false
        preserve_host: true
        paths:
          - {{ .apiGateway.backend.core.service.apiUrl}}
  # OAuth2 authentication handlers for the login and logout routes
  - name: core-login-logout
    host: {{ .apiGateway.backend.core.service.name }}
    port: {{ .apiGateway.backend.core.service.port }}
    protocol: http
    path: /api
    routes:
      - name: core-oauth2_route
        strip_path: false
        preserve_host: true
        paths:
          - {{ .apiGateway.backend.fe.service.loginUrl}}
          - {{ .apiGateway.backend.fe.service.logoutUrl}}
  # Frontend service for the administrator interface
  - name: fe-administrator
    host: {{ .apiGateway.backend.fe.service.name}}
    port: {{ .apiGateway.backend.fe.service.port }}
    protocol: http
    routes:
      - name: fe-administrator_route-cert
        preserve_host: true
        strip_path: true
        paths:
          - {{ .apiGateway.backend.fe.service.baseUrl}}
  {{- if or .global.keycloak.enabled }}
  # Management of Keycloak users and roles
  - name: keycloak-internal-service
    host: keycloak-internal-service
    port: 8080
    routes:
      - name: keycloak
        strip_path: false
        preserve_host: true
        paths:
          - /kc
  {{- end }}
  {{- if or .global.messaging.remoteAccess }}
  # RabbitMQ management
  - name: messaging-service
    host: messaging-service
    port: 15672
    routes:
      - name: rabbitmq
        strip_path: true
        preserve_host: true
        paths:
          - /mq
  {{- end }}
  {{- if or .global.utils.enabled }}
  # Utility services
  - name: utils-service-service
    host: utils-service-service
    port: 8080
    routes:
      - name: v1-utils-route
        strip_path: true
        preserve_host: true
        paths:
          - /utils
  {{- end }}
  {{- if .global.mcp.enabled }}
  # MCP server and its OAuth discovery path. Streamable HTTP responses are not buffered, and a client
  # certificate header is removed because MCP authenticates through OAuth and never consumes it.
  - name: mcp-server-service
    host: {{ .apiGateway.backend.mcp.service.name }}
    port: {{ .apiGateway.backend.mcp.service.port }}
    protocol: http
    routes:
      - name: mcp
        strip_path: false
        preserve_host: true
        response_buffering: false
        paths:
          - /mcp
          - /.well-known/oauth-protected-resource
    plugins:
      - name: request-transformer
        config:
          remove:
            headers:
              - {{ .clientCertHeader | default "ssl-client-cert" }}
  {{- end }}
{{- if or .apiGateway.cors.enabled .apiGateway.logging.request}}
plugins:
  {{- if .apiGateway.cors.enabled }}
  - name: cors
    config:
      origins: {{ toYaml .apiGateway.cors.origins | nindent 8 }}
      credentials: true
      max_age: 3600
      exposed_headers: {{ toYaml .apiGateway.cors.exposedHeaders | nindent 8 }}
      preflight_continue: false
  {{- end }}
  {{- if .apiGateway.logging.request }}
  - name: file-log
    config:
      path: /dev/stdout
  {{- end }}
{{- end }}
{{- end }}
{{- end -}}
