"""Render actual charts with fake inputs; no cluster access is required."""
import os
import copy
import subprocess
import yaml
import unittest

from helm_render import (
    BASELINE, COMPONENTS, ROOT, assert_no_credential_sentinels, legacy_contract, object_by_name, render,
    render_public_archive, synthetic_values,
)

BUNDLE_CONTRACTS = {
    'scheduler-service': {'JDBC_USERNAME': 'dbUsername', 'JDBC_PASSWORD': 'dbPassword'},
    'email-notification-provider': {'JDBC_USERNAME': 'dbUsername', 'JDBC_PASSWORD': 'dbPassword',
                                    'SMTP_USERNAME': 'smtpUsername', 'SMTP_PASSWORD': 'smtpPassword'},
    'webhook-notification-provider': {'JDBC_USERNAME': 'dbUsername', 'JDBC_PASSWORD': 'dbPassword'},
    'common-credential-provider': {'JDBC_USERNAME': 'username', 'JDBC_PASSWORD': 'password'},
    'ejbca-ng-connector': {'JDBC_USERNAME': 'username', 'JDBC_PASSWORD': 'password'},
    'keystore-entity-provider': {'JDBC_USERNAME': 'username', 'JDBC_PASSWORD': 'password'},
    'network-discovery-provider': {'JDBC_USERNAME': 'username', 'JDBC_PASSWORD': 'password'},
    'software-cryptography-provider': {'JDBC_USERNAME': 'username', 'JDBC_PASSWORD': 'password'},
    'ct-logs-discovery-provider': {'DATABASE_HOST': 'database_host', 'DATABASE_PORT': 'database_port',
                                   'DATABASE_NAME': 'database_name', 'DATABASE_USER': 'database_user',
                                   'DATABASE_PASSWORD': 'database_password'},
    'hashicorp-vault-connector': {'DATABASE_HOST': 'database_host', 'DATABASE_PORT': 'database_port',
                                  'DATABASE_NAME': 'database_name', 'DATABASE_USER': 'database_user',
                                  'DATABASE_PASSWORD': 'database_password'},
    'pyadcs-connector': {'DATABASE_HOST': 'database_host', 'DATABASE_PORT': 'database_port',
                         'DATABASE_NAME': 'database_name', 'DATABASE_USER': 'database_user',
                         'DATABASE_PASSWORD': 'database_password'},
    'otpki-connector': {'OTPKI_LOGIN_PASSWORD_KEY': 'login_password_key'},
}


