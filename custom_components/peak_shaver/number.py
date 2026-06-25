"""Number platform — the user-set hourly kWh limit."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PeakShaverEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HourlyLimitNumber(coordinator)])


class HourlyLimitNumber(PeakShaverEntity, NumberEntity):
    _attr_name = "Hourly limit"
    _attr_native_min_value = 1
    _attr_native_max_value = 15
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator):
        super().__init__(coordinator, "hourly_limit")

    @property
    def native_value(self):
        return self.coordinator.data.get("limit")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_limit(value)
