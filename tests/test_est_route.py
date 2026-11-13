"""Render the Kong configuration and check the fixed EST (RFC 7030) well-known route; no cluster access is required."""
import unittest

import yaml

import test_mcp
from helm_render import BASELINE, object_by_name, render, synthetic_values

EST_SERVICE = {
    'name': 'core-est',
    'host': 'core-service',
    'port': 8080,
    'protocol': 'http',
    'path': '/api/v1/protocols/.well-known/est',
    'routes': [{
        'name': 'core-est_route',
        'methods': ['GET', 'POST'],
        'strip_path': True,
        'preserve_host': True,
        'request_buffering': False,
        'response_buffering': False,
        'paths': ['/.well-known/est'],
    }],
}
EST_ONLY_KEYS = {'methods', 'request_buffering'}


def kong_config(objects, configmap='global-configmap'):
    return yaml.safe_load(object_by_name(objects, 'ConfigMap', configmap)['data']['kong.yml'])


def everything_on_values():
    values = test_mcp.mcp_values()
    values['global']['utils'] = {'enabled': True}
    values['global']['messaging']['remoteAccess'] = True
    values['apiGateway'] = {'cors': {'enabled': True}, 'logging': {'request': True}}
    values['auth'] = {'header': {'certificate': 'x-client-cert'}}
    return values


def without_est(config):
    return [service for service in config['services'] if service['name'] != 'core-est']


class ESTRouteTest(unittest.TestCase):
    def assert_est_route(self, config):
        services = [service['name'] for service in config['services']]
        self.assertEqual(services[:4], ['core', 'core-login-logout', 'core-est', 'fe-administrator'])
        self.assertEqual(config['services'][2], EST_SERVICE)
        for service in without_est(config):
            for route in service['routes']:
                self.assertFalse(EST_ONLY_KEYS & route.keys(), route['name'])

    def test_umbrella_renders_the_route_by_default(self):
        self.assert_est_route(kong_config(render('ilm', synthetic_values('ilm'))))

    def test_standalone_chart_renders_the_route_by_default(self):
        self.assert_est_route(kong_config(render('api-gateway-kong', {}), 'api-gateway-configmap'))

    def test_route_is_unchanged_with_every_option_on(self):
        config = kong_config(render('ilm', everything_on_values()))
        self.assert_est_route(config)
        services = {service['name'] for service in config['services']}
        self.assertTrue({'keycloak-internal-service', 'messaging-service', 'utils-service-service',
                         'mcp-server-service'} <= services)
        self.assertEqual([plugin['name'] for plugin in config['plugins']], ['cors', 'file-log'])
        mcp = next(service for service in config['services'] if service['name'] == 'mcp-server-service')
        self.assertEqual(mcp['plugins'][0]['config']['remove']['headers'], ['x-client-cert'])

    def test_request_log_omits_the_client_certificate_header(self):
        for header, expected in [(None, 'ssl-client-cert'), ('X-Client-Cert', 'x-client-cert')]:
            with self.subTest(header=header):
                values = everything_on_values()
                if header:
                    values['auth']['header']['certificate'] = header
                else:
                    del values['auth']
                config = kong_config(render('ilm', values))
                file_log = next(plugin for plugin in config['plugins'] if plugin['name'] == 'file-log')
                self.assertEqual(file_log['config']['custom_fields_by_lua'],
                                 {'request.headers.' + expected: 'return nil'})

    def test_standalone_request_log_omits_the_default_header(self):
        values = {'logging': {'request': True}}
        config = kong_config(render('api-gateway-kong', values), 'api-gateway-configmap')
        self.assertEqual(config['plugins'][0]['config']['custom_fields_by_lua'],
                         {'request.headers.ssl-client-cert': 'return nil'})

    def test_custom_configuration_is_rendered_verbatim(self):
        custom = "_format_version: '2.1'\nservices: []\n"
        values = synthetic_values('ilm')
        values['apiGateway'] = {'config': {'custom': custom}}
        config = object_by_name(render('ilm', values), 'ConfigMap', 'global-configmap')['data']['kong.yml']
        self.assertEqual(config.strip(), custom.strip())

    @unittest.skipUnless(BASELINE, 'explicit release compatibility baseline')
    def test_only_the_est_route_differs_from_the_baseline(self):
        edge_kinds = {'Ingress', 'Certificate', 'HTTPRoute', 'Gateway'}
        for name, values in [('defaults', synthetic_values('ilm')), ('everything on', everything_on_values())]:
            with self.subTest(values=name):
                current, baseline = render('ilm', values), render('ilm', values, baseline=True)
                config, baseline_config = kong_config(current), kong_config(baseline)
                self.assertEqual(without_est(config), baseline_config['services'])
                self.assertEqual(config.get('plugins'), baseline_config.get('plugins'))
                self.assertEqual([obj for obj in current if obj['kind'] in edge_kinds],
                                 [obj for obj in baseline if obj['kind'] in edge_kinds])


if __name__ == '__main__':
    unittest.main()
