"""Shared base for Peak Shaver entities."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import PeakShaverCoordinator


class PeakShaverEntity(CoordinatorEntity[PeakShaverCoordinator]):
    """Base entity tying everything to one device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PeakShaverCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name="Grid Tariff Peak Shaver",
            manufacturer="Peak Shaver",
            model="Predictive load shedding",
        )
