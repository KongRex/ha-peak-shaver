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
    BooleanSelector,
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


# Transient flow-only field (never persisted into the config entry).
CONF_SHOW_ALL_SENSORS = "show_all_sensors"


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

    # Carried from the first step into the unfiltered fallback step.
    _limit_default: float = DEFAULT_LIMIT

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: pick from the power-class-filtered sensor list.

        Some HAN integrations expose their instantaneous-power entity without
        ``device_class: power``, so it never appears in the filtered picker. If
        the user can't find theirs, the "show all sensors" toggle routes them to
        an unfiltered step rather than dead-ending the setup.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            self._limit_default = user_input.get(CONF_LIMIT, DEFAULT_LIMIT)
            sensor = user_input.get(CONF_POWER_SENSOR)
            if sensor:
                return self.async_create_entry(
                    title="Grid Tariff Peak Shaver",
                    data={
                        CONF_POWER_SENSOR: sensor,
                        CONF_LIMIT: user_input[CONF_LIMIT],
                    },
                )
            if user_input.get(CONF_SHOW_ALL_SENSORS):
                return await self.async_step_pick_all()
            errors["base"] = "no_sensor"

        schema = vol.Schema(
            {
                vol.Optional(CONF_POWER_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="power")
                ),
                vol.Required(CONF_LIMIT, default=self._limit_default): _num(
                    1, 15, 0.1, "kWh"
                ),
                vol.Optional(
                    CONF_SHOW_ALL_SENSORS, default=False
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_pick_all(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fallback step: choose from ALL sensor entities (no device-class filter)."""
        if user_input is not None:
            return self.async_create_entry(
                title="Grid Tariff Peak Shaver",
                data={
                    CONF_POWER_SENSOR: user_input[CONF_POWER_SENSOR],
                    CONF_LIMIT: user_input[CONF_LIMIT],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_POWER_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor")
                ),
                vol.Required(CONF_LIMIT, default=self._limit_default): _num(
                    1, 15, 0.1, "kWh"
                ),
            }
        )
        return self.async_show_form(step_id="pick_all", data_schema=schema)

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
