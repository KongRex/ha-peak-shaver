"""Binary sensor — is the system currently shedding any load."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PeakShaverEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SheddingActiveBinarySensor(coordinator)])


class SheddingActiveBinarySensor(PeakShaverEntity, BinarySensorEntity):
    _attr_name = "Shedding active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:flash-off"

    def __init__(self, coordinator):
        super().__init__(coordinator, "shedding")

    @property
    def is_on(self):
        return self.coordinator.data.get("shedding", False)

    @property
    def extra_state_attributes(self):
        return {"shed": self.coordinator.data.get("shed", [])}
