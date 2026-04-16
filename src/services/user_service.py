from typing import Any, Dict

from src.services.api_client import ApiClient


class UserService:
    def __init__(self) -> None:
        self.api = ApiClient()

    async def upsert_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.api.post("/v1/telegram/profile/upsert", payload)

    async def get_dashboard(self, telegram_id: str) -> Dict[str, Any]:
        return await self.api.get(f"/v1/telegram/users/{telegram_id}/dashboard")