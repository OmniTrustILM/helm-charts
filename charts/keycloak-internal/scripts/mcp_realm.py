#!/usr/bin/python3

# This script adds the MCP server's Keycloak objects to an existing ILM realm (enable), or removes them (cleanup).
# The chart's realm import creates these objects only with a new realm, so run enable for a realm that was imported
# before MCP was enabled, and cleanup when MCP stops using the bundled Keycloak. Both are idempotent: a second run
# changes nothing.
#
# enable creates the objects that are missing and corrects only the fields it sets:
#   1. The client scopes mcp:access, ilm-mcp-upstream and delegation:client. ilm-mcp-upstream gets copies of the ilm
#      client's Username and Groups mappers, so that MCP's tokens carry the claims of ILM's own.
#   2. The confidential client ilm-mcp, with the client secret that the MCP server is configured with.
#   3. The client profiles and policies mcp-pkce and, unless --no-cimd, mcp-cimd.
#   4. Fine-grained admin permissions (v2) for the realm, then mcp:access and delegation:client as default optional
#      client scopes of the realm.
#   5. The permission that lets ilm-mcp act for users: for all users or, with --group, for the members of one group,
#      which is created when missing. The permission of the other form is deleted.
#
# cleanup removes these objects and keeps groups, delegation:client and fine-grained admin permissions. Keycloak
# without the cimd feature fails every sign-in in a realm that stores mcp-cimd, so cleanup removes mcp-cimd first,
# and enable --no-cimd removes it before any other write. Run one of them before switching that feature off.
#
# enable writes nothing and asks the operator to resolve the cause first when the ilm client lacks a mapper that
# ilm-mcp-upstream copies, when ilm-mcp has secret rotation state that an update would clear, or when a scope it
# assigns is assigned with another type, which only a DELETE could change.
#
# enable needs the Keycloak features token-exchange-delegation, parameterized-scopes and, unless --no-cimd, cimd.
# --dry-run prints the planned changes and writes nothing.
#
# This script was tested on Keycloak 26.8.1.

import argparse
import copy
import getpass
import re
import sys
from dataclasses import dataclass, field

import requests
from requests.exceptions import SSLError
import urllib3

REALM = 'ILM'
REALM_PATH = f'/admin/realms/{REALM}'
PROFILES_PATH = f'{REALM_PATH}/client-policies/profiles'
POLICIES_PATH = f'{REALM_PATH}/client-policies/policies'
DELEGATION_FEATURES = ('token-exchange-delegation', 'parameterized-scopes')
CLIENT_ID = 'ilm-mcp'
ADMIN_PERMISSIONS_CLIENT = 'admin-permissions'
DELEGATING_CLIENT_POLICY = 'ilm-mcp-delegating-client'
ALL_USERS_PERMISSION = 'ilm-mcp-all-users-delegation'
GROUP_PERMISSION = 'ilm-mcp-selected-users-delegation'
PKCE = 'mcp-pkce'
CIMD = 'mcp-cimd'
# cleanup keeps delegation:client, which Keycloak itself adds to a realm migrated with the delegation features on.
MCP_SCOPES = ('mcp:access', 'ilm-mcp-upstream')
SCOPE_ATTRIBUTES = {'include.in.token.scope': 'true', 'display.on.consent.screen': 'true'}
# Keycloak keeps these while a client's secret rotates. An update of the client can clear them, which ends the grace
# period of the previous secret.
ROTATION_ATTRIBUTES = ('client.secret.rotation.enabled', 'client.secret.expiration.time',
                       'client.secret.remaining.expiration.time', 'client.secret.rotated',
                       'client.secret.rotated.creation.time', 'client.secret.rotated.expiration.time')

# ilm-mcp-upstream carries copies of these mappers of the realm's own ilm client, as the realm import does, so that a
# token exchanged for MCP carries the claims of ILM's own tokens however the realm maps them.
ILM_CLAIM_MAPPERS = ('Username', 'Groups')

