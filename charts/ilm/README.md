# ILM-Helm-Charts

> This repository is part of the commercial open-source project ILM. You can find more information about the project at [ILM](https://github.com/OmniTrustILM/ilm) repository, including the contribution guide.

This repository contains [Helm](https://helm.sh/) charts as part of the ILM platform.

## Resources

- [Overview](./docs/overview.md)
- [Configurable parameters](./docs/configurable-parameters.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Upgrading](./docs/upgrading.md)

## Existing credential Secrets

Optional namespace-local Secret references preserve current credential key schemas and suppress the matching generated credential resources. See [Existing credential bundles](docs/configurable-parameters.md#existing-credential-bundles) for per-component names, complete messaging/realm inputs and independent registration controls. Prepare existing bundles before workload synchronization. Empty options preserve legacy behavior; external Secret changes require an explicit rollout.
