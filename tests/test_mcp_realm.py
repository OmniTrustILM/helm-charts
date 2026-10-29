"""Run the MCP realm script against an in-process fake of Keycloak's Admin REST API; no Keycloak or cluster is used."""
import contextlib
import copy
import importlib.util
import io
import json
import re
import threading
import unittest
import uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from helm_render import ROOT
from test_mcp import DELEGATION_CLIENT, GROUP, mcp_values, realm_with

_SPEC = importlib.util.spec_from_file_location(
    'mcp_realm', ROOT / 'charts' / 'keycloak-internal' / 'scripts' / 'mcp_realm.py')
mcp_realm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mcp_realm)

HOST = 'ilm.example.invalid'
# The same value as mcp_values(), so that the script's objects can be compared with the rendered realm import.
SECRET = 'SYNTHETIC_MCP_SECRET'
ROTATED_SECRET = 'SYNTHETIC_ROTATED_MCP_SECRET'
ADMIN_PASSWORD = 'SYNTHETIC_ADMIN_PASSWORD'
TOKEN = 'SYNTHETIC_ADMIN_TOKEN'
TOKEN_PATH = '/realms/master/protocol/openid-connect/token'
R = '/admin/realms/ILM'
AUTHZ = R + '/clients/(?P<admin>[^/]+)/authz/resource-server'
FEATURES = ('CIMD', 'TOKEN_EXCHANGE_DELEGATION', 'PARAMETERIZED_SCOPES')
# An ILM realm that Keycloak 26.8 migrated with the delegation features on: the migration created delegation:client,
# without userinfo.token.claim on its mappers, and made it and delegation:user default optional scopes.
BUILT_IN_SCOPES = ('profile', 'email', 'roles', 'web-origins', 'acr', 'basic', 'service_account', 'address', 'phone',
                   'offline_access', 'microprofile-jwt', 'delegation:user')
REALM_OPTIONAL_SCOPES = ('offline_access', 'address', 'phone', 'microprofile-jwt', 'delegation:client',
                         'delegation:user')
REALM_DEFAULT_SCOPES = ('profile', 'email', 'roles', 'web-origins', 'acr', 'basic')
REALM_SCOPE_TYPE = '(?P<kind>default-default|default-optional)'
PREVIOUS_SECRET = 'SYNTHETIC_PREVIOUS_MCP_SECRET'
MCP_SCOPES = ('ilm-mcp-upstream', 'mcp:access', 'delegation:client')
ALL_USERS = 'ilm-mcp-all-users-delegation'
SELECTED_USERS = 'ilm-mcp-selected-users-delegation'
DELEGATING_CLIENT = 'ilm-mcp-delegating-client'
FOREIGN_PROFILE = {'name': 'kc-foreign', 'executors': [{'executor': 'pkce-enforcer', 'configuration': {}}]}
FOREIGN_POLICY = {'name': 'kc-foreign', 'enabled': False, 'conditions': [], 'profiles': ['kc-foreign']}
# Mappers of the ilm client as the chart's realm has them; ilm-mcp-upstream copies Username and Groups.
ILM_MAPPERS = [
    {'name': 'Groups', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-attribute-mapper',
     'consentRequired': False,
     'config': {'aggregate.attrs': 'false', 'userinfo.token.claim': 'true', 'multivalued': 'true',
                'user.attribute': 'groups', 'id.token.claim': 'true', 'access.token.claim': 'true',
                'claim.name': 'roles'}},
    {'name': 'Username', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-usermodel-property-mapper',
     'consentRequired': False,
     'config': {'introspection.token.claim': 'true', 'userinfo.token.claim': 'true', 'user.attribute': 'username',
                'id.token.claim': 'true', 'lightweight.claim': 'false', 'access.token.claim': 'true',
                'claim.name': 'username', 'jsonType.label': 'String'}},
    {'name': 'Audience', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
     'consentRequired': False, 'config': {'included.client.audience': 'ilm', 'access.token.claim': 'true'}},
]
# Roles from group membership instead of the groups attribute, as a realm whose groups come from LDAP may map them.
GROUP_MEMBERSHIP_ROLES = {'name': 'Groups', 'protocol': 'openid-connect',
                          'protocolMapper': 'oidc-group-membership-mapper', 'consentRequired': False,
                          'config': {'full.path': 'false', 'id.token.claim': 'true', 'access.token.claim': 'true',
                                     'userinfo.token.claim': 'true', 'claim.name': 'roles'}}


def new_id():
    return str(uuid.uuid4())


def without_id(entry):
    return {key: value for key, value in entry.items() if key != 'id'}


def normalized(scope):
    """A client scope without IDs, its mappers by name."""
    return {**without_id(scope), 'protocolMappers': sorted((without_id(mapper) for mapper in scope['protocolMappers']),
                                                          key=lambda mapper: mapper['name'])}


def uses_cimd(entries):
    """Whether client profiles or policies need Keycloak's cimd feature."""
    return any(part.get('executor') == 'client-id-metadata-document' or part.get('condition') == 'client-id-uri'
               for entry in entries for part in entry.get('executors', []) + entry.get('conditions', []))


def keycloak_delegation_client():
    scope = copy.deepcopy(DELEGATION_CLIENT)
    for mapper in scope['protocolMappers']:
        mapper['config'].pop('userinfo.token.claim', None)
    return scope


@dataclass
class Request:
    method: str
    path: str
    query: dict
    body: object


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self):
        split = urlsplit(self.path)
        length = int(self.headers.get('Content-Length') or 0)
        status, payload, location = self.server.fake.dispatch(
            self.command, split.path, {key: values[0] for key, values in parse_qs(split.query).items()},
            self.rfile.read(length) if length else b'', self.headers.get('Authorization'))
        data = b'' if payload is None else json.dumps(payload).encode()
        self.send_response(status)
        if data:
            self.send_header('Content-Type', 'application/json')
        if location:
            self.send_header('Location', location)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = respond


