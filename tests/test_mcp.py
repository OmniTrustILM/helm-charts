"""Render the ILM chart with the MCP server dependency and fake inputs; no cluster access is required."""
import base64
import copy
import json
import re
import unittest
import uuid

import yaml

from helm_render import assert_no_credential_sentinels, object_by_name, render, synthetic_values

MCP_DEPLOYMENT = 'czertainly-develop-mcp-server'
PROVIDER = {
    'issuer': 'https://identity.example.invalid/tenant',
    'jwkSetUri': 'https://identity.example.invalid/oauth/jwks',
    'tokenUri': 'https://identity.example.invalid/oauth/token',
    'clientId': 'ilm-mcp-exchange',
    'clientSecretRef': {'name': 'mcp-idp-client'},
    'exchangeMode': 'standard',
}
GROUP = 'ilm-mcp-users'
# delegation:client as measured on Keycloak 26.8.1 with the cimd, token-exchange-delegation and parameterized-scopes
# features.
DELEGATION_CLIENT = {
    'name': 'delegation:client',
    'description': 'OpenID Connect scope for agent/client token exchange delegation',
    'protocol': 'openid-connect',
    'attributes': {
        'include.in.token.scope': 'true', 'parameterized.scope.type': 'client-delegation',
        'display.on.consent.screen': 'true', 'always.display.consent': 'true', 'is.parameterized.scope': 'true',
        'consent.screen.text': '${clientDelegationScopeConsentText}'},
    'protocolMappers': [
        {'name': 'client delegation audience', 'protocol': 'openid-connect',
         'protocolMapper': 'oidc-parameterized-scope-audience-mapper', 'consentRequired': False,
         'config': {'introspection.token.claim': 'true', 'access.token.claim': 'true'}},
        {'name': 'client may_act client_id', 'protocol': 'openid-connect',
         'protocolMapper': 'oidc-parameterized-scope-mapper', 'consentRequired': False,
         'config': {'id.token.claim': 'true', 'introspection.token.claim': 'true', 'access.token.claim': 'true',
                    'claim.name': 'may_act.client_id', 'jsonType.label': 'String', 'userinfo.token.claim': 'true'}},
        {'name': 'client may_act sub', 'protocol': 'openid-connect',
         'protocolMapper': 'oidc-parameterized-scope-client-sub-mapper', 'consentRequired': False,
         'config': {'id.token.claim': 'true', 'introspection.token.claim': 'true', 'access.token.claim': 'true',
                    'claim.name': 'may_act.sub', 'jsonType.label': 'String', 'userinfo.token.claim': 'true'}},
    ],
}
DELEGATING_CLIENT_POLICY = {'name': 'ilm-mcp-delegating-client', 'type': 'client', 'logic': 'POSITIVE',
                            'decisionStrategy': 'UNANIMOUS', 'config': {'clients': '["ilm-mcp"]'}}


def mcp_values(mode='managed'):
    values = synthetic_values('ilm')
    values['global'].update(hostName='ilm.example.invalid')
    values['global']['keycloak']['enabled'] = True
    values['global']['mcp'] = {'enabled': True, 'identity': {'mode': mode}}
    if mode == 'managed':
        values['global']['mcp']['clientSecret'] = 'SYNTHETIC_MCP_SECRET'
    else:
        values['mcpServer'] = {'security': copy.deepcopy(PROVIDER)}
    return values


def mcp_reference_values(ref):
    values = mcp_values()
    del values['global']['mcp']['clientSecret']
    values['global']['mcp']['clientSecretRef'] = ref
    values['keycloakInternal']['realmImport'] = {'existingSecret': 'external-realm'}
    return values


def mcp_external_inline_values():
    """External mode whose client secret is global.mcp.clientSecret, not a Secret that the provider's settings name."""
    values = mcp_values('external')
    del values['mcpServer']['security']['clientSecretRef']
    values['global']['mcp']['clientSecret'] = 'SYNTHETIC_MCP_SECRET'
    return values


def pod_template(objects, workload):
    return object_by_name(objects, 'Deployment', workload)['spec']['template']


