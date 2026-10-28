"""一键运行预设按摩程序。"""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PRESET_PLANS
from .coordinator import RtchairCoordinator
from .entity import RtchairEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: RtchairCoordinator = entry.runtime_data
    async_add_entities(
        RtchairPresetButton(coordinator, name) for name in PRESET_PLANS
    )
    async_add_entities([RtchairLegroomButton(coordinator)])


class RtchairPresetButton(RtchairEntity, ButtonEntity):
    _attr_icon = "mdi:play-circle"

    def __init__(self, coordinator, plan_name):
        super().__init__(coordinator, f"plan_{plan_name}", f"运行程序：{plan_name}")
        self._plan_name = plan_name
        self._running = False

    @property
    def extra_state_attributes(self):
        return {"running": self._running}

    async def async_press(self) -> None:
        if self._running:
            return
        self._running = True
        self.async_write_ha_state()
        plan = PRESET_PLANS[self._plan_name]

        async def run() -> None:
            try:
                elapsed = 0
                for delay, items in plan:
                    if delay > elapsed:
                        await asyncio.sleep(delay - elapsed)
                        elapsed = delay
                    await self.coordinator.api.async_set(items)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("预设程序 %s 执行失败: %s", self._plan_name, err)
            finally:
                self._running = False
                await self.coordinator.async_request_refresh()
                self.async_write_ha_state()

        self.hass.async_create_task(run())


class RtchairLegroomButton(RtchairEntity, ButtonEntity):
    """把小腿伸缩 + 膝盖伸缩都伸到最大（腿部空间最大）。"""

    _attr_icon = "mdi:human-male-height"

    def __init__(self, coordinator):
        super().__init__(coordinator, "legroom_max", "腿部空间最大")

    async def async_press(self) -> None:
        self.hass.async_create_task(self._extend())

    async def _extend(self) -> None:
        try:
            await self.coordinator.api.async_set(
                {"SettingShankControl": 1, "SettingKneeControl": 1}
            )
            await asyncio.sleep(10)
            await self.coordinator.api.async_set(
                {"SettingShankControl": 0, "SettingKneeControl": 0}
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("腿部空间调整失败: %s", err)
