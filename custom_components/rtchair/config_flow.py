"""配置流程：填本地 broker 地址即可。"""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RtchairApi, RtchairApiError
from .const import DEFAULT_BASE_URL, DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


class RtchairConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = user_input["base_url"].strip().rstrip("/")
            api = RtchairApi(async_get_clientsession(self.hass), base_url)
            try:
                await api.async_status()
            except RtchairApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(base_url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=DEFAULT_NAME, data={"base_url": base_url}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required("base_url", default=DEFAULT_BASE_URL): str}
            ),
            errors=errors,
        )
