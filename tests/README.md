# Chart render contracts

Run `python3 -m unittest discover -s tests -p 'test_*.py' -v` with Helm available and `tests/requirements.txt` installed. `HELM_BIN` can select a specific Helm binary. Tests use synthetic inputs and temporary chart dependencies, without a cluster or registry credentials. The local charts are copied from this repository; the MCP server chart, which is released from its own repository, is pulled anonymously from the registry at the version `charts/ilm/Chart.yaml` pins.

`MCP_SERVER_CHART` can name a checkout of the MCP server chart (the directory that holds its `Chart.yaml`) to render behavior that is not published yet. Its `Chart.yaml` version has to be the one `charts/ilm/Chart.yaml` pins, because Helm takes a chart for the dependency only then. The tests use a temporary copy of the checkout and leave it untouched.

`test_mcp.py` renders the ILM chart with the MCP server in both identity modes, and `test_mcp_realm.py` runs `charts/keycloak-internal/scripts/mcp_realm.py` against an in-process fake of Keycloak's Admin REST API, without a Keycloak.

The normal CI suite checks existing-Secret key schemas, suppression, composition and registration behavior against the current charts, and the optional MCP server dependency. Release equivalence checks are opt-in: set `ILM_COMPATIBILITY_BASELINE` to the Git commit being preserved. These checks compare application versions, images and legacy rendered objects, allowing only changed package-version labels. Keeping this baseline explicit lets ordinary application upgrades proceed through CI.

`ILM_BASELINE_CHART_ARCHIVE` optionally supplies a retrieved public baseline archive for a hash-checked render comparison. It requires a compatible `ILM_COMPATIBILITY_BASELINE`. The historical archive check describes its pinned artifact; it is skipped in normal CI.
