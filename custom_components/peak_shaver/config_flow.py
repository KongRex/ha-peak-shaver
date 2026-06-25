"""Config and options flow for Peak Shaver."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
    ConfigFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import (
    DOMAIN,
    CONF_POWER_SENSOR,
    CONF_LIMIT,
    CONF_SHED_OFFSET,
    CONF_RESTORE_OFFSET,
    CONF_SMOOTHING,
    CONF_DEBOUNCE,
    CONF_SETTLE,
    CONF_RESTORE_INTERVAL,
    DEFAULT_LIMIT,
    DEFAULT_SHED_OFFSET,
    DEFAULT_RESTORE_OFFSET,
    DEFAULT_SMOOTHING,
    DEFAULT_DEBOUNCE,
    DEFAULT_SETTLE,
    DEFAULT_RESTORE_INTERVAL,
)


def _num(minv, maxv, step, unit=None):
    return NumberSelector(
        NumberSelectorConfig(
            min=minv, max=maxv, step=step,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


class PeakShaverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="Grid Tariff Peak Shaver", data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_POWER_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="power")
                ),
                vol.Required(CONF_LIMIT, default=DEFAULT_LIMIT): _num(1, 15, 0.1, "kWh"),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return PeakShaverOptionsFlow(entry)


class PeakShaverOptionsFlow(OptionsFlow):
    """Tuning options."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    def _current(self, key, default):
        return self._entry.options.get(key, self._entry.data.get(key, default))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SHED_OFFSET,
                    default=self._current(CONF_SHED_OFFSET, DEFAULT_SHED_OFFSET),
                ): _num(0.0, 2.0, 0.1, "kWh"),
                vol.Required(
                    CONF_RESTORE_OFFSET,
                    default=self._current(CONF_RESTORE_OFFSET, DEFAULT_RESTORE_OFFSET),
                ): _num(0.0, 3.0, 0.1, "kWh"),
                vol.Required(
                    CONF_SMOOTHING,
                    default=self._current(CONF_SMOOTHING, DEFAULT_SMOOTHING),
                ): _num(10, 300, 5, "s"),
                vol.Required(
                    CONF_DEBOUNCE,
                    default=self._current(CONF_DEBOUNCE, DEFAULT_DEBOUNCE),
                ): _num(0, 300, 5, "s"),
                vol.Required(
                    CONF_SETTLE,
                    default=self._current(CONF_SETTLE, DEFAULT_SETTLE),
                ): _num(10, 600, 10, "s"),
                vol.Required(
                    CONF_RESTORE_INTERVAL,
                    default=self._current(CONF_RESTORE_INTERVAL, DEFAULT_RESTORE_INTERVAL),
                ): _num(30, 1800, 30, "s"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
