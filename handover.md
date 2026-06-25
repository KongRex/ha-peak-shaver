# handover.md — Grid Tariff Peak Shaver (HA custom integration)

> For a Claude Code agent continuing this project. Read this before editing.
> User-facing docs are in `README.md`; this file is the engineering handover:
> contracts, invariants, validation status, gotchas, and the backlog.

## 1. What this is

A Home Assistant **custom integration** (`custom_components/peak_shaver/`) that
does predictive, prioritized peak-shaving to keep a clock hour's grid
consumption under a configurable kWh cap (Norwegian *nettleie* context, default
5 kWh). It is the integration repackaging of an earlier YAML build (template
sensors + utility_meter + statistics + scripts + automations + input_text/number
helpers). All of that logic now lives in Python. The only user input is one HAN
**power sensor (instantaneous watts)**; energy integration, smoothing,
projection, thresholds, and the shed/restore engine are internal.

Domain: `peak_shaver`. No external deps (`requirements: []`), local_push.

## 2. Repo layout

```
custom_components/peak_shaver/
  __init__.py          setup/unload, service registration, frontend static-path + add_extra_js_url
  const.py             all keys, defaults, signal/event names, FRONTEND_URL
  coordinator.py       THE CORE: energy integration + smoothing + projection + shed/restore engine + persistence
  config_flow.py       config flow (power sensor + limit) and options flow (tuning)
  entity.py            PeakShaverEntity base (device_info, unique_id, CoordinatorEntity)
  sensor.py            6 sensors incl. PrioritySensor (card reads its attributes)
  number.py            HourlyLimitNumber (the kWh cap)
  binary_sensor.py     SheddingActiveBinarySensor
  services.yaml        add_load / remove_load / move_load descriptions
  strings.json         + translations/en.json (UI text)
  frontend/peak-shaver-card.js   vanilla-JS Lovelace card (no build step, auto-registered)
hacs.json              HACS metadata (min HA 2024.8.0)
README.md              user-facing
handover.md            this file
```

## 3. Data flow & the one contract that matters

```
power sensor state events ─┐
                           ├─> PeakShaverCoordinator
10 s tick (time_interval) ─┘     - integrates energy (left Riemann), resets at clock hour
                                 - rolling-mean power smoothing (deque, last sample retained)
                                 - computes coordinator.data  (THE interface)
                                 - runs the shed/restore engine
                                          │
                                 coordinator.data dict
                                          │
            ┌─────────────────────────────┼───────────────────────────┐
        entities (sensor/number/binary)   PrioritySensor attributes    services
            read coordinator.data          (loads, shed, integration)   mutate coordinator
                                                   │
                                          peak-shaver-card.js reads attrs + calls services
```

**`coordinator.data` is the load-bearing contract.** Produced by
`PeakShaverCoordinator._compute()`. Keys (do not rename without updating every
consumer in `sensor.py` / `number.py` / `binary_sensor.py`):

| key | type | meaning |
|-----|------|---------|
| `consumed` | float | kWh banked this clock hour |
| `power_avg_w` | float\|None | smoothed power, watts |
| `projection` | float | banked + smoothed_power_kw × hours_remaining |
| `limit` | float | user cap (kWh) |
| `shed_threshold` | float | limit − shed_offset |
| `restore_threshold` | float | max(limit − restore_offset, 0) |
| `priority` | list[str] | ordered entity entries, least-critical first |
| `shed` | list[str] | entries currently shed by the engine (shed order) |
| `shedding` | bool | `bool(shed)` |

**Card auto-discovery contracts** (breaking these silently breaks the card):
- `PrioritySensor.extra_state_attributes` must expose `integration: "peak_shaver"`,
  `loads`, and `shed`. The card finds the priority sensor by scanning for
  `attributes.integration === "peak_shaver"`.
- The limit number's `unique_id`/entity_id must contain `hourly_limit`; the card
  finds it via `entity_id.includes("hourly_limit")`.

**Service contracts** (card → integration, also usable in user automations):
- `peak_shaver.add_load {item}`
- `peak_shaver.remove_load {item}` — restores the entity first if currently shed
- `peak_shaver.move_load {item, direction: up|down}`

**Persistence schema** (`Store` key `peak_shaver.<entry_id>`):
`{priority: list, shed: list, climate_modes: dict, limit: float}`. Saved on
every mutation via `coordinator._save()`.

## 4. Engine internals (coordinator.py)

- **Energy**: `_power_event` integrates `last_power_kw * dt_h` (left Riemann) on
  each reading. `_async_tick` (every `TICK_SECONDS`=10) resets `_consumed` to 0
  when the local clock hour changes. Boundary precision is utility_meter-grade
  (a reading landing just after :00 can attribute a sub-tick sliver to the new
  hour before the next tick resets — acceptable, documented; tighten only if a
  user complains).
- **Smoothing**: `_samples` deque pruned to `smoothing` seconds; `_power_avg_w`
  returns the mean, or the last reading if the deque is empty. This is why the
  projection **cannot go unavailable** the way the old YAML `statistics` sensor
  did — there is no separate entity to empty out. Preserve this property.
- **Projection**: `_compute()`; `hours_remaining = (60 − (min + sec/60))/60`.
- **Engine**: `_run_engine(data)` on each tick.
  - SHED: if `projection > shed_threshold`, start `_over_since`; once it has held
    for `debounce` seconds AND `now >= _settle_until`, call `_shed_next()` and set
    `_settle_until = now + settle`. This cascades one load per `settle` window.
  - RESTORE: if `projection < restore_threshold` and `now >= _restore_next` and
    `shed` non-empty, call `_restore_last()` and set
    `_restore_next = now + restore_interval`.