def kong_config(objects, configmap='global-configmap'):
    return yaml.safe_load(object_by_name(objects, 'ConfigMap', configmap)['data']['kong.yml'])


def kong_services(objects, configmap='global-configmap'):
    return {service['name']: service for service in kong_config(objects, configmap)['services']}


def realm(objects):
    return json.loads(object_by_name(objects, 'ConfigMap', 'keycloak-internal-configmap')['data']['ilm_realm.json'])


def realm_with(values, **mcp):
    values['global']['mcp'].update(mcp)
    return realm(render('ilm', values))


def by_name(entries, key='name'):
    return {entry[key]: entry for entry in entries}


def audiences(scope):
    return sorted(mapper['config'].get('included.client.audience') or mapper['config']['included.custom.audience']
                  for mapper in scope['protocolMappers'] if mapper['protocolMapper'] == 'oidc-audience-mapper'
                  and mapper['config']['access.token.claim'] == 'true')


def delegation_permission(name, resource_type, resource, scope):
    """The FGAP v2 permission that lets ilm-mcp act for the users of one resource."""
    return {'name': name, 'type': 'scope', 'logic': 'POSITIVE', 'decisionStrategy': 'UNANIMOUS',
            'config': {'defaultResourceType': resource_type, 'resources': json.dumps([resource]),
                       'scopes': json.dumps([scope]), 'applyPolicies': '["ilm-mcp-delegating-client"]'}}


def registration_body(objects):
    script = object_by_name(objects, 'ConfigMap', 'core-scripts-configmap')['data']['register-internal-keycloak.sh']
    body = re.search(r"-d '(.*?)' \\\n", script, re.S).group(1)
    # The script splices the client secret into the JSON between shell quotes; a placeholder keeps it parseable.
    return json.loads(body.replace("'\"$CLIENT_SECRET\"'", 'CLIENT_SECRET'))


def registration_with(values, **mcp):
    values['global']['mcp'].update(mcp)
    return registration_body(render('ilm', values))


