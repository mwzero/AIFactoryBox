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



def test_knowledge_primitives_pgvector_via_litellm(monkeypatch):
    from aiohttp import web
    from orchestrator import main as orch_main

    class FakeConn:
        def __init__(self, state):
            self.state = state

        async def execute(self, query, *args):
            q = " ".join(query.split())
            if q.startswith("INSERT INTO kb_collections"):
                name, vec_size, dist = args[0], args[1], args[2] if len(args) > 2 else "Cosine"
                self.state["collections"].setdefault(name, {"vector_size": vec_size, "distance": dist})
            elif q.startswith("DELETE FROM kb_collections"):
                name = args[0]
                if name not in self.state["collections"]:
                    return "DELETE 0"
                del self.state["collections"][name]
                self.state["chunks"] = [c for c in self.state["chunks"] if c["collection_name"] != name]
                return "DELETE 1"
            return "OK"

        async def executemany(self, query, records):
            for rec in records:
                cid, col, doc_id, src, idx, content, meta_json, vec_str = rec
                self.state["chunks"].append({
                    "id": cid,
                    "collection_name": col,
                    "document_id": doc_id,
                    "source": src,
                    "chunk_index": idx,
                    "content": content,
                    "metadata": meta_json,
                    "embedding": vec_str,
                })

        async def fetchrow(self, query, *args):
            q = " ".join(query.split())
            if "FROM kb_collections WHERE name = $1" in q:
                col = self.state["collections"].get(args[0])
                return dict(col) if col else None
            return None

        async def fetch(self, query, *args):
            q = " ".join(query.split())
            if "FROM kb_collections c" in q:
                res = []
                for name, meta in self.state["collections"].items():
                    cnt = sum(1 for c in self.state["chunks"] if c["collection_name"] == name)
                    from datetime import datetime, timezone
                    res.append({
                        "name": name,
                        "vector_size": meta["vector_size"],
                        "distance": meta["distance"],
                        "chunks_count": cnt,
                        "created_at": datetime.now(timezone.utc),
                    })
                return res
            if "FROM kb_chunks" in q:
                col = args[1]
                matching = [c for c in self.state["chunks"] if c["collection_name"] == col]
                return [
                    {
                        "id": c["id"],
                        "document_id": c["document_id"],
                        "source": c["source"],
                        "chunk_index": c["chunk_index"],
                        "content": c["content"],
                        "metadata": c["metadata"],
                        "score": 0.94,
                    }
                    for c in matching
                ]
            return []

        def transaction(self):
            class Tx:
                async def __aenter__(self_tx):
                    return self_tx

                async def __aexit__(self_tx, exc_type, exc, tb):
                    return False

            return Tx()

    class FakePool:
        def __init__(self):
            self.state = {"collections": {}, "chunks": []}

        def acquire(self):
            pool_self = self

            class Acq:
                async def __aenter__(self):
                    return FakeConn(pool_self.state)

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            return Acq()

        async def close(self):
            pass

    async def run():
        litellm_calls = []

        async def handle_litellm_embed(request):
            body = await request.json()
            litellm_calls.append({
                "path": "/v1/embeddings",
                "auth": request.headers.get("Authorization"),
                "model": body.get("model"),
                "count": len(body.get("input", []))
            })
            return web.json_response({
                "object": "list",
                "model": body.get("model"),
                "data": [
                    {"object": "embedding", "index": i, "embedding": [0.1, 0.2, 0.3, 0.4]}
                    for i in range(len(body.get("input", [])))
                ]
            })

        async def handle_litellm_rerank(request):
            body = await request.json()
            litellm_calls.append({
                "path": "/rerank",
                "auth": request.headers.get("Authorization"),
                "model": body.get("model"),
                "count": len(body.get("documents", []))
            })
            return web.json_response({
                "results": [
                    {"index": i, "relevance_score": 0.95 - i * 0.1}
                    for i in range(len(body.get("documents", [])))
                ]
            })

        server = web.Application()
        server.router.add_post("/v1/embeddings", handle_litellm_embed)
        server.router.add_post("/rerank", handle_litellm_rerank)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        fake_pool = FakePool()

        async def fake_get_db_pool():
            return fake_pool

        monkeypatch.setattr(orch_main, "get_db_pool", fake_get_db_pool)
        monkeypatch.setattr(orch_main, "LITELLM_BASE_URL", f"http://127.0.0.1:{port}")
        monkeypatch.setattr(orch_main, "LITELLM_SERVICE_KEY", "sk-service-fallback")

        try:
            with TestClient(app) as client:
                # 1. Ingest with caller Bearer token -> propagated to LiteLLM
                res_ingest = client.post(
                    "/v1/knowledge/ingest",
                    headers={"Authorization": "Bearer sk-tenant-alpha"},
                    data={
                        "collection": "enterprise_pg",
                        "text": "First chunk about security. Second chunk about governance.",
                        "chunk_size": "30",
                        "chunk_overlap": "0",
                        "metadata": '{"tenant": "alpha"}'
                    }
                )
                assert res_ingest.status_code == 200, res_ingest.text
                assert res_ingest.json()["chunks_indexed"] >= 2
                assert litellm_calls[-1]["auth"] == "Bearer sk-tenant-alpha"
                assert litellm_calls[-1]["model"] == "embedding-small"

                # 2. Search with caller Bearer token -> invokes LiteLLM /v1/embeddings + /rerank
                res_search = client.post(
                    "/v1/knowledge/search",
                    headers={"Authorization": "Bearer sk-tenant-alpha"},
                    json={
                        "collection": "enterprise_pg",
                        "query": "security governance",
                        "top_k": 2,
                        "rerank": True,
                        "filter_metadata": {"tenant": "alpha"}
                    }
                )
                assert res_search.status_code == 200, res_search.text
                body = res_search.json()
                assert body["reranked"] is True
                assert body["results"][0]["metadata"]["tenant"] == "alpha"
                assert litellm_calls[-1]["path"] == "/rerank"
                assert litellm_calls[-1]["auth"] == "Bearer sk-tenant-alpha"
                assert litellm_calls[-1]["model"] == "rerank-small"
        finally:
            await runner.cleanup()

    asyncio.run(run())


