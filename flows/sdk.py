from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json
import os
import httpx


class AIFactoryClient:
    """Client async leggero verso l'ingress pubblico (Nginx/LiteLLM) di AIFactoryBox."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or os.getenv("AIFACTORYBOX_BASE_URL") or "http://localhost").rstrip("/")
        resolved_key = api_key if api_key is not None else os.getenv("AIFACTORYBOX_API_KEY", "")
        self.headers = {"Authorization": f"Bearer {resolved_key}"} if resolved_key else {}
        self.default_timeout = timeout

    def _client(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout or self.default_timeout,
            trust_env=False,
        )

    async def health(self) -> Dict[str, Any]:
        async with self._client(timeout=10.0) as client:
            resp = await client.get("/specialized/health")
            resp.raise_for_status()
            return resp.json()

    async def to_markdown(self, file_path: Union[str, Path]) -> str:
        path = Path(file_path)
        async with self._client(timeout=90.0) as client:
            with path.open("rb") as fh:
                resp = await client.post("/v1/document/to-markdown", files={"file": (path.name, fh)})
            resp.raise_for_status()
            data = resp.json()
            return (
                data.get("document", {}).get("md_content")
                or data.get("markdown")
                or data.get("text")
                or str(data)
            )

    async def ocr(self, image_path: Union[str, Path], language: str = "ita+eng") -> str:
        path = Path(image_path)
        async with self._client(timeout=45.0) as client:
            with path.open("rb") as fh:
                resp = await client.post(
                    "/v1/vision/ocr",
                    params={"language": language},
                    files={"file": (path.name, fh)},
                )
            resp.raise_for_status()
            return resp.json()["result"]["text"]

    async def anonymize(
        self,
        text: str,
        language: str = "it",
        entities: Optional[List[str]] = None,
    ) -> str:
        payload: Dict[str, Any] = {"text": text, "language": language}
        if entities is not None:
            payload["entities"] = entities
        async with self._client(timeout=15.0) as client:
            resp = await client.post("/v1/privacy/anonymize", json=payload)
            resp.raise_for_status()
            return resp.json()["text"]

    async def transcribe(
        self,
        audio_path: Union[str, Path],
        model: Optional[str] = None,
        language: str = "it",
    ) -> str:
        path = Path(audio_path)
        params: Dict[str, Any] = {"language": language}
        if model:
            params["model"] = model
        async with self._client(timeout=120.0) as client:
            with path.open("rb") as fh:
                resp = await client.post(
                    "/v1/audio/transcribe",
                    params=params,
                    files={"file": (path.name, fh)},
                )
            resp.raise_for_status()
            data = resp.json()
            return data.get("text") or str(data)

    async def synthesize(self, text: str, voice: str = "it_IT-riccardo-x_low") -> Dict[str, Any]:
        async with self._client(timeout=30.0) as client:
            resp = await client.post("/v1/audio/synthesize", json={"text": text, "voice": voice})
            resp.raise_for_status()
            return resp.json()

    async def list_collections(self) -> List[Dict[str, Any]]:
        async with self._client(timeout=10.0) as client:
            resp = await client.get("/v1/knowledge/collections")
            resp.raise_for_status()
            return resp.json().get("collections", [])

    async def create_collection(
        self,
        name: str,
        vector_size: int = 384,
        distance: str = "Cosine",
    ) -> Dict[str, Any]:
        async with self._client(timeout=10.0) as client:
            resp = await client.post(
                "/v1/knowledge/collections",
                json={"name": name, "vector_size": vector_size, "distance": distance},
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_collection(self, name: str) -> Dict[str, Any]:
        async with self._client(timeout=10.0) as client:
            resp = await client.delete(f"/v1/knowledge/collections/{name}")
            resp.raise_for_status()
            return resp.json()

    async def ingest(
        self,
        collection: str,
        text: Optional[str] = None,
        file_path: Optional[Union[str, Path]] = None,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not text and not file_path:
            raise ValueError("Provide either 'text' or 'file_path'.")

        data: Dict[str, Any] = {
            "collection": collection,
            "chunk_size": str(chunk_size),
            "chunk_overlap": str(chunk_overlap),
        }
        if text is not None:
            data["text"] = text
        if metadata:
            data["metadata"] = json.dumps(metadata)

        async with self._client(timeout=90.0) as client:
            if file_path is not None:
                path = Path(file_path)
                with path.open("rb") as fh:
                    resp = await client.post(
                        "/v1/knowledge/ingest",
                        data=data,
                        files={"file": (path.name, fh)},
                    )
            else:
                resp = await client.post("/v1/knowledge/ingest", data=data)
            resp.raise_for_status()
            return resp.json()

    async def search(
        self,
        collection: str,
        query: str,
        top_k: int = 3,
        rerank: bool = True,
        score_threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "collection": collection,
            "query": query,
            "top_k": top_k,
            "rerank": rerank,
        }
        if score_threshold is not None:
            payload["score_threshold"] = score_threshold
        if filters:
            payload["filter_metadata"] = filters

        async with self._client(timeout=20.0) as client:
            resp = await client.post("/v1/knowledge/search", json=payload)
            resp.raise_for_status()
            return resp.json().get("results", [])

    async def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: str = "chat-small",
        temperature: float = 0.2,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with self._client(timeout=60.0) as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={"model": model, "messages": messages, "temperature": temperature},
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
