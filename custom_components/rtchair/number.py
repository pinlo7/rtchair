"""数值调节类实体。"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RtchairCoordinator
from .entity import RtchairEntity

NUMBERS = [
    # key, name, min, max, icon
    ("SettingStrength3D", "3D 力度", 0, 5, "mdi:weight"),
    ("SettingSpeedMotor", "机芯速度", 1, 6, "mdi:speedometer"),
    ("SettingStrengthAirBag", "气囊力度", 0, 5, "mdi:air-filter"),
    ("SettingHeatBack", "背部加热", 0, 3, "mdi:radiator"),
    ("SettingHeatShank", "小腿加热", 0, 3, "mdi:radiator-disabled"),
    ("SettingSpeedWheel", "脚底滚轮", 0, 3, "mdi:rotate-3d-variant"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: RtchairCoordinator = entry.runtime_data
    async_add_entities(
        RtchairNumber(coordinator, k, n, lo, hi, i) for k, n, lo, hi, i in NUMBERS
    )
    async_add_entities([
        RtchairRockReclineNumber(coordinator),
        RtchairRockReturnNumber(coordinator),
    ])


class RtchairNumber(RtchairEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator, key, name, lo, hi, icon):
        super().__init__(coordinator, key, name, icon)
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi

    @property
    def native_value(self) -> float | None:
        value = self.raw
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.async_write(int(value))


class RtchairRockReclineNumber(RtchairEntity, NumberEntity):
    """摇椅模式后仰停留秒数。"""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 2
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_icon = "mdi:arrow-expand-vertical"

    def __init__(self, coordinator):
        super().__init__(coordinator, "rock_recline_seconds", "摇椅后仰秒数")

    @property
    def native_value(self) -> float:
        return float(self.hass.data.get(DOMAIN, {}).get("rock_recline_seconds", 10.0))

    async def async_set_native_value(self, value: float) -> None:
        self.hass.data.setdefault(DOMAIN, {})["rock_recline_seconds"] = float(value)
        self.async_write_ha_state()


class RtchairRockReturnNumber(RtchairEntity, NumberEntity):
    """摇椅模式回正停留秒数（越小整体越快）。"""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_icon = "mdi:arrow-collapse-vertical"

    def __init__(self, coordinator):
        super().__init__(coordinator, "rock_return_seconds", "摇椅回正秒数")

    @property
    def native_value(self) -> float:
        return float(self.hass.data.get(DOMAIN, {}).get("rock_return_seconds", 5.0))

    async def async_set_native_value(self, value: float) -> None:
        self.hass.data.setdefault(DOMAIN, {})["rock_return_seconds"] = float(value)
        self.async_write_ha_state()
