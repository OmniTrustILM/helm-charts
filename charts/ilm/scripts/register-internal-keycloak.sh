{{- $hostName := pluck "hostName" .Values.global .Values | compact | first }}
{{- $internalKeycloakHttpPort := .Values.keycloakInternal.service.port }}
#!/bin/sh

# Check if the client secret is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <clientSecret>"
  exit 1
fi

# Assign the first parameter to a variable
CLIENT_SECRET=$1

# Wait for services to be ready
while ! nc -z localhost {{ .Values.service.port }}; do sleep 1; done
while ! nc -z localhost 8181; do sleep 1; done

# Perform the cURL request
curl -X PUT \
  -H 'content-type: application/json' \
  -d '
  {
    "issuerUrl":"https://{{ $hostName }}/kc/realms/ILM",
    "clientId": "ilm",
    "clientSecret": "'"$CLIENT_SECRET"'",
    "authorizationUrl": "https://{{ $hostName }}/kc/realms/ILM/protocol/openid-connect/auth",
    "tokenUrl": "http://keycloak-internal-service.{{ .Release.Namespace }}.svc.{{ .Values.clustering.domain }}:{{ $internalKeycloakHttpPort }}/kc/realms/ILM/protocol/openid-connect/token",
    "logoutUrl": "https://{{ $hostName }}/kc/realms/ILM/protocol/openid-connect/logout",
    "jwkSetUrl": "http://keycloak-internal-service.{{ .Release.Namespace }}.svc.{{ .Values.clustering.domain }}:{{ $internalKeycloakHttpPort }}/kc/realms/ILM/protocol/openid-connect/certs",
    "scope": ["openid"],
    "audiences": ["ilm"],
    "postLogoutUrl": "https://{{ $hostName }}/administrator/",
    "skew": 60
  }' \
  http://localhost:{{ .Values.service.port }}/api/v1/settings/authentication/oauth2Providers/internal
