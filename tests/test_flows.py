"""Exercise the lightweight Python SDK and composable workflow pipelines."""
import asyncio
import json
from pathlib import Path
import sys

from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flows.sdk import AIFactoryClient
from flows.pipelines.ingest_safe import safe_ingest_pipeline
from flows.pipelines.rag_assistant import rag_answer_pipeline
from flows.pipelines.voice_support import voice_rag_pipeline


def test_flows_sdk_and_pipelines(tmp_path):
    async def run():
        calls = []

        async def handler(request):
            path = request.path
            auth = request.headers.get("Authorization")
            if path == "/v1/document/to-markdown":
                calls.append({"path": path, "auth": auth})
                return web.json_response({"markdown": "Contratto firmato da Mario Rossi (mario@example.com)."})
            if path == "/v1/vision/ocr":
                calls.append({"path": path, "auth": auth, "lang": request.query.get("language")})
                return web.json_response({"filename": "scan.png", "result": {"text": "Fattura intestata a Luigi Verdi"}})
            if path == "/v1/privacy/anonymize":
                body = await request.json()
                calls.append({"path": path, "auth": auth, "text": body["text"]})
                masked = body["text"].replace("Mario Rossi", "<PERSON>").replace("mario@example.com", "<EMAIL_ADDRESS>")
                masked = masked.replace("Luigi Verdi", "<PERSON>")
                return web.json_response({"text": masked})
            if path == "/v1/knowledge/ingest":
                form = await request.post()
                calls.append({
                    "path": path,
                    "auth": auth,
                    "collection": form["collection"],
                    "text": form["text"],
                    "metadata": json.loads(form["metadata"]),
                })
                return web.json_response({"status": "indexed", "chunks_indexed": 1})
            if path == "/v1/knowledge/search":
                body = await request.json()
                calls.append({"path": path, "auth": auth, "body": body})
                return web.json_response({
                    "results": [
                        {
                            "id": "chunk-1",
                            "score": 0.91,
                            "rerank_score": 0.97,
                            "text": "I resi sono accettati entro 30 giorni.",
                            "metadata": {"source_file": "policy.pdf", "tenant": "acme"},
                        }
                    ]
                })
            if path == "/v1/chat/completions":
                body = await request.json()
                calls.append({"path": path, "auth": auth, "messages": body["messages"]})
                return web.json_response({
                    "choices": [{"message": {"content": "Puoi restituire l'articolo entro 30 giorni [1]."}}]
                })
            if path == "/v1/audio/transcribe":
                calls.append({"path": path, "auth": auth})
                return web.json_response({"text": "Qual è la politica di reso?"})
            if path == "/v1/audio/synthesize":
                body = await request.json()
                calls.append({"path": path, "auth": auth, "text": body["text"]})
                return web.json_response({"audio_base64": "UklGRg=="})
            return web.Response(status=404)

        server = web.Application()
        server.router.add_route("*", "/{path:.*}", handler)
        runner = web.AppRunner(server)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]

        client = AIFactoryClient(base_url=f"http://127.0.0.1:{port}", api_key="sk-flow-test")

        try:
            # 1. Safe ingest on PDF
            pdf_file = tmp_path / "contratto.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 dummy")
            res_pdf = await safe_ingest_pipeline(client, pdf_file, collection="kb_acme", tenant="acme")
            assert res_pdf["chunks_indexed"] == 1
            ingest_call = [c for c in calls if c["path"] == "/v1/knowledge/ingest"][-1]
            assert "<PERSON>" in ingest_call["text"]
            assert "Mario Rossi" not in ingest_call["text"]
            assert ingest_call["metadata"]["tenant"] == "acme"
            assert ingest_call["auth"] == "Bearer sk-flow-test"

            # 2. Safe ingest on scanned PNG (uses OCR)
            img_file = tmp_path / "scan.png"
            img_file.write_bytes(b"PNG dummy")
            await safe_ingest_pipeline(client, img_file, collection="kb_acme", tenant="acme")
            assert any(c["path"] == "/v1/vision/ocr" for c in calls)

            # 3. RAG Q&A
            rag_out = await rag_answer_pipeline(client, collection="kb_acme", question="Politica di reso?", tenant="acme")
            assert "30 giorni" in rag_out["answer"]
            assert rag_out["sources"][0]["source"] == "policy.pdf"

            # 4. Voice support end-to-end
            audio_file = tmp_path / "domanda.wav"
            audio_file.write_bytes(b"RIFF dummy")
            voice_out = await voice_rag_pipeline(client, audio_file, collection="kb_acme", tenant="acme")
            assert voice_out["transcript"] == "Qual è la politica di reso?"
            assert voice_out["audio"]["audio_base64"] == "UklGRg=="
        finally:
            await runner.cleanup()

    asyncio.run(run())
