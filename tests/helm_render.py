"""Temporary, offline chart renders with deterministic synthetic inputs."""
import atexit
import base64
import copy
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE = os.environ.get('ILM_COMPATIBILITY_BASELINE')
ARCHIVE_SHA256 = '5a63c556841b4c920896ab59e82d3b7f3266325b162f21096b427a321dd1cb13'
HELM = os.environ.get('HELM_BIN', 'helm')
COMPONENTS = {
    'common-credential-provider': 'commonCredentialProvider',
    'ejbca-ng-connector': 'ejbcaNgConnector',
    'email-notification-provider': 'emailNotificationProvider',
    'webhook-notification-provider': 'webhookNotificationProvider',
    'keystore-entity-provider': 'keystoreEntityProvider',
    'network-discovery-provider': 'networkDiscoveryProvider',
    'software-cryptography-provider': 'softwareCryptographyProvider',
    'ct-logs-discovery-provider': 'ctLogsDiscoveryProvider',
    'hashicorp-vault-connector': 'hashicorpVaultConnector',
    'pyadcs-connector': 'pyAdcsConnector',
    'otpki-connector': 'otpkiConnector',
}


def synthetic_values(chart):
    values = {
        'global': {
            'database': {'host': 'db.example.invalid', 'port': 5432, 'name': 'testdb',
                         'username': 'testuser', 'password': 'SYNTHETIC_DB_PASSWORD'},
            'keycloak': {'enabled': True, 'clientSecret': 'SYNTHETIC_OAUTH_SECRET'},
            'admin': {'username': 'testadmin', 'password': 'SYNTHETIC_REALM_PASSWORD'},
            'messaging': {key: ('testuser' if key.endswith('Username') or key == 'username'
                               else 'SYNTHETIC_MQ_PASSWORD')
                          for key in ('username', 'password', 'coreUsername', 'corePassword',
                                      'proxyUsername', 'proxyPassword', 'provisionerUsername',
                                      'provisionerPassword', 'timeQualityMonitorUsername',
                                      'timeQualityMonitorPassword')},
        },
        'keycloak': {'admin': {'username': 'masteradmin', 'password': 'SYNTHETIC_MASTER_PASSWORD'}},
        'smtp': {'username': 'smtpuser', 'password': 'SYNTHETIC_SMTP_PASSWORD'},
        'otpki': {'loginPasswordKey': 'SYNTHETIC_OTPKI_KEY'},
        'messaging': {'erlang': {'cookie': 'SYNTHETIC_MQ_COOKIE'}},
    }
    if chart == 'ilm':
        for alias in COMPONENTS.values():
            values[alias] = {'enabled': True}
        values['keycloakInternal'] = {'keycloak': values.pop('keycloak')}
        values['emailNotificationProvider']['smtp'] = values.pop('smtp')
        values['otpkiConnector']['otpki'] = values.pop('otpki')
        values['messagingService'] = {'messaging': values.pop('messaging')}
        values['provisioningRabbitMq'] = {'enabled': False}
        values['registerAdmin'] = {'enabled': False}
    return values


@lru_cache(maxsize=2)
def _tree(baseline):
    tmp = tempfile.TemporaryDirectory(prefix='ilm-chart-render-')
    atexit.register(tmp.cleanup)
    destination = Path(tmp.name)
    if baseline:
        if not BASELINE:
            raise AssertionError('Set ILM_COMPATIBILITY_BASELINE for release equivalence checks')
        data = subprocess.check_output(['git', 'archive', BASELINE, 'charts'], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(destination, filter='data')
    else:
        shutil.copytree(ROOT / 'charts', destination / 'charts',
                        ignore=shutil.ignore_patterns('*.tgz'))
    return destination


@lru_cache(maxsize=None)
def _build(chart, baseline):
    path = _tree(baseline) / 'charts' / chart
    metadata = yaml.safe_load((path / 'Chart.yaml').read_text())
    for dependency in metadata.get('dependencies', []):
        repository = dependency.get('repository', '')
        if not repository.startswith('file://../'):
            raise AssertionError('Tests require local chart dependencies')
        source = _build(repository.removeprefix('file://../'), baseline)
        # Helm accepts unpacked dependencies. Use actual chart sources while
        # avoiding repeated compression and any registry access in render tests.
        shutil.copytree(source, path / 'charts' / dependency['name'], dirs_exist_ok=True)
    return path


def _render_path(path, values):
    with tempfile.TemporaryDirectory(prefix='ilm-synthetic-values-') as tmp:
        inputs = Path(tmp) / 'values.yaml'
        inputs.write_text(yaml.safe_dump(values))
        result = subprocess.run([HELM, 'template', 'czertainly-develop', str(path),
                                 '--namespace', 'czertainly-develop', '--kube-version', '1.30.14',
                                 '-f', str(inputs)], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [obj for obj in yaml.safe_load_all(result.stdout) if obj]


def render(chart, values, *, baseline=False):
    return _render_path(_build(chart, baseline), values)


def render_public_archive(values):
    source = Path(os.environ['ILM_BASELINE_CHART_ARCHIVE'])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == ARCHIVE_SHA256
    with tempfile.TemporaryDirectory(prefix='ilm-public-baseline-') as tmp:
        with tarfile.open(source) as archive:
            archive.extractall(tmp, filter='data')
        return _render_path(Path(tmp) / 'ilm', values)


def object_by_name(objects, kind, name):
    matching = [obj for obj in objects if obj['kind'] == kind and obj['metadata']['name'] == name]
    if len(matching) != 1:
        raise AssertionError(f'Expected one {kind}/{name}, found {len(matching)}')
    return matching[0]


def legacy_contract(objects):
    result = copy.deepcopy(objects)
    changed_names = set(COMPONENTS) | set(COMPONENTS.values()) | {
        'ilm', 'auth-service', 'authService', 'pg-bouncer', 'pgBouncer',
        'keycloak-internal', 'keycloakInternal', 'scheduler-service', 'schedulerService',
        'messaging-rabbitmq', 'messagingService', 'provisioning-rabbitmq', 'provisioningRabbitMq',
    }

    def normalize(value):
        if isinstance(value, dict):
            # Package labels on both resources and Pod templates change on a
            # chart-only release. Selectors and every other field are compared.
            labels = value.get('metadata', {}).get('labels', {})
            if any(labels.get('helm.sh/chart', '').startswith(name + '-') for name in changed_names):
                labels.pop('helm.sh/chart', None)
            for child in value.values():
                normalize(child)
        elif isinstance(value, list):
            for child in value:
                normalize(child)

    normalize(result)
    return sorted(result, key=lambda obj: (obj['kind'], obj['metadata']['name']))


def assert_no_credential_sentinels(testcase, objects, sentinels):
    text = json.dumps(objects, sort_keys=True)
    decoded = []
    for obj in objects:
        if obj['kind'] == 'Secret':
            decoded.extend(base64.b64decode(value).decode(errors='replace')
                           for value in obj.get('data', {}).values())
    for sentinel in sentinels:
        testcase.assertNotIn(sentinel, text)
        for value in decoded:
            testcase.assertNotIn(sentinel, value)
