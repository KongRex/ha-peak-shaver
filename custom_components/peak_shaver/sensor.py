"""Sensor platform for Peak Shaver."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import PeakShaverEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ProjectionSensor(coordinator),
            ConsumedSensor(coordinator),
            PowerAvgSensor(coordinator),
            ShedThresholdSensor(coordinator),
            RestoreThresholdSensor(coordinator),
            PrioritySensor(coordinator),
        ]
    )


class ProjectionSensor(PeakShaverEntity, SensorEntity):
    _attr_name = "Projected hourly total"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-line"

    def __init__(self, coordinator):
        super().__init__(coordinator, "projection")

    @property
    def native_value(self):
        return self.coordinator.data.get("projection")


class ConsumedSensor(PeakShaverEntity, SensorEntity):
    _attr_name = "Hourly consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator):
        super().__init__(coordinator, "consumed")

    @property
    def native_value(self):
        return self.coordinator.data.get("consumed")


class PowerAvgSensor(PeakShaverEntity, SensorEntity):
    _attr_name = "Power average"
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"

    def __init__(self, coordinator):
        super().__init__(coordinator, "power_avg")

    @property
    def native_value(self):
        return self.coordinator.data.get("power_avg_w")


class ShedThresholdSensor(PeakShaverEntity, SensorEntity):
    _attr_name = "Shed threshold"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:arrow-down-bold"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator):
        super().__init__(coordinator, "shed_threshold")

    @property
    def native_value(self):
        return self.coordinator.data.get("shed_threshold")


class RestoreThresholdSensor(PeakShaverEntity, SensorEntity):
    _attr_name = "Restore threshold"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:arrow-up-bold"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator):
        super().__init__(coordinator, "restore_threshold")

    @property
    def native_value(self):
        return self.coordinator.data.get("restore_threshold")


class PrioritySensor(PeakShaverEntity, SensorEntity):
    """State = number of loads; attributes carry the ordered list + shed list.

    The Lovelace card reads `loads`, `shed`, and `integration` from here.
    """

    _attr_name = "Priority"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator):
        super().__init__(coordinator, "priority")

    @property
    def native_value(self):
        return len(self.coordinator.data.get("priority", []))

    @property
    def extra_state_attributes(self):
        return {
            "integration": DOMAIN,
            "loads": self.coordinator.data.get("priority", []),
            "shed": self.coordinator.data.get("shed", []),
            "toggle_intervals": self.coordinator.data.get("toggle_intervals", {}),
            "default_toggle": self.coordinator.data.get("default_toggle"),
        }
