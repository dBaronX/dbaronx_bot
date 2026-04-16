from typing import Any, Dict, Optional
import httpx

from src.config.settings import get_settings


class ApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.nest_api_base_url
        self.timeout = self.settings.request_timeout
        self.headers = {
            "x-internal-api-key": self.settings.nest_internal_api_key,
            "Content-Type": "application/json",
        }

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{path}",
                params=params,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

    async def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=payload or {},
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()