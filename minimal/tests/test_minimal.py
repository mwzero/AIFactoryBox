"""Test the native launcher and actual LiteLLM HTTP proxy without model downloads."""
import asyncio
import importlib.util
import os
from pathlib import Path
import socket
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("minimal_run", ROOT / "minimal/run.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_initialization_is_private_and_preserves_existing_key(tmp_path, capsys):
    path = tmp_path / ".env"
    launcher.initialize(path)
    content = path.read_text()
    assert content.startswith("LITELLM_MASTER_KEY=sk-")
    assert len(content.splitlines()[0].split("=", 1)[1]) >= 24
    assert content.splitlines()[0].split("=", 1)[1] not in capsys.readouterr().out
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    launcher.initialize(path)
    assert path.read_text() == content


def test_refuses_missing_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "DIRECTORY", tmp_path)
    monkeypatch.delenv("LITELLM_MASTER_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py"])
    with pytest.raises(SystemExit) as error:
        launcher.main()
    assert error.value.code == 2


def test_live_python_gateway_routes_chat_and_streaming_without_database(tmp_path):
    from aiohttp import web

    async def run():
        calls = []

        async def ollama_chat(request):
            body = await request.json()
            calls.append(body)
            result = {"model": "gemma3:1b", "created_at": "2026-11-10T12:00:00Z",
                      "message": {"role": "assistant", "content": "Ciao"},
                      "done": True, "prompt_eval_count": 2, "eval_count": 1}
            if body.get("stream"):
                import json
                response = web.StreamResponse(headers={"Content-Type": "application/x-ndjson"})
                await response.prepare(request)
                chunk = {**result, "done": False}
                await response.write((json.dumps(chunk) + "\n").encode())
                await response.write((json.dumps({**result, "message": {"role": "assistant", "content": ""}}) + "\n").encode())
                await response.write_eof()
                return response
            return web.json_response(result)

        backend = web.Application()
        backend.router.add_post("/api/chat", ollama_chat)
        runner = web.AppRunner(backend)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        ollama_port = site._server.sockets[0].getsockname()[1]
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            gateway_port = reservation.getsockname()[1]
        key = "sk-minimal-test-key-long-enough"
        environment = {**os.environ, "LITELLM_MASTER_KEY": key,
                       "OLLAMA_API_BASE": f"http://127.0.0.1:{ollama_port}",
                       "DATABASE_URL": "postgresql://unused:unused@127.0.0.1:1/unused",
                       "HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1",
                       "NO_PROXY": "example.invalid", "no_proxy": "example.invalid"}
        with (tmp_path / "gateway.log").open("w+") as log:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / "minimal/run.py"), "--port", str(gateway_port),
                env=environment, stdout=log, stderr=log)
            try:
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{gateway_port}", trust_env=False, timeout=10) as client:
                    for _ in range(240):
                        if process.returncode is not None:
                            log.seek(0)
                            pytest.fail("Gateway exited during startup:\n" + log.read())
                        try:
                            if (await client.get("/health/liveliness")).status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        await asyncio.sleep(0.1)
                    else:
                        log.seek(0)
                        pytest.fail("Gateway not ready:\n" + log.read())
                    payload = {"model": "chat-default", "messages": [{"role": "user", "content": "Ciao"}], "max_tokens": 8}
                    assert (await client.post("/v1/chat/completions", json=payload)).status_code in (401, 403)
                    assert not calls
                    headers = {"Authorization": "Bearer " + key}
                    response = await client.get("/v1/models", headers=headers)
                    assert response.status_code == 200, response.text
                    assert "chat-default" in [model["id"] for model in response.json()["data"]]
                    response = await client.post("/v1/chat/completions", json=payload, headers=headers)
                    assert response.status_code == 200, response.text
                    assert response.json()["choices"][0]["message"]["content"] == "Ciao"
                    assert calls[0]["model"] == "gemma3:1b"
                    assert calls[0]["messages"][0]["content"] == "Ciao"
                    async with client.stream("POST", "/v1/chat/completions", json={**payload, "stream": True}, headers=headers) as stream:
                        assert stream.status_code == 200
                        content = "".join([line async for line in stream.aiter_lines()])
                        assert "Ciao" in content
                        assert "[DONE]" in content
            finally:
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                await runner.cleanup()

    asyncio.run(run())