class McpUmbrella(unittest.TestCase):
    def env(self, workload, name):
        entries = [entry for entry in workload['spec']['template']['spec']['containers'][0]['env']
                   if entry['name'] == name]
        self.assertEqual(len(entries), 1, name)
        return entries[0]

    def assert_env_values(self, workload, expected):
        for name, value in expected.items():
            self.assertEqual(self.env(workload, name), {'name': name, 'value': value}, name)

    def assert_includes(self, mapping, expected):
        self.assertEqual({key: mapping.get(key) for key in expected}, expected)

    def assert_no_delegate(self, registration):
        self.assertEqual(registration.keys() & {'allowedDelegates', 'delegateClaim'}, set())

    def secret_names(self, objects):
        return [obj['metadata']['name'] for obj in objects if obj['kind'] == 'Secret']

    def kong_mcp_service(self, values):
        services = kong_services(render('ilm', values))
        self.assertIn('mcp-server-service', services)
        return services['mcp-server-service']

    def test_mcp_is_off_by_default_and_adds_nothing(self):
        objects = render('ilm', synthetic_values('ilm'))
        self.assertEqual([obj['metadata']['name'] for obj in objects if 'mcp-server' in obj['metadata']['name']], [])
        self.assertNotIn('mcp-server-secret', self.secret_names(objects))
        self.assertNotIn('mcp-server-service', kong_services(objects))
        registration = registration_body(objects)
        platform = json.dumps([kong_config(objects), realm(objects), registration])
        self.assertNotIn('mcp', platform.lower())
        self.assert_no_delegate(registration)
        settings_only = realm_with(mcp_values(), enabled=False, delegation={'group': GROUP})
        self.assertNotIn('ilm-mcp', json.dumps(settings_only))

    def test_mcp_on_renders_the_delegation_workload(self):
        objects = render('ilm', mcp_values())
        workload = object_by_name(objects, 'Deployment', MCP_DEPLOYMENT)
        self.assert_env_values(workload, {
            'ILM_MCP_SECURITY_EXCHANGE_MODE': 'delegation',
            'ILM_MCP_SECURITY_EXCHANGE_SCOPE': 'openid ilm-mcp-upstream',
            'ILM_MCP_SECURITY_AUTHORIZATION_SCOPES': 'openid,delegation:client:ilm-mcp',
            'ILM_MCP_SECURITY_ALLOW_HTTP_BACKCHANNEL': 'true',
            'ILM_API_URL': 'http://core-service:8080/api',
            'ILM_MCP_SECURITY_RESOURCE': 'https://ilm.example.invalid/mcp',
            'ILM_MCP_SECURITY_ISSUER': 'https://ilm.example.invalid/kc/realms/ILM',
            'ILM_MCP_SECURITY_CLIENT_ID': 'ilm-mcp',
        })
        service = object_by_name(objects, 'Service', 'mcp-server-service')
        self.assertEqual([port['port'] for port in service['spec']['ports']], [8080])
        secret = object_by_name(objects, 'Secret', 'mcp-server-secret')
        self.assertEqual({key: base64.b64decode(value).decode() for key, value in secret['data'].items()},
                         {'client-secret': 'SYNTHETIC_MCP_SECRET'})
        self.assertEqual(self.env(workload, 'ILM_MCP_SECURITY_CLIENT_SECRET'), {
            'name': 'ILM_MCP_SECURITY_CLIENT_SECRET',
            'valueFrom': {'secretKeyRef': {'name': 'mcp-server-secret', 'key': 'client-secret'}}})
        # The realm import carries the client secret of ilm-mcp, as it does that of ILM's own client.
        realm_import = object_by_name(objects, 'ConfigMap', 'keycloak-internal-configmap')
        assert_no_credential_sentinels(self, [obj for obj in objects if obj is not secret and obj is not realm_import],
                                       ['SYNTHETIC_MCP_SECRET'])
        self.assertFalse(any(obj['kind'] == 'NetworkPolicy' for obj in objects))

    def test_mcp_external_renders_the_provider(self):
        objects = render('ilm', mcp_values('external'))
        workload = object_by_name(objects, 'Deployment', MCP_DEPLOYMENT)
        self.assert_env_values(workload, {
            'ILM_MCP_SECURITY_ISSUER': PROVIDER['issuer'],
            'ILM_MCP_SECURITY_JWK_SET_URI': PROVIDER['jwkSetUri'],
            'ILM_MCP_SECURITY_TOKEN_URI': PROVIDER['tokenUri'],
            'ILM_MCP_SECURITY_CLIENT_ID': PROVIDER['clientId'],
            'ILM_MCP_SECURITY_EXCHANGE_MODE': 'standard',
            'ILM_MCP_SECURITY_EXCHANGE_SCOPE': '',
            'ILM_MCP_SECURITY_AUTHORIZATION_SCOPES': '',
            'ILM_API_URL': 'http://core-service:8080/api',
            'ILM_MCP_SECURITY_RESOURCE': 'https://ilm.example.invalid/mcp',
        })
        self.assertEqual(self.env(workload, 'ILM_MCP_SECURITY_CLIENT_SECRET')['valueFrom']['secretKeyRef'],
                         {'name': 'mcp-idp-client', 'key': 'client-secret'})
        self.assertNotIn('mcp-server-secret', self.secret_names(objects))
        self.assertNotIn('checksum/client-secret', workload['spec']['template']['metadata'].get('annotations', {}))

    def test_mcp_external_inline_secret(self):
        objects = render('ilm', mcp_external_inline_values())
        workload = object_by_name(objects, 'Deployment', MCP_DEPLOYMENT)
        secret = object_by_name(objects, 'Secret', 'mcp-server-secret')
        self.assertEqual({key: base64.b64decode(value).decode() for key, value in secret['data'].items()},
                         {'client-secret': 'SYNTHETIC_MCP_SECRET'})
        self.assertEqual(self.env(workload, 'ILM_MCP_SECURITY_CLIENT_SECRET')['valueFrom']['secretKeyRef'],
                         {'name': 'mcp-server-secret', 'key': 'client-secret'})
        self.assertIn('checksum/client-secret', workload['spec']['template']['metadata']['annotations'])
        self.assert_env_values(workload, {'ILM_MCP_SECURITY_ISSUER': PROVIDER['issuer'],
                                          'ILM_MCP_SECURITY_CLIENT_ID': PROVIDER['clientId']})
        # Nothing else carries the secret, the bundled Keycloak's realm import included.
        assert_no_credential_sentinels(self, [obj for obj in objects if obj is not secret], ['SYNTHETIC_MCP_SECRET'])

    def test_mcp_secret_needs_exactly_one_source(self):
        neither = mcp_values()
        del neither['global']['mcp']['clientSecret']
        both = mcp_reference_values({'name': 'external-mcp', 'key': 'client-secret'})
        both['global']['mcp']['clientSecret'] = 'SYNTHETIC_MCP_SECRET'
        for name, values in [('neither', neither), ('both', both)]:
            with self.subTest(sources=name):
                with self.assertRaisesRegex(AssertionError,
                                            'exactly one of global.mcp.clientSecret and global.mcp.clientSecretRef'):
                    render('ilm', values)

    def test_mcp_secret_reference_replaces_the_managed_secret(self):
        objects = render('ilm', mcp_reference_values({'name': 'external-mcp', 'key': 'mcp-key'}))
        workload = object_by_name(objects, 'Deployment', MCP_DEPLOYMENT)
        self.assertEqual(self.env(workload, 'ILM_MCP_SECURITY_CLIENT_SECRET')['valueFrom']['secretKeyRef'],
                         {'name': 'external-mcp', 'key': 'mcp-key'})
        self.assertNotIn('mcp-server-secret', self.secret_names(objects))

    def test_mcp_secret_reference_cannot_reuse_the_managed_secret(self):
        values = mcp_reference_values({'name': 'mcp-server-secret', 'key': 'client-secret'})
        with self.assertRaisesRegex(AssertionError, 'chart-managed'):
            render('ilm', values)

    def test_mcp_secret_reference_needs_the_realm_secret(self):
        values = mcp_reference_values({'name': 'external-mcp', 'key': 'client-secret'})
        del values['keycloakInternal']['realmImport']
        with self.assertRaisesRegex(AssertionError, 'keycloakInternal.realmImport.existingSecret'):
            render('ilm', values)

    def test_partial_mcp_secret_reference_fails(self):
        for ref, message in [({'name': 'external-mcp'}, 'clientSecretRef requires name and key'),
                             ({'key': 'client-secret'}, 'clientSecretRef requires name and key'),
                             # The MCP chart's schema rejects these before any template renders.
                             ({'name': 1, 'key': 'secret'}, 'clientSecretRef'), ('invalid', 'clientSecretRef')]:
            with self.subTest(ref=ref):
                with self.assertRaisesRegex(AssertionError, message):
                    render('ilm', mcp_reference_values(ref))

    def test_external_mode_refuses_managed_only_globals(self):
        for path, value in [(('clientSecretRef',), {'name': 'external-mcp', 'key': 'client-secret'}),
                            (('delegation', 'group'), 'mcp-users')]:
            name = '.'.join(('global', 'mcp') + path)
            with self.subTest(value=name):
                values = mcp_values('external')
                target = values['global']['mcp']
                for key in path[:-1]:
                    target = target.setdefault(key, {})
                target[path[-1]] = value
                with self.assertRaisesRegex(AssertionError, re.escape(name) + ' cannot be set'):
                    render('ilm', values)

    def test_external_secret_needs_exactly_one_source(self):
        neither = mcp_external_inline_values()
        del neither['global']['mcp']['clientSecret']
        both = mcp_values('external')
        both['global']['mcp']['clientSecret'] = 'SYNTHETIC_MCP_SECRET'
        # The MCP chart enforces this rule, so these are its messages.
        for name, values, message in [
                ('neither', neither, 'security.clientSecretRef.name or global.mcp.clientSecret is required '
                                     'with global.mcp.identity.mode external'),
                ('both', both, 'set only one of security.clientSecretRef.name and global.mcp.clientSecret')]:
            with self.subTest(sources=name):
                with self.assertRaisesRegex(AssertionError, re.escape(message)):
                    render('ilm', values)

    def test_external_secret_reference_cannot_reuse_the_managed_secret(self):
        # External mode stops rendering mcp-server-secret, so Helm would delete it from an installation that had it.
        values = mcp_values('external')
        values['mcpServer']['security']['clientSecretRef']['name'] = 'mcp-server-secret'
        with self.assertRaisesRegex(AssertionError, re.escape(
                'mcpServer.security.clientSecretRef.name must differ from the chart-managed mcp-server-secret; '
                'use a Secret with another name')):
            render('ilm', values)

    def test_realm_carries_the_mcp_objects(self):
        imported, plain = realm_with(mcp_values()), realm_with(mcp_values(), enabled=False)
        self.assertEqual({key for key in imported.keys() | plain.keys() if imported.get(key) != plain.get(key)},
                         {'adminPermissionsEnabled', 'defaultOptionalClientScopes', 'clientScopes', 'clients',
                          'clientProfiles', 'clientPolicies'})
        self.assertIs(imported['adminPermissionsEnabled'], True)
        # Keycloak's own migration adds delegation:client there; a second entry rolls the whole import back.
        self.assertEqual(imported['defaultOptionalClientScopes'], plain['defaultOptionalClientScopes'] + ['mcp:access'])
        for key in ('clientScopes', 'clients'):
            self.assertEqual(imported[key][:len(plain[key])], plain[key], key)
        scopes, clients = by_name(imported['clientScopes']), by_name(imported['clients'], 'clientId')

        client = clients['ilm-mcp']
        self.assert_includes(client, {
            'publicClient': False, 'clientAuthenticatorType': 'client-secret', 'secret': 'SYNTHETIC_MCP_SECRET',
            'serviceAccountsEnabled': True, 'standardFlowEnabled': False, 'implicitFlowEnabled': False,
            'directAccessGrantsEnabled': False, 'fullScopeAllowed': False})
        self.assert_includes(client['attributes'], {
            'standard.token.exchange.enabled': 'true', 'standard.token.exchange.enableRefreshRequestedTokenType': 'NO'})
        self.assertIn('ilm-mcp-upstream', client['optionalClientScopes'])
        # Every scope named exists, so the import skips none.
        self.assertLessEqual(set(client['defaultClientScopes'] + client['optionalClientScopes']
                                 + imported['defaultOptionalClientScopes']), set(scopes))

        self.assertEqual(audiences(scopes['mcp:access']), ['https://ilm.example.invalid/mcp', 'ilm-mcp'])
        self.assertEqual(audiences(scopes['ilm-mcp-upstream']), ['ilm'])
        upstream = by_name(scopes['ilm-mcp-upstream']['protocolMappers'])
        ilm = by_name(clients['ilm']['protocolMappers'])
        self.assertEqual(set(upstream), {'ilm-api-audience', 'Username', 'Groups'})
        for name in ('Username', 'Groups'):
            self.assertEqual(upstream[name], {key: value for key, value in ilm[name].items() if key != 'id'}, name)
        self.assertEqual(scopes['delegation:client'], DELEGATION_CLIENT)

        profiles = by_name(imported['clientProfiles']['profiles'])
        policies = by_name(imported['clientPolicies']['policies'])
        self.assertEqual(profiles['mcp-cimd']['executors'], [{
            'executor': 'client-id-metadata-document', 'configuration': {
                'cimd-allow-permitted-domains': ['claude.ai', 'localhost', '127.0.0.1'],
                'accept-public-client-with-confidential-client-only-grant': True,
                'cimd-resource-indicator-allow-list': ['https://ilm.example.invalid/mcp']}}])
        self.assertEqual(policies['mcp-cimd'], {'name': 'mcp-cimd', 'enabled': True, 'profiles': ['mcp-cimd'],
                                                'conditions': [{'condition': 'client-id-uri', 'configuration': {
                                                    'client-id-uri-scheme': ['https'],
                                                    'client-id-uri-allow-permitted-domains': ['claude.ai']}}]})
        self.assertEqual(profiles['mcp-pkce']['executors'], [
            {'executor': 'pkce-enforcer', 'configuration': {'auto-configure': True}}])
        self.assertEqual(policies['mcp-pkce'], {'name': 'mcp-pkce', 'enabled': True, 'profiles': ['mcp-pkce'],
                                                'conditions': [{'condition': 'client-scopes', 'configuration': {
                                                    'scopes': ['mcp:access'], 'type': 'Optional'}}]})

        self.assertEqual(clients['admin-permissions'], {'clientId': 'admin-permissions', 'authorizationSettings': {
            'policies': [DELEGATING_CLIENT_POLICY,
                         delegation_permission('ilm-mcp-all-users-delegation', 'Users', 'Users', 'delegate')]}})

    def test_external_mode_adds_nothing_to_keycloak(self):
        for name, make_values in [('provider secret', lambda: mcp_values('external')),
                                  ('inline secret', mcp_external_inline_values)]:
            with self.subTest(client_secret=name):
                self.assertEqual(realm_with(make_values()), realm_with(make_values(), enabled=False))
                registration = registration_with(make_values())
                self.assertEqual(registration, registration_with(make_values(), enabled=False))
                self.assert_no_delegate(registration)

    def test_registration_allows_the_mcp_delegate(self):
        self.assertEqual(registration_with(mcp_values()), {
            **registration_with(mcp_values(), enabled=False),
            'allowedDelegates': ['ilm-mcp'], 'delegateClaim': 'client_id'})

    def test_cimd_switch_removes_only_the_cimd_policy(self):
        expected = realm_with(mcp_values())
        for key, entries in (('clientProfiles', 'profiles'), ('clientPolicies', 'policies')):
            self.assertEqual([entry['name'] for entry in expected[key][entries]], ['mcp-pkce', 'mcp-cimd'], key)
            expected[key][entries] = expected[key][entries][:1]
        self.assertEqual(realm_with(mcp_values(), cimd={'enabled': False}), expected)

    def test_group_option_limits_delegation_to_the_group(self):
        imported = realm_with(mcp_values(), delegation={'group': GROUP})
        groups = by_name(imported['groups'])
        self.assertEqual(list(groups), [GROUP])
        group = groups[GROUP]
        self.assertEqual(group, {'id': str(uuid.UUID(group['id'])), 'name': GROUP, 'path': '/' + GROUP,
                                 'subGroups': [], 'attributes': {}, 'realmRoles': [], 'clientRoles': {}})
        # The permission names the group by its id, so the id is fixed rather than generated on each render.
        self.assertEqual(realm_with(mcp_values(), delegation={'group': GROUP})['groups'], imported['groups'])
        self.assertEqual(by_name(imported['clients'], 'clientId')['admin-permissions']['authorizationSettings'], {
            'policies': [DELEGATING_CLIENT_POLICY, delegation_permission(
                'ilm-mcp-selected-users-delegation', 'Groups', group['id'], 'delegate-members')]})

    def test_standalone_realm_leaves_an_unset_secret_to_keycloak(self):
        values = synthetic_values('keycloak-internal')
        values['global']['mcp'] = {'enabled': True}
        clients = by_name(realm(render('keycloak-internal', values))['clients'], 'clientId')
        self.assertIn('ilm-mcp', clients.keys())
        self.assertNotIn('secret', clients['ilm-mcp'].keys())

    def test_mcp_secret_change_rolls_the_pod(self):
        def checksum(make_values, secret):
            values = make_values()
            values['global']['mcp']['clientSecret'] = secret
            workload = object_by_name(render('ilm', values), 'Deployment', MCP_DEPLOYMENT)
            return workload['spec']['template']['metadata']['annotations']['checksum/client-secret']
        for mode, make_values in [('managed', mcp_values), ('external', mcp_external_inline_values)]:
            with self.subTest(mode=mode):
                self.assertNotEqual(checksum(make_values, 'SYNTHETIC_MCP_SECRET'),
                                    checksum(make_values, 'SYNTHETIC_MCP_SECRET_ROTATED'))

    def test_core_restarts_when_the_delegate_registration_changes(self):
        # Core registers the bundled provider at startup, so its pod template has to change whenever the registration
        # gains or loses the MCP delegate.
        def annotations(values, kind='Deployment', workload='core-deployment'):
            template = object_by_name(render('ilm', values), kind, workload)['spec']['template']
            return template['metadata'].get('annotations', {})

        stateful = mcp_values()
        stateful['workloadType'] = 'StatefulSet'
        for name, values, kind, workload in [('Deployment', mcp_values(), 'Deployment', 'core-deployment'),
                                             ('StatefulSet', stateful, 'StatefulSet', 'core')]:
            with self.subTest(workload=name):
                self.assertIn('checksum/mcp-delegate', annotations(values, kind, workload))
        off = mcp_values()
        off['global']['mcp']['enabled'] = False
        unregistered = mcp_values()
        unregistered['registerInternalKeycloak'] = False
        for name, values in [('MCP off', off), ('external', mcp_values('external')),
                             ('registerInternalKeycloak false', unregistered)]:
            with self.subTest(case=name):
                self.assertNotIn('checksum/mcp-delegate', annotations(values))

    def test_mcp_network_policy_selects_kong_core_and_keycloak(self):
        values = mcp_values()
        values['mcpServer'] = {'networkPolicy': {'enabled': True}}
        objects = render('ilm', values)
        policy = object_by_name(objects, 'NetworkPolicy', MCP_DEPLOYMENT)['spec']
        egress = policy['egress'][-1]
        peers = policy['ingress'][0]['from'] + egress['to']
        kong, core, keycloak = ['api-gateway-deployment', 'core-deployment', 'keycloak-internal-deployment']
        names = [pod_template(objects, workload)['metadata']['labels']['app.kubernetes.io/name']
                 for workload in (kong, core, keycloak)]
        self.assertEqual([peer['podSelector']['matchLabels'] for peer in peers],
                         [{'app.kubernetes.io/name': name} for name in names])
        self.assertEqual(egress['ports'], [{'protocol': 'TCP', 'port': 8080}])
        for workload in (core, keycloak):
            containers = pod_template(objects, workload)['spec']['containers']
            self.assertIn(8080, {port['containerPort'] for container in containers
                                 for port in container.get('ports', [])}, workload)

    def test_kong_routes_mcp_without_buffering_or_client_certificates(self):
        keycloak_off = mcp_values('external')
        keycloak_off['global']['keycloak']['enabled'] = False
        for name, values in [('managed', mcp_values()), ('external', mcp_values('external')),
                             ('external without the bundled Keycloak', keycloak_off)]:
            with self.subTest(mode=name):
                service = self.kong_mcp_service(values)
                self.assertEqual((service['host'], service['port'], service['protocol']),
                                 ('mcp-server-service', 8080, 'http'))
                self.assertEqual(service['routes'], [{
                    'name': 'mcp', 'strip_path': False, 'preserve_host': True, 'response_buffering': False,
                    'paths': ['/mcp', '/.well-known/oauth-protected-resource']}])
                self.assertEqual(service['plugins'], [{
                    'name': 'request-transformer', 'config': {'remove': {'headers': ['ssl-client-cert']}}}])

    def test_kong_removes_a_custom_client_certificate_header(self):
        values = mcp_values()
        values['auth'] = {'header': {'certificate': 'x-client-cert'}}
        self.assertEqual(self.kong_mcp_service(values)['plugins'], [{
            'name': 'request-transformer', 'config': {'remove': {'headers': ['x-client-cert']}}}])

    def test_standalone_kong_removes_the_default_client_certificate_header(self):
        objects = render('api-gateway-kong', {'global': {'mcp': {'enabled': True}}})
        service = kong_services(objects, 'api-gateway-configmap')['mcp-server-service']
        self.assertEqual(service['plugins'], [{
            'name': 'request-transformer', 'config': {'remove': {'headers': ['ssl-client-cert']}}}])

    def test_mcp_needs_the_host_name(self):
        values = mcp_values()
        del values['global']['hostName']
        with self.assertRaisesRegex(AssertionError, 'global.hostName'):
            render('ilm', values)


if __name__ == '__main__':
    unittest.main()
