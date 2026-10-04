---
sidebar_position: 3
---

# Upgrading

:::warning[Before upgrading]
Before upgrading, make sure you have backed up your configuration, trusted certificates and data to be able to restore the platform in case of any issues.

Never downgrade the platform version, as it may cause data loss or other issues. Be sure that you are upgrading to higher version of the Helm chart.
:::

:::info[Upgrade vs Install]
Platform can be installed from scratch anytime when you have a backup of your database and configuration. New installation through the Helm chart will deploy new environment connecting to the same database. You can install multiple instances of the platform in different clusters and infrastructures with the same database.
:::

The following contains important information and instructions about upgrading Helm charts.

Upgrading Helm chart is done by running the `helm upgrade` command. The command upgrades the platform to the specified version. The command can be used to upgrade the platform to the same version with changed parameters.

## To 2.20.0

:::warning[Before upgrading]
- If you run the Software Cryptography Provider, back up its database schema first. Its 1.4.0 upgrade cannot be undone, see [Software Cryptography Provider 1.4.0](#software-cryptography-provider-140).
- If you use an external RabbitMQ, create the new `provider.discovery-work` queue first, see [RabbitMQ queue for discovery work](#rabbitmq-queue-for-discovery-work).
- Core migrates the `discovery_certificate` table at startup, which can take a while on a large installation, see [Longer Core startup](#longer-core-startup).
:::

### Registering connectors on upgrade

The job that registers connectors runs on `helm install` only. `helm upgrade` registers neither a connector you enable during the upgrade nor a new interface version of a connector that is already registered.

In 2.20.0 the Network Discovery Provider and the Software Cryptography Provider implement the v2 provider interfaces. A fresh installation registers each of them twice, at the same URL: as v1 under its existing name, and as v2 under the name below. On an upgrade, register the v2 interfaces yourself:

| Connector                      | v2 name                             | URL                                                  |
|--------------------------------|-------------------------------------|------------------------------------------------------|
| Network Discovery Provider     | `Network-Discovery-Provider-v2`     | `http://network-discovery-provider-service:8080`     |
| Software Cryptography Provider | `Software-Cryptography-Provider-v2` | `http://software-cryptography-provider-service:8080` |

Register them on the Connectors page of the administrator interface, or through the API from a pod inside the cluster:

```bash
kubectl run register-connector --rm -i --restart=Never --namespace <your-namespace> --image=curlimages/curl -- \
  -sS -X POST -H 'content-type: application/json' \
  -d '{"name": "Network-Discovery-Provider-v2", "version": "v2", "url": "http://network-discovery-provider-service:8080", "authType": "none", "customAttributes": []}' \
  http://core-service:8080/api/v2/connector/register
```

Keep the existing v1 registrations. Adjust the ports if you changed `service.port` of Core or of the connector.

### RabbitMQ queue for discovery work

Core 2.20.0 drives discovery v2 runs through the new `provider.discovery-work` queue. The bundled `messaging-rabbitmq` declares the queue, binds it and grants Core read access to it, so the internal broker needs no action.

With external messaging (`global.messaging.external.enabled: true`), create it before the upgrade, on the platform virtual host (`messaging.virtualHost`, `/` by default):

- a durable queue `provider.discovery-work`
- a binding from the `ilm` exchange (`bootstrap.exchange`) to the queue, with the routing key `provider.discovery-work`
- read permission on the queue for Core's user (`global.messaging.coreUsername`)

For example:

```bash
rabbitmqadmin --vhost=/ declare queue name=provider.discovery-work durable=true
rabbitmqadmin --vhost=/ declare binding source=ilm destination=provider.discovery-work routing_key=provider.discovery-work
rabbitmqctl set_permissions -p / <core-username> '' '^ilm(-proxy)?$' \
  '^core(\..+|-.+)?$|^provider\.(status-poll|discovery-work)$|^time-quality\.(config-request|results)$'
```

`rabbitmqctl set_permissions` replaces all of the user's permissions on the virtual host. The patterns above are the ones the bundled broker grants Core; adjust them if your exchange names differ.

### Longer Core startup

Core runs its database migrations at startup, before it answers the startup probe. The 2.20.0 migration `V202608291000` converts two columns of `discovery_certificate`, which rewrites the whole table under an exclusive lock, and then builds a new index on it. On a large installation that can take longer than the previous startup budget of about 8 minutes, and a pod restarted mid-migration rolls the migration back and starts it over.

`image.probes.startup.failureThreshold` is raised from `45` to `180`, which gives Core about 30 minutes. If your values set it, raise it as well. To estimate the work, check the size of the table before the upgrade:

```sql
SELECT count(*), pg_size_pretty(pg_total_relation_size('core.discovery_certificate'))
FROM core.discovery_certificate;
```

Plan the upgrade for a maintenance window: while the migration runs, requests that touch discovered certificates wait for the lock.

### Network Discovery Provider

The connector moves to ip-discovery-provider 1.7.0, which adds the discovery v2 interface.

- **Single replica.** A discovery v2 run lives in the memory of the pod that started it, so the chart runs one replica and ignores `global.replicaCount`. If you set `global.replicaCount` above `1`, the connector now drops back to one pod. It is updated with the `Recreate` strategy, so the old pod stops before the new one starts.
- **Probe timeout.** The new `discovery.probe.connectTimeoutMs` value defaults to `300`, which keeps the sweep times of 1.6.1. The connector's own default of 500 ms makes a long sweep about 1.7 times longer, enough to pass Core's 6-hour limit for a run.
- **Memory.** The connector buffers the undrained results of its discovery v2 runs in heap, up to 512 MiB in total by default (`DISCOVERY_BUFFER_MAX_TOTAL_BYTES`). Size `image.resources` and `javaOpts` for it, or lower the bound through `additionalEnv`.

### Software Cryptography Provider 1.4.0

:::warning[No way back to 1.3.2]
Back up the connector's database schema (`softcp` by default) before upgrading. Migration `V202609011200` re-encrypts the stored token passwords in a format 1.3.2 cannot read, so restoring the backup is the only way back.
:::

- **Duplicate token names fail the upgrade.** Migration `V202609031200` adds a unique constraint on the token name. Find duplicates before upgrading and make the names unique:
  ```sql
  SELECT name, count(*) FROM softcp.token_instance GROUP BY name HAVING count(*) > 1;
  ```
- **Recreate strategy.** An old and a new instance must not serve the same database at once, so the connector is updated with the `Recreate` strategy: the old pod stops before the new one starts.
- **Encryption key.** The new `encryptionKey` value sets the key the token passwords are encrypted with (`ENCRYPTION_KEY`). Without it, the connector runs on its published default key and 1.4.0 warns about it at startup. Set it only on a new installation, before the first start: the token passwords stay encrypted with the key they were written under, so changing the key of an existing installation leaves them unreadable. If you already pass `ENCRYPTION_KEY` through `additionalEnv`, keep it there or move the same value to `encryptionKey`, not both.

### OT PKI Connector 1.1.0

The connector moves to the OTPKI v1.0.0 API and no longer works with earlier OTPKI servers, so upgrade OTPKI first. OTPKI v1.0.0 also checks the enrollment password on every request, so keep `otpki.loginPasswordKey` at the value the existing end entities were created with. If you built the connector's OTPKI role by hand, make sure it has the `Update` permission on End Entity, which renewal needs. See the connector's README for the full list of prerequisites.

### cbom-repository 1.2.0 or later

Core 2.20.0 pages the CBOM repository with a keyset cursor that cbom-repository 1.1.0 does not serve, so it needs cbom-repository 1.2.0 or later. The charts do not deploy cbom-repository; upgrade it before or together with the platform.

### Logo uploads through ingress-nginx

The platform branding accepts logos of up to 1 MB, but the request that carries a logo is larger than the file itself. The ingress-nginx default body limit of 1 MiB therefore answers files over about 750 KB with `413 Request Entity Too Large`. To accept them, add the annotation to your values; Helm merges it into the default annotations:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "2m"
```

## To 2.19.0

### Additional connector sub-charts

The following sub-charts were added to support additional connectors as optional components:
- OT PKI Connector
- Timestamp Formatting Connector

Both are disabled by default, so no action is required for existing deployments. When you enable a new connector during upgrade, you need to register the connector manually in the platform:
```yaml
otpkiConnector:
  enabled: false
timestampFormattingConnector:
  enabled: false
```

### RabbitMQ virtual host and exchange rename

The default RabbitMQ virtual host has changed from `czertainly` to `/` (the RabbitMQ default), and the exchange names have changed from `czertainly`/`czertainly-proxy` to `ilm`/`ilm-proxy`.

| Parameter                  | Old default        | New default |
|----------------------------|--------------------|-------------|
| `messaging.virtualHost`    | `czertainly`       | `/`         |
| `bootstrap.exchange`       | `czertainly`       | `ilm`       |
| `bootstrap.proxy.exchange` | `czertainly-proxy` | `ilm-proxy` |

:::note[The old names are identifiers, not stale branding]
Left at the defaults above, a pre-2.19.0 deployment created three separate objects in RabbitMQ: the virtual host `czertainly`, the main exchange `czertainly` — a different object that happens to carry the same name — and the proxy exchange `czertainly-proxy`. If your values file set `messaging.virtualHost`, `bootstrap.exchange` or `bootstrap.proxy.exchange`, your deployment created the names you chose instead.

Whichever names yours has, they stay until you migrate. Type them exactly as they exist in the broker wherever you inspect, override, or delete the old topology — that is what RabbitMQ resolves, regardless of the platform having been renamed to ILM.
:::

#### Fresh installation

No manual steps are required. The new virtual host and exchanges are created automatically by `provisioning-rabbitmq` on first startup.

#### Upgrade from a previous version

After `helm upgrade`, `provisioning-rabbitmq` will create the new exchanges and queues on the `/` vhost automatically. The old `czertainly` vhost and its queues remain in RabbitMQ untouched — they are orphaned but not deleted.

**What to do with the old `czertainly` vhost:**

| Situation                                    | Action                                                                                                                                                                                         |
|----------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| No messages in queues / messages can be lost | Delete the `czertainly` vhost from the RabbitMQ management UI after confirming the upgrade is stable.                                                                                          |
| Messages must be preserved                   | Follow the drain procedure below before upgrading.                                                                                                                                             |
| You cannot migrate yet                       | Override `messaging.virtualHost` back to `czertainly` and exchange names back to `czertainly`/`czertainly-proxy` in your values to keep using the old topology until you are ready to migrate. |

##### Drain procedure

Stop new messages from entering the system by scaling down the API gateway:

```bash
kubectl scale deployment api-gateway-deployment --replicas=0 --namespace <your-namespace>
```

Then wait for critical queues to drain using the following script (adjust `RABBIT_HOST`, `AUTH`, and `QUEUES` to match your environment):

```bash
#!/bin/bash
RABBIT_HOST="localhost"
RABBIT_PORT="15672"
AUTH="admin:admin"
VHOST="czertainly"
QUEUES=("core.audit-logs")

echo "Waiting for queues to drain on vhost '$VHOST'..."

while true; do
  TOTAL=0
  for QUEUE in "${QUEUES[@]}"; do
    COUNT=$(curl -s -u "$AUTH" \
      "http://$RABBIT_HOST:$RABBIT_PORT/api/queues/$(printf '%s' "$VHOST" | sed 's|/|%2F|g')/$QUEUE" \
      | grep -o '"messages":[0-9]*' | head -1 | cut -d: -f2)
    COUNT=${COUNT:-0}
    echo "  $QUEUE: $COUNT messages"
    TOTAL=$((TOTAL + COUNT))
  done

  echo "Total remaining: $TOTAL"

  if [ "$TOTAL" -eq 0 ]; then
    echo "All queues drained. Safe to upgrade."
    exit 0
  fi

  sleep 5
done
```

Once the script exits, run `helm upgrade` as usual. The API gateway will be restored automatically as part of the upgrade.


## To 2.18.0

This release rebrands the Helm charts from CZERTAINLY to ILM (OmniTrust ILM). The umbrella chart was renamed from `czertainly` to `ilm`, and the library chart from `czertainly-lib` to `ilm-lib`. Container images, registry, database defaults, Keycloak realm, and project URLs were all updated.

### Manual steps required when upgrading from any earlier version

The rebrand changes the rendered values of `app.kubernetes.io/name` (the Deployment selector), `ilm.fullname` (the optional Ingress resource name), and the Keycloak realm/client identifiers. Three constraints make `helm upgrade` fail without manual intervention:

1. **`Deployment.spec.selector` is immutable** — the existing `core-deployment` selector cannot be patched in place.
2. **The nginx Ingress admission webhook rejects duplicate host/path** — the new Ingress would briefly coexist with the old (renamed) one, both claiming the same host and path.
3. **Keycloak `--import-realm` fails with a duplicate primary-key error** — the realm in the database has the same UUID as in the new realm JSON but a different name (`CZERTAINLY` vs `ILM`).

:::warning[Order matters]
Perform the steps below in the order shown. In particular, run the Keycloak migration script BEFORE running `helm upgrade` — the script needs the still-running pre-upgrade Keycloak to be reachable. If you run `helm upgrade` first, the new Keycloak pod will crash on startup and the script will be unable to connect.
:::

#### 1. Migrate the Keycloak realm

| Deployment                    | Configuration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|-------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fresh installation            | The new ILM realm is automatically created. No manual changes are required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| Upgrade from previous version | The existing `CZERTAINLY` realm must be renamed and its clients, default role, audience mapper, and built-in client URLs updated to match the new `ILM` identifiers in the realm JSON shipped with this release. Use the provided Python script [update_realm_from_2.17.0_to_2.18.0.py](https://github.com/OmniTrustILM/helm-charts/tree/main/charts/keycloak-internal/scripts/update_realm_from_2.17.0_to_2.18.0.py). The script will prompt you for the Keycloak URL, admin username, and password. It is idempotent (safe to run multiple times) and serves as documentation for the necessary changes — every UUID is preserved, only human-readable identifiers and URLs are updated, so existing users, sessions, group memberships, and client secrets are not affected. |

The script connects via the Keycloak Admin REST API, so it works against any Keycloak (chart-managed or external) and does not depend on any specific database access.

:::info[Upgrading from a chart version older than 2.17.0]
If you are upgrading from a chart version older than 2.17.0, also run the realm-update scripts for each version transition you are crossing, in version order, BEFORE running the rebrand script. Those older scripts target the `CZERTAINLY` realm by name, which only exists until the rebrand-rename completes. The natural order is:

1. [`update_realm_from_2.7.0_to_2.14.0.py`](https://github.com/OmniTrustILM/helm-charts/tree/main/charts/keycloak-internal/scripts/update_realm_from_2.7.0_to_2.14.0.py) — only if upgrading from a chart version earlier than 2.14.0
2. [`update_realm_from_2.14.0_to_2.17.0.py`](https://github.com/OmniTrustILM/helm-charts/tree/main/charts/keycloak-internal/scripts/update_realm_from_2.14.0_to_2.17.0.py) — only if upgrading from a chart version earlier than 2.17.0
3. [`update_realm_from_2.17.0_to_2.18.0.py`](https://github.com/OmniTrustILM/helm-charts/tree/main/charts/keycloak-internal/scripts/update_realm_from_2.17.0_to_2.18.0.py) — always, this is the rebrand-rename script
:::

#### 2. Delete the old core and pg-bouncer deployment

```bash
kubectl delete deployment core-deployment --namespace <your-ilm-namespace>
kubectl delete deployment pg-bouncer-deployment --namespace <your-ilm-namespace>
```

This removes only the Deployment objects; existing data is unaffected (ILM is stateless at this layer). There will be brief downtime while the new core and pg-bouncer pods become ready after the upgrade.

#### 3. Delete the old ingress (only if `ingress.enabled: true`)

List the existing Ingresses to find the one bound to your ILM hostname (the exact name depends on your release name, because the fullname helper drops the chart-name suffix when the release name already contains the chart name):

```bash
kubectl get ingress --namespace <your-ilm-namespace>
kubectl delete ingress <existing-ingress-name> --namespace <your-ilm-namespace>
```

#### 4. Run helm upgrade

After the three cleanups above, run `helm upgrade` as usual. Helm will create the new resources, and the new Keycloak pod will boot cleanly because the realm in the database now matches the new identifiers.

If you apply the rendered manifest out of band (e.g., `helm template ... | kubectl apply -f -`, or via a GitOps tool such as Argo CD or Flux) instead of running `helm upgrade`, the same three cleanups (steps 1–3) are required before re-applying — the constraints are at the Kubernetes API server / Ingress controller / Keycloak layer, not in Helm.

### Stable identifier going forward

The umbrella chart now ships with `nameOverride: platform-core` in its default values, decoupling selectors and fullname-based resources from the chart name. Sub-charts have analogous `nameOverride` defaults set to their respective chart names. Future chart renames will not require similar manual cleanup.

:::warning[Do not override nameOverride]
Passing `--set nameOverride=...` (or setting `nameOverride` in your custom values) at install or upgrade time will reintroduce the same risk on subsequent upgrades. Leave the default values intact.
:::

## To 2.15.0

### New connector sub-charts

The following sub-charts were added to support additional connectors as optional components:
- Webhook Notification Provider

When you enable new connector during upgrade, you need to register the connector manually in the platform:
```yaml
webhookNotificationProvider:
  enabled: false
```

### User option removed from PgBouncer

The `user` configuration option was removed from the `pg-bouncer` sub-chart to avoid conflicts with the running user in the container for different K8s distributions. If you need to set the user, you can do it by setting the following properties in the `pgBouncer` section of the `values.yaml` file:
```yaml
pgBouncer:
  section:
    pgbouncer:
      user: "postgres"
```

### Removed default runAsUser option

The default `runAsUser` was removed from the Helm chart for optimized deployment on different K8s distributions, including OpenShift. The `runAsUser` value can be set in the `securityContext` and `podSecurityContext` sections of the `values.yaml` file.

### Global configuration of replica count

The global `replicaCount` parameter was introduced to allow setting the number of replicas for all components in the platform. The parameter can be set in the `global` section of the `values.yaml` file:
```yaml
global:
  replicaCount: 1
```

## To 2.14.1

### External messaging support

The platform now supports external messaging services. The messaging service can be configured to use external RabbitMQ. The internal RabbitMQ service is still supported and considered as default option.

In order to use external messaging service, the following parameters must be set in the values:
```yaml
global:
  messaging:
    external:
      # Enable external messaging service
      enabled: true
      # Hostname of the external messaging service
      host: "my.messaging.com"
      amqp:
        # AMQP port of the external messaging service
        port: 5672
    # Username for the external messaging service
    username: "messaging-user"
    # Password for the external messaging service
    password: "your-strong-password"

# Disable internal messaging service, as external messaging service is going to be used
# If it is not disabled, the internal messaging service will be deployed, but not used
messagingService:
  enabled: false
```

## Database connection pooling using PgBouncer

The platform now supports database connection pooling using PgBouncer. The PgBouncer service is enabled by default and can be configured using the following parameters:
```yaml
global:
  database:
    pgBouncer:
      enabled: true
      host: "pg-bouncer-service"
      port: 5432
```

## To 2.14.0

:::warning[Breaking changes]
This version introduced breaking changes in the configuration of OAuth2 providers and logging that need your attention.
:::

### OAuth2 provider configuration

The platform now supports multiple configurations of OAuth2 providers. If you are using the internal Keycloak for authentication (`global.keycloak.enabled=true`), a different approach must be applied depending on whether you are deploying the platform for the first time or upgrading from a previous version:

| Deployment                    | Configuration                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
|-------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Fresh installation            | The OAuth2 `internal` provider is automatically configured. No manual changes are required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Upgrade from previous version | The OAuth2 `internal` provider is automatically configured. However, changes to the OAuth2 Keycloak client configuration must be applied manually. For a convenient upgrade, use the provided Python script [update_realm_from_2.7.0_to_2.14.0.py](https://github.com/OmniTrustILM/helm-charts/tree/main/charts/keycloak-internal/scripts/update_realm_from_2.7.0_to_2.14.0.py). The script will prompt you for the required parameters and update the Keycloak client configuration. It also serves as a guide and documentation for the necessary changes. |

### Logging configuration

The logging was updated to support structured records and better integration with the logging infrastructure. The previous implementation of audit logs was removed and replaced with the new implementation.

:::danger[Audit logs]
It is recommended to create a backup or export of all audit logs you want to keep before upgrading to this version. The audit logs are reset during the upgrade.
:::

The `logging.audit.enabled` parameter was removed. The audit logs are now configured in the platform.
For more information on logging and how to configure it, see the [Logging](https://docs.otilm.com/docs/certificate-key/logging/overview) section in the documentation.

### Changed parameters

The following parameters were changed or removed. Please update your configuration accordingly:

- Configuration of header names and OIDC for API gateway is removed in favor of the new OAuth2 provider configuration. Particularly, the `auth`, `oidc`, and `hostAliases` parameters were removed from the `apiGateway` section and are not supported anymore.
- The certification authentication header name was changed from default `X-APP-CERTIFICATE` to `ssl-client-cert` in the `auth.header.certificate` parameter. Be sure to update your configuration if you are using the certificate-based authentication and terminate the SSL connection outside the platform.

## To 2.13.1

Added support for custom command and args for the containers. The following parameters were added to the umbrella chart and all sub-charts:
```yaml
# custom command and args
command: []
args: []
```

### Removed deprecated sub-charts

Deprecated sub-charts were removed:
- MS ADCS Connector
- API Gateway HAProxy

You can remove the deprecated dependencies from the umbrella chart, if they are still used (they will not be applied anymore):
```yaml
msAdcsConnector:
  nameOverride: ms-adcs-connector
  enabled: false
```

## To 2.13.0

### Additional connector sub-charts

The following sub-charts were added to support additional connectors as optional components:
- CT Logs Discovery Provider

When you enable new connector during upgrade, you need to register the connector manually in the platform:
```yaml
ctLogsDiscoveryProvider:
  enabled: false
```

## To 2.11.0-1

### Additional connector sub-charts

The following sub-charts were added to support additional connectors as optional components:
- HashiCorp Vault Connector

When you enable new connector during upgrade, you need to register the connector manually in the platform:
```yaml
hashicorpVaultConnector:
  enabled: false
```

See the [ILM Helm chart 2.11.0-1 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.11.0-1) for more information.

## To 2.11.0

### New PyADCS connector

To resolve compatibility issues and improve performance of the ADCS certificate related operations and authentication, the new ADCS connector was introduced based on Python technology.
MS ADCS connector is considered from this version as deprecated and will be removed in the future.

When you enable PyADCS connector during upgrade, you need to register the connector manually in the platform:
```yaml
pyAdcsConnector:
  enabled: true
```

See the [ILM Helm chart 2.11.0 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.11.0) for more information.

## To 2.9.0

### Persistent volume provisioner

This version introduced requirement for the persistent volume provisioner support in the underlying infrastructure. The `StorageClass` is required to be available in the cluster. The volumes are dynamically provisioned by default, but it can be changed by setting existing persistent volume claim or disabling persistence (which will use `emptyDir` volume).

The list of components that need persistence can be found in the [Overview - Persistence](./overview.md#persistence) section.

:::warning[Persistent volume claim]
The provisioner of the persistent volume must be properly configured to upgrade the platform, in case the dynamic storage should be created. In case the dynamic provisioning is not enabled, the persistent volume claim must be created manually before upgrading the platform. Form more information see [Dynamic Volume Provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/).
:::

### Container image configuration and repository

To support multiple container registries, including better support for privately managed registries, where there are different naming conventions and images are organized in projects, we have split image `repository` property to `repository` and `name`.

This allows to control the repository name using the global configuration, providing better support for private repositories with different organization of images and repositories. For example the following values:

```yaml
global:
  image:
    registry: myregistry.com
    repository: ilm/project

image:
  # default registry name
  registry: hub.omnitrustregistry.com
  repository: ilm
  name: core
  tag: 2.9.0
```

will result in the following image name: `myregistry.com/ilm/project/core:2.9.0`.

### Customization of the deployment

The deployment of the platform can be customized using the following parameters:
```yaml
initContainers: []
sidecarContainers: []
additionalVolumes: []
additionalVolumeMounts: []
additionalPorts: []
additionalEnv:
  variables: []
  configMaps: []
  secrets: []
```

When the parameters are set globally, they are applied to all charts and sub-charts. When the parameters are set for specific chart or sub-chart, they are applied only to the sub-chart. If they global and local parameters are defined, they are merged together.

## To 2.8.0

Using `NodePort` to access the platform should be configured on API Gateway level, not for the Core service (as a service in `ilm` chart). The `nodePort` parameter is included for both `admin` and `consumer` service in `api-gateway-kong` sub-chart. The proper way to configure `NodePort` is:

```yaml
ingress:
  # disable ingress as we are going to use direct access to the platform
  enabled: false

apiGateway:
  service:
    # use NodePort to access the platform
    type: "NodePort"
    consumer:
      port: 8000
      nodePort: 30080
    admin:
      port: 8001
      nodePort: 30081
```

See the [ILM Helm chart 2.8.0 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.8.0) for more information.

## To 2.7.1

### Enabling Utils Service

Enabling parameter of Utils Service was moved from the `utilsService.enabled` to global parameters:
```yaml
global:
  utils:
    enabled: false
```

See the [ILM Helm chart 2.7.1 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.7.1) for more information.

## To 2.7.0

### Cleanup of the global parameters

The global parameters were cleaned up and reorganized.

The following default parameters were removed. They must be explicitly set now in the values, if you want to use them. Check your current configuration and update it accordingly:
```yaml
global:
  database:
    type: ""
    host: ""
    port: ""
    name: ""
    username: ""
    password: ""
  trusted:
    certificates: ""
```

Hostname was introduced as a global parameter that can be shared across the deployment. The main reason is optional implementation of the internal Keycloak service that requires to know the hostname of the platform to properly set URLs:
```yaml
global:
  hostName: ""
```

Administrator registration information is introduced as global parameters. This allows to share for example the same data with internal Keycloak, if enabled. If you want to keep the client certificate-based authentication for administrator, configure certificate in the `registerAdmin.admin.certificate` parameter:
```yaml
global:
  admin:
    username: ""
    password: ""
    name: ""
    surname: ""
    email: ""
```

Be aware that you can always enable auto-provisioning of the users with JSON ID using the following parameter:
```yaml
authService:
  createUnknownUsers: "true"
  createUnknownRoles: "true"
```

### Hardening of the deployment

The deployment was hardened to be more secure and stable. The following changes were made for every container:
- running as non-root user
- running with read-only root filesystem
- specified default `securityContext`
- added configuration and default values for `livenessProbe`, `readinessProbe` and `startupProbe`
- added configuration for resource limits and requests

### Optional services

New optional services were added to the umbrella chart:
- Keycloak internal service
- Utils service

Keycloak internal service is disabled by default and can be enabled by setting the following values:
```yaml
global:
  keycloak:
    enabled: true
    # client secret must be set if keycloak is enabled
    clientSecret: ""
```

Utils service is disabled by default and can be enabled by setting the following values:

```yaml
utilsService:
  enabled: false
```

See the [ILM Helm chart 2.7.0 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.7.0) for more information.

## To 2.6.0

### ACME endpoint and trusted IPs

The API gateway sub-chart was updated to support ACME endpoint and trusted IPs.
Trusted IP addresses defines blocks that are known to send correct `X-Forwarded-*` headers which is important to generate correct URLs for the clients communicating with the platform behind gateway and proxy.

Trusted IP addresses can be configured in the API gateway dependency for the umbrella:
```yaml
apiGateway:
  trustedIps: ""
```

### Additional connector sub-charts

The Software Cryptography Provider connector was added as sub-chart to the umbrella chart.

When you enable new connector during upgrade, you need to register the connector manually in the platform:
```yaml
softwareCryptographyProvider:
  enabled: false
```

See the [ILM Helm chart 2.6.0 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.6.0) for more information.

## To 2.5.2

### Container image configuration

Configuration of container registry has changed. The new configuration is more flexible and allows to use multiple container registries, including configuration of registry globally.

Every image that is supported in the umbrella chart or sub-charts now has the following structure:
```yaml
image:
  # default registry name
  registry: hub.omnitrustregistry.com
  # default repository name
  repository: ilm/core
  # default image tag
  tag: "2.5.2"
  # the digest to be used instead of the tag, will override tag if specified
  digest: ""
  # default image pull policy
  pullPolicy: IfNotPresent
  # array of image pull secrets
  pullSecrets: []
```

Container registry and image pull secrets can be also configured globally for the umbrella chart and all of its sub-charts using global parameters, for example:
```yaml
global:
  image:
    # registry name
    registry: "harbor.ilm.online"
    # array of secret names
    pullSecrets:
      - harbor-registry-credentials
      - dockerhub-registry-credentials
```

### Additional connector sub-charts

The following sub-charts were added to support additional connectors as optional components:
- Cryptosense Discovery Provider
- Network Discovery Provider
- Keystore Entity Provider

When you enable new connector during upgrade, you need to register the connector manually in the platform:
```yaml
cryptosenseDiscoveryProvider:
  enabled: false

networkDiscoveryProvider:
  enabled: false

keystoreEntityProvider:
  enabled: false
```

See the [ILM Helm chart 2.5.2 release notes](https://github.com/OmniTrustILM/helm-charts/releases/tag/2.5.2) for more information.