class CredentialSecretReferences(unittest.TestCase):
    def env(self, workload, name):
        entries = [entry for container in workload['spec']['template']['spec']['containers']
                   for entry in container.get('env', []) if entry['name'] == name]
        self.assertEqual(len(entries), 1, name)
        return entries[0]

    def assert_ref(self, workload, env_name, secret_name, key):
        self.assertEqual(self.env(workload, env_name),
                         {'name': env_name, 'valueFrom': {'secretKeyRef': {'name': secret_name, 'key': key}}})

    def assert_no_secret(self, objects, name):
        self.assertFalse(any(obj['kind'] == 'Secret' and obj['metadata']['name'] == name
                             for obj in objects), name)

    def test_external_bundle_cannot_reuse_chart_managed_secret(self):
        # Reusing a generated name would remove that resource during Helm upgrade.
        contracts = [
            ('ilm', None, ('database', 'existingSecret'), 'core-secret'),
            ('auth-service', 'authService', ('database', 'existingSecret'), 'auth-secret'),
            ('pg-bouncer', 'pgBouncer', ('database', 'existingSecret'), 'pg-bouncer-secret'),
            ('keycloak-internal', 'keycloakInternal', ('existingSecret',), 'keycloak-internal-secret'),
            ('scheduler-service', 'schedulerService', ('existingSecret',), 'scheduler-service-secret'),
        ] + [(chart, COMPONENTS[chart], ('existingSecret',), chart + '-secret')
             for chart in BUNDLE_CONTRACTS if chart != 'scheduler-service']
        for chart, alias, path, name in contracts:
            for umbrella in (False, True):
                with self.subTest(chart=chart, umbrella=umbrella):
                    values = synthetic_values('ilm' if umbrella else chart)
                    target = values.setdefault(alias, {}) if umbrella and alias else values
                    for key in path[:-1]:
                        target = target.setdefault(key, {})
                    target[path[-1]] = name
                    with self.assertRaisesRegex(AssertionError, 'chart-managed'):
                        render('ilm' if umbrella else chart, values)

    def test_messaging_bundle_cannot_reuse_chart_managed_secret(self):
        for chart, local_name in [
            ('ilm', 'messaging-secret'),
            ('messaging-rabbitmq', 'messaging-secret-messaging-rabbitmq'),
            ('scheduler-service', 'messaging-secret-scheduler-service'),
            ('provisioning-rabbitmq', 'messaging-secret-provisioning-rabbitmq'),
        ]:
            for shared in (False, True):
                for name in {local_name, 'messaging-secret'}:
                    with self.subTest(chart=chart, shared=shared, name=name):
                        values = synthetic_values(chart)
                        values['global']['config'] = {'enabled': shared}
                        values['global']['messaging']['existingSecret'] = name
                        with self.assertRaisesRegex(AssertionError, 'chart-managed'):
                            render(chart, values)

    def test_local_messaging_bundle_cannot_reuse_chart_managed_secret(self):
        for chart, name in [
            ('ilm', 'messaging-secret'),
            ('messaging-rabbitmq', 'messaging-secret-messaging-rabbitmq'),
            ('scheduler-service', 'messaging-secret-scheduler-service'),
            ('provisioning-rabbitmq', 'messaging-secret-provisioning-rabbitmq'),
        ]:
            with self.subTest(chart=chart):
                values = synthetic_values(chart)
                values['global']['config'] = {'enabled': False}
                values.setdefault('messaging', {})['existingSecret'] = name
                with self.assertRaisesRegex(AssertionError, 'chart-managed'):
                    render(chart, values)

    @unittest.skipUnless(BASELINE, 'explicit release compatibility baseline')
    def test_legacy_render_matches_baseline(self):
        values = synthetic_values('ilm')
        self.assertEqual(legacy_contract(render('ilm', values)),
                         legacy_contract(render('ilm', values, baseline=True)))

    @unittest.skipUnless(BASELINE == '5b736cb7cfcc823c3255ec83b80e28748143131e', 'original legacy characterization')
    def test_baseline_has_no_core_external_secret_capability(self):
        values = synthetic_values('ilm')
        values['database'] = {'existingSecret': 'external-core-database'}
        objects = render('ilm', values, baseline=True)
        self.assertIn('jdbcPassword', object_by_name(objects, 'Secret', 'core-secret')['data'])

    @unittest.skipUnless(BASELINE and os.environ.get('ILM_BASELINE_CHART_ARCHIVE'), 'optional public archive and baseline')
    def test_public_archive_matches_fixed_git_baseline(self):
        values = synthetic_values('ilm')
        self.assertEqual(legacy_contract(render_public_archive(values)),
                         legacy_contract(render('ilm', values, baseline=True)))

    def test_core_external_database(self):
        values = synthetic_values('ilm')
        values['database'] = {'existingSecret': 'external-core-database'}
        objects = render('ilm', values)
        self.assert_no_secret(objects, 'core-secret')
        workload = object_by_name(objects, 'Deployment', 'core-deployment')
        self.assert_ref(workload, 'JDBC_USERNAME', 'external-core-database', 'jdbcUsername')
        self.assert_ref(workload, 'JDBC_PASSWORD', 'external-core-database', 'jdbcPassword')
        assert_no_credential_sentinels(self, [workload], ['SYNTHETIC_DB_PASSWORD'])

    def test_auth_complete_connection_string_reference(self):
        values = synthetic_values('auth-service')
        values['database'] = {'existingSecret': 'external-auth-database'}
        objects = render('auth-service', values)
        self.assert_no_secret(objects, 'auth-secret')
        workload = object_by_name(objects, 'Deployment', 'auth-deployment')
        self.assert_ref(workload, 'AUTH_DB_CONNECTION_STRING', 'external-auth-database', 'connection-string')
        self.assertNotIn('checksum/secret', workload['spec']['template']['metadata']['annotations'])

    def test_pgbouncer_external_userlist_projection(self):
        values = synthetic_values('pg-bouncer')
        values['database'] = {'existingSecret': 'external-pgbouncer-users'}
        objects = render('pg-bouncer', values)
        self.assert_no_secret(objects, 'pg-bouncer-secret')
        workload = object_by_name(objects, 'Deployment', 'pg-bouncer-deployment')
        sources = workload['spec']['template']['spec']['volumes'][0]['projected']['sources']
        self.assertEqual(sources[1]['secret'], {'name': 'external-pgbouncer-users',
                                              'items': [{'key': 'userlist.txt', 'path': 'userlist.txt'}]})
        annotations = workload['spec']['template']['metadata']['annotations']
        self.assertNotIn('checksum/secret', annotations)
        self.assertIn('checksum/config', annotations)

    def test_database_references_work_standalone_and_in_umbrella(self):
        for enabled in (True, False):
            with self.subTest(pgbouncer=enabled):
                values = synthetic_values('ilm')
                values['global']['database']['pgBouncer'] = {'enabled': enabled}
                values['authService'] = {'database': {'existingSecret': 'external-auth-database'}}
                values['pgBouncer'] = {'database': {'existingSecret': 'external-pgbouncer-users'}}
                objects = render('ilm', values)
                self.assert_no_secret(objects, 'auth-secret')
                self.assert_ref(object_by_name(objects, 'Deployment', 'auth-deployment'),
                                'AUTH_DB_CONNECTION_STRING', 'external-auth-database', 'connection-string')
                if enabled:
                    self.assert_no_secret(objects, 'pg-bouncer-secret')

    def test_keycloak_existing_secret_preserves_seven_keys(self):
        values = synthetic_values('keycloak-internal')
        values['existingSecret'] = 'external-keycloak-credentials'
        objects = render('keycloak-internal', values)
        self.assert_no_secret(objects, 'keycloak-internal-secret')
        workload = object_by_name(objects, 'Deployment', 'keycloak-internal-deployment')
        for env, key in [('KEYCLOAK_ADMIN', 'username'), ('KEYCLOAK_ADMIN_PASSWORD', 'password'),
                         ('KC_DB_USERNAME', 'database_user'), ('KC_DB_PASSWORD', 'database_password'),
                         ('PGHOST', 'database_host'), ('PGPORT', 'database_port'),
                         ('PGDATABASE', 'database_name'), ('PGUSER', 'database_user'),
                         ('PGPASSWORD', 'database_password')]:
            self.assert_ref(workload, env, 'external-keycloak-credentials', key)

    def test_realm_secret_keeps_schema_script(self):
        values = synthetic_values('keycloak-internal')
        values['realmImport'] = {'existingSecret': 'external-realm'}
        for schema in (True, False):
            with self.subTest(schema=schema):
                values['createDbSchema'] = schema
                objects = render('keycloak-internal', values)
                config = object_by_name(objects, 'ConfigMap', 'keycloak-internal-configmap')
                self.assertEqual(set(config['data']), {'create_schema.sh'})
                assert_no_credential_sentinels(self, [config], ['SYNTHETIC_REALM_PASSWORD', 'SYNTHETIC_OAUTH_SECRET'])
                workload = object_by_name(objects, 'Deployment', 'keycloak-internal-deployment')
                spec = workload['spec']['template']['spec']
                container = spec['containers'][0]
                self.assertEqual('lifecycle' in container, schema)
                self.assertIn({'name': 'keycloak-internal-configmap-volume',
                               'mountPath': '/opt/keycloak/create_schema.sh', 'subPath': 'create_schema.sh'},
                              container['volumeMounts'])

    def test_custom_realm_key_maps_to_fixed_import_path(self):
        values = synthetic_values('keycloak-internal')
        values['realmImport'] = {'existingSecret': 'external-realm', 'key': 'saved-realm.json'}
        workload = object_by_name(render('keycloak-internal', values), 'Deployment', 'keycloak-internal-deployment')
        spec = workload['spec']['template']['spec']
        self.assertIn({'name': 'keycloak-internal-realm-volume', 'secret': {
            'secretName': 'external-realm', 'items': [{'key': 'saved-realm.json', 'path': 'ilm_realm.json'}]}},
                      spec['volumes'])
        self.assertIn({'name': 'keycloak-internal-realm-volume', 'mountPath': '/opt/keycloak/data/import/ilm_realm.json',
                       'subPath': 'ilm_realm.json', 'readOnly': True}, spec['containers'][0]['volumeMounts'])

    def test_oauth_reference_overrides_inline(self):
        values = synthetic_values('ilm')
        values['global']['keycloak']['clientSecretRef'] = {'name': 'external-oauth', 'key': 'client-secret'}
        values['keycloakInternal']['realmImport'] = {'existingSecret': 'external-realm'}
        workload = object_by_name(render('ilm', values), 'Deployment', 'core-deployment')
        self.assert_ref(workload, 'INTERNAL_OAUTH_SECRET', 'external-oauth', 'client-secret')
        assert_no_credential_sentinels(self, [workload], ['SYNTHETIC_OAUTH_SECRET'])

    def test_partial_oauth_reference_fails(self):
        for ref in ({'name': 'external-oauth'}, {'key': 'client-secret'}, {'name': 1, 'key': 'secret'}, 'invalid'):
            with self.subTest(ref=ref):
                values = synthetic_values('ilm')
                values['global']['keycloak']['clientSecretRef'] = ref
                values['keycloakInternal']['realmImport'] = {'existingSecret': 'external-realm'}
                with self.assertRaisesRegex(AssertionError, 'clientSecretRef'):
                    render('ilm', values)

    def test_registration_false_removes_client_secret_and_preserves_admin_independence(self):
        for admin in (True, False):
            with self.subTest(admin=admin):
                values = synthetic_values('ilm')
                values['registerInternalKeycloak'] = False
                values['registerAdmin']['enabled'] = admin
                values['global']['keycloak']['clientSecretRef'] = {'name': 'external-oauth', 'key': 'client-secret'}
                values['keycloakInternal']['realmImport'] = {'existingSecret': 'external-realm'}
                objects = render('ilm', values)
                workload = object_by_name(objects, 'Deployment', 'core-deployment')
                self.assertFalse(any(entry['name'] == 'INTERNAL_OAUTH_SECRET'
                                     for container in workload['spec']['template']['spec']['containers']
                                     for entry in container.get('env', [])))
                self.assertTrue(any(obj['metadata']['name'] == 'keycloak-internal-deployment' for obj in objects))
                core = next(c for c in workload['spec']['template']['spec']['containers'] if c['name'] == 'core')
                self.assertEqual('lifecycle' in core, admin)
                scripts = [obj for obj in objects if obj['kind'] == 'ConfigMap'
                           and obj['metadata']['name'] == 'core-scripts-configmap']
                self.assertEqual(len(scripts), int(admin))
                if admin:
                    self.assertEqual(set(scripts[0]['data']), {'register-admin.sh'})
                    self.assertNotIn('register-internal-keycloak.sh', str(core['lifecycle']))

    def test_registration_false_removes_inline_client_secret(self):
        values = synthetic_values('ilm')
        values['registerInternalKeycloak'] = False
        workload = object_by_name(render('ilm', values), 'Deployment', 'core-deployment')
        self.assertFalse(any(entry['name'] == 'INTERNAL_OAUTH_SECRET'
                             for container in workload['spec']['template']['spec']['containers']
                             for entry in container.get('env', [])))
        assert_no_credential_sentinels(self, [workload], ['SYNTHETIC_OAUTH_SECRET'])

    def test_missing_registration_toggle_preserves_legacy_true(self):
        values = synthetic_values('ilm')
        scripts = object_by_name(render('ilm', values), 'ConfigMap', 'core-scripts-configmap')
        self.assertIn('register-internal-keycloak.sh', scripts['data'])
        values['global']['keycloak']['enabled'] = False
        self.assertFalse(any(obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'core-scripts-configmap'
                             for obj in render('ilm', values)))

    def test_component_external_bundle_contracts(self):
        for chart, mapping in BUNDLE_CONTRACTS.items():
            for populated in (True, False):
                with self.subTest(chart=chart, inline=populated):
                    values = synthetic_values(chart)
                    values['existingSecret'] = 'external-component-credentials'
                    if not populated:
                        values['global']['database']['password'] = ''
                        values['smtp']['password'] = ''
                        values['otpki']['loginPasswordKey'] = ''
                    objects = render(chart, values)
                    self.assert_no_secret(objects, chart + '-secret')
                    workload = object_by_name(objects, 'Deployment', chart + '-deployment')
                    for env, key in mapping.items():
                        self.assert_ref(workload, env, 'external-component-credentials', key)
                    if chart == 'scheduler-service':
                        self.assertNotIn('checksum/config', workload['spec']['template']['metadata'].get('annotations') or {})
                    if chart == 'otpki-connector':
                        self.assertNotIn('checksum/secret', workload['spec']['template']['metadata']['annotations'])
                    assert_no_credential_sentinels(self, [workload], ['SYNTHETIC_DB_PASSWORD',
                                                                    'SYNTHETIC_SMTP_PASSWORD', 'SYNTHETIC_OTPKI_KEY'])

    def test_email_database_and_smtp_are_external(self):
        values = synthetic_values('ilm')
        values['emailNotificationProvider']['existingSecret'] = 'external-email-credentials'
        objects = render('ilm', values)
        self.assert_no_secret(objects, 'email-notification-provider-secret')
        workload = object_by_name(objects, 'Deployment', 'email-notification-provider-deployment')
        for env, key in BUNDLE_CONTRACTS['email-notification-provider'].items():
            self.assert_ref(workload, env, 'external-email-credentials', key)

    def test_otpki_external_key_without_inline_password(self):
        for external, literal, expected in [('', '', False), ('', 'SYNTHETIC_OTPKI_KEY', True),
                                            ('external-otpki', '', True),
                                            ('external-otpki', 'SYNTHETIC_OTPKI_KEY', True)]:
            with self.subTest(external=external, literal=bool(literal)):
                values = synthetic_values('otpki-connector')
                values.update(existingSecret=external, otpki={'loginPasswordKey': literal})
                objects = render('otpki-connector', values)
                workload = object_by_name(objects, 'Deployment', 'otpki-connector-deployment')
                entries = workload['spec']['template']['spec']['containers'][0]['env']
                self.assertEqual(any(e['name'] == 'OTPKI_LOGIN_PASSWORD_KEY' for e in entries), expected)
                if external:
                    self.assert_ref(workload, 'OTPKI_LOGIN_PASSWORD_KEY', external, 'login_password_key')
                    self.assert_no_secret(objects, 'otpki-connector-secret')

    def test_software_cryptography_encryption_key_follows_bundle(self):
        for external, literal in [('', ''), ('', 'SYNTHETIC_ENCRYPTION_KEY'),
                                  ('external-softcp', ''), ('external-softcp', 'SYNTHETIC_ENCRYPTION_KEY')]:
            with self.subTest(external=external, literal=bool(literal)):
                values = synthetic_values('software-cryptography-provider')
                values.update(existingSecret=external, encryptionKey=literal)
                objects = render('software-cryptography-provider', values)
                workload = object_by_name(objects, 'Deployment', 'software-cryptography-provider-deployment')
                entries = [entry for entry in workload['spec']['template']['spec']['containers'][0]['env']
                           if entry['name'] == 'ENCRYPTION_KEY']
                if external:
                    self.assertEqual(entries, [{'name': 'ENCRYPTION_KEY', 'valueFrom': {'secretKeyRef': {
                        'name': external, 'key': 'encryption_key', 'optional': True}}}])
                    self.assert_no_secret(objects, 'software-cryptography-provider-secret')
                    assert_no_credential_sentinels(self, objects, ['SYNTHETIC_ENCRYPTION_KEY'])
                elif literal:
                    self.assert_ref(workload, 'ENCRYPTION_KEY', 'software-cryptography-provider-secret',
                                    'encryption_key')
                else:
                    self.assertEqual(entries, [])

    def test_unrelated_database_configuration_is_preserved(self):
        for chart, mapping in BUNDLE_CONTRACTS.items():
            with self.subTest(chart=chart):
                values = synthetic_values(chart)
                old = object_by_name(render(chart, values), 'Deployment', chart + '-deployment')
                values['existingSecret'] = 'external-component-credentials'
                new = object_by_name(render(chart, values), 'Deployment', chart + '-deployment')
                normalized = copy.deepcopy(new)
                for env in mapping:
                    self.env(normalized, env)['valueFrom']['secretKeyRef']['name'] = chart + '-secret'
                if chart in ('scheduler-service', 'otpki-connector'):
                    key = 'checksum/config' if chart == 'scheduler-service' else 'checksum/secret'
                    old['spec']['template']['metadata']['annotations'].pop(key)
                if chart == 'software-cryptography-provider':
                    # The only addition: the bundle's optional encryption_key, covered by its own test.
                    container = normalized['spec']['template']['spec']['containers'][0]
                    container['env'] = [entry for entry in container['env'] if entry['name'] != 'ENCRYPTION_KEY']
                for obj in (old, normalized):
                    metadata = obj['spec']['template']['metadata']
                    if not metadata.get('annotations'):
                        metadata.pop('annotations', None)
                self.assertEqual(legacy_contract([normalized]), legacy_contract([old]))

    def test_messaging_consumers_share_external_bundle(self):
        values = synthetic_values('ilm')
        values['global']['messaging']['existingSecret'] = 'external-messaging'
        values['messaging'] = {'existingSecret': 'local-shadow'}
        values['timeQualityMonitor'] = {'enabled': True}
        values['provisioningRabbitMq']['enabled'] = True
        objects = render('ilm', values)
        self.assert_no_secret(objects, 'messaging-secret')
        for workload, mapping in [
            ('core-deployment', {'BROKER_USERNAME': 'messaging.core.username', 'BROKER_PASSWORD': 'messaging.core.password'}),
            ('scheduler-service-deployment', {'BROKER_USERNAME': 'messaging.username', 'BROKER_PASSWORD': 'messaging.password'}),
            ('provisioning-rabbitmq-deployment', {'RABBITMQ_USERNAME': 'messaging.provisioner.username',
                                                'RABBITMQ_PASSWORD': 'messaging.provisioner.password',
                                                'PROXY_RABBITMQ_USERNAME': 'messaging.proxy.username',
                                                'PROXY_RABBITMQ_PASSWORD': 'messaging.proxy.password'})]:
            obj = object_by_name(objects, 'Deployment', workload)
            if workload == 'core-deployment':
                obj = copy.deepcopy(obj)
                obj['spec']['template']['spec']['containers'] = [c for c in obj['spec']['template']['spec']['containers']
                                                                if c['name'] == 'core']
            for env, key in mapping.items():
                self.assert_ref(obj, env, 'external-messaging', key)
        core = object_by_name(objects, 'Deployment', 'core-deployment')
        self.assertNotIn('checksum/mq-secret', core['spec']['template']['metadata']['annotations'])
        tqm = copy.deepcopy(core)
        tqm['spec']['template']['spec']['containers'] = [c for c in tqm['spec']['template']['spec']['containers']
                                                        if c['name'] == 'time-quality-monitor']
        self.assert_ref(tqm, 'BROKER_PASSWORD', 'external-messaging', 'messaging.time-quality-monitor.password')

    def test_standalone_messaging_ownership(self):
        for chart, workload, env, key in [
            ('messaging-rabbitmq', 'messaging-statefulset', 'RABBITMQ_DEFAULT_PASS', 'messaging.password'),
            ('scheduler-service', 'scheduler-service-deployment', 'BROKER_PASSWORD', 'messaging.password'),
            ('provisioning-rabbitmq', 'provisioning-rabbitmq-deployment', 'RABBITMQ_PASSWORD', 'messaging.provisioner.password')]:
            for global_config in (True, False):
                for global_name, expected in [('', 'local-messaging'), ('global-messaging', 'global-messaging')]:
                    with self.subTest(chart=chart, config=global_config, global_name=global_name):
                        values = synthetic_values(chart)
                        values['global']['config'] = {'enabled': global_config}
                        values['global']['messaging']['existingSecret'] = global_name
                        values['messaging']['existingSecret'] = 'local-messaging'
                        if global_config and not global_name:
                            with self.assertRaisesRegex(AssertionError, 'global.messaging.existingSecret'):
                                render(chart, values)
                            continue
                        objects = render(chart, values)
                        self.assertFalse(any(o['kind'] == 'Secret' and o['metadata']['name'].startswith('messaging-secret')
                                             for o in objects))
                        obj = object_by_name(objects, 'StatefulSet' if chart == 'messaging-rabbitmq' else 'Deployment', workload)
                        self.assert_ref(obj, env, expected, key)

    def test_rabbitmq_definition_and_cookie_refs(self):
        values = synthetic_values('messaging-rabbitmq')
        values['global']['messaging']['existingSecret'] = 'external-messaging'
        legacy_values = copy.deepcopy(values)
        legacy_values['global']['messaging'].pop('existingSecret')
        old = object_by_name(render('messaging-rabbitmq', legacy_values), 'StatefulSet', 'messaging-statefulset')
        workload = object_by_name(render('messaging-rabbitmq', values), 'StatefulSet', 'messaging-statefulset')
        self.assert_ref(workload, 'RABBITMQ_ERLANG_COOKIE', 'external-messaging', 'messaging.cookie')
        volumes = workload['spec']['template']['spec']['volumes']
        definition = next(v['secret'] for v in volumes if v.get('secret'))
        self.assertEqual(definition['secretName'], 'external-messaging')
        self.assertEqual(definition['items'], [{'key': 'messaging.definitions.json', 'path': 'definitions.json'}])
        self.assertNotIn('checksum/secret', workload['spec']['template']['metadata']['annotations'])
        self.assertEqual(workload['spec']['volumeClaimTemplates'], old['spec']['volumeClaimTemplates'])
        self.assertEqual(workload['spec']['template']['metadata']['annotations']['checksum/config'],
                         old['spec']['template']['metadata']['annotations']['checksum/config'])

    def test_rabbitmq_helm_test_uses_secret_env(self):
        values = synthetic_values('ilm')
        values['global']['messaging']['existingSecret'] = 'external-messaging'
        pod = object_by_name(render('ilm', values), 'Pod', 'czertainly-develop-messaging-service-test-connection')
        container = pod['spec']['containers'][0]
        self.assertEqual(container['env'], [
            {'name': 'RABBITMQ_TEST_USER', 'valueFrom': {'secretKeyRef': {'name': 'external-messaging', 'key': 'messaging.username'}}},
            {'name': 'RABBITMQ_TEST_PASSWORD', 'valueFrom': {'secretKeyRef': {'name': 'external-messaging', 'key': 'messaging.password'}}},
        ])
        self.assertIn('"${RABBITMQ_TEST_USER}:${RABBITMQ_TEST_PASSWORD}"', container['command'][2])
        assert_no_credential_sentinels(self, [pod], ['SYNTHETIC_MQ_PASSWORD'])

    def test_messaging_reference_wins_without_credential_literals(self):
        for populated in (True, False):
            values = synthetic_values('ilm')
            if not populated:
                values['global']['messaging'] = {}
                values['messagingService']['messaging']['erlang']['cookie'] = ''
            values['global']['messaging']['existingSecret'] = 'external-messaging'
            objects = render('ilm', values)
            assert_no_credential_sentinels(self, objects, ['SYNTHETIC_MQ_PASSWORD', 'SYNTHETIC_MQ_COOKIE'])

    def external_profile(self):
        values = synthetic_values('ilm')
        values['database'] = {'existingSecret': 'external-core'}
        values['authService'] = {'database': {'existingSecret': 'external-auth'}}
        values['pgBouncer'] = {'database': {'existingSecret': 'external-pgbouncer'}}
        values['keycloakInternal'].update(existingSecret='external-keycloak',
                                         realmImport={'existingSecret': 'external-realm'})
        values['global']['keycloak']['clientSecretRef'] = {'name': 'external-oauth', 'key': 'client-secret'}
        values['global']['messaging']['existingSecret'] = 'external-messaging'
        values['schedulerService'] = {'existingSecret': 'external-scheduler'}
        for alias in COMPONENTS.values():
            values[alias]['existingSecret'] = 'external-' + alias.lower()
        values.update(registerConnectors=False, registerInternalKeycloak=False)
        return values

    def test_full_external_umbrella_has_no_credential_outputs(self):
        objects = render('ilm', self.external_profile())
        assert_no_credential_sentinels(self, objects, ['SYNTHETIC_DB_PASSWORD', 'SYNTHETIC_OAUTH_SECRET',
                                                      'SYNTHETIC_REALM_PASSWORD', 'SYNTHETIC_MASTER_PASSWORD',
                                                      'SYNTHETIC_SMTP_PASSWORD', 'SYNTHETIC_OTPKI_KEY',
                                                      'SYNTHETIC_MQ_PASSWORD', 'SYNTHETIC_MQ_COOKIE'])
        secrets = [obj for obj in objects if obj['kind'] == 'Secret']
        self.assertEqual([(obj['metadata']['name'], set(obj.get('data', {}))) for obj in secrets],
                         [('trusted-certificates', {'ca.crt'})])
        config = object_by_name(objects, 'ConfigMap', 'keycloak-internal-configmap')
        self.assertNotIn('ilm_realm.json', config['data'])

    def test_registration_suppression_profile(self):
        objects = render('ilm', self.external_profile())
        self.assertFalse(any(obj['kind'] == 'Job' for obj in objects))
        core = object_by_name(objects, 'Deployment', 'core-deployment')
        container = next(c for c in core['spec']['template']['spec']['containers'] if c['name'] == 'core')
        self.assertNotIn('lifecycle', container)
        self.assertFalse(any(obj['kind'] == 'ConfigMap' and obj['metadata']['name'] == 'core-scripts-configmap'
                             for obj in objects))

    @unittest.skipUnless(BASELINE, 'explicit release compatibility baseline')
    def test_application_versions_and_images_unchanged(self):
        for path in (ROOT / 'charts').glob('*/Chart.yaml'):
            old = yaml.safe_load(subprocess.check_output(['git', 'show', f'{BASELINE}:{path.relative_to(ROOT)}'], cwd=ROOT))
            self.assertEqual(yaml.safe_load(path.read_text()).get('appVersion'), old.get('appVersion'), path.parent.name)
        def images(objects):
            result = {}
            for obj in objects:
                if obj['kind'] in ('Deployment', 'StatefulSet'):
                    spec = obj['spec']['template']['spec']
                elif obj['kind'] in ('Pod', 'Job'):
                    spec = obj['spec'] if obj['kind'] == 'Pod' else obj['spec']['template']['spec']
                else:
                    continue
                for container in spec.get('containers', []) + spec.get('initContainers', []):
                    result[(obj['kind'], obj['metadata']['name'], container['name'])] = container['image']
            return result
        values = synthetic_values('ilm')
        self.assertEqual(images(render('ilm', values)), images(render('ilm', values, baseline=True)))

    def test_dependency_pins_match_packages(self):
        for path in (ROOT / 'charts').glob('*/Chart.yaml'):
            for dependency in yaml.safe_load(path.read_text()).get('dependencies', []):
                repository = dependency.get('repository', '')
                if repository.startswith('file://'):
                    target = path.parent / repository.removeprefix('file://') / 'Chart.yaml'
                    self.assertEqual(dependency['version'], yaml.safe_load(target.read_text())['version'],
                                     (path.parent.name, dependency['name']))

    def test_composed_local_messaging_reference_requires_global_bundle(self):
        for chart in ('ilm', 'scheduler-service', 'provisioning-rabbitmq'):
            with self.subTest(chart=chart):
                values = synthetic_values(chart)
                if chart == 'ilm':
                    values['messaging'] = {}
                values['messaging'].update(local=True, existingSecret='local-messaging')
                with self.assertRaisesRegex(AssertionError, 'global.messaging.existingSecret'):
                    render(chart, values)
                values['global']['messaging']['existingSecret'] = 'shared-messaging'
                objects = render(chart, values)
                if chart == 'ilm':
                    self.assert_ref(object_by_name(objects, 'Deployment', 'scheduler-service-deployment'),
                                    'BROKER_PASSWORD', 'shared-messaging', 'messaging.password')
                self.assert_ref(object_by_name(objects, 'StatefulSet', 'messaging-statefulset'),
                                'RABBITMQ_DEFAULT_PASS', 'shared-messaging', 'messaging.password')

    def test_shared_child_messaging_requires_global_bundle(self):
        for chart, alias in [('messaging-rabbitmq', 'messagingService'),
                             ('scheduler-service', 'schedulerService'),
                             ('provisioning-rabbitmq', 'provisioningRabbitMq')]:
            with self.subTest(chart=chart, mode='standalone'):
                values = synthetic_values(chart)
                values['global']['config'] = {'enabled': True}
                values['messaging']['existingSecret'] = 'local-messaging'
                with self.assertRaisesRegex(AssertionError, 'global.messaging.existingSecret'):
                    render(chart, values)
            with self.subTest(chart=chart, mode='umbrella'):
                values = synthetic_values('ilm')
                values.setdefault(alias, {}).update(enabled=True)
                values[alias].setdefault('messaging', {})['existingSecret'] = 'local-messaging'
                with self.assertRaisesRegex(AssertionError, 'global.messaging.existingSecret'):
                    render('ilm', values)

    def test_oauth_reference_requires_external_realm_input(self):
        for chart in ('ilm', 'keycloak-internal'):
            with self.subTest(chart=chart):
                values = synthetic_values(chart)
                values['global']['keycloak']['clientSecretRef'] = {'name': 'external-oauth', 'key': 'client-secret'}
                with self.assertRaisesRegex(AssertionError, 'realmImport.existingSecret'):
                    render(chart, values)


if __name__ == '__main__':
    unittest.main()
