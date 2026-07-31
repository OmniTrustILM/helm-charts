{{- $username := pluck "username" .Values.global.admin .Values.registerAdmin.admin | compact | first | quote }}
{{- $name := pluck "name" .Values.global.admin .Values.registerAdmin.admin | compact | first | quote }}
{{- $surname := pluck "surname" .Values.global.admin .Values.registerAdmin.admin | compact | first | quote }}
{{- $email := pluck "email" .Values.global.admin .Values.registerAdmin.admin | compact | first | quote }}
#!/bin/sh

while ! nc -z localhost {{ .Values.service.port }}; do sleep 1; done
while ! nc -z localhost 8181; do sleep 1; done

ADMIN_CERT=$( echo $ADMIN_CERT | awk '{gsub(/[[:blank:]]/,""); print}' )
ADMIN_CERT=$( echo $ADMIN_CERT | awk '{gsub(/-----BEGINCERTIFICATE-----/,""); print}' )
ADMIN_CERT=$( echo $ADMIN_CERT | awk '{gsub(/-----ENDCERTIFICATE-----/,""); print}' )

curl -X POST \
  -H 'content-type: application/json' \
  -d '
  {
    "username": {{ $username }},
    "description": {{ .Values.registerAdmin.admin.description | quote}},
    "firstName": {{ $name }},
    "lastName": {{ $surname }},
    "email": {{ $email }},
    "enabled": "true",
    "certificateData": "'$ADMIN_CERT'",
    "certificateUuid": ""
  }' \
  http://localhost:{{ .Values.service.port }}/api/v1/local/admins
