"""Optional real Nginx routing/auth check: RUN_DOCKER_TESTS=1 pytest -q."""
import os
from pathlib import Path
import subprocess
import time
import uuid

import httpx
import pytest


@pytest.mark.skipif(os.getenv('RUN_DOCKER_TESTS') != '1', reason='Set RUN_DOCKER_TESTS=1 to run Docker ingress checks')
def test_ingress_routes_every_api_via_litellm_and_blocks_invalid_keys(tmp_path):
    prefix = 'aifactorybox-test-' + uuid.uuid4().hex[:10]
    containers = []

    def docker(*args):
        return subprocess.check_output(['docker', *args], text=True).strip()

    try:
        docker('network', 'create', prefix)
        for service, port in [('litellm-proxy', 4000), ('open-webui', 8080)]:
            path = tmp_path / f'{service}.conf'
            auth = '''location = /v1/models {
                if ($http_authorization = "") { return 401; }
                if ($http_authorization != "Bearer sk-test") { return 400; }
                return 200 "[]";
            }''' if service == 'litellm-proxy' else ''
            path.write_text(f'events {{}} http {{ server {{ listen {port}; {auth} location / {{ return 200 "{service}"; }} }} }}')
            name = f'{prefix}-{service}'
            docker('run', '-d', '--name', name, '--network', prefix, '--network-alias', service,
                   '-v', f'{path}:/etc/nginx/nginx.conf:ro', 'nginx:alpine')
            containers.append(name)
        name = f'{prefix}-ingress'
        config = Path(__file__).resolve().parents[1] / 'nginx/nginx.conf'
        docker('run', '-d', '--name', name, '--network', prefix, '-p', '127.0.0.1::80',
               '-v', f'{config}:/etc/nginx/nginx.conf:ro', 'nginx:alpine')
        containers.append(name)
        address = docker('port', name, '80/tcp').splitlines()[0]
        with httpx.Client(base_url=f'http://{address}', trust_env=False, timeout=5) as client:
            for attempt in range(30):
                try:
                    if client.get('/health').status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail('Nginx did not become ready')
            specialized = ['/v1/document/to-markdown', '/v1/privacy/anonymize',
                           '/v1/audio/transcribe', '/v1/audio/synthesize', '/v1/vision/ocr',
                           '/specialized/docs', '/specialized/openapi.json', '/specialized/health']
            for route in specialized:
                method = 'POST' if route.startswith('/v1/') else 'GET'
                assert client.request(method, route).status_code == 401
                assert client.request(method, route, headers={'Authorization': 'Bearer invalid'}).status_code == 401
                response = client.request(method, route, headers={'Authorization': 'Bearer sk-test'})
                assert response.status_code == 200, response.text
                assert response.text == 'litellm-proxy'
            for route in ['/v1/chat/completions', '/v1/embeddings', '/v1/rerank', '/rerank', '/docs', '/openapi.json']:
                assert client.get(route).text == 'litellm-proxy'
            assert client.get('/_litellm_auth').status_code == 404
            assert client.get('/').text == 'open-webui'
    finally:
        for name in reversed(containers):
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', prefix], capture_output=True)
