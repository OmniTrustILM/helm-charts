# OT PKI Connector - ILM

This repository contains [Helm](https://helm.sh/) charts as part of the ILM platform.

The OT PKI Connector is a stateless Go service implementing the **Authority Provider v3**
interface. It is configured entirely through environment variables and requires no
database. See [OmniTrustILM/otpki-connector](https://github.com/OmniTrustILM/otpki-connector)
for the connector itself.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+

## Using this Chart

### Installation

**Create namespace**

We’ll need to define a Kubernetes namespace where the resources created by the Chart should be installed:
```bash
kubectl create namespace ilm
```

**Clone this chart**

> **Note**
> You can also use `--set` options for the helm to apply configuration for the chart.

Now edit the `values.yaml` according to your desired state, see [Configurable parameters](#configurable-parameters) for more information.

**Install**

For the basic installation, run:
```bash
helm install --namespace ilm -f values.yaml ilm-otpki-connector charts/otpki-connector
```

**Save your configuration**

Always make sure you save the `values.yaml` and all `--set` and `--set-file` options you used. You will need to use the same options when you upgrade to new versions with Helm. In case you are changing the configuration, save the new configuration.

### Upgrade

> **Warning**
> Be sure that you always save your previous configuration!

For upgrading the installation, update your configuration and run:
```bash
helm upgrade --namespace ilm -f values.yaml ilm-otpki-connector charts/otpki-connector
```

### Uninstall

You can use the `helm uninstall` command to uninstall the application:
```bash
helm uninstall --namespace ilm ilm-otpki-connector
```

## Configurable parameters

You can find current values in the [values.yaml](values.yaml).
You can also specify each parameter using the `--set` or `--set-file` argument to `helm install`.

### Global parameters

Global values are used to define common parameters for the chart and all its sub-charts by exactly the same name.

| Parameter                                  | Default value | Description                                                        |
|--------------------------------------------|---------------|--------------------------------------------------------------------|
| global.replicaCount                        | `1`           | Number of replicas for the application                             |
| global.image.registry                      | `""`          | Global docker registry name                                        |
| global.image.repository                    | `""`          | Global docker image repository name                                |
| global.image.pullSecrets                   | `[]`          | Global array of secret names for image pull                        |
| global.volumes.ephemeral.type              | `""`          | Global ephemeral volume type to be used                            |
| global.volumes.ephemeral.sizeLimit         | `""`          | Global ephemeral volume size limit                                 |
| global.volumes.ephemeral.storageClassName  | `""`          | Global ephemeral volume storage class name for `storage` type      |
| global.volumes.ephemeral.custom            | `{}`          | Global custom definition of the ephemeral volume for `custom` type |
| global.trusted.certificates                | `""`          | Global PEM bundle of trusted CA certificates                       |
| global.httpProxy                           | `""`          | Global HTTP proxy for outbound connections                         |
| global.httpsProxy                          | `""`          | Global HTTPS proxy for outbound connections                        |
| global.noProxy                             | `""`          | Global comma-separated no-proxy list                               |
| global.initContainers                      | `[]`          | Global init containers                                             |
| global.sidecarContainers                   | `[]`          | Global sidecar containers                                          |
| global.additionalVolumes                   | `[]`          | Global additional volumes                                          |
| global.additionalVolumeMounts              | `[]`          | Global additional volume mounts                                    |
| global.additionalPorts                     | `[]`          | Global additional ports                                            |
| global.additionalEnv.variables             | `[]`          | Global additional environment variables                            |
| global.additionalEnv.secrets               | `[]`          | Global additional environment secrets                              |
| global.additionalEnv.configMaps            | `[]`          | Global additional environment config maps                          |

### Local parameters

The following values may be configured:

| Parameter                                    | Default value               | Description                                                                                                                                                                                                                                      |
|----------------------------------------------|-----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| nameOverride                                 | `otpki-connector`           | Override for the chart name. Used as the `app.kubernetes.io/name` selector label value and as input to the fullname helper. Pinned to keep selectors stable across chart renames; changing this requires manual cleanup of existing Deployments. |
| fullnameOverride                             | `""`                        | Override for the fully qualified app name.                                                                                                                                                                                                       |
| image.registry                               | `hub.omnitrustregistry.com` | Docker registry name for the image                                                                                                                                                                                                               |
| image.repository                             | `ilm-private`               | Docker image repository name                                                                                                                                                                                                                     |
| image.name                                   | `otpki-connector`           | Docker image name                                                                                                                                                                                                                                |
| image.tag                                    | `1.0.0`                     | Docker image tag                                                                                                                                                                                                                                 |
| image.digest                                 | `""`                        | Docker image digest, will override tag if specified                                                                                                                                                                                              |
| image.pullPolicy                             | `IfNotPresent`              | Image pull policy                                                                                                                                                                                                                                |
| image.pullSecrets                            | `[]`                        | Array of secret names for image pull                                                                                                                                                                                                             |
| image.command                                | `[]`                        | Override the default command                                                                                                                                                                                                                     |
| image.args                                   | `[]`                        | Override the default args                                                                                                                                                                                                                        |
| image.securityContext.runAsNonRoot           | `true`                      | Run the container as non-root user                                                                                                                                                                                                               |
| image.securityContext.readOnlyRootFilesystem | `true`                      | Run the container with read-only root filesystem                                                                                                                                                                                                 |
| image.resources                              | `{}`                        | The resources for the container                                                                                                                                                                                                                  |
| podLabels                                    | `{}`                        | Labels to be added to the pod                                                                                                                                                                                                                    |
| podAnnotations                               | `{}`                        | Annotations to be added to the pod                                                                                                                                                                                                               |
| podSecurityContext                           | `{}`                        | Pod security context                                                                                                                                                                                                                             |
| volumes.ephemeral.type                       | `memory`                    | Ephemeral volume type to be used                                                                                                                                                                                                                 |
| volumes.ephemeral.sizeLimit                  | `"1Mi"`                     | Ephemeral volume size limit                                                                                                                                                                                                                      |
| volumes.ephemeral.storageClassName           | `""`                        | Ephemeral volume storage class name for `storage` type                                                                                                                                                                                           |
| volumes.ephemeral.custom                     | `{}`                        | Custom definition of the ephemeral volume for `custom` type                                                                                                                                                                                      |
| service.type                                 | `"ClusterIP"`               | Type of the service that is exposed                                                                                                                                                                                                              |
| service.port                                 | `8080`                      | Port number of the exposed service. Passed to the connector as `PORT`                                                                                                                                                                            |
| logging.level                                | `"INFO"`                    | Connector log level (`LOG_LEVEL`). Allowed values are `"DEBUG"`, `"INFO"`, `"WARN"`, `"ERROR"`                                                                                                                                                   |
| trusted.certificates                         | `""`                        | PEM bundle of trusted CA certificates, passed to the connector as `TRUSTED_CERTIFICATES`. Stored in the `trusted-certificates-otpki-connector` Secret. Overridden by `global.trusted.certificates` when set                                      |
| otel.serviceName                             | `"otpki-connector"`         | OpenTelemetry service name (`OTEL_SERVICE_NAME`)                                                                                                                                                                                                 |
| otel.exporterOtlpEndpoint                    | `""`                        | OTLP trace exporter endpoint (`OTEL_EXPORTER_OTLP_ENDPOINT`). Tracing is a no-op when empty                                                                                                                                                      |
| tracing.samplingProbability                  | `"1.0"`                     | Ratio sampler probability `0.0`–`1.0` (`TRACING_SAMPLING_PROBABILITY`)                                                                                                                                                                           |
| otpki.loginPasswordKey                       | `""`                        | HMAC-SHA256 key for deriving end-entity passwords (`OTPKI_LOGIN_PASSWORD_KEY`). Stored in the `otpki-connector-secret` Secret when set; empty means keyless (loginId verbatim)                                                                   |
| httpProxy                                    | `""`                        | HTTP proxy for outbound connections (`HTTP_PROXY`)                                                                                                                                                                                               |
| httpsProxy                                   | `""`                        | HTTPS proxy for outbound connections (`HTTPS_PROXY`)                                                                                                                                                                                             |
| noProxy                                      | `""`                        | Comma-separated no-proxy list (`NO_PROXY`)                                                                                                                                                                                                       |
| serviceAccount.create                        | `true`                      | Specifies whether a service account should be created                                                                                                                                                                                            |
| serviceAccount.annotations                   | `{}`                        | Annotations to add to the service account                                                                                                                                                                                                        |
| serviceAccount.name                          | `"otpki-connector-sa"`      | The name of the service account to use. If not set and create is true, a name is generated using the fullname template                                                                                                                           |

#### Customization parameters

| Parameter                | Default value | Description                        |
|--------------------------|---------------|------------------------------------|
| initContainers           | `[]`          | Init containers                    |
| sidecarContainers        | `[]`          | Sidecar containers                 |
| additionalVolumes        | `[]`          | Additional volumes                 |
| additionalVolumeMounts   | `[]`          | Additional volume mounts           |
| additionalPorts          | `[]`          | Additional ports                   |
| additionalEnv.variables  | `[]`          | Additional environment variables   |
| additionalEnv.secrets    | `[]`          | Additional environment secrets     |
| additionalEnv.configMaps | `[]`          | Additional environment config maps |

#### Probes parameters

The liveness and startup probes are wired to `/v2/health/liveness` and the readiness probe to `/v2/health/readiness`.
For more details about probes, see the [Kubernetes documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

| Parameter                                  | Default value | Description                                                                        |
|--------------------------------------------|---------------|------------------------------------------------------------------------------------|
| image.probes.liveness.enabled              | `false`       | Enable/disable liveness probe                                                      |
| image.probes.liveness.custom               | `{}`          | Custom liveness probe command. When defined, it will override the default command  |
| image.probes.liveness.initialDelaySeconds  | `10`          | Initial delay seconds for liveness probe                                           |
| image.probes.liveness.timeoutSeconds       | `5`           | Timeout seconds for liveness probe                                                 |
| image.probes.liveness.periodSeconds        | `10`          | Period seconds for liveness probe                                                  |
| image.probes.liveness.successThreshold     | `1`           | Success threshold for liveness probe                                               |
| image.probes.liveness.failureThreshold     | `3`           | Failure threshold for liveness probe                                               |
| image.probes.readiness.enabled             | `true`        | Enable/disable readiness probe                                                     |
| image.probes.readiness.custom              | `{}`          | Custom readiness probe command. When defined, it will override the default command |
| image.probes.readiness.initialDelaySeconds | `5`           | Initial delay seconds for readiness probe                                          |
| image.probes.readiness.timeoutSeconds      | `5`           | Timeout seconds for readiness probe                                                |
| image.probes.readiness.periodSeconds       | `10`          | Period seconds for readiness probe                                                 |
| image.probes.readiness.successThreshold    | `1`           | Success threshold for readiness probe                                              |
| image.probes.readiness.failureThreshold    | `3`           | Failure threshold for readiness probe                                              |
| image.probes.startup.enabled               | `true`        | Enable/disable startup probe                                                       |
| image.probes.startup.custom                | `{}`          | Custom startup probe command. When defined, it will override the default command   |
| image.probes.startup.initialDelaySeconds   | `10`          | Initial delay seconds for startup probe                                            |
| image.probes.startup.timeoutSeconds        | `5`           | Timeout seconds for startup probe                                                  |
| image.probes.startup.periodSeconds         | `10`          | Period seconds for startup probe                                                   |
| image.probes.startup.successThreshold      | `1`           | Success threshold for startup probe                                                |
| image.probes.startup.failureThreshold      | `10`          | Failure threshold for startup probe                                                |

### Additional parameters

Additional parameters may be found in the [values.yaml](values.yaml) and dependencies.
See dependent charts for the description of available parameters.
