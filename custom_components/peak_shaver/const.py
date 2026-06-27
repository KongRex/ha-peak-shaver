"""Constants for the Grid Tariff Peak Shaver integration."""
from __future__ import annotations

DOMAIN = "peak_shaver"
PLATFORMS = ["sensor", "number", "binary_sensor"]

# Config / options keys
CONF_POWER_SENSOR = "power_sensor"
CONF_LIMIT = "hourly_limit"
CONF_SHED_OFFSET = "shed_offset"
CONF_RESTORE_OFFSET = "restore_offset"
CONF_SMOOTHING = "smoothing_seconds"
CONF_DEBOUNCE = "debounce_seconds"
CONF_SETTLE = "settle_seconds"
CONF_RESTORE_INTERVAL = "restore_interval_seconds"
CONF_MIN_TOGGLE = "min_toggle_seconds"

# Defaults (mirror the original YAML behaviour at a 5 kWh limit)
DEFAULT_LIMIT = 5.0
DEFAULT_SHED_OFFSET = 0.2          # shed threshold = limit - 0.2
DEFAULT_RESTORE_OFFSET = 1.0       # restore threshold = limit - 1.0
DEFAULT_SMOOTHING = 60             # rolling-mean window for power (s)
DEFAULT_DEBOUNCE = 30              # projection must stay over for this long (s)
DEFAULT_SETTLE = 90               # wait after each shed before shedding more (s)
DEFAULT_RESTORE_INTERVAL = 300     # min gap between restores (s)
DEFAULT_MIN_TOGGLE = 300           # min time between toggling the SAME device (s); 0 disables

TICK_SECONDS = 10                  # engine evaluation cadence
STORAGE_VERSION = 1

SIGNAL_UPDATE = f"{DOMAIN}_update"
EVENT_ACTION = f"{DOMAIN}_action"
FRONTEND_URL = f"/{DOMAIN}/peak-shaver-card.js"

# Services
SERVICE_ADD = "add_load"
SERVICE_REMOVE = "remove_load"
SERVICE_MOVE = "move_load"
SERVICE_SET_INTERVAL = "set_toggle_interval"
ATTR_ITEM = "item"
ATTR_DIRECTION = "direction"
ATTR_SECONDS = "seconds"
