"""Exercise real adapters with local upstream doubles; no paid API calls."""
import asyncio
import io
from pathlib import Path
import shutil
import sys

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.main import app


def test_specialized_schema_does_not_duplicate_model_apis():
    with TestClient(app) as client:
        paths = client.get('/openapi.json').json()['paths']
        assert '/v1/vision/ocr' in paths
        assert '/v1/embeddings/generate' not in paths
        assert '/v1/rerank' not in paths
        assert '/v1/security/guardrail' not in paths
        assert client.get('/health').json()['status'] == 'ok'


def test_real_tesseract_ocr():
    if not shutil.which('tesseract'):
        pytest.skip('Install Tesseract to exercise OCR')
    image = Image.new('RGB', (900, 140), 'white')
    font = ImageFont.truetype('DejaVuSans.ttf', 48)
    ImageDraw.Draw(image).text((20, 30), 'INVOICE TOTAL 12345', font=font, fill='black')
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    with TestClient(app) as client:
        response = client.post('/v1/vision/ocr?language=eng',
                               files={'file': ('invoice.png', buf.getvalue(), 'image/png')})
        assert response.status_code == 200, response.text
        assert '12345' in response.json()['result']['text']
        assert client.post('/v1/vision/ocr?language=invalid',
                           files={'file': ('x.png', b'x')}).status_code == 422
        assert client.post('/v1/vision/ocr?language=eng',
                           files={'file': ('x.png', b'not an image')}).status_code == 422


@pytest.mark.parametrize('failure', [None, 'http', 'json', 'body', 'anonymizer'])
def test_native_presidio_masks_or_blocks(failure):
    from aiohttp import web
    from litellm.proxy.guardrails.guardrail_hooks.presidio import _OPTIONAL_PresidioPIIMasking
    from litellm.proxy._types import UserAPIKeyAuth
    from litellm.caching.caching import DualCache

    async def run():
        analyzer_calls = []
        anonymizer_calls = []

        async def analyze(request):
            payload = await request.json()
            analyzer_calls.append(payload)
            if failure == 'http':
                return web.json_response({'error': 'unavailable'}, status=503)
            if failure == 'json':
                return web.Response(text='not JSON', content_type='text/plain')
            if failure == 'body':
                return web.json_response({'error': 'unsupported language'})
            text = payload['text']
            start = text.index('mario@example.com')
            return web.json_response([{'entity_type': 'EMAIL_ADDRESS', 'start': start,
                                       'end': start + len('mario@example.com'), 'score': 1.0}])

        async def anonymize(request):
            payload = await request.json()
            anonymizer_calls.append(payload)
            if failure == 'anonymizer':
                return web.json_response({'error': 'unavailable'}, status=503)
            return web.json_response({'text': payload['text'].replace('mario@example.com', '<EMAIL_ADDRESS>'),
                                      'items': []})

        server = web.Application()
        server.router.add_post('/analyze', analyze)
        server.router.add_post('/anonymize', anonymize)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        config = yaml.safe_load(Path('config/litellm-config.yaml').read_text())
        params = config['guardrails'][0]['litellm_params'].copy()
        params.pop('guardrail')
        mode = params.pop('mode')
        params.update(presidio_analyzer_api_base=f'http://127.0.0.1:{port}/',
                      presidio_anonymizer_api_base=f'http://127.0.0.1:{port}/')
        guard = _OPTIONAL_PresidioPIIMasking(guardrail_name='pii-before-model', event_hook=mode, **params)
        request = {'model': 'chat-small', 'messages': [
            {'role': 'user', 'content': 'Contatta mario@example.com'}]}
        try:
            if failure:
                with pytest.raises(Exception):
                    await guard.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), request, 'completion')
            else:
                result = await guard.async_pre_call_hook(UserAPIKeyAuth(), DualCache(), request, 'completion')
                assert 'mario@example.com' not in str(result['messages'])
                assert '<EMAIL_ADDRESS>' in str(result['messages'])
                assert analyzer_calls[0]['language'] == 'it'
                assert 'EMAIL_ADDRESS' in analyzer_calls[0]['entities']
                assert anonymizer_calls[0]['analyzer_results']
        finally:
            for session in [guard._http_session, *guard._loop_sessions.values()]:
                if session and not session.closed:
                    await session.close()
            await runner.cleanup()

    asyncio.run(run())


def test_model_adapters_use_native_litellm_contracts():
    import litellm
    from aiohttp import web

    async def run():
        calls = {}

        async def embeddings(request):
            calls['embeddings'] = await request.json()
            return web.json_response({'object': 'list', 'model': 'embedding-small',
                'data': [{'object': 'embedding', 'index': 0, 'embedding': [0.1, 0.2]}],
                'usage': {'prompt_tokens': 1, 'total_tokens': 1}})

        async def rerank(request):
            calls['rerank'] = await request.json()
            return web.json_response([{'index': 1, 'score': 0.9}, {'index': 0, 'score': 0.1}])

        server = web.Application()
        server.router.add_post('/v1/embeddings', embeddings)
        server.router.add_post('/rerank', rerank)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        models = yaml.safe_load(Path('config/litellm-config.yaml').read_text())['model_list']
        try:
            params = models[1]['litellm_params'].copy()
            params['api_base'] = f'http://127.0.0.1:{port}/v1'
            response = await litellm.aembedding(input=['hello'], **params)
            assert response.data[0]['embedding'] == [0.1, 0.2]
            assert calls['embeddings']['input'] == ['hello']
            params = models[2]['litellm_params'].copy()
            params['api_base'] = f'http://127.0.0.1:{port}'
            response = await litellm.arerank(query='returns', documents=['unrelated', 'Returns in 30 days'], top_n=1, **params)
            assert response.results[0]['index'] == 1
            assert calls['rerank']['texts'] == ['unrelated', 'Returns in 30 days']
        finally:
            await runner.cleanup()

    asyncio.run(run())
