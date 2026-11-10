"""Real community LiteLLM routes against local specialized-service doubles."""
import asyncio
import copy
from pathlib import Path

import httpx
import yaml


def test_real_proxy_passthrough_and_key_validation(monkeypatch):
    from aiohttp import web
    from litellm.proxy import proxy_server as proxy
    from litellm.proxy.pass_through_endpoints import pass_through_endpoints as passthrough

    async def run():
        received = []

        async def backend(request):
            entry = {'path': request.path, 'query': dict(request.query),
                     'authorization': request.headers.get('Authorization')}
            if request.content_type.startswith('multipart/'):
                form = await request.post()
                file = form['file']
                entry.update(filename=file.filename, content=file.file.read().decode())
            elif request.can_read_body:
                entry['body'] = await request.json()
            received.append(entry)
            if request.query.get('error'):
                return web.json_response({'detail': 'invalid image'}, status=422)
            if request.path == '/docs':
                return web.Response(text='<html>Scalar</html>', content_type='text/html')
            return web.json_response(entry)

        server = web.Application()
        server.router.add_route('*', '/{path:.*}', backend)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        settings = copy.deepcopy(yaml.safe_load(Path('config/litellm-config.yaml').read_text())['general_settings'])
        endpoints = settings['pass_through_endpoints']
        for endpoint in endpoints:
            endpoint['target'] = endpoint['target'].replace('http://orchestrator:8080', f'http://127.0.0.1:{port}')
        monkeypatch.setattr(proxy, 'general_settings', settings)
        monkeypatch.setattr(proxy, 'master_key', 'sk-test-gateway-key')
        monkeypatch.setattr(proxy, 'premium_user', False)
        monkeypatch.setattr(proxy, 'config_passthrough_endpoints', None)
        monkeypatch.setattr(passthrough, '_registered_pass_through_routes', {})
        original_routes = list(proxy.app.router.routes)
        try:
            await passthrough.initialize_pass_through_endpoints(endpoints)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy.app), base_url='http://gateway') as c:
                # This is the real endpoint used by the Nginx auth subrequest.
                assert (await c.get('/v1/models')).status_code in (401, 403)
                assert (await c.get('/v1/models', headers={'Authorization': 'Bearer sk-wrong'})).status_code in (400, 401, 403)
                assert (await c.get('/v1/models', headers={'Authorization': 'Bearer sk-test-gateway-key'})).status_code == 200
                response = await c.post('/v1/privacy/anonymize', json={'text': 'hello', 'language': 'it'},
                                        headers={'Authorization': 'Bearer sk-test-gateway-key'})
                assert response.status_code == 200, response.text
                assert response.json()['body']['text'] == 'hello'
                assert not response.json()['authorization']
                for route in ['/v1/document/to-markdown', '/v1/audio/transcribe', '/v1/vision/ocr']:
                    response = await c.post(route, params={'language': 'ita+eng'},
                                            files={'file': ('sample.txt', b'uploaded bytes', 'text/plain')})
                    assert response.status_code == 200, response.text
                    assert response.json()['content'] == 'uploaded bytes'
                    assert response.json()['filename'] == 'sample.txt'
                    assert response.json()['query']['language'] == 'ita+eng'
                response = await c.post('/v1/vision/ocr?error=1', files={'file': ('bad.png', b'x')})
                assert response.status_code == 422, response.text
                assert 'invalid image' in response.json()['error']['message']
                response = await c.get('/specialized/docs')
                assert response.status_code == 200
                assert 'text/html' in response.headers['content-type']
                assert 'Scalar' in response.text
                # These are intentionally unauthenticated inside the private network;
                # the public ingress must protect them (native auth is Enterprise).
                assert (await c.post('/v1/privacy/anonymize', json={'text': 'hello'})).status_code == 200
        finally:
            proxy.app.router.routes[:] = original_routes
            await runner.cleanup()

    asyncio.run(run())
