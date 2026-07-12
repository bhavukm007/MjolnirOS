"""Minimal official GitHub REST API client with token-safe behavior."""
from __future__ import annotations
from typing import Any
import httpx

class GitHubRestClient:
    """Call GitHub REST endpoints without persisting or logging tokens."""
    def __init__(self, token: str | None, base_url: str) -> None:
        self._token, self._base_url = token, base_url.rstrip("/")
    async def request(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._token: raise ValueError("GitHub authentication is unavailable. Configure a session environment token or use existing Git credentials for local Git operations.")
        headers={"Accept":"application/vnd.github+json", "Authorization":f"Bearer {self._token}", "X-GitHub-Api-Version":"2022-11-28"}
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as client:
            response=await client.request(method,path,headers=headers,json=payload); response.raise_for_status(); data=response.json()
        return data if isinstance(data,dict) else {}
