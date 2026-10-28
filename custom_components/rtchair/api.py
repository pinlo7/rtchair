"""与路由器上的本地假阿里云 broker 通信。"""
from __future__ import annotations

import asyncio

import aiohttp

from .const import DEFAULT_BASE_URL


class RtchairApiError(Exception):
    """API 错误。"""


class RtchairApi:
    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")

    async def async_status(self) -> dict:
        try:
            async with asyncio.timeout(8):
                async with self._session.get(f"{self.base_url}/status") as resp:
                    if resp.status != 200:
                        raise RtchairApiError(f"HTTP {resp.status}")
                    return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise RtchairApiError(str(err)) from err

    async def async_set(self, items: dict) -> None:
        try:
            async with asyncio.timeout(8):
                async with self._session.post(f"{self.base_url}/set", json=items) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status != 200 or not data.get("ok"):
                        raise RtchairApiError(str(data))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise RtchairApiError(str(err)) from err
