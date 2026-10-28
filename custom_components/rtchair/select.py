"""下拉选择类实体。"""
from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import POSITIONS, PROGRAMS, SKILLS, TIMES
from .coordinator import RtchairCoordinator
from .entity import RtchairEntity

SELECTS = [
    ("ProgramAuto", "自动程序", PROGRAMS, "mdi:playlist-play"),
    ("SettingMassageSkill", "按摩手法", SKILLS, "mdi:hand-back-right"),
    ("SettingMassageTime", "按摩时长", TIMES, "mdi:timer-outline"),
    ("SettingMotorPosition", "机芯部位", POSITIONS, "mdi:map-marker-radius"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: RtchairCoordinator = entry.runtime_data
    async_add_entities(
        RtchairSelect(coordinator, k, n, m, i) for k, n, m, i in SELECTS
    )


class RtchairSelect(RtchairEntity, SelectEntity):
    def __init__(self, coordinator, key, name, mapping, icon):
        super().__init__(coordinator, key, name, icon)
        self._mapping = dict(mapping)
        self._labels = list(mapping.values())
        self._attr_options = self._labels

    @property
    def current_option(self) -> str | None:
        value = self.raw
        if value is None:
            return None
        try:
            return self._mapping.get(int(value))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        reverse = {v: k for k, v in self._mapping.items()}
        if option in reverse:
            await self.async_write(reverse[option])
