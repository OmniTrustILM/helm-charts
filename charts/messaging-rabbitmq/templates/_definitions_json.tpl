{{/*
Return the RabbitMQ definitions JSON for the messaging service.

Inputs:
- global: global configuration
- messagingService: messaging service configuration

Example:
{{ include "messaging-rabbitmq.definitions.json" ( dict "global" .Values.global "messagingService" .Values ) }}
*/}}
{{- define "messaging-rabbitmq.definitions.json" -}}
{{- $username                   := pluck "username"                   .global.messaging .messagingService.messaging | compact | first }}
{{- $password                   := pluck "password"                   .global.messaging .messagingService.messaging | compact | first }}
{{- $provisionerUsername        := pluck "provisionerUsername"        .global.messaging .messagingService.messaging | compact | first }}
{{- $provisionerPassword        := pluck "provisionerPassword"        .global.messaging .messagingService.messaging | compact | first }}
{{- $proxyUsername              := pluck "proxyUsername"              .global.messaging .messagingService.messaging | compact | first }}
{{- $proxyPassword              := pluck "proxyPassword"              .global.messaging .messagingService.messaging | compact | first }}
{{- $coreUsername               := pluck "coreUsername"               .global.messaging .messagingService.messaging | compact | first }}
{{- $corePassword               := pluck "corePassword"               .global.messaging .messagingService.messaging | compact | first }}
{{- $timeQualityMonitorUsername := pluck "timeQualityMonitorUsername" .global.messaging .messagingService.messaging | compact | first }}
{{- $timeQualityMonitorPassword := pluck "timeQualityMonitorPassword" .global.messaging .messagingService.messaging | compact | first }}
{{- $virtualHost                := pluck "virtualHost"                .global.messaging .messagingService.messaging | compact | first | default "czertainly" }}
{
  "users": [
    {
      "name": "{{ $username }}",
      "password": "{{ $password }}",
      "tags": [
        "administrator"
      ],
      "limits": {}
    },
    {
      "name": "{{ $provisionerUsername }}",
      "password": "{{ $provisionerPassword }}",
      "tags": [
        "administrator"
      ],
      "limits": {}
    },
    {
      "name": "{{ $proxyUsername }}",
      "password": "{{ $proxyPassword }}",
      "tags": []
    },
    {
      "name": "{{ $coreUsername }}",
      "password": "{{ $corePassword }}",
      "tags": []
    },
    {
      "name": "{{ $timeQualityMonitorUsername }}",
      "password": "{{ $timeQualityMonitorPassword }}",
      "tags": []
    }
  ],
  "vhosts": [
    {
      "name": "{{ $virtualHost }}"
    }
  ],
  "permissions": [
    {
      "user": "{{ $username }}",
      "vhost": "{{ $virtualHost }}",
      "configure": ".*",
      "write": ".*",
      "read": ".*"
    },
    {
      "user": "{{ $provisionerUsername }}",
      "vhost": "{{ $virtualHost }}",
      "configure": ".*",
      "write": ".*",
      "read": ".*"
    },
    {
      "user": "{{ $proxyUsername }}",
      "vhost": "{{ $virtualHost }}",
      "configure": "",
      "write": "^czertainly-proxy$",
      "read": "^proxy\\..*$"
    },
    {
      "user": "{{ $coreUsername }}",
      "vhost": "{{ $virtualHost }}",
      "configure": "",
      "write": "^czertainly(-proxy)?$",
      "read": "^core(\\..+|-.+)?$|^time-quality\\.(config-request|results)$"
    },
    {
      "user": "{{ $timeQualityMonitorUsername }}",
      "vhost": "{{ $virtualHost }}",
      "configure": "",
      "write": "^czertainly$",
      "read": "^time-quality\\.config$"
    }
  ],
  "exchanges": [
    {
      "name": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "type": "direct",
      "durable": true,
      "auto_delete": false,
      "internal": false,
      "arguments": {}
    },
    {
      "name": "czertainly-proxy",
      "vhost": "{{ $virtualHost }}",
      "type": "topic",
      "durable": true,
      "auto_delete": false,
      "internal": false,
      "arguments": {}
    }
  ],
  "queues": [
    {
      "name": "core.audit-logs",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core.notifications",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core.scheduler",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core.actions",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core.validation",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core.events",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "core",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    },
    {
      "name": "time-quality.config",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-max-length": 1,
        "x-overflow": "drop-head"
      }
    },
    {
      "name": "time-quality.config-request",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-max-length": 1,
        "x-overflow": "drop-head"
      }
    },
    {
      "name": "time-quality.results",
      "vhost": "{{ $virtualHost }}",
      "durable": true,
      "auto_delete": false,
      "arguments": {}
    }
  ],
  "bindings": [
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.audit-logs",
      "destination_type": "queue",
      "routing_key": "audit-logs",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.notifications",
      "destination_type": "queue",
      "routing_key": "notification",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.actions",
      "destination_type": "queue",
      "routing_key": "action",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.scheduler",
      "destination_type": "queue",
      "routing_key": "scheduler",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.validation",
      "destination_type": "queue",
      "routing_key": "validation",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "core.events",
      "destination_type": "queue",
      "routing_key": "event",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "time-quality.config",
      "destination_type": "queue",
      "routing_key": "time-quality.config",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "time-quality.config-request",
      "destination_type": "queue",
      "routing_key": "time-quality.config-request",
      "arguments": {}
    },
    {
      "source": "czertainly",
      "vhost": "{{ $virtualHost }}",
      "destination": "time-quality.results",
      "destination_type": "queue",
      "routing_key": "time-quality.results",
      "arguments": {}
    }
  ]
}
{{- end }}