# Keycloak's own delegation:client, which a realm lacks when the delegation features were switched on after Keycloak
# migrated it. A realm import stores userinfo.token.claim on the may_act mappers; Keycloak's migration leaves it out,
# which puts the claims in userinfo all the same.
DELEGATION_CLIENT_SCOPE = {
    'name': 'delegation:client',
    'description': 'OpenID Connect scope for agent/client token exchange delegation',
    'protocol': 'openid-connect',
    'attributes': {'include.in.token.scope': 'true', 'parameterized.scope.type': 'client-delegation',
                   'display.on.consent.screen': 'true', 'always.display.consent': 'true',
                   'is.parameterized.scope': 'true', 'consent.screen.text': '${clientDelegationScopeConsentText}'},
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

# Keycloak generates the ID of an object that an earlier change of the same plan creates, so the plan names that
# object as {kind:name} in a path or in a permission's resources, and apply_changes looks the ID up before the call.
REFERENCE = re.compile(r'\{(client|client-scope|group):([^{}]+)\}')


@dataclass(frozen=True)
class Change:
    """One Admin REST call that writes. The description names objects and fields, never a value. The body may hold
    the client secret, so it is left out of repr."""
    method: str
    path: str
    body: object = field(repr=False)
    description: str


class KeycloakError(Exception):
    """An Admin REST call that Keycloak refused."""


class PlanError(Exception):
    """A state of the realm that enable must not change itself: the operator resolves it, then runs enable again."""


class AdminSession(requests.Session):
    """A session whose request paths are relative to the Keycloak URL."""

    def __init__(self, url, verify=True):
        super().__init__()
        self.url = url
        self.verify = verify

    def request(self, method, path, *args, **kwargs):
        return super().request(method, self.url + path, *args, **kwargs)


def checked(response):
    """The response, or a KeycloakError with the call, the status and Keycloak's message, without request data."""
    if response.ok:
        return response
    try:
        detail = response.json()
    except ValueError:
        detail = None
    message = ''
    if isinstance(detail, dict):
        message = detail.get('errorMessage') or detail.get('error_description') or detail.get('error') or ''
    raise KeycloakError(f'{response.request.method} {response.request.path_url} returned HTTP '
                        f'{response.status_code}' + (f': {message}' if message else ''))


def connect(keycloak_url, username, password, verify=True):
    """Signs in as an admin of the master realm through admin-cli, as the realm update scripts do."""
    session = AdminSession(keycloak_url, verify)
    response = checked(session.post('/realms/master/protocol/openid-connect/token', data={
        'client_id': 'admin-cli', 'username': username, 'password': password, 'grant_type': 'password'}))
    session.headers['Authorization'] = f"Bearer {response.json()['access_token']}"
    return session


def read(session, path, **params):
    """The JSON that a GET returns, or None when Keycloak answers without content."""
    response = checked(session.get(path, params=params))
    return response.json() if response.content else None


def read_realm(session):
    """The realm, or None when Keycloak has no realm ILM."""
    response = session.get(REALM_PATH)
    return None if response.status_code == 404 else checked(response).json()


def by_name(entries):
    return {entry['name']: entry for entry in entries}


def find_client(session, client_id):
    clients = read(session, f'{REALM_PATH}/clients', clientId=client_id)
    return next((client for client in clients if client['clientId'] == client_id), None)


def find_scope(session, name):
    return by_name(read(session, f'{REALM_PATH}/client-scopes')).get(name)


def find_group(session, name):
    """The top-level group with this name, or None."""
    groups = read(session, f'{REALM_PATH}/groups', search=name, exact='true')
    return next((group for group in groups if group['name'] == name and group.get('path') == f'/{name}'), None)


def authz_path(admin_permissions_id):
    """Fine-grained admin permissions (v2) keep their policies in the authorization settings of this client."""
    return f'{REALM_PATH}/clients/{admin_permissions_id}/authz/resource-server'


def search(session, base, kind, name):
    """A policy or permission by name, or None: Keycloak answers 204 when there is none."""
    return read(session, f'{base}/{kind}/search', name=name)


def reference(kind, name):
    return '{%s:%s}' % (kind, name)


def resolve(session, text):
    """text with each reference replaced by the ID of the object it names."""
    def object_id(match):
        kind, name = match.groups()
        found = {'client': find_client, 'client-scope': find_scope, 'group': find_group}[kind](session, name)
        if found is None:
            raise KeycloakError(f'{kind} {name} was not found')
        return found['id']
    return REFERENCE.sub(object_id, text)


def covers(actual, wanted):
    """Whether actual holds every field of wanted with an equal value. Other fields of a dict are not compared; a list
    is compared whole."""
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and all(key in actual and covers(actual[key], value)
                                                for key, value in wanted.items())
    if isinstance(wanted, list):
        return isinstance(actual, list) and len(actual) == len(wanted) and all(map(covers, actual, wanted))
    return actual == wanted


def merged(current, wanted):
    """current with the fields of wanted set; a dict field keeps its other keys."""
    result = dict(current)
    for key, value in wanted.items():
        result[key] = {**current.get(key, {}), **value} if isinstance(value, dict) else value
    return result


def audience_mapper(name, kind, audience):
    return {'name': name, 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
            'consentRequired': False,
            'config': {kind: audience, 'id.token.claim': 'false', 'access.token.claim': 'true',
                       'introspection.token.claim': 'true', 'userinfo.token.claim': 'false'}}


def ilm_claim_mappers(ilm_client):
    """Copies of the ilm client's Username and Groups mappers without their IDs, as the realm import makes them."""
    if ilm_client is None:
        raise PlanError(f"Client ilm not found. ilm-mcp-upstream copies its {' and '.join(ILM_CLAIM_MAPPERS)} "
                        'mappers.')
    mappers = by_name(ilm_client.get('protocolMappers', []))
    for name in ILM_CLAIM_MAPPERS:
        if name not in mappers:
            raise PlanError(f"Client ilm has no protocol mapper {name}, which ilm-mcp-upstream copies so that MCP's "
                            "tokens carry the claims of ILM's own. Add it, then run enable again.")
    return [{key: value for key, value in mappers[name].items() if key != 'id'} for name in ILM_CLAIM_MAPPERS]


def desired_objects(host: str, secret: str, cimd: bool, group: str | None) -> dict:
    """MCP's objects as the chart's realm import (realms/mcp-objects.json) creates them. plan_enable adds the copies
    of the ilm client's mappers to ilm-mcp-upstream."""
    resource = f'https://{host}/mcp'
    profiles = [{'name': PKCE, 'executors': [{'executor': 'pkce-enforcer', 'configuration': {'auto-configure': True}}]}]
    policies = [{'name': PKCE, 'enabled': True, 'profiles': [PKCE], 'conditions': [
        {'condition': 'client-scopes', 'configuration': {'scopes': ['mcp:access'], 'type': 'Optional'}}]}]
    if cimd:
        profiles.append({'name': CIMD, 'executors': [{'executor': 'client-id-metadata-document', 'configuration': {
            'cimd-allow-permitted-domains': ['claude.ai', 'localhost', '127.0.0.1'],
            'accept-public-client-with-confidential-client-only-grant': True,
            'cimd-resource-indicator-allow-list': [resource]}}]})
        policies.append({'name': CIMD, 'enabled': True, 'profiles': [CIMD], 'conditions': [
            {'condition': 'client-id-uri', 'configuration': {
                'client-id-uri-scheme': ['https'], 'client-id-uri-allow-permitted-domains': ['claude.ai']}}]})
    if group:
        permission = {'name': GROUP_PERMISSION, 'resourceType': 'Groups', 'scopes': ['delegate-members']}
    else:
        permission = {'name': ALL_USERS_PERMISSION, 'resourceType': 'Users', 'scopes': ['delegate']}
    return copy.deepcopy({
        'clientScopes': [
            {'name': 'ilm-mcp-upstream', 'protocol': 'openid-connect', 'attributes': SCOPE_ATTRIBUTES,
             'protocolMappers': [audience_mapper('ilm-api-audience', 'included.client.audience', 'ilm')]},
            {'name': 'mcp:access', 'protocol': 'openid-connect', 'attributes': SCOPE_ATTRIBUTES,
             'protocolMappers': [audience_mapper('mcp-exchange-requester', 'included.client.audience', CLIENT_ID),
                                 audience_mapper('mcp-public-resource', 'included.custom.audience', resource)]},
            DELEGATION_CLIENT_SCOPE,
        ],
        'client': {
            'clientId': CLIENT_ID, 'surrogateAuthRequired': False, 'enabled': True, 'alwaysDisplayInConsole': False,
            'clientAuthenticatorType': 'client-secret', 'secret': secret, 'redirectUris': [], 'webOrigins': [],
            'notBefore': 0, 'bearerOnly': False, 'consentRequired': False, 'standardFlowEnabled': False,
            'implicitFlowEnabled': False, 'directAccessGrantsEnabled': False, 'serviceAccountsEnabled': True,
            'publicClient': False, 'frontchannelLogout': False, 'protocol': 'openid-connect',
            'attributes': {'realm_client': 'false', 'backchannel.logout.session.required': 'true',
                           'standard.token.exchange.enabled': 'true',
                           'backchannel.logout.revoke.offline.tokens': 'false',
                           'standard.token.exchange.enableRefreshRequestedTokenType': 'NO'},
            'authenticationFlowBindingOverrides': {}, 'fullScopeAllowed': False, 'nodeReRegistrationTimeout': -1,
            # basic adds the sub claim. Keycloak's migration adds it to the clients of an imported realm, while a
            # client created through the Admin API with its own scope lists gets only the scopes they name.
            'defaultClientScopes': ['web-origins', 'acr', 'roles', 'profile', 'email', 'basic'],
            'optionalClientScopes': ['ilm-mcp-upstream', 'address', 'phone', 'offline_access', 'microprofile-jwt'],
        },
        'defaultOptionalClientScopes': ['mcp:access', 'delegation:client'],
        'clientProfiles': profiles,
        'clientPolicies': policies,
        'adminPermissionsEnabled': True,
        'group': group or None,
        'clientPolicy': {'name': DELEGATING_CLIENT_POLICY, 'type': 'client', 'logic': 'POSITIVE',
                         'decisionStrategy': 'UNANIMOUS', 'clients': [CLIENT_ID]},
        'permission': {**permission, 'type': 'scope', 'logic': 'POSITIVE', 'decisionStrategy': 'UNANIMOUS',
                       'policies': [DELEGATING_CLIENT_POLICY]},
    })


def plan_scope(current, desired):
    name = desired['name']
    if current is None:
        return [Change('POST', f'{REALM_PATH}/client-scopes', desired, f'Create client scope {name}')]
    path = f"{REALM_PATH}/client-scopes/{current['id']}"
    changes = []
    owned = {key: value for key, value in desired.items() if key != 'protocolMappers'}
    if not covers(current, owned):
        # Without protocolMappers, Keycloak updates the scope and leaves its mappers alone.
        body = merged({key: value for key, value in current.items() if key != 'protocolMappers'}, owned)
        changes.append(Change('PUT', path, body, f'Correct client scope {name}'))
    mappers = by_name(current.get('protocolMappers', []))
    for mapper in desired['protocolMappers']:
        found = mappers.get(mapper['name'])
        if found is None:
            changes.append(Change('POST', f'{path}/protocol-mappers/models', mapper,
                                  f"Add mapper '{mapper['name']}' to client scope {name}"))
        elif not covers(found, mapper):
            changes.append(Change('PUT', f"{path}/protocol-mappers/models/{found['id']}", merged(found, mapper),
                                  f"Correct mapper '{mapper['name']}' of client scope {name}"))
    return changes


def plan_scope_assignments(session, path, owner, types, desired, scope_ids):
    """Changes that assign the desired client scopes, by type, to the owner at path. types maps each type, as the path
    names it, to its label. A scope assigned with another type stops the plan, because changing its type takes a
    DELETE, which enable does not make."""
    assigned = {kind: {scope['name'] for scope in read(session, f'{path}/{kind}-client-scopes')} for kind in types}
    changes = []
    for kind, names in desired.items():
        for name in names:
            for other in types:
                if other != kind and name in assigned[other]:
                    raise PlanError(f'Client scope {name} is assigned to {owner} as {types[other]}, but must be '
                                    f'{types[kind]}. Change its assigned type, then run enable again.')
            # Like Keycloak when it creates a client, this skips a scope that the realm lacks.
            if name not in assigned[kind] and name in scope_ids:
                changes.append(Change('PUT', f'{path}/{kind}-client-scopes/{scope_ids[name]}', None,
                                      f'Add {name} to the {types[kind]} client scopes of {owner}'))
    return changes


def plan_client(session, current, desired, scope_ids):
    client_id = desired['clientId']
    if current is None:
        return [Change('POST', f'{REALM_PATH}/clients', desired, f'Create client {client_id} with its service account')]
    path = f"{REALM_PATH}/clients/{current['id']}"
    owned = {key: value for key, value in desired.items()
             if key not in ('secret', 'defaultClientScopes', 'optionalClientScopes')}
    fields = [key for key, value in owned.items() if not covers(current.get(key), value)]
    notes = [f"correct {', '.join(fields)}"] if fields else []
    body = merged({key: value for key, value in current.items() if key != 'secret'}, owned)
    if current.get('secret') != desired['secret']:
        body['secret'] = desired['secret']
        notes.append('set its secret')
    changes = []
    if notes:
        rotation = [key for key in ROTATION_ATTRIBUTES if current.get('attributes', {}).get(key)]
        if rotation:
            raise PlanError(f"Client {client_id} has secret rotation state ({', '.join(rotation)}), which an update "
                            f"to {' and '.join(notes)} would clear. Finish or remove the secret rotation, then run "
                            'enable again.')
        changes.append(Change('PUT', path, body, f"Update client {client_id}: {' and '.join(notes)}"))
    # Keycloak changes the scopes of an existing client only through these assignments.
    changes += plan_scope_assignments(session, path, f'client {client_id}',
                                      {'default': 'default', 'optional': 'optional'},
                                      {'default': desired['defaultClientScopes'],
                                       'optional': desired['optionalClientScopes']}, scope_ids)
    return changes


def upsert(entries, desired):
    """entries with each desired entry added, or merged in where it differs, and the realm's other entries kept."""
    result, notes = list(entries), []
    for wanted in desired:
        index = next((i for i, entry in enumerate(result) if entry['name'] == wanted['name']), None)
        if index is None:
            result.append(wanted)
            notes.append(f"add {wanted['name']}")
        elif not covers(result[index], wanted):
            result[index] = merged(result[index], wanted)
            notes.append(f"correct {wanted['name']}")
    return result, notes


def plan_removals(profiles, policies, names):
    """Changes that remove each named client policy and then its profile, so that no stored policy names a missing
    profile, with the lists that remain."""
    changes = []
    for name in names:
        if any(policy['name'] == name for policy in policies):
            policies = [policy for policy in policies if policy['name'] != name]
            changes.append(Change('PUT', POLICIES_PATH, {'policies': policies}, f'Remove client policy {name}'))
        if any(profile['name'] == name for profile in profiles):
            profiles = [profile for profile in profiles if profile['name'] != name]
            changes.append(Change('PUT', PROFILES_PATH, {'profiles': profiles}, f'Remove client profile {name}'))
    return changes, profiles, policies


def plan_client_policies(profiles, policies, desired_profiles, desired_policies):
    changes = []
    # Profiles first: Keycloak refuses a policy that names a missing profile.
    for path, key, entries, desired in ((PROFILES_PATH, 'profiles', profiles, desired_profiles),
                                        (POLICIES_PATH, 'policies', policies, desired_policies)):
        entries, notes = upsert(entries, desired)
        if notes:
            changes.append(Change('PUT', path, {key: entries},
                                  f"Write the client {key} of the realm: {', '.join(notes)}"))
    return changes


def plan_permission_policy(session, base, current, desired, client):
    name = desired['name']
    if current is None:
        return [Change('POST', f'{base}/policy/client', desired, f'Create permission policy {name}')]
    stored = read(session, f"{base}/policy/client/{current['id']}")
    # The Admin API returns the IDs of the clients that the policy names by clientId.
    if client is not None and stored.get('clients') == [client['id']] and covers(
            stored, {key: desired[key] for key in ('logic', 'decisionStrategy')}):
        return []
    return [Change('PUT', f"{base}/policy/client/{current['id']}", {**desired, 'id': current['id']},
                   f'Correct permission policy {name}')]


def plan_permission(session, base, current, desired):
    name = desired['name']
    if current is None:
        return [Change('POST', f'{base}/permission/scope', desired, f'Create permission {name}')]

    def names(part):
        return sorted(entry['name'] for entry in read(session, f"{base}/policy/{current['id']}/{part}") or [])

    # The resource of a permission for all users is its resource type.
    if (covers(current, {key: desired[key] for key in ('resourceType', 'logic', 'decisionStrategy')})
            and names('resources') == sorted(desired.get('resources', [desired['resourceType']]))
            and names('scopes') == sorted(desired['scopes'])
            and names('associatedPolicies') == sorted(desired['policies'])):
        return []
    # Without a resources key Keycloak keeps a permission's resources, so a narrowed all-users permission would stay
    # narrowed.
    return [Change('PUT', f"{base}/permission/scope/{current['id']}", {'resources': [], **desired, 'id': current['id']},
                   f'Correct permission {name}')]


def plan_delegation(session, desired, client):
    """The group, the permission policy and the permission that let ilm-mcp act for users."""
    changes = []
    group, permission = desired['group'], dict(desired['permission'])
    if group:
        found = find_group(session, group)
        if found is None:
            changes.append(Change('POST', f'{REALM_PATH}/groups', {'name': group}, f'Create group {group}'))
        permission['resources'] = [found['id'] if found else reference('group', group)]
    admin = find_client(session, ADMIN_PERMISSIONS_CLIENT)
    base = authz_path(admin['id'] if admin else reference('client', ADMIN_PERMISSIONS_CLIENT))

    def lookup(kind, name):
        return search(session, base, kind, name) if admin else None

    changes += plan_permission_policy(session, base, lookup('policy', DELEGATING_CLIENT_POLICY),
                                      desired['clientPolicy'], client)
    other = lookup('permission', ALL_USERS_PERMISSION if group else GROUP_PERMISSION)
    if other is not None:
        changes.append(Change('DELETE', f"{base}/policy/{other['id']}", None,
                              f"Delete permission {other['name']} of the other delegation form"))
    changes += plan_permission(session, base, lookup('permission', permission['name']), permission)
    return changes


def plan_enable(session, desired: dict) -> list[Change]:
    """The changes that add MCP's objects to the realm, or correct the fields of them that enable sets."""
    removed = [] if any(profile['name'] == CIMD for profile in desired['clientProfiles']) else [CIMD]
    # Before any other write: Keycloak without the cimd feature fails client writes while the realm stores mcp-cimd.
    changes, profiles, policies = plan_removals(read(session, PROFILES_PATH)['profiles'],
                                                read(session, POLICIES_PATH)['policies'], removed)
    scopes = by_name(read(session, f'{REALM_PATH}/client-scopes'))
    scope_ids = {name: scope['id'] for name, scope in scopes.items()}
    copies = ilm_claim_mappers(find_client(session, 'ilm'))
    for scope in desired['clientScopes']:
        if scope['name'] == 'ilm-mcp-upstream':
            scope = {**scope, 'protocolMappers': scope['protocolMappers'] + copies}
        changes += plan_scope(scopes.get(scope['name']), scope)
        scope_ids.setdefault(scope['name'], reference('client-scope', scope['name']))
    client = find_client(session, CLIENT_ID)
    changes += plan_client(session, client, desired['client'], scope_ids)
    changes += plan_client_policies(profiles, policies, desired['clientProfiles'], desired['clientPolicies'])
    if read(session, REALM_PATH).get('adminPermissionsEnabled') != desired['adminPermissionsEnabled']:
        changes.append(Change('PUT', REALM_PATH, {'adminPermissionsEnabled': desired['adminPermissionsEnabled']},
                              'Enable fine-grained admin permissions in the realm'))
    # After fine-grained admin permissions: Keycloak gives the admin-permissions client it creates the realm's default
    # optional scopes, and an imported realm gives it none of MCP's.
    changes += plan_scope_assignments(session, REALM_PATH, 'the realm',
                                      {'default-default': 'default', 'default-optional': 'default optional'},
                                      {'default-optional': desired['defaultOptionalClientScopes']}, scope_ids)
    changes += plan_delegation(session, desired, client)
    return changes


def plan_cleanup(session) -> list[Change]:
    """The changes that remove MCP's objects, mcp-cimd first."""
    changes = plan_removals(read(session, PROFILES_PATH)['profiles'], read(session, POLICIES_PATH)['policies'],
                            (CIMD, PKCE))[0]
    admin = find_client(session, ADMIN_PERMISSIONS_CLIENT)
    if admin is not None:
        base = authz_path(admin['id'])
        for kind, name in (('permission', ALL_USERS_PERMISSION), ('permission', GROUP_PERMISSION),
                           ('policy', DELEGATING_CLIENT_POLICY)):
            found = search(session, base, kind, name)
            if found is not None:
                label = 'permission' if kind == 'permission' else 'permission policy'
                changes.append(Change('DELETE', f"{base}/policy/{found['id']}", None, f'Delete {label} {name}'))
    client = find_client(session, CLIENT_ID)
    if client is not None:
        changes.append(Change('DELETE', f"{REALM_PATH}/clients/{client['id']}", None, f'Delete client {CLIENT_ID}'))
    scopes = by_name(read(session, f'{REALM_PATH}/client-scopes'))
    optional = {scope['name'] for scope in read(session, f'{REALM_PATH}/default-optional-client-scopes')}
    for name in MCP_SCOPES:
        if name in scopes:
            if name in optional:
                changes.append(Change('DELETE', f"{REALM_PATH}/default-optional-client-scopes/{scopes[name]['id']}",
                                      None, f'Remove {name} from the default optional client scopes of the realm'))
            changes.append(Change('DELETE', f"{REALM_PATH}/client-scopes/{scopes[name]['id']}", None,
                                  f'Delete client scope {name}'))
    return changes


def apply_changes(session, changes: list[Change]) -> None:
    """Makes the changes in order, printing each description first."""
    for change in changes:
        print(f'- {change.description}')
        body = change.body
        if isinstance(body, dict) and 'resources' in body:
            body = {**body, 'resources': [resolve(session, resource) for resource in body['resources']]}
        checked(session.request(change.method, resolve(session, change.path), json=body))


def missing_features(session, cimd):
    """The features enable needs that Keycloak does not report as enabled, named as --features names them."""
    info = read(session, '/admin/serverinfo')
    enabled = {feature['name'].lower().replace('_', '-') for feature in info.get('features', [])
               if feature.get('enabled')}
    return [name for name in DELEGATION_FEATURES + (('cimd',) if cimd else ()) if name not in enabled]


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "mcp_realm.py: add the MCP server's Keycloak objects to the existing ILM realm (enable), or remove "
            "them (cleanup). Idempotent: a second run changes nothing."
        )
    )
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument(
        '--insecure', action='store_true', default=False,
        help='disable TLS certificate validation (default: %(default)s)',
    )
    options.add_argument(
        '--dry-run', action='store_true', default=False,
        help='print the planned changes and write nothing (default: %(default)s)',
    )
    actions = parser.add_subparsers(dest='action', required=True)
    enable = actions.add_parser('enable', parents=[options], help="add MCP's objects, or correct them")
    enable.add_argument(
        '--no-cimd', action='store_true', default=False,
        help=f'leave out the client policy {CIMD}, and remove it, for a Keycloak without the cimd feature '
             '(default: %(default)s)',
    )
    enable.add_argument(
        '--group', metavar='NAME',
        help=f'let {CLIENT_ID} act only for the members of this group, which is created when missing, '
             'instead of for all users',
    )
    actions.add_parser('cleanup', parents=[options], help="remove MCP's objects")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.insecure:
        urllib3.disable_warnings()

    # Every answer comes before signing in: an access token of the master realm lasts 60 seconds by default.
    keycloak_url = input('Enter the URL of the Keycloak (e.g., https://my.ilm.local/kc): ').rstrip('/')
    username = input('Enter the admin username: ')
    password = getpass.getpass('Enter the admin password: ')
    if args.action == 'enable':
        host = input('Enter the public host name of ILM (e.g., my.ilm.local): ').strip()
        secret = getpass.getpass(f'Enter the client secret of {CLIENT_ID}, as the MCP server has it: ')
        if not host or '/' in host or not secret:
            print('ERROR: Enter the host name, without https:// or a path, and the client secret.')
            return 1

    try:
        session = connect(keycloak_url, username, password, verify=not args.insecure)
        print('Authenticated successfully.')
        if read_realm(session) is None:
            print(f"ERROR: Realm '{REALM}' not found.")
            return 1
        if args.action == 'enable':
            missing = missing_features(session, cimd=not args.no_cimd)
            if missing:
                print(f"ERROR: These Keycloak features are not enabled: {', '.join(missing)}. Enable them with "
                      '--features' + ('; without cimd, run enable --no-cimd.' if 'cimd' in missing else '.'))
                return 1
            changes = plan_enable(session, desired_objects(host, secret, not args.no_cimd, args.group))
        else:
            changes = plan_cleanup(session)

        if not changes:
            print('Nothing to change.')
        elif args.dry_run:
            print(f'Dry run, nothing is written. {len(changes)} planned changes:')
            for change in changes:
                print(f'- {change.description}')
        else:
            print(f'Making {len(changes)} changes:')
            apply_changes(session, changes)
            print('Done.')
        return 0
    except SSLError as e:
        print(f'An SSL error occurred, maybe try --insecure option? Exception: {e}')
    except (requests.exceptions.RequestException, KeycloakError) as e:
        print(f'An error occurred: {e}')
    except PlanError as e:
        print(f'ERROR: {e}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
