# Messaging - RabbitMQ - ILM

> This repository is part of the commercial open-source project ILM. You can find more information about the project at [ILM](https://github.com/OmniTrustILM/ilm) repository, including the contribution guide.

This repository contains [Helm](https://helm.sh/) charts as part of the ILM platform.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+
- PV provisioner support in the underlying infrastructure

## Using this Chart

### Installation

**Create namespace**

We’ll need to define a Kubernetes namespace where the resources created by the Chart should be installed:
```bash
kubectl create namespace ilm
```

**Create `values.yaml`**

> **Note**
> You can also use `--set` options for the helm to apply configuration for the chart.

Copy the default `values.yaml` from the Helm chart and modify the values accordingly:
```bash
helm show values oci://hub.omnitrustregistry.com/ilm-helm/messaging-rabbitmq > values.yaml
```
Now edit the `values.yaml` according to your desired stated, see [Configurable parameters](#configurable-parameters) for more information.

**Install**

For the basic installation, run:
```bash
helm install --namespace ilm -f values.yaml ilm-messaging-rabbitmq oci://hub.omnitrustregistry.com/ilm-helm/messaging-rabbitmq
```

**Save your configuration**

Always make sure you save the `values.yaml` and all `--set` and `--set-file` options you used. You will need to use the same options when you upgrade to new versions with Helm. In case you are changing the configuration, save the new configuration.

### Upgrade

> **Warning**
> Be sure that you always save your previous configuration!

For upgrading the installation, update your configuration and run:
```bash
helm upgrade --namespace ilm -f values.yaml ilm-messaging-rabbitmq oci://hub.omnitrustregistry.com/ilm-helm/messaging-rabbitmq
```

### Uninstall

You can use the `helm uninstall` command to uninstall the application:
```bash
helm uninstall --namespace ilm ilm-messaging-rabbitmq
```

## Configurable parameters

You can find current values in the [values.yaml](values.yaml).
You can also Specify each parameter using the `--set` or `--set-file` argument to `helm install`.

### Global parameters

Global values are used to define common parameters for the chart and all its sub-charts by exactly the same name.

| Parameter                                 | Default value | Description                                                           |
|-------------------------------------------|---------------|-----------------------------------------------------------------------|
| global.replicaCount                       | `1`           | Number of replicas for the application                                |
| global.config.enabled                     | `false`       | Enables global configuration                                          |
| global.image.registry                     | `""`          | Global docker registry name                                           |
| global.image.repository                   | `""`          | Global docker image repository name                                   |
| global.image.pullSecrets                  | `[]`          | Global array of secret names for image pull                           |
| global.volumes.ephemeral.type             | `""`          | Global ephemeral volume type to be used                               |
| global.volumes.ephemeral.sizeLimit        | `""`          | Global ephemeral volume size limit                                    |
| global.volumes.ephemeral.storageClassName | `""`          | Global ephemeral volume storage class name for `storage` type         |
| global.volumes.ephemeral.custom           | `{}`          | Global custom definition of the ephemeral volume for `custom` type    |
| global.messaging.remoteAccess             | `false`       | Enable remote access to messaging service                             |
| global.messaging.username                 | `""`          | Username to access the messaging                                      |
| global.messaging.password                 | `""`          | Password to access the messaging                                      |
| global.httpProxy                          | `""`          | Proxy to be used to access external resources through http            |
| global.httpsProxy                         | `""`          | Proxy to be used to access external resources through https           |
| global.noProxy                            | `""`          | Defines list of external resources that should not use proxy settings |
| global.initContainers                     | `[]`          | Global init containers                                                |
| global.sidecarContainers                  | `[]`          | Global sidecar containers                                             |
| global.additionalVolumes                  | `[]`          | Global additional volumes                                             |
| global.additionalVolumeMounts             | `[]`          | Global additional volume mounts                                       |
| global.additionalPorts                    | `[]`          | Global additional ports                                               |
| global.additionalEnv.variables            | `[]`          | Global additional environment variables                               |
| global.additionalEnv.secrets              | `[]`          | Global additional environment secrets                                 |
| global.additionalEnv.configMaps           | `[]`          | Global additional environment config maps                             |

### Local parameters

The following values may be configured:

| Parameter                                    | Default value             | Description                                                                                                            |
|----------------------------------------------|---------------------------|------------------------------------------------------------------------------------------------------------------------|
| nameOverride                                 | `messaging-rabbitmq`                      | Override for the chart name. Used as the `app.kubernetes.io/name` selector label value and as input to the fullname helper. Pinned to keep selectors stable across chart renames; changing this requires manual cleanup of existing Deployments. |
| fullnameOverride                             | `""`                                      | Override for the fully qualified app name.                                                                             |
| image.registry                               | `hub.omnitrustregistry.com`               | Docker registry name for the image                                                                                     |
| image.repository                             | `ilm`              | Docker image repository name                                                                                           |
| image.name                                   | `rabbitmq`     | Docker image name                                                                                                      |
| image.tag                                    | `4.2.0`                   | Docker image tag                                                                                                       |
| image.digest                                 | `""`                      | Docker image digest, will override tag if specified                                                                    |
| image.pullPolicy                             | `IfNotPresent`            | Image pull policy                                                                                                      |
| image.pullSecrets                            | `[]`                      | Array of secret names for image pull                                                                                   |
| image.command                                | `[]`                      | Override the default command                                                                                           |
| image.args                                   | `[]`                      | Override the default args                                                                                              |
| image.securityContext.runAsNonRoot           | `true`                    | Run the container as non-root user                                                                                     |
| image.securityContext.readOnlyRootFilesystem | `true`                    | Run the container with read-only root filesystem                                                                       |
| image.resources                              | `{}`                      | The resources for the container                                                                                        |
| podLabels                                    | `{}`                      | Additional labels for the pod                                                                                          |
| podAnnotations                               | `{}`                      | Additional annotations for the pod                                                                                     |
| podSecurityContext.fsGroup                   | `999`                     | File system group for the pod                                                                                          |
| volumes.ephemeral.type                       | `memory`                  | Ephemeral volume type to be used                                                                                       |
| volumes.ephemeral.sizeLimit                  | `"1Mi"`                   | Ephemeral volume size limit                                                                                            |
| volumes.ephemeral.storageClassName           | `""`                      | Ephemeral volume storage class name for `storage` type                                                                 |
| volumes.ephemeral.custom                     | `{}`                      | Custom definition of the ephemeral volume for `custom` type                                                            |
| logging.level                                | `"info"`                  | Allowed values are `info`, `error`, `warning`, `deubg`                                                                 |
| service.client.type                          | `"ClusterIP"`             | Type of the service that is exposed                                                                                    |
| service.client.http.port                     | `15672`                   | Http port number of the exposed service                                                                                |
| service.client.amqp.port                     | `5672`                    | Amqp port number of the exposed service                                                                                |
| serviceAccount.create                        | `true`                    | Specifies whether a service account should be created                                                                  |
| serviceAccount.annotations                   | `{}`                      | Annotations to add to the service account                                                                              |
| serviceAccount.name                          | `"messaging-rabbitmq-sa"` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template |

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

#### RabbitMQ associated parameters

| Parameter                        | Default value                                           | Description                                               |
|----------------------------------|---------------------------------------------------------|-----------------------------------------------------------|
| service.headless.epmd.port       | `4369`                                                  | EPMD Discovery service port                               |
| service.headless.clusterRpc.port | `25672`                                                 | Cluster RPC service port                                  |
| persistence.enabled              | `true`                                                  | Enable persistence for RabbitMQ                           |
| persistence.storageClassName     | `""`                                                    | Storage class name for RabbitMQ persistence               |
| persistence.selector             | `{}`                                                    | Selector for dynamic provisioning of RabbitMQ persistence |
| persistence.accessModes          | `["ReadWriteOnce"]`                                     | Access mode for RabbitMQ persistence                      |
| persistence.existingClaim        | `""`                                                    | Existing claim name for RabbitMQ persistence              |
| persistence.size                 | `100Mi`                                                 | Size for RabbitMQ persistence                             |
| persistence.annotations          | `{}`                                                    | Annotations for RabbitMQ persistence                      |
| messaging.remoteAccess           | `false`                                                 | Enable remote access to messaging service                 |
| messaging.username               | `"admin"`                                               | Username to access the messaging                          |
| messaging.password               | `"admin"`                                               | Password to access the messaging                          |
| messaging.erlang.cookie          | `"c4eGHK4gM3v+5BHTFkGaRzqNQu0JcokVJkFK7CmJ"`            | Erlang cookie for RabbitMQ cluster communication          |
| messaging.plugins.enabled        | `"[rabbitmq_peer_discovery_k8s, rabbitmq_management]."` | Enabled plugins for RabbitMQ cluster                      |

#### Probes parameters

For mode details about probes, see the [Kubernetes documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

| Parameter                                  | Default value | Description                                                                        |
|--------------------------------------------|---------------|------------------------------------------------------------------------------------|
| image.probes.liveness.enabled              | `false`       | Enable/disable liveness probe                                                      |
| image.probes.liveness.custom               | `{}`          | Custom liveness probe command. When defined, it will override the default command  |
| image.probes.liveness.initialDelaySeconds  | `120`         | Initial delay seconds for liveness probe                                           |
| image.probes.liveness.timeoutSeconds       | `20`          | Timeout seconds for liveness probe                                                 |
| image.probes.liveness.periodSeconds        | `30`          | Period seconds for liveness probe                                                  |
| image.probes.liveness.successThreshold     | `1`           | Success threshold for liveness probe                                               |
| image.probes.liveness.failureThreshold     | `6`           | Failure threshold for liveness probe                                               |
| image.probes.readiness.enabled             | `true`        | Enable/disable readiness probe                                                     |
| image.probes.readiness.custom              | `{}`          | Custom readiness probe command. When defined, it will override the default command |
| image.probes.readiness.initialDelaySeconds | `10`          | Initial delay seconds for readiness probe                                          |
| image.probes.readiness.timeoutSeconds      | `20`          | Timeout seconds for readiness probe                                                |
| image.probes.readiness.periodSeconds       | `30`          | Period seconds for readiness probe                                                 |
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

## Persistence

The [RabbitMQ image](https://hub.docker.com/_/rabbitmq) stores the RabbitMQ data and configurations at the `/var/lib/rabbitmq/` path of the container.

By default, the volume is created using dynamic volume provisioning. However, an existing `PersistentVolumeClaim` can be used, or persistence can be turned off.

### Using existing PersistentVolumeClaim

To use an existing `PersistentVolumeClaim`, specify the `persistence.existingClaim` parameter.

### Disabling persistence

Persistence can be disabled by setting the `persistence.enabled` parameter to `false`.

### Global persistence configuration

When the global configuration is enabled, meaning that this chart is used with the complete ILM deployment, the persistence is managed globally by the umbrella chart. In this case, the local persistence configuration is ignored.
