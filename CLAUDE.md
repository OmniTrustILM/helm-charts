# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ILM Helm Charts repository for the ILM (OmniTrust ILM) certificate/trust lifecycle management platform. Contains 25+ Helm charts organized around an umbrella chart pattern. Repository: [OmniTrustILM/helm-charts](https://github.com/OmniTrustILM/helm-charts).

## Key Commands

### Linting
```bash
# Lint changed charts (requires chart-testing CLI: https://github.com/helm/chart-testing)
ct lint --target-branch main --check-version-increment=false

# Lint a specific chart with helm
helm lint charts/<chart-name>
```

### Dependency Management
```bash
# Update all chart dependencies (order matters: lib first, umbrella last)
./update-all-dependencies.sh

# Update a single chart's dependencies
helm dependency update charts/<chart-name> --skip-refresh
```

### Testing
```bash
# Run chart-testing install tests (requires a running Kubernetes cluster)
ct install --namespace chart-testing --target-branch main --excluded-charts ilm-lib

# Template a chart locally for inspection
helm template charts/<chart-name>
```

## Architecture

### Chart Hierarchy
- **`ilm-lib`** — Library chart providing shared helpers (image rendering, JDBC/connection string formatting, volume/secret utilities). All other charts depend on it.
- **`ilm`** — Umbrella chart that bundles all components. Optional subcharts are toggled via `condition` fields in `Chart.yaml` (e.g., `commonCredentialProvider.enabled`).
- **Individual charts** — Each service/connector/provider has its own chart in `charts/` and can be installed standalone.

### Dependency Order
`ilm-lib` → all subcharts (no inter-dependencies) → `ilm` umbrella (last). This order is enforced in `update-all-dependencies.sh` and the publish workflow.

### Library Helpers (ilm-lib)
All charts use helpers from `charts/ilm-lib/templates/`:
- `_images.yaml` — `ilm-lib.images.image` for image references, `ilm-lib.images.pullSecrets` for pull secrets
- `_util.yaml` — `ilm-lib.util.merge` for YAML merging, `ilm-lib.util.format.jdbcUrl` / `ilm-lib.util.format.netUrl` for DB connection strings
- `_volumes.yaml`, `_secrets.yaml`, `_persistence.yaml`, `_customizations.yaml`, `_tplvalues.yaml`, `_trusted-certificates-secret.yaml`

### Global Values Pattern
The umbrella chart cascades configuration to all subcharts via `global.*` values:
- `global.database.*` — PostgreSQL connection (host, port, name, credentials, pgBouncer toggle)
- `global.messaging.*` — RabbitMQ configuration (internal/external)
- `global.valkey.*` — Valkey/session caching (required when `replicaCount >= 2`)
- `global.keycloak.*` — Optional OIDC authentication
- `global.trusted.certificates` — CA certificate bundle
- `global.image.*` — Registry and pull secrets

Individual charts merge global and local values using `pluck` (e.g., `pluck "host" $.Values.global.database $.Values.database | compact | first`).

### Chart Template Pattern
Each application chart follows a consistent structure:
```
charts/<name>/
  Chart.yaml          # Depends on ilm-lib
  values.yaml
  templates/
    _helpers.tpl       # Chart-specific helpers wrapping ilm-lib
    <name>-deployment.yaml
    <name>-service.yaml
    <name>-secret.yaml
    trusted-certificates-secret.yaml
    rbac/
    tests/
```

## Versioning

- **Development:** `X.Y.Z-PATCH-develop` (e.g., `1.6.3-1-develop`) — required for PRs to main from non-release branches
- **Release:** `X.Y.Z-PATCH` (e.g., `1.6.3-1`) — required for PRs from `release*` branches and tag pushes
- CI enforces version format: develop suffix for branch pushes, no develop suffix for releases
- `--check-version-increment=false` is used with chart-testing (custom versioning scheme)

## CI/CD

- **PR checks** (`check_pr.yml`) — Detects changed charts, validates version format, runs linting
- **Testing** (`test_charts.yml`) — Dispatched after PR check; runs lint + install tests on KinD cluster with PostgreSQL 18 and mailserver services
- **Publishing** (`publish_charts.yml`) — On push to main or tag; packages, pushes to `oci://hub.omnitrustregistry.com/ilm-helm`, signs with Cosign
- Charts are published in dependency order; `ilm-lib` excluded from install tests (library chart)
- The `ilm` umbrella packages a frozen copy of every subchart, so a change to *any* chart also triggers the umbrella — even when `charts/ilm`'s own files are untouched. All three workflows detect this case (`umbrella_in_set`) and additionally lint the umbrella (`check_pr.yml`, `publish_charts.yml`), install-test it on KinD (`test_charts.yml`), and repackage + republish it (`publish_charts.yml`). This keeps the deployed umbrella artifact in sync with its subcharts (it would otherwise embed the pre-change copy)

## Development Notes

- Chart dependencies use `repository: file://../<chart-name>` for local development (commented-out OCI references show production registry)
- Test values for various deployment scenarios are in `for-testing/` and `charts/ilm/ci/`
- Dummy certificates in `dummy-certificates/` are included by default for dev/testing
- When adding a new chart, add it to `update-all-dependencies.sh` and if it's a subchart of the umbrella, add a dependency entry in `charts/ilm/Chart.yaml`
- Java packages still use `com.czertainly` namespace — the `LOGGING_LEVEL_COM_CZERTAINLY` env var in deployment templates is intentional and will be updated when Java code is refactored
