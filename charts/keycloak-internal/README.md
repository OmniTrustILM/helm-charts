# Internal Keycloak Authorization - ILM

> This repository is part of the commercial open-source project ILM. You can find more information about the project at [ILM](https://github.com/OmniTrustILM/ilm) repository, including the contribution guide.

This repository contains [Helm](https://helm.sh/) charts as part of the ILM platform.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+
- PostgreSQL 11+

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
helm show values oci://hub.omnitrustregistry.com/ilm-helm/keycloak-internal > values.yaml
```
Now edit the `values.yaml` according to your desired stated, see [Configurable parameters](#configurable-parameters) for more information.

**Install**

For the basic installation, run:
```bash
helm install --namespace ilm -f values.yaml ilm-keycloak-internal oci://hub.omnitrustregistry.com/ilm-helm/keycloak-internal
```

**Save your configuration**

Always make sure you save the `values.yaml` and all `--set` and `--set-file` options you used. You will need to use the same options when you upgrade to new versions with Helm. In case you are changing the configuration, save the new configuration.

### Upgrade

> **Warning**
> Be sure that you always save your previous configuration!

For upgrading the installation, update your configuration and run:
```bash
helm upgrade --namespace ilm -f values.yaml ilm-keycloak-internal oci://hub.omnitrustregistry.com/ilm-helm/keycloak-internal
```

### Uninstall

You can use the `helm uninstall` command to uninstall the application:
```bash
helm uninstall --namespace ilm ilm-keycloak-internal
```

## Configurable parameters

You can find current values in the [values.yaml](values.yaml).
You can also Specify each parameter using the `--set` or `--set-file` argument to `helm install`.

### Global parameters

Global values are used to define common parameters for the chart and all its sub-charts by exactly the same name.

| Parameter                                 | Default value          | Description                                                        |
|-------------------------------------------|------------------------|--------------------------------------------------------------------|
| global.replicaCount                       | `1`                    | Number of replicas for the application                             |
| global.image.registry                     | `""`                   | Global docker registry name                                        |
| global.image.repository                   | `""`                   | Global docker image repository name                                |
| global.image.pullSecrets                  | `[]`                   | Global array of secret names for image pull                        |
| global.volumes.ephemeral.type             | `""`                   | Global ephemeral volume type to be used                            |
| global.volumes.ephemeral.sizeLimit        | `""`                   | Global ephemeral volume size limit                                 |
| global.volumes.ephemeral.storageClassName | `""`                   | Global ephemeral volume storage class name for `storage` type      |
| global.volumes.ephemeral.custom           | `{}`                   | Global custom definition of the ephemeral volume for `custom` type |
| global.database.type                      | `""`                   | Type of the database, currently only `postgresql` is supported     |
| global.database.host                      | `""`                   | Host where is the database located                                 |
| global.database.port                      | `""`                   | Port on which is the database listening                            |
| global.database.name                      | `""`                   | Database name                                                      |
| global.database.username                  | `""`                   | Username to access the database                                    |
| global.database.password                  | `""`                   | Password to access the database                                    |
| global.database.pgBouncer.enabled         | `true`                 | Enable pgBouncer for database connection pooling and management    |
| global.database.pgBouncer.host            | `"pg-bouncer-service"` | Host where is the pgBouncer located                                |
| global.database.pgBouncer.port            | `5432`                 | Port on which is the pgBouncer listening                           |
| global.trusted.certificates               | `""`                   | List of additional CA certificates that should be trusted          |
| global.hostName                           | `""`                   | Global hostname of the running instance                            |
| global.keycloak.clientSecret              | `""`                   | Keycloak OIDC client secret to be used for ILM              |
| global.admin.username                     | `""`                   | Initial administrator username                                     |
| global.admin.password                     | `""`                   | Initial administrator password                                     |
| global.admin.name                         | `""`                   | Initial administrator first name                                   |
| global.admin.surname                      | `""`                   | Initial administrator last name                                    |
| global.admin.email                        | `""`                   | Initial administrator email                                        |
| global.initContainers                     | `[]`                   | Global init containers                                             |
| global.sidecarContainers                  | `[]`                   | Global sidecar containers                                          |
| global.additionalVolumes                  | `[]`                   | Global additional volumes                                          |
| global.additionalVolumeMounts             | `[]`                   | Global additional volume mounts                                    |
| global.additionalPorts                    | `[]`                   | Global additional ports                                            |
| global.additionalEnv.variables            | `[]`                   | Global additional environment variables                            |
| global.additionalEnv.secrets              | `[]`                   | Global additional environment secrets                              |
| global.additionalEnv.configMaps           | `[]`                   | Global additional environment config maps                          |

### Local parameters

The following values may be configured:

| Parameter                                      | Default value                          | Description                                                                                                            |
|------------------------------------------------|----------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| trusted.certificates                           | `""`                                   | List of additional CA certificates that should be trusted                                                              |
| nameOverride                                   | `keycloak-internal`                    | Override for the chart name. Used as the `app.kubernetes.io/name` selector label value and as input to the fullname helper. Pinned to keep selectors stable across chart renames; changing this requires manual cleanup of existing Deployments. |
| fullnameOverride                               | `""`                                   | Override for the fully qualified app name.                                                                             |
| image.registry                                 | `hub.omnitrustregistry.com`            | Docker registry name for the image                                                                                     |
| image.repository                               | `ilm`                                  | Docker image repository name                                                                                           |
| image.name                                     | `keycloak-optimized`                   | Docker image name                                                                                                      |
| image.tag                                      | `26.4.2-0`                             | Docker image tag                                                                                                       |
| image.digest                                   | `""`                                   | Docker image digest, will override tag if specified                                                                    |
| image.pullPolicy                               | `IfNotPresent`                         | Image pull policy                                                                                                      |
| image.pullSecrets                              | `[]`                                   | Array of secret names for image pull                                                                                   |
| image.command                                  | `[]`                                   | Override the default command                                                                                           |
| image.args                                     | `[start, --optimized, --import-realm]` | Override the default args                                                                                              |
| image.securityContext.runAsNonRoot             | `true`                                 | Run the container as non-root user                                                                                     |
| image.securityContext.readOnlyRootFilesystem   | `true`                                 | Run the container with read-only root filesystem                                                                       |
| image.securityContext.allowPrivilegeEscalation | `false`                                | Do not allow privilege escalation for the container                                                                    |
| image.securityContext.capabilities.drop        | `["ALL"]`                              | Drop all Linux capabilities                                                                                            |
| image.securityContext.seccompProfile.type      | `RuntimeDefault`                       | Seccomp profile type for the container                                                                                 |
| image.resources                                | `{}`                                   | The resources for the container                                                                                        |
| podLabels                                      | `{}`                                   | Labels to be added to the pod                                                                                          |
| podAnnotations                                 | `{}`                                   | Annotations to be added to the pod                                                                                     |
| podSecurityContext.seccompProfile.type         | `RuntimeDefault`                       | Seccomp profile type for the pod                                                                                       |
| volumes.ephemeral.type                         | `memory`                               | Ephemeral volume type to be used                                                                                       |
| volumes.ephemeral.sizeLimit                    | `"1Mi"`                                | Ephemeral volume size limit                                                                                            |
| volumes.ephemeral.storageClassName             | `""`                                   | Ephemeral volume storage class name for `storage` type                                                                 |
| volumes.ephemeral.custom                       | `{}`                                   | Custom definition of the ephemeral volume for `custom` type                                                            |
| logging.level                                  | `"info"`                               | Allowed values are `fatal`, `error`, `warn`, `info`, `debug`, `trace`, `all`, or `off`                                 |
| service.type                                   | `"ClusterIP"`                          | Type of the service that is exposed                                                                                    |
| service.port                                   | `8080`                                 | Port number of the exposed service                                                                                     |
| createDbSchema                                 | true                                   | Deploy simple startupHook to create schema for Keycloak in database                                                    |
| serviceAccount.create                          | `true`                                 | Specifies whether a service account should be created                                                                  |
| serviceAccount.annotations                     | `{}`                                   | Annotations to add to the service account                                                                              |
| serviceAccount.name                            | `"keycloak-internal-sa"`               | The name of the service account to use. If not set and create is true, a name is generated using the fullname template |

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

#### Parameters for associated containers

**ILM Keycloak theme**

| Parameter                                            | Default value               | Description                                         |
|------------------------------------------------------|-----------------------------|-----------------------------------------------------|
| theme.image.registry                                 | `hub.omnitrustregistry.com` | Docker registry name for the image                  |
| theme.image.repository                               | `ilm`                       | Docker image repository name                        |
| theme.image.name                                     | `keycloak-theme`            | Docker image name                                   |
| theme.image.tag                                      | `0.1.4`                     | Docker image tag                                    |
| theme.image.digest                                   | `""`                        | Docker image digest, will override tag if specified |
| theme.image.pullPolicy                               | `IfNotPresent`              | Image pull policy                                   |
| theme.image.pullSecrets                              | `[]`                        | Array of secret names for image pull                |
| theme.image.command                                  | `[]`                        | Override the default command for the container      |
| theme.image.args                                     | `[]`                        | Arguments passed to the entrypoint in the container |
| theme.image.securityContext.runAsNonRoot             | `true`                      | Run the container as non-root user                  |
| theme.image.securityContext.readOnlyRootFilesystem   | `true`                      | Run the container with read-only root filesystem    |
| theme.image.securityContext.allowPrivilegeEscalation | `false`                     | Do not allow privilege escalation for the container |
| theme.image.securityContext.capabilities.drop        | `["ALL"]`                   | Drop all Linux capabilities                         |
| theme.image.securityContext.seccompProfile.type      | `RuntimeDefault`            | Seccomp profile type for the container              |
| theme.image.resources                                | {}                          | Specify requests and limits for the image if needed |

#### Keycloak associated parameters

| Parameter                 | Default value | Description                                                                                                                                      |
|---------------------------|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| keycloak.dbSchema         | `"keycloak"`  | The database schema to be used                                                                                                                   |
| keycloak.admin.username   | `"admin"`     | Initial Keycloak master realm administrator username                                                                                             |
| keycloak.admin.password   | `"admin"`     | Initial Keycloak master realm administrator password                                                                                             |
| keycloak.httpRelativePath | `/kc`         | Set the path relative to `/` for serving resources. **Hardcoded in keycloak-optimized image, change only if you know what you are doing!**       |
| keycloak.httpEnabled      | `true`        | Enables the HTTP listener                                                                                                                        |
| keycloak.proxyHeaders     | `xforwarded`  | Should server accept `forwarded` or `xforwarded` values? See [official documentation](https://www.keycloak.org/server/all-config#category-proxy) |
#### ILM realm parameters

| Parameter                  | Default value            | Description                                                                           |
|----------------------------|--------------------------|---------------------------------------------------------------------------------------|
| ilm.admin.username         | `"ilm-admin"`            | Initial `superadmin` username                                                         |
| ilm.admin.password         | `"your-strong-password"` | Initial `superadmin` password                                                         |
| ilm.admin.name             | `"admin"`                | Initial `superadmin` first name                                                       |
| ilm.admin.surname          | `"ilm"`                  | Initial `superadmin` last name                                                        |
| ilm.admin.email            | `"admin@ilm.local"`      | Initial `superadmin` email                                                            |
| ilm.hostName               | `"ilm.local"`            | Hostname to be used as the Root URL for the OIDC configuration                        |
| ilm.clientSecret           | `""`                     | Keycloak OIDC client secret to be used for ILM                                        |
| ilm.redirectUri.login      | `"/login/"`              | Allowed redirect URI for login. **Change only if you know what you are doing!**       |
| ilm.redirectUri.postLogout | `"/administrator/"`      | Allowed redirect URI for post logout. **Change only if you know what you are doing!** |

#### Probes parameters

For mode details about probes, see the [Kubernetes documentation](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

| Parameter                                  | Default value | Description                                                                        |
|--------------------------------------------|---------------|------------------------------------------------------------------------------------|
| image.probes.liveness.enabled              | `false`       | Enable/disable liveness probe                                                      |
| image.probes.liveness.custom               | `{}`          | Custom liveness probe command. When defined, it will override the default command  |
| image.probes.liveness.initialDelaySeconds  | `30`          | Initial delay seconds for liveness probe                                           |
| image.probes.liveness.timeoutSeconds       | `5`           | Timeout seconds for liveness probe                                                 |
| image.probes.liveness.periodSeconds        | `10`          | Period seconds for liveness probe                                                  |
| image.probes.liveness.successThreshold     | `1`           | Success threshold for liveness probe                                               |
| image.probes.liveness.failureThreshold     | `3`           | Failure threshold for liveness probe                                               |
| image.probes.readiness.enabled             | `true`        | Enable/disable readiness probe                                                     |
| image.probes.readiness.custom              | `{}`          | Custom readiness probe command. When defined, it will override the default command |
| image.probes.readiness.initialDelaySeconds | `30`          | Initial delay seconds for readiness probe                                          |
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
