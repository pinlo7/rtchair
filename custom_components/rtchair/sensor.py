"""传感器实体。"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime

from .const import TIMES
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CHAIR_STATUS, PROGRAMS
from .coordinator import RtchairCoordinator
from .entity import RtchairEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: RtchairCoordinator = entry.runtime_data
    async_add_entities([
        RtchairStatusSensor(coordinator),
        RtchairProgramSensor(coordinator),
        RtchairRuntimeSensor(coordinator),
        RtchairRemainingSensor(coordinator),
    ])


class RtchairStatusSensor(RtchairEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:chair-rolling"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ChairStatus", "状态")
        self._attr_options = list(CHAIR_STATUS.values())

    @property
    def native_value(self) -> str | None:
        value = self.raw
        if value is None:
            return None
        try:
            return CHAIR_STATUS.get(int(value))
        except (TypeError, ValueError):
            return None


class RtchairProgramSensor(RtchairEntity, SensorEntity):
    _attr_icon = "mdi:playlist-music"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ProgramAuto", "当前程序")

    @property
    def native_value(self) -> str | None:
        value = self.raw
        if value is None:
            return None
        try:
            iv = int(value)
        except (TypeError, ValueError):
            return None
        if iv in (0, 254):
            return "手动模式"
        return PROGRAMS.get(iv, f"程序 {iv}")


class RtchairRuntimeSensor(RtchairEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer"

    def __init__(self, coordinator):
        super().__init__(coordinator, "ChairRunTime", "已运行时长")

    @property
    def native_value(self) -> int | None:
        value = self.raw
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class RtchairRemainingSensor(RtchairEntity, SensorEntity):
    """本次按摩剩余时间（分钟）。"""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"

    _MINUTES = {1: 10, 2: 20, 3: 30}

    def __init__(self, coordinator):
        super().__init__(coordinator, "remaining_time", "剩余时间")

    @property
    def _total_minutes(self) -> int | None:
        try:
            return self._MINUTES.get(int(self.coordinator.props.get("SettingMassageTime")))
        except (TypeError, ValueError):
            return None

    @property
    def native_value(self) -> float | None:
        total = self._total_minutes
        if total is None:
            return None
        try:
            runtime = int(self.coordinator.props.get("ChairRunTime") or 0)
        except (TypeError, ValueError):
            runtime = 0
        return round(max(0.0, total - runtime / 60), 1)

    @property
    def extra_state_attributes(self):
        return {"total_minutes": self._total_minutes}
