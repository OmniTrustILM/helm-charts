# Overview

Helm chart simplifies the deployment of the platform using already pre-defined templates that are parsed as Kubernetes manifests and managed by Helm.

## Prerequisites
- Kubernetes 1.19+
- Helm 3.8.0+
- PostgreSQL 12+
- PV provisioner support in the underlying infrastructure

In case you want to enable Ingress you need to have installed Ingress Controller, for example:
```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.7.0/deploy/static/provider/cloud/deploy.yaml
```

If you are using internal CA for Ingress and Administrator certificate, you also need to have installed [cert-manager](https://cert-manager.io/docs/).

> cert-manager is only required to use certificates issued by internally generated CA:
> - `ingress.certificate.source=internal` for internally generated Ingress certificate
> - `ingress.certificate.source=letsEncrypt` for Ingress Let’s Encrypt issued certificate
> - `registerAdmin.source=generated` for internally generated certificate for first administrator

## Using this Chart

### Installation

**Create namespace**

We’ll need to define a Kubernetes namespace where the resources created by the Chart should be installed:
```bash
kubectl create namespace ilm
```

**Create `ilm-values.yaml`**

Copy the default `values.yaml` from the ILM Helm chart and modify the values accordingly:
```bash
helm show values oci://hub.omnitrustregistry.com/ilm-helm/ilm > ilm-values.yaml
```
Now edit the `ilm-values.yaml` according to your desired stated, see [Configurable parameters](./configurable-parameters.md) for more information.

**Prepare list of trusted CA certificates**

Create new file called `trusted-certificates.pem` and add to the file PEM certificates of all certification authorities that should be trusted by the platform. No worries, you can always change the list of trusted certificates in the future.

The list of trusted certificates is need for the installation of the ILM using Helm chart.

> **Note**
> Trusted certificates can be defined globally for the ILM chart and all of its sub-charts, or it can be applied only for specific sub-chart, see [global parameters](./configurable-parameters.md#global-parameters). For global, set `global.trusted.certificates`, otherwise set `trusted.certificates`.

**Install ILM**

There are couple of options to install ILM based on you TLS configuration and administrator certificate handling. See the [Configurable parameters](./configurable-parameters.md) for more information.

For the basic installation, run:
```bash
helm install --namespace ilm -f ilm-values.yaml --set-file global.trusted.certificates=trusted-certificates.pem ilm-tlm oci://hub.omnitrustregistry.com/ilm-helm/ilm
```

**Save your configuration**

Always make sure you save the `ilm-values.yaml` and all `--set` and `--set-file` options you used. You will need to use the same options when you upgrade ILM to new versions with Helm. In case you are changing the configuration, save the new configuration.

### Upgrade

> **Warning**
> Be sure that you always save your previous configuration!

For upgrading the ILM installation, update your configuration and run:
```bash
helm upgrade --namespace ilm -f ilm-values.yaml --set-file global.trusted.certificates=trusted-certificates.pem ilm-tlm oci://hub.omnitrustregistry.com/ilm-helm/ilm
```

### Uninstall

You can use the `helm uninstall` command to uninstall the ILM:
```bash
helm uninstall --namespace ilm ilm-tlm
```

:::info[Helm chart]
See [ILM-Helm-Charts](https://github.com/OmniTrustILM/helm-charts) for description of all charts and sub-charts that are available for the platform.
:::

## High Availability

ILM supports High Availability (HA) deployments by running multiple replicas of the Core service. Set `global.replicaCount` to the desired number of replicas.

Per-instance AMQP queues handle response distribution across replicas — no additional caching infrastructure is required.

If you need stable per-pod identities for proxy queue provisioning, set `workloadType=StatefulSet`. The default `Deployment` mode remains suitable for the existing single-workload behavior.

## Persistence

Internal services can use Persistence Volume Claims to store the data. The PVC is created dynamically by default, but different behaviour can be configured.

The following sub-charts requires persistence:

- [Messaging RabbitMQ](../../messaging-rabbitmq)