class FakeKeycloak:
    """Keycloak 26.8's Admin REST API for realm ILM, in memory on 127.0.0.1. It records every request, stores what the
    API stores and refuses what Keycloak refuses on the calls the script makes."""

    def __init__(self, test, features=FEATURES, ilm_mappers=ILM_MAPPERS):
        self.requests = []
        self.features = set(features)
        self.fail = None
        self.realm = {'realm': 'ILM', 'adminPermissionsEnabled': False}
        self.scopes, self.clients, self.links, self.groups, self.authz = {}, {}, {}, {}, {}
        self.realm_scopes = {'default-default': [], 'default-optional': []}
        self.profiles, self.policies = [], []
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.fake = self
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.stop)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.routes = [
            ('GET', '/admin/serverinfo', self.serverinfo),
            ('GET', R, self.get_realm),
            ('PUT', R, self.put_realm),
            ('GET', R + '/client-scopes', lambda **_: (200, list(self.scopes.values()), None)),
            ('POST', R + '/client-scopes', lambda body, **_: self.create_scope(body)),
            ('PUT', R + '/client-scopes/(?P<sid>[^/]+)', self.update_scope),
            ('DELETE', R + '/client-scopes/(?P<sid>[^/]+)', self.delete_scope),
            ('POST', R + '/client-scopes/(?P<sid>[^/]+)/protocol-mappers/models', self.add_mapper),
            ('PUT', R + '/client-scopes/(?P<sid>[^/]+)/protocol-mappers/models/(?P<mid>[^/]+)', self.update_mapper),
            ('GET', R + f'/{REALM_SCOPE_TYPE}-client-scopes', self.realm_scope_list),
            ('PUT', R + f'/{REALM_SCOPE_TYPE}-client-scopes/(?P<sid>[^/]+)', self.assign_realm_scope),
            ('DELETE', R + f'/{REALM_SCOPE_TYPE}-client-scopes/(?P<sid>[^/]+)', self.unassign_realm_scope),
            ('GET', R + '/clients', self.list_clients),
            ('POST', R + '/clients', lambda body, **_: self.create_client(body)),
            ('PUT', R + '/clients/(?P<cid>[^/]+)', self.update_client),
            ('DELETE', R + '/clients/(?P<cid>[^/]+)', self.delete_client),
            ('GET', R + '/clients/(?P<cid>[^/]+)/(?P<kind>default|optional)-client-scopes', self.client_scopes),
            ('PUT', R + '/clients/(?P<cid>[^/]+)/(?P<kind>default|optional)-client-scopes/(?P<sid>[^/]+)', self.link),
            ('GET', R + '/client-policies/(?P<key>profiles|policies)', self.get_client_policies),
            ('PUT', R + '/client-policies/(?P<key>profiles|policies)', self.put_client_policies),
            ('GET', R + '/groups', self.search_groups),
            ('POST', R + '/groups', self.create_group),
            ('GET', AUTHZ + '/(?:policy|permission)/search', self.search_authz),
            ('POST', AUTHZ + '/policy/client', self.create_client_policy),
            ('POST', AUTHZ + '/permission/scope', self.create_permission),
            ('GET', AUTHZ + '/policy/client/(?P<pid>[^/]+)', self.get_client_policy),
            ('PUT', AUTHZ + '/policy/client/(?P<pid>[^/]+)', self.update_client_policy),
            ('PUT', AUTHZ + '/permission/scope/(?P<pid>[^/]+)', self.update_permission),
            ('GET', AUTHZ + '/policy/(?P<pid>[^/]+)/(?P<part>resources|scopes|associatedPolicies)', self.authz_part),
            ('DELETE', AUTHZ + '/policy/(?P<pid>[^/]+)', self.delete_authz),
        ]
        for name in BUILT_IN_SCOPES:
            self.create_scope({'name': name, 'protocol': 'openid-connect'})
        self.create_scope(keycloak_delegation_client())
        self.realm_scopes = {kind: [self.scope_named(name)['id'] for name in names] for kind, names in
                             (('default-default', REALM_DEFAULT_SCOPES), ('default-optional', REALM_OPTIONAL_SCOPES))}
        self.create_client({'clientId': 'ilm', 'publicClient': False, 'secret': 'SYNTHETIC_ILM_SECRET',
                            'protocolMappers': ilm_mappers})

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def dispatch(self, method, path, query, raw, authorization):
        if path == TOKEN_PATH:
            self.requests.append(Request(method, path, query, None))
            form = {key: values[0] for key, values in parse_qs(raw.decode()).items()}
            if form == {'client_id': 'admin-cli', 'grant_type': 'password', 'username': 'admin',
                        'password': ADMIN_PASSWORD}:
                return 200, {'access_token': TOKEN, 'expires_in': 60}, None
            return 401, {'error': 'invalid_grant', 'error_description': 'Invalid user credentials'}, None
        body = json.loads(raw) if raw else None
        self.requests.append(Request(method, path, query, copy.deepcopy(body)))
        if authorization != f'Bearer {TOKEN}':
            return 401, {'error': 'HTTP 401 Unauthorized'}, None
        if self.fail == (method, path):
            return 400, {'errorMessage': 'Refused by the test'}, None
        # Keycloak without the cimd feature fails client writes while the realm stores mcp-cimd.
        if (method != 'GET' and re.fullmatch(R + '/clients(?:/[^/]+)?', path) and 'CIMD' not in self.features
                and uses_cimd(self.profiles + self.policies)):
            return 500, {'error': 'unknown_error'}, None
        for route_method, pattern, action in self.routes:
            match = re.fullmatch(pattern, path)
            if match and route_method == method:
                return action(query=query, body=body, **match.groupdict())
        return 404, {'error': 'Unknown route'}, None

    def writes(self):
        return [(request.method, request.path) for request in self.requests
                if request.method != 'GET' and request.path != TOKEN_PATH]

    def bodies(self, method, path):
        return [request.body for request in self.requests if (request.method, request.path) == (method, path)]

    # Lookups for the tests and the routes.

    def scope_named(self, name):
        return next((scope for scope in self.scopes.values() if scope['name'] == name), None)

    def client_named(self, client_id):
        return next((client for client in self.clients.values() if client['clientId'] == client_id), None)

    def authz_named(self, name):
        return next((policy for policy in self.authz.values() if policy['name'] == name), None)

    def authz_path(self):
        return f"{R}/clients/{self.client_named('admin-permissions')['id']}/authz/resource-server"

    def link_names(self, client_id, kind):
        return sorted(self.scopes[sid]['name'] for sid in self.links[self.client_named(client_id)['id']][kind])

    def mcp_view(self):
        """MCP's objects in the realm, without generated IDs: clients, groups and scopes by name."""
        client = self.client_named('ilm-mcp')
        if client is not None:
            client = {**without_id(client), 'defaultClientScopes': self.link_names('ilm-mcp', 'default'),
                      'optionalClientScopes': self.link_names('ilm-mcp', 'optional')}
        return {
            'clientScopes': {name: normalized(self.scope_named(name)) for name in MCP_SCOPES if self.scope_named(name)},
            'client': client,
            'defaultOptionalClientScopes': sorted(self.scopes[sid]['name']
                                                  for sid in self.realm_scopes['default-optional']),
            'clientProfiles': self.profiles,
            'clientPolicies': self.policies,
            'adminPermissionsEnabled': self.realm['adminPermissionsEnabled'],
            'groups': sorted(group['name'] for group in self.groups.values()),
            'authorization': {policy['name']: self.authz_view(policy) for policy in self.authz.values()},
        }

    def authz_view(self, policy):
        view = {key: value for key, value in policy.items() if key not in ('id', 'name')}
        if policy['type'] == 'client':
            view['clients'] = [self.clients[cid]['clientId'] for cid in policy['clients']]
        else:
            view['resources'] = [self.groups[rid]['name'] if rid in self.groups else rid for rid in policy['resources']]
        return view

    # Routes. Each returns the status, the JSON payload or None, and the Location header or None.

    def serverinfo(self, **_):
        return 200, {'features': [{'name': name, 'enabled': name in self.features} for name in FEATURES]}, None

    def get_realm(self, **_):
        return (404, {'error': 'Realm not found.'}, None) if self.realm is None else (200, self.realm, None)

    def put_realm(self, body, **_):
        self.realm.update(body)
        if self.realm['adminPermissionsEnabled'] and self.client_named('admin-permissions') is None:
            self.create_client({'clientId': 'admin-permissions'})
        return 204, None, None

    def create_scope(self, body):
        if self.scope_named(body['name']):
            return 409, {'errorMessage': f"Client Scope {body['name']} already exists"}, None
        scope = {**copy.deepcopy(body), 'id': body.get('id') or new_id()}
        for mapper in scope.setdefault('protocolMappers', []):
            mapper['id'] = new_id()
        self.scopes[scope['id']] = scope
        return 201, None, f"{self.url}{R}/client-scopes/{scope['id']}"

    def update_scope(self, sid, body, **_):
        scope = self.scopes[sid]
        for key, value in body.items():
            if key == 'attributes':
                scope['attributes'] = {**scope.get('attributes', {}), **value}
            elif key not in ('id', 'protocolMappers'):
                scope[key] = value
        return 204, None, None

    def delete_scope(self, sid, **_):
        del self.scopes[sid]
        for kind, assigned in self.realm_scopes.items():
            self.realm_scopes[kind] = [scope for scope in assigned if scope != sid]
        for links in self.links.values():
            for kind in links:
                links[kind] = [scope for scope in links[kind] if scope != sid]
        return 204, None, None

    def add_mapper(self, sid, body, **_):
        mappers = self.scopes[sid]['protocolMappers']
        if any(mapper['name'] == body['name'] for mapper in mappers):
            return 409, {'errorMessage': 'Protocol mapper exists with same name'}, None
        mappers.append({**body, 'id': new_id()})
        return 201, None, None

    def update_mapper(self, sid, mid, body, **_):
        mappers = self.scopes[sid]['protocolMappers']
        index = next(i for i, mapper in enumerate(mappers) if mapper['id'] == mid)
        mappers[index] = {**body, 'id': mid}
        return 204, None, None

    def realm_scope_list(self, kind, **_):
        return 200, [{'id': sid, 'name': self.scopes[sid]['name'], 'protocol': 'openid-connect'}
                     for sid in self.realm_scopes[kind]], None

    def assign_realm_scope(self, kind, sid, **_):
        if sid not in self.scopes:
            return 404, {'error': 'Client scope not found'}, None
        if any(sid in assigned for assigned in self.realm_scopes.values()):
            return 409, {'errorMessage': 'Duplicate resource error'}, None
        self.realm_scopes[kind].append(sid)
        return 204, None, None

    def unassign_realm_scope(self, kind, sid, **_):
        if sid not in self.realm_scopes[kind]:
            return 404, {'error': 'Client scope not found'}, None
        self.realm_scopes[kind].remove(sid)
        return 204, None, None

    def list_clients(self, query, **_):
        clients = [client for client in self.clients.values() if query.get('clientId') in (None, client['clientId'])]
        return 200, [{**client, 'defaultClientScopes': self.link_names(client['clientId'], 'default'),
                      'optionalClientScopes': self.link_names(client['clientId'], 'optional')}
                     for client in clients], None

    def create_client(self, body):
        if self.client_named(body['clientId']):
            return 409, {'errorMessage': f"Client {body['clientId']} already exists"}, None
        client = {key: copy.deepcopy(value) for key, value in body.items()
                  if key not in ('defaultClientScopes', 'optionalClientScopes')}
        client['id'] = body.get('id') or new_id()
        for mapper in client.get('protocolMappers', []):
            mapper['id'] = new_id()
        self.clients[client['id']] = client
        # A client created with its own scope lists gets the scopes that exist; otherwise the realm's defaults.
        if 'defaultClientScopes' in body or 'optionalClientScopes' in body:
            self.links[client['id']] = {kind: [self.scope_named(name)['id'] for name in body.get(key, [])
                                               if self.scope_named(name)]
                                        for kind, key in (('default', 'defaultClientScopes'),
                                                          ('optional', 'optionalClientScopes'))}
        else:
            self.links[client['id']] = {'default': list(self.realm_scopes['default-default']),
                                        'optional': list(self.realm_scopes['default-optional'])}
        return 201, None, f"{self.url}{R}/clients/{client['id']}"

    def update_client(self, cid, body, **_):
        client = self.clients[cid]
        for key, value in body.items():
            if key == 'attributes':
                client['attributes'] = {**client.get('attributes', {}), **value}
            elif key not in ('id', 'defaultClientScopes', 'optionalClientScopes'):
                client[key] = value
        return 204, None, None

    def delete_client(self, cid, **_):
        del self.clients[cid]
        del self.links[cid]
        return 204, None, None

    def client_scopes(self, cid, kind, **_):
        return 200, [{'id': sid, 'name': self.scopes[sid]['name']} for sid in self.links[cid][kind]], None

    def link(self, cid, kind, sid, **_):
        if sid not in self.scopes:
            return 404, {'error': 'Client scope not found'}, None
        if any(sid in linked for linked in self.links[cid].values()):
            return 409, {'errorMessage': 'Duplicate resource error'}, None
        self.links[cid][kind].append(sid)
        return 204, None, None

    def get_client_policies(self, key, **_):
        return 200, {key: getattr(self, key)}, None

    def put_client_policies(self, key, body, **_):
        entries = body[key]
        if 'CIMD' not in self.features and uses_cimd(entries):
            return 400, {'error': 'invalid_request', 'error_description': 'Invalid executor or condition'}, None
        for entry in entries:
            for part in entry.get('executors', []) + entry.get('conditions', []):
                if part.get('condition') == 'client-scopes' and not all(
                        self.scope_named(name) for name in part['configuration']['scopes']):
                    return 400, {'error': 'invalid_request', 'error_description': 'Invalid client-scopes'}, None
            if key == 'policies' and not set(entry['profiles']) <= {profile['name'] for profile in self.profiles}:
                return 400, {'error': 'invalid_request',
                             'error_description': f"Policy {entry['name']} contains invalid profile"}, None
        setattr(self, key, copy.deepcopy(entries))
        return 204, None, None

    def search_groups(self, query, **_):
        return 200, [group for group in self.groups.values() if group['name'] == query['search']], None

    def create_group(self, body, **_):
        if any(group['name'] == body['name'] for group in self.groups.values()):
            return 409, {'errorMessage': f"Top level group named '{body['name']}' already exists."}, None
        group = {'id': new_id(), 'name': body['name'], 'path': '/' + body['name'], 'subGroups': []}
        self.groups[group['id']] = group
        return 201, None, f"{self.url}{R}/groups/{group['id']}"

    def admin_client(self, admin):
        client = self.client_named('admin-permissions')
        return client is not None and client['id'] == admin

    def search_authz(self, admin, query, **_):
        if not self.admin_client(admin):
            return 404, {'error': 'Could not find client'}, None
        policy = self.authz_named(query['name'])
        if policy is None:
            return 204, None, None
        view = {key: policy[key] for key in ('id', 'name', 'type', 'logic', 'decisionStrategy')}
        if policy['type'] == 'client':
            return 200, {**view, 'config': {'clients': json.dumps(policy['clients'])}}, None
        return 200, {**view, 'resourceType': policy['resourceType']}, None

    def store_client_policy(self, pid, body):
        clients = [self.client_named(value) or self.clients.get(value) for value in body['clients']]
        if None in clients:
            return 400, {'error': 'invalid_request', 'error_description': 'Client could not be found'}, None
        self.authz[pid] = {'id': pid, 'name': body['name'], 'type': 'client', 'logic': body['logic'],
                           'decisionStrategy': body['decisionStrategy'], 'clients': [c['id'] for c in clients]}
        return 201, {**body, 'id': pid}, None

    def store_permission(self, pid, body):
        if body['decisionStrategy'] != 'UNANIMOUS':
            return 400, {'error': 'invalid_request', 'error_description': 'Only UNANIMOUS is supported'}, None
        resources = body.get('resources', self.authz[pid]['resources'] if pid in self.authz else [])
        if body['resourceType'] == 'Groups' and not set(resources) <= set(self.groups):
            return 400, {'error': 'invalid_request', 'error_description': 'Resource does not exist'}, None
        if not all(self.authz_named(name) for name in body['policies']):
            return 400, {'error': 'invalid_request', 'error_description': 'Policy not found'}, None
        self.authz[pid] = {'id': pid, 'name': body['name'], 'type': 'scope', 'logic': body['logic'],
                           'decisionStrategy': body['decisionStrategy'], 'resourceType': body['resourceType'],
                           'resources': list(resources), 'scopes': list(body['scopes']),
                           'policies': list(body['policies'])}
        return 201, {**body, 'id': pid}, None

    def create_client_policy(self, admin, body, **_):
        if not self.admin_client(admin) or self.authz_named(body['name']):
            return 409, {'error': 'Policy with same name already exists'}, None
        return self.store_client_policy(new_id(), body)

    def create_permission(self, admin, body, **_):
        if not self.admin_client(admin) or self.authz_named(body['name']):
            return 409, {'error': 'Policy with same name already exists'}, None
        return self.store_permission(new_id(), body)

    def get_client_policy(self, admin, pid, **_):
        return 200, {key: value for key, value in self.authz[pid].items()}, None

    def update_client_policy(self, admin, pid, body, **_):
        return self.store_client_policy(pid, body)

    def update_permission(self, admin, pid, body, **_):
        # Without a resources key, Keycloak keeps the permission's resources.
        return self.store_permission(pid, body)

    def authz_part(self, admin, pid, part, **_):
        policy = self.authz[pid]
        if part == 'scopes':
            return 200, [{'name': name} for name in policy.get('scopes', [])], None
        if part == 'associatedPolicies':
            return 200, [{'name': name} for name in policy.get('policies', [])], None
        if policy['type'] != 'scope':
            return 200, [], None
        if not policy['resources']:
            return 200, [{'name': policy['resourceType']}], None
        return 200, [{'name': rid, **({'displayName': self.groups[rid]['name']} if rid in self.groups else {})}
                     for rid in policy['resources']], None

    def delete_authz(self, admin, pid, **_):
        del self.authz[pid]
        return 204, None, None


