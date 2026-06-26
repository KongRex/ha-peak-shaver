"""Energy tracking and load-shedding engine for Peak Shaver."""
from __future__ import annotations

import logging
from collections import deque
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    EVENT_ACTION,
    STORAGE_VERSION,
    TICK_SECONDS,
    CONF_POWER_SENSOR,
    CONF_LIMIT,
    CONF_SHED_OFFSET,
    CONF_RESTORE_OFFSET,
    CONF_SMOOTHING,
    CONF_DEBOUNCE,
    CONF_SETTLE,
    CONF_RESTORE_INTERVAL,
    CONF_MIN_TOGGLE,
    DEFAULT_LIMIT,
    DEFAULT_SHED_OFFSET,
    DEFAULT_RESTORE_OFFSET,
    DEFAULT_SMOOTHING,
    DEFAULT_DEBOUNCE,
    DEFAULT_SETTLE,
    DEFAULT_RESTORE_INTERVAL,
    DEFAULT_MIN_TOGGLE,
)

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = ("unavailable", "unknown", "none", "")


class PeakShaverCoordinator(DataUpdateCoordinator):
    """Integrates HAN power into hourly energy and runs the shed/restore engine."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

        # Persisted, mutable state
        self._priority: list[str] = []
        self._shed: list[str] = []
        self._climate_modes: dict[str, str] = {}
        # entry -> the exact non-climate members we switched OFF for that entry,
        # so restore only turns those back on (not members that were already off).
        self._shed_switches: dict[str, list[str]] = {}
        # entry -> UTC epoch seconds of the last time we toggled it (shed OR restore).
        # Enforces the per-device minimum toggle interval (anti short-cycle).
        self._last_toggle: dict[str, float] = {}
        self._limit: float = self._opt(CONF_LIMIT, DEFAULT_LIMIT)

        # Energy accumulation state
        self._consumed: float = 0.0
        self._last_power_w: float | None = None
        self._last_ts = None
        self._hour: int = dt_util.now().hour
        self._samples: deque = deque()

        # Engine timing state
        self._over_since = None
        self._settle_until = dt_util.utcnow()
        self._restore_next = dt_util.utcnow()

        self._unsubs: list = []

    # ---- config/options helpers ------------------------------------------

    def _opt(self, key, default):
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def power_sensor(self) -> str:
        return self.entry.data[CONF_POWER_SENSOR]

    @property
    def smoothing(self) -> int:
        return int(self._opt(CONF_SMOOTHING, DEFAULT_SMOOTHING))

    @property
    def debounce(self) -> int:
        return int(self._opt(CONF_DEBOUNCE, DEFAULT_DEBOUNCE))

    @property
    def settle(self) -> int:
        return int(self._opt(CONF_SETTLE, DEFAULT_SETTLE))

    @property
    def restore_interval(self) -> int:
        return int(self._opt(CONF_RESTORE_INTERVAL, DEFAULT_RESTORE_INTERVAL))

    @property
    def min_toggle(self) -> int:
        """Minimum seconds between toggling the SAME device (0 disables)."""
        return int(self._opt(CONF_MIN_TOGGLE, DEFAULT_MIN_TOGGLE))

    @property
    def shed_threshold(self) -> float:
        return round(self._limit - self._opt(CONF_SHED_OFFSET, DEFAULT_SHED_OFFSET), 2)

    @property
    def restore_threshold(self) -> float:
        return round(max(self._limit - self._opt(CONF_RESTORE_OFFSET, DEFAULT_RESTORE_OFFSET), 0), 2)

    @property
    def limit(self) -> float:
        return self._limit

    @property
    def priority(self) -> list[str]:
        return list(self._priority)

    @property
    def shed_list(self) -> list[str]:
        return list(self._shed)

    # ---- lifecycle -------------------------------------------------------

    async def async_init(self) -> None:
        """Load persisted state and start listeners/timers."""
        stored = await self._store.async_load()
        if stored:
            self._priority = stored.get("priority", [])
            self._shed = stored.get("shed", [])
            self._climate_modes = stored.get("climate_modes", {})
            self._shed_switches = stored.get("shed_switches", {})
            self._last_toggle = stored.get("last_toggle", {})
            self._limit = stored.get("limit", self._limit)

        # Seed energy state from the current power reading if present
        st = self.hass.states.get(self.power_sensor)
        if st and st.state not in _UNAVAILABLE:
            try:
                self._last_power_w = float(st.state)
                self._last_ts = dt_util.utcnow()
                self._samples.append((self._last_ts, self._last_power_w))
            except (ValueError, TypeError):
                pass

        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [self.power_sensor], self._power_event
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass, self._async_tick, timedelta(seconds=TICK_SECONDS)
            )
        )
        self.async_set_updated_data(self._compute())

    async def async_shutdown(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "priority": self._priority,
                "shed": self._shed,
                "climate_modes": self._climate_modes,
                "shed_switches": self._shed_switches,
                "last_toggle": self._last_toggle,
                "limit": self._limit,
            }
        )

    # ---- energy accumulation --------------------------------------------

    @callback
    def _power_event(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in _UNAVAILABLE:
            return
        try:
            watts = float(new.state)
        except (ValueError, TypeError):
            return
        now = dt_util.utcnow()
        if self._last_ts is not None and self._last_power_w is not None:
            dt_h = (now - self._last_ts).total_seconds() / 3600.0
            if dt_h > 0:
                self._consumed += (self._last_power_w / 1000.0) * dt_h
        self._last_power_w = watts
        self._last_ts = now
        self._samples.append((now, watts))
        self._prune(now)
        self.async_set_updated_data(self._compute())

    def _prune(self, now) -> None:
        window = self.smoothing
        while len(self._samples) > 1 and (now - self._samples[0][0]).total_seconds() > window:
            self._samples.popleft()

    def _power_avg_w(self) -> float | None:
        if self._samples:
            return sum(v for _, v in self._samples) / len(self._samples)
        return self._last_power_w

    # ---- projection ------------------------------------------------------

    def _compute(self) -> dict:
        local = dt_util.now()
        remaining_h = (60 - (local.minute + local.second / 60)) / 60
        avg_w = self._power_avg_w()
        power_kw = (avg_w / 1000.0) if avg_w is not None else 0.0
        projection = round(self._consumed + power_kw * remaining_h, 2)
        return {
            "consumed": round(self._consumed, 3),
            "power_avg_w": round(avg_w, 1) if avg_w is not None else None,
            "projection": projection,
            "limit": self._limit,
            "shed_threshold": self.shed_threshold,
            "restore_threshold": self.restore_threshold,
            "priority": list(self._priority),
            "shed": list(self._shed),
            "shedding": bool(self._shed),
        }

    # ---- engine tick -----------------------------------------------------

    async def _async_tick(self, now=None) -> None:
        local = dt_util.now()
        if local.hour != self._hour:
            self._hour = local.hour
            self._consumed = 0.0
        data = self._compute()
        self.async_set_updated_data(data)
        await self._run_engine(data)

    async def _run_engine(self, data: dict) -> None:
        now = dt_util.utcnow()
        proj = data["projection"]
        if proj is None:
            return

        if proj > data["shed_threshold"]:
            if self._over_since is None:
                self._over_since = now
            over_for = (now - self._over_since).total_seconds()
            if over_for >= self.debounce and now >= self._settle_until:
                if await self._shed_next():
                    self._settle_until = now + timedelta(seconds=self.settle)
                    self.async_set_updated_data(self._compute())
        else:
            self._over_since = None

        if proj < data["restore_threshold"] and now >= self._restore_next and self._shed:
            if await self._restore_last():
                self._restore_next = now + timedelta(seconds=self.restore_interval)
                self.async_set_updated_data(self._compute())

    # ---- domain-aware expand / state helpers -----------------------------

    def _expand(self, entry: str, seen: set | None = None) -> list[str]:
        seen = seen or set()
        if entry in seen:
            return []
        seen.add(entry)
        st = self.hass.states.get(entry)
        if st is None:
            return []
        if entry.startswith("group."):
            members = st.attributes.get("entity_id", [])
            out: list[str] = []
            for m in members:
                out.extend(self._expand(m, seen))
            return out
        return [entry]

    def _is_on(self, entity: str) -> bool:
        st = self.hass.states.get(entity)
        if st is None:
            return False
        if entity.startswith("climate."):
            return st.state not in ("off", "unavailable", "unknown")
        return st.state == "on"

    # ---- per-device anti short-cycle ------------------------------------

    def _in_cooldown(self, entry: str, now_ts: float) -> bool:
        """True if ``entry`` was toggled less than ``min_toggle`` seconds ago."""
        window = self.min_toggle
        if window <= 0:
            return False
        last = self._last_toggle.get(entry)
        return last is not None and (now_ts - last) < window

    def _mark_toggle(self, entry: str, now_ts: float) -> None:
        self._last_toggle[entry] = now_ts

    # ---- shed / restore --------------------------------------------------

    async def _shed_next(self) -> bool:
        now_ts = dt_util.utcnow().timestamp()
        for entry in self._priority:
            if entry in self._shed:
                continue
            if self._in_cooldown(entry, now_ts):
                continue
            members = self._expand(entry)
            climate_on = [m for m in members if m.startswith("climate.") and self._is_on(m)]
            other_on = [m for m in members if not m.startswith("climate.") and self._is_on(m)]
            if not climate_on and not other_on:
                continue
            for m in climate_on:
                cst = self.hass.states.get(m)
                self._climate_modes[m] = cst.state if cst else "heat"
            if climate_on:
                await self.hass.services.async_call(
                    "climate", "turn_off", {"entity_id": climate_on}, blocking=False
                )
            if other_on:
                await self.hass.services.async_call(
                    "homeassistant", "turn_off", {"entity_id": other_on}, blocking=False
                )
            # Remember exactly what we actuated so restore only re-enables those.
            self._shed_switches[entry] = other_on
            self._shed.append(entry)
            self._mark_toggle(entry, now_ts)
            await self._save()
            self._log(f"Shed {entry}")
            return True
        return False

    async def _restore_entry(self, entry: str) -> None:
        """Re-enable exactly what we shed for ``entry`` — nothing that was already off.

        Non-climate members come from ``_shed_switches`` (the set we switched off).
        Climate members are restored only if we have a saved prior mode for them,
        i.e. only those we turned off — a member that was already off is left alone.
        """
        members = self._expand(entry)
        if entry in self._shed_switches:
            switches = self._shed_switches[entry]
        else:
            # Legacy entry shed before per-member tracking existed: best effort.
            switches = [m for m in members if not m.startswith("climate.")]
        if switches:
            await self.hass.services.async_call(
                "homeassistant", "turn_on", {"entity_id": switches}, blocking=False
            )
        for m in members:
            if m.startswith("climate.") and m in self._climate_modes:
                mode = self._climate_modes.pop(m, "heat")
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": m, "hvac_mode": mode}, blocking=False,
                )

    async def _restore_last(self) -> bool:
        if not self._shed:
            return False
        entry = self._shed[-1]
        now_ts = dt_util.utcnow().timestamp()
        # Honour the per-device minimum toggle interval: a device we just shed
        # must not be switched back on until its cooldown has elapsed (protects
        # compressors/boilers from short-cycling). Leave it shed and retry later.
        if self._in_cooldown(entry, now_ts):
            return False
        await self._restore_entry(entry)
        self._shed.pop()
        self._shed_switches.pop(entry, None)
        self._mark_toggle(entry, now_ts)
        await self._save()
        self._log(f"Restored {entry}")
        return True

    def _log(self, message: str) -> None:
        _LOGGER.info(message)
        self.hass.bus.async_fire(EVENT_ACTION, {"message": message})
        # Best-effort logbook entry
        try:
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "logbook", "log",
                    {"name": "Peak Shaver", "message": message},
                    blocking=False,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    # ---- public mutators (services / number entity) ----------------------

    async def async_set_limit(self, value: float) -> None:
        self._limit = round(float(value), 2)
        await self._save()
        self.async_set_updated_data(self._compute())

    async def async_add_load(self, item: str) -> None:
        if item and item not in self._priority:
            self._priority.append(item)
            await self._save()
            self.async_set_updated_data(self._compute())

    async def async_remove_load(self, item: str) -> None:
        # If it was shed by us, restore it first
        if item in self._shed:
            await self._restore_entry(item)
            self._shed = [e for e in self._shed if e != item]
            self._shed_switches.pop(item, None)
            self._log(f"Removed {item} — restored (was shed)")
        self._last_toggle.pop(item, None)
        self._priority = [e for e in self._priority if e != item]
        await self._save()
        self.async_set_updated_data(self._compute())

    async def async_move_load(self, item: str, direction: str) -> None:
        if item not in self._priority:
            return
        i = self._priority.index(item)
        j = i - 1 if direction == "up" else i + 1
        if 0 <= j < len(self._priority):
            self._priority[i], self._priority[j] = self._priority[j], self._priority[i]
            await self._save()
            self.async_set_updated_data(self._compute())