- **Domain-aware actions** (`_shed_next` / `_restore_last`):
  - `_expand(entry)` recursively expands `group.` entities to leaf members.
  - climate members → `climate.turn_off` to shed (prior `hvac_mode` saved into
    `_climate_modes`); restore via `climate.set_hvac_mode` to the saved mode
    (fallback `heat`).
  - everything else → `homeassistant.turn_off` / `turn_on`.
  - `_is_on`: climate active = state not in {off,unavailable,unknown}; else
    state == "on".
- **Coordinator is intentionally `DataUpdateCoordinator(update_interval=None)`**.
  Updates are pushed manually via `async_set_updated_data` from `_power_event`
  and the separate `async_track_time_interval` tick. Do **not** "fix" this by
  setting an `update_interval` — it would double-drive and fight the manual push.

## 5. Validation status — READ THIS

Generated and **statically validated only**. NOT run on a live HA instance.

Passed:
- `python3 -m compileall custom_components/peak_shaver` — all modules compile.
- JSON valid: manifest.json, hacs.json, strings.json, translations/en.json.
- YAML valid: services.yaml.
- `node --check frontend/peak-shaver-card.js`.
- Const symbol cross-check (the only "misses" were `UnitOfEnergy`/`UnitOfPower`,
  which are imported from `homeassistant.const`, not the local `const.py` — false
  positive).

NOT done (this is the agent's P0): no live HA load, no runtime exercise of the
engine, no climate round-trip test, no config-flow render test.

## 6. Gotchas / risk register

1. **HA version floor.** `async_register_static_paths` + `StaticPathConfig`
   (in `__init__._async_register_frontend`) require HA **2024.7+**. On older
   cores fall back to the deprecated `hass.http.register_static_path(url, path,
   False)`. `add_extra_js_url` is `homeassistant.components.frontend`.
2. **Config-flow power-sensor selector** filters on
   `EntitySelectorConfig(domain="sensor", device_class="power")`. If the user's
   HAN entity has no `device_class: power`, it won't appear in the picker. If the
   smoke test shows an empty/short list, drop the `device_class` filter (or make
   a second unfiltered step). High-likelihood first-run snag.
3. **Climate shed = full off**, not setpoint setback. Blunt for a heat pump in a
   Norwegian winter. Open decision (see backlog P2). To switch: store prior
   `temperature` instead of mode in `_shed_next`, call `climate.set_temperature`
   low to shed, restore the prior target in `_restore_last`.
4. **Logbook call is best-effort** (`_log` wraps it in try/except + fires
   `peak_shaver_action` event + logger.info). Don't make it blocking/required.
5. **Multi-instance**: services iterate ALL coordinators (no target); the card
   auto-detects the FIRST matching priority sensor. Fine for one instance. For
   multiple, add device/entity targeting to services and require explicit
   `priority_entity`/`limit_entity` in the card config.
6. **Options changes reload the entry** (`_async_reload` via update listener).
   Expected; just know edits to tuning bounce the integration.

## 7. Backlog (priority order)

- **P0** — Live smoke test on the user's HA. Add integration, pick HAN sensor,
  confirm entities populate, watch Logbook + `peak_shaver_action` on the first
  few sheds. Fix whatever traceback appears (most likely #1 or #2 above).
- **P1** — Verify climate restore returns the exact prior `hvac_mode` for the
  user's specific climate platform (heat pump). Some platforms reject
  `set_hvac_mode` for unsupported modes.
- **P1** — Confirm the power-sensor selector surfaces the HAN entity (#2).
- **P2** — Climate setpoint-setback option (gentler than off). Config toggle +
  per-entity strategy.
- **P2 (biggest domain win)** — Monthly *kapasitetsledd* awareness. The per-hour
  cap is a proxy; real billing is the mean of the 3 highest hours/month across 3
  days, bracketed (*trinn*). A correct engine tracks the running monthly top-3
  and only sheds when the current hour is trending into it AND near a bracket
  edge. Needs persisted monthly state + bracket config (Oslo area ≈ Elvia;
  confirm boundaries, they are not all at 5 kWh). This is the high-value feature.
- **P3** — Tests via `pytest-homeassistant-custom-component`; config-entry
  diagnostics; more translations; per-instance card targeting.

## 8. Local validation commands

```bash
# from repo root
python3 -m compileall custom_components/peak_shaver
python3 -c "import json,yaml,glob; [json.load(open(f)) for f in glob.glob('custom_components/peak_shaver/**/*.json',recursive=True)]; yaml.safe_load(open('custom_components/peak_shaver/services.yaml'))"
node --check custom_components/peak_shaver/frontend/peak-shaver-card.js
```

Live: copy `custom_components/peak_shaver/` into HA `config/custom_components/`,
restart, Settings → Devices & Services → Add Integration → Grid Tariff Peak
Shaver. Hard-refresh the browser before adding `type: custom:peak-shaver-card`.

## 9. Conventions to keep

- Card stays **vanilla JS, no build, no HACS frontend dependency** — matches the
  user's established self-contained-tool pattern. Theme via HA CSS vars only.
- Entities use `_attr_has_entity_name = True` and the shared `PeakShaverEntity`
  base; one device per config entry.
- Keep the integration self-contained: one user input (the power sensor). Resist
  reintroducing helper-entity dependencies (utility_meter/statistics/input_*).

---

*Note: Claude Code auto-reads `CLAUDE.md` at repo root. If you want this picked up
automatically on session start, copy or symlink: `cp handover.md CLAUDE.md`.*