def desired(cimd=True, group=None, secret=SECRET):
    return mcp_realm.desired_objects(HOST, secret, cimd, group)


def with_copies(objects, copies):
    """objects with copies of the ilm client's mappers in ilm-mcp-upstream, which enable adds when it plans."""
    return {**objects, 'clientScopes': [
        {**scope, 'protocolMappers': scope['protocolMappers'] + copies} if scope['name'] == 'ilm-mcp-upstream'
        else scope for scope in objects['clientScopes']]}


def expected_view(objects, ilm_mappers=ILM_MAPPERS):
    """What FakeKeycloak.mcp_view() shows once enable has applied objects to the fake's realm, whose ilm client has
    ilm_mappers."""
    objects = with_copies(objects, [without_id(mapper) for mapper in ilm_mappers
                                    if mapper['name'] in ('Username', 'Groups')])
    group, permission = objects['group'], objects['permission']
    client = {**objects['client'], 'defaultClientScopes': sorted(objects['client']['defaultClientScopes']),
              'optionalClientScopes': sorted(objects['client']['optionalClientScopes'])}
    return {
        'clientScopes': {scope['name']: normalized(scope) for scope in objects['clientScopes']},
        'client': client,
        'defaultOptionalClientScopes': sorted(set(REALM_OPTIONAL_SCOPES) | set(objects['defaultOptionalClientScopes'])),
        'clientProfiles': objects['clientProfiles'],
        'clientPolicies': objects['clientPolicies'],
        'adminPermissionsEnabled': True,
        'groups': [group] if group else [],
        'authorization': {
            objects['clientPolicy']['name']: without_name(objects['clientPolicy']),
            permission['name']: {**without_name(permission), 'resources': [group] if group else []},
        },
    }


