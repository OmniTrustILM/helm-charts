# Provisioning RabbitMQ - ILM

> This repository is part of the commercial open-source project ILM. You can find more information about the project at [ILM](https://github.com/OmniTrustILM/ilm) repository, including the contribution guide.

This repository contains [Helm](https://helm.sh/) charts as part of the ILM platform.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+
- RabbitMQ (internal `messaging-rabbitmq` or external)

## Using this Chart

### Installation

**Create namespace**

We'll need to define a Kubernetes namespace where the resources created by the Chart should be installed:
```bash
kubectl create namespace ilm
```

**Create `values.yaml`**

> **Note**
> You can also use `--set` options for the helm to apply configuration for the chart.

Copy the default `values.yaml` from the Helm chart and modify the values accordingly:
```bash
helm show values oci://hub.omnitrustregistry.com/ilm-helm/provisioning-rabbitmq > values.yaml
```
Now edit the `values.yaml` according to your desired state, see [Configurable parameters](#configurable-parameters) for more information.

**Install**

For the basic installation, run:
```bash
helm install --namespace ilm -f values.yaml ilm-provisioning-rabbitmq oci://hub.omnitrustregistry.com/ilm-helm/provisioning-rabbitmq
```

**Save your configuration**

Always make sure you save the `values.yaml` and all `--set` and `--set-file` options you used. You will need to use the same options when you upgrade to new versions with Helm. In case you are changing the configuration, save the new configuration.

### Upgrade

> **Warning**
> Be sure that you always save your previous configuration!

For upgrading the installation, update your configuration and run:
```bash
helm upgrade --namespace ilm -f values.yaml ilm-provisioning-rabbitmq oci://hub.omnitrustregistry.com/ilm-helm/provisioning-rabbitmq
```

### Uninstall

You can use the `helm uninstall` command to uninstall the application:
```bash
helm uninstall --namespace ilm ilm-provisioning-rabbitmq
```

## Configurable parameters

You can find current values in the [values.yaml](values.yaml).
You can also specify each parameter using the `--set` or `--set-file` argument to `helm install`.

### Global parameters

Global values are used to define common parameters for the chart and all its sub-charts by exactly the same name.

| Parameter                                 | Default value | Description                                                        |
|-------------------------------------------|---------------|--------------------------------------------------------------------|
| global.replicaCount                       | `1`           | Number of replicas for the application                             |
| global.config.enabled                     | `false`       | Enables global configuration                                       |
| global.image.registry                     | `""`          | Global docker registry name                                        |
| global.image.repository                   | `""`          | Global docker image repository name                                |
| global.image.pullSecrets                  | `[]`          | Global array of secret names for image pull                        |
| global.volumes.ephemeral.type             | `""`          | Global ephemeral volume type to be used                            |
| global.volumes.ephemeral.sizeLimit        | `""`          | Global ephemeral volume size limit                                 |
| global.volumes.ephemeral.storageClassName | `""`          | Global ephemeral volume storage class name for `storage` type      |
| global.volumes.ephemeral.custom           | `{}`          | Global custom definition of the ephemeral volume for `custom` type |
| global.messaging.external.enabled         | `false`       | Enable external messaging                                          |
| global.messaging.external.host            | `""`          | Host where the external messaging is located                       |
| global.messaging.external.amqp.port       | `""`          | Port on which the external messaging is listening                  |
| global.messaging.username                 | `""`          | Username to access the messaging                                   |
| global.messaging.password                 | `""`          | Password to access the messaging                                   |
| global.messaging.provisionerUsername      | `""`          | Provisioner username to access the messaging                       |
| global.messaging.provisionerPassword      | `""`          | Provisioner password to access the messaging                       |
| global.messaging.proxyUsername            | `""`          | Proxy username to access the messaging                             |
| global.messaging.proxyPassword            | `""`          | Proxy password to access the messaging                             |
| global.initContainers                     | `[]`          | Global init containers                                             |
| global.sidecarContainers                  | `[]`          | Global sidecar containers                                          |
| global.additionalVolumes                  | `[]`          | Global additional volumes                                          |
| global.additionalVolumeMounts             | `[]`          | Global additional volume mounts                                    |
| global.additionalPorts                    | `[]`          | Global additional ports                                            |
| global.additionalEnv.variables            | `[]`          | Global additional environment variables                            |
| global.additionalEnv.secrets              | `[]`          | Global additional environment secrets                              |
| global.additionalEnv.configMaps           | `[]`          | Global additional environment config maps                          |

### Local parameters

The following values may be configured:

| Parameter                                    | Default value                     | Description                                                                                                              |
|----------------------------------------------|-----------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| nameOverride                                 | `provisioning-rabbitmq`           | Override for the chart name. Used as the `app.kubernetes.io/name` selector label value and as input to the fullname helper. Pinned to keep selectors stable across chart renames; changing this requires manual cleanup of existing Deployments. |
| fullnameOverride                             | `""`                              | Override for the fully qualified app name.                                                                               |
| image.registry                               | `hub.omnitrustregistry.com`       | Docker registry name for the image                                                                                       |
| image.repository                             | `ilm`                             | Docker image repository name                                                                                             |
| image.name                                   | `provisioning-rabbitmq`           | Docker image name                                                                                                        |
| image.tag                                    | `1.0.0`                           | Docker image tag                                                                                                         |
| image.digest                                 | `""`                              | Docker image digest, will override tag if specified                                                                      |
| image.pullPolicy                             | `IfNotPresent`                    | Image pull policy                                                                                                        |
| image.pullSecrets                            | `[]`                              | Array of secret names for image pull                                                                                     |
| image.command                                | `[]`                              | Override the default command                                                                                             |
| image.args                                   | `[]`                              | Override the default args                                                                                                |
| image.securityContext.runAsNonRoot           | `true`                            | Run the container as non-root user                                                                                       |
| image.securityContext.readOnlyRootFilesystem | `true`                            | Run the container with read-only root filesystem                                                                         |
| image.resources                              | `{}`                              | The resources for the container                                                                                          |
| podLabels                                    | `{}`                              | Labels to be added to the pod                                                                                            |
| podAnnotations                               | `{}`                              | Annotations to be added to the pod                                                                                       |
| podSecurityContext                           | `{}`                              | Pod security context                                                                                                     |
| volumes.ephemeral.type                       | `memory`                          | Ephemeral volume type to be used                                                                                         |
| volumes.ephemeral.sizeLimit                  | `"1Mi"`                           | Ephemeral volume size limit                                                                                              |
| volumes.ephemeral.storageClassName           | `""`                              | Ephemeral volume storage class name for `storage` type                                                                   |
| volumes.ephemeral.custom                     | `{}`                              | Custom definition of the ephemeral volume for `custom` type                                                              |
| logging.level                                | `"INFO"`                          | Allowed values are `"INFO"`, `"DEBUG"`, `"WARN"`, `"TRACE"`                                                             |
| service.type                                 | `"ClusterIP"`                     | Type of the service that is exposed                                                                                      |
| service.port                                 | `8077`                            | Port number of the exposed service                                                                                       |
| javaOpts                                     | `""`                              | Customize Java system properties                                                                                         |
| messaging.external.enabled                   | `false`                           | Enable external messaging                                                                                                |
| messaging.external.host                      | `""`                              | Host where the external messaging is located                                                                             |
| messaging.external.amqp.port                 | `""`                              | Port on which the external messaging is listening                                                                        |
| messaging.provisionerUsername                | `"provisioner"`                   | Admin/provisioner username for managing RabbitMQ queues and exchanges                                                    |
| messaging.provisionerPassword                | `"provisioner"`                   | Admin/provisioner password for managing RabbitMQ queues and exchanges                                                    |
| messaging.proxyUsername                      | `"proxy"`                         | Proxy user credentials included in generated JWT tokens for proxy services                                               |
| messaging.proxyPassword                      | `"proxy"`                         | Proxy user password included in generated JWT tokens for proxy services                                                  |
| messaging.host                               | `"messaging-service"`             | Host where the messaging service is located. **Change only if you know what you are doing!**                             |
| messaging.virtualHost                        | `"/"`                             | RabbitMQ virtual host                                                                                                    |
| messaging.amqp.port                          | `5672`                            | AMQP port of the messaging service. **Change only if you know what you are doing!**                                      |
| bootstrap.proxy.amqpUrl                      | `"amqp://messaging-service:5672"` | External AMQP URL that proxy services use to connect to RabbitMQ (may differ from internal host when using NodePort/LB) |
| bootstrap.proxy.exchange                     | `"ilm-proxy"`                     | RabbitMQ exchange name for proxy communication                                                                           |
| bootstrap.proxy.responseQueue                | `"core"`                          | RabbitMQ queue name for proxy responses                                                                                  |
| bootstrap.security.enabled                   | `false`                           | Enable the X-API-Key filter on bootstrap endpoints. When `false`, endpoints are unauthenticated.                         |
| bootstrap.security.apiKey                    | `""`                              | API key used to secure the bootstrap service endpoints. Required when `bootstrap.security.enabled` is `true`.            |
| bootstrap.token.signingKey                   | `""`                              | JWT signing key used to sign tokens for proxy services. Optional; must be at least 32 characters if set.                |
| serviceAccount.create                        | `true`                            | Specifies whether a service account should be created                                                                    |
| serviceAccount.annotations                   | `{}`                              | Annotations to add to the service account                                                                                |
| serviceAccount.name                          | `"provisioning-rabbitmq-sa"`      | The name of the service account to use                                                                                   |

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

For more details about probes, see the [Kubernetes documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

| Parameter                                  | Default value | Description                                                                        |
|--------------------------------------------|---------------|------------------------------------------------------------------------------------|
| image.probes.liveness.enabled              | `false`       | Enable/disable liveness probe                                                      |
| image.probes.liveness.custom               | `{}`          | Custom liveness probe command. When defined, it will override the default command  |
| image.probes.liveness.initialDelaySeconds  | `60`          | Initial delay seconds for liveness probe                                           |
| image.probes.liveness.timeoutSeconds       | `5`           | Timeout seconds for liveness probe                                                 |
| image.probes.liveness.periodSeconds        | `10`          | Period seconds for liveness probe                                                  |
| image.probes.liveness.successThreshold     | `1`           | Success threshold for liveness probe                                               |
| image.probes.liveness.failureThreshold     | `3`           | Failure threshold for liveness probe                                               |
| image.probes.readiness.enabled             | `true`        | Enable/disable readiness probe                                                     |
| image.probes.readiness.custom              | `{}`          | Custom readiness probe command. When defined, it will override the default command |
| image.probes.readiness.initialDelaySeconds | `15`          | Initial delay seconds for readiness probe                                          |
| image.probes.readiness.timeoutSeconds      | `5`           | Timeout seconds for readiness probe                                                |
| image.probes.readiness.periodSeconds       | `10`          | Period seconds for readiness probe                                                 |
| image.probes.readiness.successThreshold    | `1`           | Success threshold for readiness probe                                              |
| image.probes.readiness.failureThreshold    | `3`           | Failure threshold for readiness probe                                              |
| image.probes.startup.enabled               | `true`        | Enable/disable startup probe                                                       |
| image.probes.startup.custom                | `{}`          | Custom startup probe command. When defined, it will override the default command   |
| image.probes.startup.initialDelaySeconds   | `15`          | Initial delay seconds for startup probe                                            |
| image.probes.startup.timeoutSeconds        | `5`           | Timeout seconds for startup probe                                                  |
| image.probes.startup.periodSeconds         | `10`          | Period seconds for startup probe                                                   |
| image.probes.startup.successThreshold      | `1`           | Success threshold for startup probe                                                |
| image.probes.startup.failureThreshold      | `45`          | Failure threshold for startup probe                                                |

### Additional parameters

Additional parameters may be found in the [values.yaml](values.yaml) and dependencies.
See dependent charts for the description of available parameters.
