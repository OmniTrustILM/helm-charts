# Chart Library - ILM

> This repository is part of the commercial open-source project ILM. You can find more information about the project at [ILM](https://github.com/OmniTrustILM/ilm) repository, including the contribution guide.

This repository contains [Helm](https://helm.sh/) library as part of the ILM platform.
The library groups the common logic that can be applied across all Helm charts.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+

## Using this Chart

**Include the library in `chart.yaml`**

Include the dependency into your target `chart.yaml`:
```yaml
dependencies:
  - name: ilm-lib
    version: 1.2.0
    repository: oci://hub.omnitrustregistry.com/ilm-helm/ilm-helm
```

**Update dependencies**

Once the dependency is configured, update chart dependencies to apply the changes
```bash
helm dependency update
```

## Templates

The following templates are available:

| Identifier                                             | Description                                                                                                                                               |
|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ilm-lib.trusted.certificates.secret.tpl`       | Template for the secret containing global additional trusted CA certificates applied for all sub-charts. The secret name is static `trusted-certificates` |
| `ilm-lib.trusted.certificates.secret.local.tpl` | Template for the secret containing local additional trusted CA certificates applied for all sub-charts                                                    |
| `ilm-lib.trusted.certificates.secret.global`    | Static template for the secret containing trusted certificates                                                                                            |

## Functions

The following functions are defined:

| Identifier                                         | Description                                                                      |
|----------------------------------------------------|----------------------------------------------------------------------------------|
| `ilm-lib.trusted.certificates.secret`       | Prepares the `trusted-certificates` secret                                       |
| `ilm-lib.trusted.certificates.secret.local` | Prepares local secret with additionally trusted certificates                     |
| `ilm-lib.util.merge`                        | Merge two templates to one yaml                                                  |
| `ilm-lib.util.format.jdbcUrl`               | Format the JDBC URL connection string based in the database configuration values |
| `ilm-lib.util.format.netUrl`                | Format the .NET URL connection string based in the database configuration values |

### Images

| Identifier                           | Description                                       |
|--------------------------------------|---------------------------------------------------|
| `ilm-lib.images.image`        | Prepares the image name from the image properties |
| `ilm-lib.images.pullSecrets`  | Prepares the image pull secret names              |

### Volumes

| Identifier                         | Description                                            |
|------------------------------------|--------------------------------------------------------|
| `ilm-lib.volumes.ephemeral` | Prepares the ephemeral volume for the read-only images |

### Secrets

| Identifier                                        | Description                                                                  |
|---------------------------------------------------|------------------------------------------------------------------------------|
| `ilm-lib.secrets.generate_static_password` | Return static password as a string that can be shared across multiple charts |

### Persistence

| Identifier                                 | Description                                           |
|--------------------------------------------|-------------------------------------------------------|
| `ilm-lib.persistence.spec.template` | Prepares the persistent volume claim dynamic template |

### Customizations

The following helper templates are used to render customizations (YAML templates for containers, volumes, etc.):

| Identifier                                          | Description                                           |
|-----------------------------------------------------|-------------------------------------------------------|
| `ilm-lib.customizations.render.yaml`         | Render template based on the YAML manifests           |
| `ilm-lib.customizations.render.configMapEnv` | Render `configMapRef` based on the list of configMaps |
| `ilm-lib.customizations.render.secretEnv`    | Render `secretRef` based on the list of secrets       |

### Templates

The following helper templates are used to render templates:

| Identifier                                 | Description                                                                                |
|--------------------------------------------|--------------------------------------------------------------------------------------------|
| `ilm-lib.tplvalues.render`          | Renders a value that contains template perhaps with scope if the scope is present          |
| `ilm-lib.tplvalues.merge`           | Merge a list of values that contains template after rendering them                         |
| `ilm-lib.tplvalues.merge-overwrite` | Merge a list of values that contains template after rendering them (with `mergeOverwrite`) |
