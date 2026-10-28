"""荣泰 RT7709S 按摩椅：通过本地假阿里云 broker 控制。"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RtchairApi
from .const import DOMAIN
from .coordinator import RtchairCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.setdefault(DOMAIN, {})
    data.setdefault("rock_recline_seconds", 3.0)
    data.setdefault("rock_return_seconds", 2.0)
    session = async_get_clientsession(hass)
    api = RtchairApi(session, entry.data["base_url"])
    coordinator = RtchairCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    _LOGGER.info(
        "rtchair 已连接本地 broker %s（椅子在线: %s, 状态字段: %d 个）",
        entry.data["base_url"], coordinator.connected, len(coordinator.props),
    )
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
