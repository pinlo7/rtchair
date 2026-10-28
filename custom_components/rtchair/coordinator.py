"""数据协调器：定时拉取按摩椅状态。"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RtchairApi, RtchairApiError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class RtchairCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, api: RtchairApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL),
        )
        self.api = api
        self._last_logged = -1

    @property
    def unique_id(self) -> str:
        return self.api.base_url

    @property
    def props(self) -> dict:
        return (self.data or {}).get("props") or {}

    @property
    def connected(self) -> bool:
        return bool((self.data or {}).get("connected"))

    @property
    def mac(self) -> str | None:
        mac = self.props.get("ModuleMAC")
        return str(mac) if mac else None

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.async_status()
        except RtchairApiError as err:
            raise UpdateFailed(str(err)) from err
        props = data.get("props") or {}
        if props and self._last_logged != len(props):
            self._last_logged = len(props)
            _LOGGER.info("rtchair 状态已更新：%s", ", ".join(sorted(props))[:200])
        return data
