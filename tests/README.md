# Chart render contracts

Run `python3 -m unittest discover -s tests -p 'test_credential_secret_refs.py' -v` with Helm available and `tests/requirements.txt` installed. `HELM_BIN` can select a specific Helm binary. Tests use synthetic inputs and temporary local chart dependencies, without a cluster or registry credentials.

The normal CI suite checks existing-Secret key schemas, suppression, composition and registration behavior against the current charts. Release equivalence checks are opt-in: set `ILM_COMPATIBILITY_BASELINE` to the Git commit being preserved. These checks compare application versions, images and legacy rendered objects, allowing only changed package-version labels. Keeping this baseline explicit lets ordinary application upgrades proceed through CI.

`ILM_BASELINE_CHART_ARCHIVE` optionally supplies a retrieved public baseline archive for a hash-checked render comparison. It requires a compatible `ILM_COMPATIBILITY_BASELINE`. The historical archive check describes its pinned artifact; it is skipped in normal CI.
