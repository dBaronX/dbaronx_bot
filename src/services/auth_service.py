from typing import Any, Dict

from src.services.api_client import ApiClient


class AuthService:
    def __init__(self) -> None:
        self.api = ApiClient()

    async def link_telegram_user(self, telegram_user: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "telegram_id": str(telegram_user["id"]),
            "username": telegram_user.get("username"),
            "first_name": telegram_user.get("first_name"),
            "last_name": telegram_user.get("last_name"),
            "language_code": telegram_user.get("language_code"),
        }
        return await self.api.post("/v1/telegram/auth/link", payload)