# Troubleshooting

## Timed out waiting for the condition

When the installation or upgrade fails with the following reason:
```bash
Error: INSTALLATION FAILED: failed post-install: timed out waiting for the condition
```
It is most probably because of reaching the default Helm timeout during deployment when Helm is trying to download all missing container images. This should not happen when you have all required container images already present on the target cluster.

If you are facing timeout issues, increase the Helm timeout using `--timeout` switch, for example:
```bash
helm install --namespace ilm -f ilm-values.yaml --set-file trusted.certificates=trusted-certificates.pem ilm-tlm oci://hub.omnitrustregistry.com/ilm-helm/ilm --timeout 1h
```

## It seems that I cannot log in with my generated administrator certificate

When you have installed the ILM using the auto-generated internal admin CA and issued administrator certificate for your registered administrator, it may happen that you override the list of trusted certificates and miss the create internal admin CA certificate. In this case, read the admin CA certificate, include it in the list of trusted certificates, and upgrade the configuration of the ILM. You can use the following command to get the admin CA certificate in PEM format in file `admin-ca-certificate.pem`:

```bash
kubectl get secrets --namespace ilm admin-ca-keypair -o jsonpath='{.data.tls\.crt}' | base64 --decode > admin-ca-certificate.pem
```

## Upgrade failed - invalid: spec.selector

When you are upgrading the ILM platform and get an error like:
```bash
UPGRADE FAILED: cannot patch "<deployment-name>" with kind Deployment: Deployment.apps "<deployment-name>" is invalid: spec.selector: Invalid value: {"matchLabels":{"app.kubernetes.io/instance":"<release-name>","app.kubernetes.io/name":"<new-value>"}}: field is immutable
```

The rendered selector value (`app.kubernetes.io/name`) has changed compared to the live Deployment. `spec.selector` is immutable in Kubernetes (see [Kubernetes Deployment - Selectors](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#selector)), so Helm cannot patch it in place.

The most common triggers are a chart rename, or a change to the chart's `nameOverride` default. The umbrella chart pins `nameOverride` to a stable identifier in its default values, and each sub-chart pins its own — so this error is not expected as long as those defaults are not modified or overridden at install time (for example via `--set nameOverride=...`).

Resolution is to delete the affected Deployment and re-run the upgrade — Helm will recreate it:

```bash
kubectl delete deployment <deployment-name> --namespace <your-ilm-namespace>
helm upgrade ...
```

There will be brief downtime while the new pods become ready. ILM is stateless at this layer, so no data is lost.

If you applied the rendered manifest out of band (e.g., `helm template ... | kubectl apply -f -`) instead of running `helm upgrade`, the same applies: delete the affected Deployment with `kubectl delete deployment <deployment-name>` before re-applying the manifest.

## Upgrade failed - ingress host/path conflict

When upgrading with `ingress.enabled: true`, you may get an error like:
```bash
UPGRADE FAILED: failed to create resource: admission webhook "validate.nginx.ingress.kubernetes.io" denied the request: host "<host>" and path "/" is already defined in ingress <namespace>/<old-ingress-name>
```

This happens when the rendered Ingress resource name has changed (so the new and old Ingress would briefly coexist), and the nginx Ingress admission webhook refuses to create the new one because it would duplicate the host and path of the still-existing old one.

Resolution is to delete the old Ingress before re-running the upgrade:

```bash
kubectl delete ingress <old-ingress-name> --namespace <your-ilm-namespace>
helm upgrade ...
```

The umbrella chart pins `nameOverride` to a stable identifier in its default values, which keeps the Ingress resource name stable across chart renames — so this error is not expected as long as `nameOverride` is not modified or overridden at install time.

If you applied the rendered manifest out of band (e.g., `helm template ... | kubectl apply -f -`) instead of running `helm upgrade`, the same applies: delete the old Ingress with `kubectl delete ingress <old-ingress-name>` before re-applying the manifest.
