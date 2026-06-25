"""The Grid Tariff Peak Shaver integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    PLATFORMS,
    FRONTEND_URL,
    SERVICE_ADD,
    SERVICE_REMOVE,
    SERVICE_MOVE,
    ATTR_ITEM,
    ATTR_DIRECTION,
)
from .coordinator import PeakShaverCoordinator

_LOGGER = logging.getLogger(__name__)

_ADD_SCHEMA = vol.Schema({vol.Required(ATTR_ITEM): cv.string})
_REMOVE_SCHEMA = vol.Schema({vol.Required(ATTR_ITEM): cv.string})
_MOVE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ITEM): cv.string,
        vol.Required(ATTR_DIRECTION): vol.In(["up", "down"]),
    }
)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_frontend"):
        return
    path = hass.config.path(f"custom_components/{DOMAIN}/frontend/peak-shaver-card.js")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(FRONTEND_URL, path, False)]
    )
    add_extra_js_url(hass, FRONTEND_URL)
    hass.data[f"{DOMAIN}_frontend"] = True


def _all_coordinators(hass: HomeAssistant) -> list[PeakShaverCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


async def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ADD):
        return

    async def _add(call: ServiceCall) -> None:
        for c in _all_coordinators(hass):
            await c.async_add_load(call.data[ATTR_ITEM])

    async def _remove(call: ServiceCall) -> None:
        for c in _all_coordinators(hass):
            await c.async_remove_load(call.data[ATTR_ITEM])

    async def _move(call: ServiceCall) -> None:
        for c in _all_coordinators(hass):
            await c.async_move_load(call.data[ATTR_ITEM], call.data[ATTR_DIRECTION])

    hass.services.async_register(DOMAIN, SERVICE_ADD, _add, schema=_ADD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, _remove, schema=_REMOVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_MOVE, _move, schema=_MOVE_SCHEMA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Peak Shaver from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = PeakShaverCoordinator(hass, entry)
    await coordinator.async_init()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await _async_register_frontend(hass)
    await _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: PeakShaverCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            for svc in (SERVICE_ADD, SERVICE_REMOVE, SERVICE_MOVE):
                hass.services.async_remove(DOMAIN, svc)
    return unload_ok
