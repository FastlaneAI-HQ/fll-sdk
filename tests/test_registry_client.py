import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from fastlanelabs_sdk import registry_client

KEY = 'flr_ph_0123abcd_' + 'ab' * 24


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        server = self.server
        server.seen.append((self.path, self.headers.get('Authorization')))
        script = server.script
        status, body = script.pop(0) if len(script) > 1 else script[0]
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server(monkeypatch):
    httpd = HTTPServer(('127.0.0.1', 0), _Handler)
    httpd.seen = []
    httpd.script = [(200, b'')]
    thread = threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    for name in ('http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('FASTLANELABS_REGISTRY_URL', 'http://127.0.0.1:{0}/'.format(httpd.server_port))
    monkeypatch.setenv('FASTLANELABS_REGISTRY_KEY', KEY)
    monkeypatch.setattr(registry_client, 'BACKOFF', (0, 0))
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_sends_bearer_key_and_returns_bytes(server):
    server.script = [(200, b'\x00wheel')]
    assert registry_client.get_blob('contacts/1.2.3/app.whl') == b'\x00wheel'
    assert server.seen == [('/v1/files/contacts/1.2.3/app.whl', 'Bearer ' + KEY)]


def test_get_json_and_whoami(server):
    server.script = [(200, {'tenant': 'ph', 'key_id': '0123abcd', 'apps': ['contacts']})]
    assert registry_client.whoami()['tenant'] == 'ph'
    assert server.seen[-1][0] == '/v1/whoami'
    server.script = [(200, {'api_version': 1, 'apps': {}})]
    assert registry_client.get_json('catalog.json') == {'api_version': 1, 'apps': {}}
    assert server.seen[-1][0] == '/v1/files/catalog.json'


def test_segments_are_percent_quoted(server):
    server.script = [(200, b'{}')]
    registry_client.get_json('themes/a b/1.0.0/x?y#z.json')
    assert server.seen[-1][0] == '/v1/files/themes/a%20b/1.0.0/x%3Fy%23z.json'


@pytest.mark.parametrize('status,body,kind,text', [
    (401, {'detail': 'invalid key'}, registry_client.RegistryAuthError, 'registry key rejected: revoked or mistyped'),
    (403, {'detail': 'tenant ph is not entitled to app rfq'}, registry_client.RegistryForbidden, 'tenant ph is not entitled to app rfq'),
    (404, {'detail': 'not found'}, registry_client.RegistryNotFound, 'registry has no rfq/versions.json'),
    (429, {'detail': 'slow down'}, registry_client.RegistryThrottled, 'throttling'),
])
def test_error_mapping(server, status, body, kind, text):
    server.script = [(status, body)]
    with pytest.raises(kind) as failure:
        registry_client.get_json('rfq/versions.json')
    assert failure.value.status == status
    assert text in str(failure.value)
    assert isinstance(failure.value, registry_client.RegistryError)
    assert len(server.seen) == 1  # 4xx is never retried


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500])
def test_key_never_appears_in_errors(server, status):
    # Even a server that echoes the key back must not leak it into the message.
    server.script = [(status, {'detail': 'bad key ' + KEY})]
    with pytest.raises(registry_client.RegistryError) as failure:
        registry_client.get_blob('catalog.json')
    assert KEY not in str(failure.value)
    assert KEY[-48:] not in repr(failure.value)


def test_retries_5xx_then_succeeds(server):
    server.script = [(503, b'busy'), (503, b'busy'), (200, b'ok')]
    assert registry_client.get_blob('catalog.json') == b'ok'
    assert len(server.seen) == 3


def test_gives_up_after_two_retries(server):
    server.script = [(503, b'busy')]
    with pytest.raises(registry_client.RegistryUnavailable) as failure:
        registry_client.get_blob('catalog.json')
    assert failure.value.status == 503
    assert len(server.seen) == 3


def test_connection_failure_is_retried_and_reported(monkeypatch):
    import socket
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()  # nothing listens here now
    monkeypatch.setenv('FASTLANELABS_REGISTRY_URL', 'http://127.0.0.1:{0}'.format(port))
    monkeypatch.setenv('FASTLANELABS_REGISTRY_KEY', KEY)
    monkeypatch.setattr(registry_client, 'BACKOFF', (0, 0))
    with pytest.raises(registry_client.RegistryUnavailable) as failure:
        registry_client.whoami()
    assert 'unreachable' in str(failure.value)
    assert KEY not in str(failure.value)


@pytest.mark.parametrize('path', ['../catalog.json', '/catalog.json', 'a//b', 'a/./b', 'a/../b', '', 'a\\b', 'a\nb'])
def test_path_validation(server, path):
    with pytest.raises(ValueError):
        registry_client.get_blob(path)
    assert server.seen == []


def test_no_key_configured(server, monkeypatch):
    monkeypatch.delenv('FASTLANELABS_REGISTRY_KEY')
    with pytest.raises(registry_client.RegistryConfigError) as failure:
        registry_client.get_json('catalog.json')
    assert 'Set FASTLANELABS_REGISTRY_KEY' in str(failure.value)
    assert server.seen == []


def test_malformed_key_is_rejected_without_echoing_it(server, monkeypatch):
    monkeypatch.setenv('FASTLANELABS_REGISTRY_KEY', 'not-a-key-secret123')
    with pytest.raises(registry_client.RegistryConfigError) as failure:
        registry_client.whoami()
    assert 'secret123' not in str(failure.value)
    assert server.seen == []


def test_base_url_defaults_from_apps_yaml_and_refuses_placeholder_or_plain_http(monkeypatch, tmp_path):
    monkeypatch.delenv('FASTLANELABS_REGISTRY_URL', raising=False)
    monkeypatch.delenv('FASTLANELABS_REGISTRY_PATH', raising=False)
    assert registry_client.base_url().startswith('https://fll-registry.')
    # A config still carrying the placeholder is refused, not called.
    placeholder = tmp_path / 'apps.yaml'
    placeholder.write_text('registry:\n  url: https://REGISTRY_URL_PLACEHOLDER\napps: {}\n')
    monkeypatch.setenv('FASTLANELABS_REGISTRY_PATH', str(placeholder))
    with pytest.raises(registry_client.RegistryConfigError):
        registry_client.base_url()
    monkeypatch.delenv('FASTLANELABS_REGISTRY_PATH')
    monkeypatch.setenv('FASTLANELABS_REGISTRY_URL', 'https://registry.example.com/')
    assert registry_client.base_url() == 'https://registry.example.com'
    monkeypatch.setenv('FASTLANELABS_REGISTRY_URL', 'http://registry.example.com')
    with pytest.raises(registry_client.RegistryConfigError):
        registry_client.base_url()


def test_key_tenant(monkeypatch):
    monkeypatch.setenv('FASTLANELABS_REGISTRY_KEY', KEY)
    assert registry_client.key_tenant() == 'ph'