def without_name(entry):
    return {key: value for key, value in entry.items() if key != 'name'}


def typed(policy):
    """An authorization policy of a realm import in the form the Admin API takes."""
    config = policy['config']
    result = {key: policy[key] for key in ('name', 'type', 'logic', 'decisionStrategy')}
    if policy['type'] == 'client':
        return {**result, 'clients': json.loads(config['clients'])}
    return {**result, 'resourceType': config['defaultResourceType'], 'resources': json.loads(config['resources']),
            'scopes': json.loads(config['scopes']), 'policies': json.loads(config['applyPolicies'])}


def planned(output):
    return [line for line in output.splitlines() if line.startswith('- ')]


class McpRealmScript(unittest.TestCase):
    def keycloak(self, **options):
        return FakeKeycloak(self, **options)

    def run_script(self, fake, action, *options, secret=SECRET):
        """Runs the command line against the fake with an operator's answers; returns the exit code and the output."""
        answers = [fake.url + '/', 'admin'] + ([HOST] if action == 'enable' else [])
        hidden = [ADMIN_PASSWORD] + ([secret] if action == 'enable' else [])
        output = io.StringIO()
        with mock.patch('builtins.input', side_effect=answers), mock.patch('getpass.getpass', side_effect=hidden), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = mcp_realm.main([action, *options])
        return code, output.getvalue()

    def succeed(self, fake, action, *options, **kwargs):
        fake.requests.clear()
        code, output = self.run_script(fake, action, *options, **kwargs)
        self.assertEqual(code, 0, output)
        return output

    def test_creates_the_missing_objects(self):
        for name, options, prepare in [
                ('realm migrated with the delegation features', (), lambda fake: None),
                ('realm without delegation:client', (),
                 lambda fake: fake.delete_scope(fake.scope_named('delegation:client')['id'])),
                ('group form', ('--group', GROUP), lambda fake: None),
                ('group form with an existing group', ('--group', GROUP),
                 lambda fake: fake.create_group({'name': GROUP}))]:
            with self.subTest(name):
                fake = self.keycloak()
                prepare(fake)
                groups = dict(fake.groups)
                self.succeed(fake, 'enable', *options)
                self.assertEqual(fake.mcp_view(), expected_view(desired(group=options[-1] if options else None)))
                self.assertNotIn('DELETE', {method for method, _ in fake.writes()})
                # Added after the admin-permissions client exists, so that mcp:access stays off it.
                self.assertNotIn('mcp:access', fake.link_names('admin-permissions', 'optional'))
                if groups:
                    self.assertEqual(fake.groups, groups)
                    self.assertEqual(fake.authz_named(SELECTED_USERS)['resources'], list(groups))

    def test_second_enable_changes_nothing(self):
        for options in [(), ('--group', GROUP), ('--no-cimd',)]:
            with self.subTest(options=options):
                fake = self.keycloak()
                self.succeed(fake, 'enable', *options)
                output = self.succeed(fake, 'enable', *options)
                self.assertEqual(fake.writes(), [])
                self.assertIn('Nothing to change', output)

    def test_corrects_only_fields_it_owns(self):
        fake = self.keycloak()
        fake.profiles, fake.policies = [copy.deepcopy(FOREIGN_PROFILE)], [copy.deepcopy(FOREIGN_POLICY)]
        self.succeed(fake, 'enable')
        access, upstream, client = fake.scope_named('mcp:access'), fake.scope_named('ilm-mcp-upstream'), \
            fake.client_named('ilm-mcp')
        access['attributes'].update({'include.in.token.scope': 'false', 'kc.unrelated': 'keep'})
        resource = next(mapper for mapper in access['protocolMappers'] if mapper['name'] == 'mcp-public-resource')
        resource['config'].update({'included.custom.audience': 'https://drift.example.invalid/mcp',
                                   'kc.unrelated': 'keep'})
        upstream['protocolMappers'] = [mapper for mapper in upstream['protocolMappers'] if mapper['name'] != 'Groups']
        client.update(fullScopeAllowed=True, description='kept')
        client['attributes']['kc.unrelated'] = 'keep'
        fake.links[client['id']]['optional'].remove(upstream['id'])
        fake.profiles[1]['executors'][0]['configuration']['auto-configure'] = False
        fake.authz_named(DELEGATING_CLIENT)['logic'] = 'NEGATIVE'
        fake.authz_named(ALL_USERS)['resources'] = ['narrowed-to-one-user']
        authz = fake.authz_path()
        policy, permission = fake.authz_named(DELEGATING_CLIENT)['id'], fake.authz_named(ALL_USERS)['id']

        self.succeed(fake, 'enable')
        self.assertEqual(fake.writes(), [
            ('POST', f"{R}/client-scopes/{upstream['id']}/protocol-mappers/models"),
            ('PUT', f"{R}/client-scopes/{access['id']}"),
            ('PUT', f"{R}/client-scopes/{access['id']}/protocol-mappers/models/{resource['id']}"),
            ('PUT', f"{R}/clients/{client['id']}"),
            ('PUT', f"{R}/clients/{client['id']}/optional-client-scopes/{upstream['id']}"),
            ('PUT', f'{R}/client-policies/profiles'),
            ('PUT', f'{authz}/policy/client/{policy}'),
            ('PUT', f'{authz}/permission/scope/{permission}'),
        ])
        self.assertNotIn('protocolMappers', fake.bodies('PUT', f"{R}/client-scopes/{access['id']}")[0])
        self.assertNotIn('secret', fake.bodies('PUT', f"{R}/clients/{client['id']}")[0])
        # The permission covers all users again only when the correction says so.
        self.assertEqual(fake.bodies('PUT', f'{authz}/permission/scope/{permission}')[0]['resources'], [])
        view = fake.mcp_view()
        for unrelated in (view['clientScopes']['mcp:access']['attributes'],
                          view['clientScopes']['mcp:access']['protocolMappers'][1]['config'],
                          view['client']['attributes']):
            self.assertEqual(unrelated.pop('kc.unrelated'), 'keep')
        self.assertEqual(view['client'].pop('description'), 'kept')
        expected = expected_view(desired())
        expected['clientProfiles'] = [FOREIGN_PROFILE] + expected['clientProfiles']
        expected['clientPolicies'] = [FOREIGN_POLICY] + expected['clientPolicies']
        self.assertEqual(view, expected)

        client = fake.client_named('ilm-mcp')
        client['secret'] = ROTATED_SECRET
        self.succeed(fake, 'enable')
        self.assertEqual(fake.writes(), [('PUT', f"{R}/clients/{client['id']}")])
        self.assertTrue(fake.client_named('ilm-mcp')['secret'] == SECRET, 'the secret was not set')
        self.succeed(fake, 'enable')
        self.assertEqual(fake.writes(), [])

    def test_enable_never_deletes(self):
        for options in [(), ('--group', GROUP)]:
            with self.subTest(options=options):
                fake = self.keycloak()
                self.succeed(fake, 'enable', *options)
                writes = fake.writes()
                fake.scope_named('mcp:access')['protocolMappers'].append(
                    {'id': new_id(), 'name': 'kc-extra', 'protocol': 'openid-connect',
                     'protocolMapper': 'oidc-audience-mapper', 'config': {'included.client.audience': 'ilm'}})
                fake.links[fake.client_named('ilm-mcp')['id']]['optional'].append(
                    fake.scope_named('delegation:user')['id'])
                fake.scope_named('ilm-mcp-upstream')['protocolMappers'].pop()
                self.succeed(fake, 'enable', *options)
                writes += fake.writes()
                self.assertEqual([write for write in writes if write[0] == 'DELETE'], [])
                mappers = fake.scope_named('mcp:access')['protocolMappers']
                self.assertIn('kc-extra', [mapper['name'] for mapper in mappers])
                self.assertIn('delegation:user', fake.link_names('ilm-mcp', 'optional'))

    def test_switching_forms_removes_only_the_other_permission(self):
        fake = self.keycloak()
        self.succeed(fake, 'enable')
        authz, all_users = fake.authz_path(), fake.authz_named(ALL_USERS)['id']
        self.succeed(fake, 'enable', '--group', GROUP)
        self.assertEqual([path for method, path in fake.writes() if method == 'DELETE'],
                         [f'{authz}/policy/{all_users}'])
        self.assertEqual(fake.mcp_view(), expected_view(desired(group=GROUP)))

        selected_users = fake.authz_named(SELECTED_USERS)['id']
        self.succeed(fake, 'enable')
        self.assertEqual([path for method, path in fake.writes() if method == 'DELETE'],
                         [f'{authz}/policy/{selected_users}'])
        expected = expected_view(desired())
        expected['groups'] = [GROUP]
        self.assertEqual(fake.mcp_view(), expected)

    def test_enable_needs_the_delegation_features(self):
        for feature in ('TOKEN_EXCHANGE_DELEGATION', 'PARAMETERIZED_SCOPES'):
            for options in [(), ('--no-cimd',)]:
                with self.subTest(feature=feature, options=options):
                    fake = self.keycloak(features=set(FEATURES) - {feature})
                    code, output = self.run_script(fake, 'enable', *options)
                    self.assertEqual(code, 1, output)
                    self.assertIn(feature.lower().replace('_', '-'), output)
                    self.assertEqual(fake.writes(), [])

    def test_enable_needs_the_cimd_feature(self):
        fake = self.keycloak(features=set(FEATURES) - {'CIMD'})
        code, output = self.run_script(fake, 'enable')
        self.assertEqual(code, 1, output)
        self.assertIn('cimd', output)
        self.assertIn('--no-cimd', output)
        self.assertEqual(fake.writes(), [])
        self.succeed(fake, 'enable', '--no-cimd')
        self.assertEqual(fake.mcp_view(), expected_view(desired(cimd=False)))

        # Once the feature is off, Keycloak refuses a client policy list that still holds mcp-cimd, and fails client
        # writes while the realm stores it: the removal comes before the correction of a drifted client.
        fake = self.keycloak()
        self.succeed(fake, 'enable')
        fake.features.discard('CIMD')
        client = fake.client_named('ilm-mcp')
        client['fullScopeAllowed'] = True
        self.succeed(fake, 'enable', '--no-cimd')
        self.assertEqual(fake.writes(), [('PUT', f'{R}/client-policies/policies'),
                                         ('PUT', f'{R}/client-policies/profiles'),
                                         ('PUT', f"{R}/clients/{client['id']}")])
        self.assertEqual(fake.mcp_view(), expected_view(desired(cimd=False)))

    def test_client_with_secret_rotation_state_is_not_updated(self):
        fake = self.keycloak()
        self.succeed(fake, 'enable')
        client = fake.client_named('ilm-mcp')
        client['attributes'].update({'client.secret.rotated': PREVIOUS_SECRET,
                                     'client.secret.rotated.expiration.time': '1761733600'})
        self.assertIn('Nothing to change', self.succeed(fake, 'enable'))
        self.assertEqual(fake.writes(), [])
        # An update would clear the rotation state, which ends the grace period of the previous secret.
        for name, options, secret in [('drift', (), SECRET), ('drift, dry run', ('--dry-run',), SECRET),
                                      ('another secret', (), ROTATED_SECRET)]:
            with self.subTest(name):
                client['fullScopeAllowed'] = name.startswith('drift')
                fake.requests.clear()
                code, output = self.run_script(fake, 'enable', *options, secret=secret)
                self.assertEqual(code, 1, output)
                self.assertIn('Client ilm-mcp has secret rotation state', output)
                self.assertFalse(PREVIOUS_SECRET in output, 'the previous secret was printed')
                self.assertEqual(fake.writes(), [])

    def test_upstream_scope_copies_the_ilm_client_mappers(self):
        mappers = [GROUP_MEMBERSHIP_ROLES if mapper['name'] == 'Groups' else mapper for mapper in ILM_MAPPERS]
        fake = self.keycloak(ilm_mappers=mappers)
        self.succeed(fake, 'enable')
        upstream = {mapper['name']: without_id(mapper)
                    for mapper in fake.scope_named('ilm-mcp-upstream')['protocolMappers']}
        self.assertEqual(upstream['Groups'], GROUP_MEMBERSHIP_ROLES)
        self.assertNotIn('Audience', upstream)
        self.assertEqual(fake.mcp_view(), expected_view(desired(), mappers))
        self.succeed(fake, 'enable')
        self.assertEqual(fake.writes(), [])

    def test_enable_stops_without_an_ilm_client_mapper(self):
        for missing, message in [('Username', 'Client ilm has no protocol mapper Username'),
                                 ('Groups', 'Client ilm has no protocol mapper Groups'),
                                 ('ilm', 'Client ilm not found')]:
            for options in [(), ('--dry-run',)]:
                with self.subTest(missing=missing, options=options):
                    fake = self.keycloak(ilm_mappers=[mapper for mapper in ILM_MAPPERS if mapper['name'] != missing])
                    if missing == 'ilm':
                        fake.delete_client(fake.client_named('ilm')['id'])
                    code, output = self.run_script(fake, 'enable', *options)
                    self.assertEqual(code, 1, output)
                    self.assertIn(message, output)
                    self.assertEqual(fake.writes(), [])

    def test_enable_stops_on_a_scope_of_the_wrong_type(self):
        def ilm_mcp_upstream_as_default(fake):
            links, scope = fake.links[fake.client_named('ilm-mcp')['id']], fake.scope_named('ilm-mcp-upstream')['id']
            links['optional'].remove(scope)
            links['default'].append(scope)

        def mcp_access_as_realm_default(fake):
            scope = fake.scope_named('mcp:access')['id']
            fake.realm_scopes['default-optional'].remove(scope)
            fake.realm_scopes['default-default'].append(scope)

        # Changing the type of an assigned scope takes a DELETE, which enable does not make.
        for move, message in [
                (ilm_mcp_upstream_as_default,
                 'Client scope ilm-mcp-upstream is assigned to client ilm-mcp as default, but must be optional.'),
                (mcp_access_as_realm_default,
                 'Client scope mcp:access is assigned to the realm as default, but must be default optional.')]:
            for options in [(), ('--dry-run',)]:
                with self.subTest(move=move.__name__, options=options):
                    fake = self.keycloak()
                    self.succeed(fake, 'enable')
                    move(fake)
                    fake.requests.clear()
                    code, output = self.run_script(fake, 'enable', *options)
                    self.assertEqual(code, 1, output)
                    self.assertIn(message, output)
                    self.assertEqual(fake.writes(), [])

    def test_cleanup_removes_cimd_first(self):
        for features in [FEATURES, set(FEATURES) - {'CIMD'}]:
            with self.subTest(features=sorted(features)):
                fake = self.keycloak()
                self.succeed(fake, 'enable')
                fake.features = set(features)
                authz = fake.authz_path()
                ids = {name: fake.authz_named(name)['id'] for name in (ALL_USERS, DELEGATING_CLIENT)}
                client, access, upstream = (fake.client_named('ilm-mcp')['id'], fake.scope_named('mcp:access')['id'],
                                            fake.scope_named('ilm-mcp-upstream')['id'])
                self.succeed(fake, 'cleanup')
                self.assertEqual(fake.writes(), [
                    ('PUT', f'{R}/client-policies/policies'),
                    ('PUT', f'{R}/client-policies/profiles'),
                    ('PUT', f'{R}/client-policies/policies'),
                    ('PUT', f'{R}/client-policies/profiles'),
                    ('DELETE', f'{authz}/policy/{ids[ALL_USERS]}'),
                    ('DELETE', f'{authz}/policy/{ids[DELEGATING_CLIENT]}'),
                    ('DELETE', f'{R}/clients/{client}'),
                    ('DELETE', f'{R}/default-optional-client-scopes/{access}'),
                    ('DELETE', f'{R}/client-scopes/{access}'),
                    ('DELETE', f'{R}/client-scopes/{upstream}'),
                ])
                policies, profiles = [request.body for request in fake.requests if request.method == 'PUT'][:2]
                self.assertEqual([entry['name'] for entry in policies['policies']], ['mcp-pkce'])
                self.assertEqual([entry['name'] for entry in profiles['profiles']], ['mcp-pkce'])

    def test_cleanup_keeps_groups_and_delegation_scope(self):
        fake = self.keycloak()
        self.succeed(fake, 'enable', '--group', GROUP)
        self.succeed(fake, 'cleanup')
        self.assertEqual(fake.mcp_view(), {
            'clientScopes': {'delegation:client': normalized(DELEGATION_CLIENT)},
            'client': None,
            'defaultOptionalClientScopes': sorted(REALM_OPTIONAL_SCOPES),
            'clientProfiles': [],
            'clientPolicies': [],
            'adminPermissionsEnabled': True,
            'groups': [GROUP],
            'authorization': {},
        })

    def test_second_cleanup_changes_nothing(self):
        fake = self.keycloak()
        self.succeed(fake, 'enable', '--group', GROUP)
        self.succeed(fake, 'cleanup')
        output = self.succeed(fake, 'cleanup')
        self.assertEqual(fake.writes(), [])
        self.assertIn('Nothing to change', output)

    def test_dry_run_writes_nothing(self):
        fake = self.keycloak()
        for action, options in [('enable', ()), ('enable', ('--group', GROUP)), ('cleanup', ())]:
            with self.subTest(action=action, options=options):
                before = copy.deepcopy(fake.mcp_view())
                dry_run = self.succeed(fake, action, '--dry-run', *options)
                self.assertEqual(fake.writes(), [])
                self.assertEqual(fake.mcp_view(), before)
                self.assertTrue(planned(dry_run))
                # The dry run lists every change the real run makes, including those on objects it creates.
                self.assertEqual(planned(self.succeed(fake, action, *options)), planned(dry_run))

    def test_secret_is_never_printed(self):
        fake = self.keycloak()
        outputs = [self.run_script(fake, 'enable', '--dry-run')[1], self.run_script(fake, 'enable')[1],
                   self.run_script(fake, 'enable', '--dry-run', secret=ROTATED_SECRET)[1],
                   self.run_script(fake, 'enable', secret=ROTATED_SECRET)[1]]
        fake.fail = ('PUT', f"{R}/clients/{fake.client_named('ilm-mcp')['id']}")
        code, output = self.run_script(fake, 'enable')
        self.assertEqual(code, 1, output)
        self.assertIn('HTTP 400', output)
        outputs += [output, self.run_script(fake, 'cleanup', '--dry-run')[1]]
        outputs.append(repr(mcp_realm.Change('PUT', f'{R}/clients/id', {'secret': SECRET}, 'Update client ilm-mcp')))
        for output in outputs:
            for value in (SECRET, ROTATED_SECRET, ADMIN_PASSWORD, TOKEN):
                self.assertFalse(value in output, 'a secret or token was printed')

    def test_both_actions_need_the_realm(self):
        fake = self.keycloak()
        fake.realm = None
        for action in ('enable', 'cleanup'):
            with self.subTest(action=action):
                code, output = self.run_script(fake, action)
                self.assertEqual(code, 1, output)
                self.assertIn("Realm 'ILM'", output)
                self.assertEqual(fake.writes(), [])

    def test_desired_objects_match_the_realm_import(self):
        plain = realm_with(mcp_values(), enabled=False)
        # enable copies the mappers of the realm's own ilm client, as the import copies those of the chart's realm.
        copies = mcp_realm.ilm_claim_mappers(next(client for client in plain['clients'] if client['clientId'] == 'ilm'))

        def added(imported, key, field='name'):
            existing = {entry[field] for entry in plain[key]}
            return [entry for entry in imported[key] if entry[field] not in existing]

        def view(objects):
            return {**objects, 'clientScopes': {scope['name']: normalized(scope) for scope in objects['clientScopes']},
                    'defaultOptionalClientScopes': sorted(objects['defaultOptionalClientScopes'])}

        for group in (None, GROUP):
            for cimd in (True, False):
                with self.subTest(group=group, cimd=cimd):
                    settings = {'cimd': {'enabled': cimd}, **({'delegation': {'group': group}} if group else {})}
                    imported = realm_with(mcp_values(), **settings)
                    clients = {client['clientId']: client for client in added(imported, 'clients', 'clientId')}
                    client = copy.deepcopy(clients['ilm-mcp'])
                    # Keycloak's migration of the imported realm, which says 24.0.2, adds basic to every client and
                    # delegation:client to the realm's default optional scopes.
                    client['defaultClientScopes'].append('basic')
                    policy, permission = map(typed, clients['admin-permissions']['authorizationSettings']['policies'])
                    resources = permission.pop('resources')
                    # The resource of the all-users permission is its type; enable looks the group up by name.
                    self.assertEqual(resources, [imported['groups'][0]['id']] if group else ['Users'])
                    optional = set(imported['defaultOptionalClientScopes']) - set(plain['defaultOptionalClientScopes'])
                    self.assertEqual(view({
                        'clientScopes': added(imported, 'clientScopes'),
                        'client': client,
                        'defaultOptionalClientScopes': [*optional, 'delegation:client'],
                        'clientProfiles': imported['clientProfiles']['profiles'],
                        'clientPolicies': imported['clientPolicies']['policies'],
                        'adminPermissionsEnabled': imported['adminPermissionsEnabled'],
                        'group': imported['groups'][0]['name'] if imported['groups'] else None,
                        'clientPolicy': policy,
                        'permission': permission,
                    }), view(with_copies(desired(cimd, group), copies)))


if __name__ == '__main__':
    unittest.main()
