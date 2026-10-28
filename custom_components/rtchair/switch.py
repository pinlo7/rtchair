"""开关类实体。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import RtchairCoordinator
from .entity import RtchairEntity

_LOGGER = logging.getLogger(__name__)

# 模拟摇椅：零重力开 -> 停 -> 关 -> 停，循环
ROCK_RECLINE_DEFAULT = 3.0    # 后仰停留秒数（最快档）
ROCK_RETURN_DEFAULT = 2.0     # 回正停留秒数（更短）
ROCK_PAUSE_SECONDS = 0.5
LEG_EXTEND_SECONDS = 10.0     # 腿托伸到最大所需时间

SWITCHES = [
    # key, name, icon
    ("ChairSwitch", "电源", "mdi:power"),
    ("ChairPause", "暂停", "mdi:pause"),
    ("SettingZeroGravity", "零重力", "mdi:seat-recline-extra"),
    ("SettingAllAirBag", "全身气囊", "mdi:bag-personal"),
    ("SettingShoulderAirBag", "臂肩气囊", "mdi:arm-flex"),
    ("SettingWaistAirBag", "背腰气囊", "mdi:human-handsup"),
    ("SettingHipAirBag", "臀部气囊", "mdi:seat"),
    ("SettingShankAirBag", "小腿气囊", "mdi:foot-print"),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: RtchairCoordinator = entry.runtime_data
    async_add_entities(RtchairSwitch(coordinator, k, n, i) for k, n, i in SWITCHES)
    async_add_entities([RtchairRockingSwitch(coordinator)])


class RtchairSwitch(RtchairEntity, SwitchEntity):
    def __init__(self, coordinator, key, name, icon):
        super().__init__(coordinator, key, name, icon)

    @property
    def is_on(self) -> bool | None:
        value = self.raw
        if value is None:
            return None
        return bool(int(value))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.async_write(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.async_write(0)


class RtchairRockingSwitch(RtchairEntity, SwitchEntity):
    """摇椅模式（模拟）：用零重力整椅后仰/回正做慢速往返。

    RT7709S 没有原生摇椅（同系列 Pro 才有），这里用零重力位姿模拟：
      零重力开 -> 等 N 秒（后仰完成）
      零重力关 -> 等 N 秒（回正完成）
      循环
    N 由 number 实体「摇椅每程秒数」控制（默认 15 秒）。
    """

    _attr_icon = "mdi:sine-wave"

    def __init__(self, coordinator):
        super().__init__(coordinator, "rocking_mode", "摇椅模式（模拟）")
        self._attr_is_on = False
        self._task = None

    @property
    def is_on(self) -> bool:
        return self._attr_is_on

    def _phase_seconds(self, key: str, default: float) -> float:
        data = self.hass.data.get(DOMAIN) or {}
        try:
            return float(data.get(key, default))
        except (TypeError, ValueError):
            return default

    def _recline_seconds(self) -> float:
        return self._phase_seconds("rock_recline_seconds", ROCK_RECLINE_DEFAULT)

    def _return_seconds(self) -> float:
        return self._phase_seconds("rock_return_seconds", ROCK_RETURN_DEFAULT)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if self._task is not None and not self._task.done():
            return
        await self.coordinator.api.async_set({"ChairSwitch": 1})
        self._attr_is_on = True
        self.async_write_ha_state()
        self._task = self.hass.async_create_task(self._rock_loop())

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
        try:
            await self.coordinator.api.async_set({"SettingZeroGravity": 0})
        except Exception:  # noqa: BLE001
            pass
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        await self.async_turn_off()
        await super().async_will_remove_from_hass()

    async def _rock_loop(self) -> None:
        try:
            # 先把腿托伸到最大（腿部空间最大）
            await self.coordinator.api.async_set(
                {"SettingShankControl": 1, "SettingKneeControl": 1}
            )
            await asyncio.sleep(LEG_EXTEND_SECONDS)
            await self.coordinator.api.async_set(
                {"SettingShankControl": 0, "SettingKneeControl": 0}
            )
            while self._attr_is_on and self.coordinator.connected:
                # 后仰（零重力开）
                await self.coordinator.api.async_set({"SettingZeroGravity": 1})
                await asyncio.sleep(self._recline_seconds() + ROCK_PAUSE_SECONDS)
                if not self._attr_is_on:
                    break
                # 回正（零重力关）
                await self.coordinator.api.async_set({"SettingZeroGravity": 0})
                await asyncio.sleep(self._return_seconds() + ROCK_PAUSE_SECONDS)
                await self.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("摇椅模拟中断: %s", err)
        finally:
            self._attr_is_on = False
            try:
                self.async_write_ha_state()
            except Exception:  # noqa: BLE001
                pass