def test_knowledge_auto_creates_database_on_missing_catalog(monkeypatch):
    import asyncpg
    from orchestrator import main as orch_main

    created_dbs = []
    pool_calls = []

    class DummyConn:
        async def execute(self, sql, *args):
            if sql.startswith("CREATE DATABASE"):
                created_dbs.append(sql)

        async def fetchval(self, sql, *args):
            return None

        async def close(self):
            pass

    class DummyPool:
        def acquire(self):
            class Acq:
                async def __aenter__(self):
                    return DummyConn()

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            return Acq()

        async def close(self):
            pass

    async def fake_create_pool(dsn, min_size=1, max_size=10):
        pool_calls.append(dsn)
        if len(pool_calls) == 1:
            raise asyncpg.InvalidCatalogNameError('database "knowledge_db" does not exist')
        return DummyPool()

    async def fake_connect(dsn):
        assert dsn.endswith("/postgres")
        return DummyConn()

    async def run():
        monkeypatch.setattr(orch_main, "_db_pool", None)
        monkeypatch.setattr(orch_main, "KNOWLEDGE_DB_URL", "postgresql://litellm:secret@postgres-audit:5432/knowledge_db")
        monkeypatch.setattr(orch_main.asyncpg, "create_pool", fake_create_pool)
        monkeypatch.setattr(orch_main.asyncpg, "connect", fake_connect)
        pool = await orch_main.get_db_pool()
        assert pool is not None
        assert len(pool_calls) == 2
        assert created_dbs == ['CREATE DATABASE "knowledge_db"']
        monkeypatch.setattr(orch_main, "_db_pool", None)

    asyncio.run(run())


def test_operations_console_and_status_endpoint(monkeypatch):
    from orchestrator import main as orch_main

    async def fake_probe(client, url):
        return {"status": "ok", "detail": "Reachable (HTTP 200)", "latency_ms": 1.2}

    monkeypatch.setattr(orch_main, "_probe_http", fake_probe)
    monkeypatch.setattr(orch_main, "KNOWLEDGE_DB_URL", "")

    with TestClient(app) as client:
        res_html = client.get("/console/")
        assert res_html.status_code == 200
        assert "Operations Console" in res_html.text

        res_status = client.get("/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "orchestrator" in data["services"]
        assert data["services"]["litellm_proxy"]["status"] == "ok"
