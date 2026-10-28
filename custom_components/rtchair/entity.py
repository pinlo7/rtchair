"""实体基类。"""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import RtchairCoordinator


class RtchairEntity(CoordinatorEntity[RtchairCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RtchairCoordinator, key: str, name: str,
                 icon: str | None = None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.unique_id}_{key}"
        if icon:
            self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        mac = self.coordinator.mac
        return DeviceInfo(
            identifiers={(DOMAIN, mac or self.coordinator.unique_id)},
            name=DEFAULT_NAME,
            manufacturer="荣泰 Rotai",
            model="RT7709S",
            sw_version=self._sw_version(),
        )

    def _sw_version(self) -> str | None:
        ver = self.coordinator.props.get("ModuleVersion")
        if isinstance(ver, dict):
            return " / ".join(f"{k} {v}" for k, v in ver.items())
        if ver:
            return str(ver)
        return None

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.connected

    @property
    def raw(self):
        return self.coordinator.props.get(self._key)

    async def async_write(self, value: int) -> None:
        await self.coordinator.api.async_set({self._key: int(value)})
        await self.coordinator.async_request_refresh()
