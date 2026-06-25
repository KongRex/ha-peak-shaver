# Grid Tariff Peak Shaver — Home Assistant custom integration

Predictive, prioritized peak-shaving as a proper HA integration. Point it at one
HAN power sensor (instantaneous watts) and it handles everything else:
hourly energy integration, power smoothing, a forward projection, and a
domain-aware shed/restore engine with hysteresis and debounce — all in Python,
configured from the UI. Includes a custom Lovelace card (auto-loaded) to manage
the shed-priority list and the kWh limit.

This is the integration repackaging of the original YAML/template/script build.
Nothing here needs `utility_meter`, `integration`, `input_text`, `input_number`,
manual automations, or manual resource registration.

## Install

### HACS (custom repository)
1. HACS → ⋮ → Custom repositories → add this repo, category **Integration**.
2. Install **Grid Tariff Peak Shaver**, then restart Home Assistant.

### Manual
Copy `custom_components/peak_shaver/` into your HA `config/custom_components/`
folder and restart.

### Configure
**Settings → Devices & Services → Add Integration → Grid Tariff Peak Shaver.**
Pick your HAN power sensor and set the hourly limit (default 5 kWh). Done.

Add the card to a dashboard (it is already registered — no Resources step):

```yaml
type: custom:peak-shaver-card
title: Load Shed Priority
# priority_entity / limit_entity are auto-detected; override only if needed
# domains: [switch, climate, group, light, input_boolean]
```

## What you get

Entities (all under one device):
- `sensor.*_projected_hourly_total` — banked + smoothed-power × time left
- `sensor.*_hourly_consumption` — energy this clock hour (resets at :00)
- `sensor.*_power_average` — rolling-mean power
- `sensor.*_shed_threshold` / `*_restore_threshold` — disabled by default
- `sensor.*_priority` — state = load count; attributes `loads`, `shed` (card reads these)
- `number.*_hourly_limit` — the kWh cap
- `binary_sensor.*_shedding_active` — on while any load is shed

Services (called by the card, usable in your own automations too):
- `peak_shaver.add_load` { item }
- `peak_shaver.remove_load` { item } — restores it first if currently shed
- `peak_shaver.move_load` { item, direction: up|down }

## How the engine works

A 10-second tick recomputes the projection and runs the engine:
- **Shed** when projection stays above (limit − shed_offset) for the debounce
  window: shed the next-eligible priority entry, then wait `settle` seconds
  before considering the next — this cascades through the list.
- **Restore** when projection is below (limit − restore_offset): release the
  most-critical shed entry, then wait `restore_interval` before the next.

Energy is integrated from the power sensor on every reading (left Riemann) and
reset at each clock-hour boundary. Power smoothing is a rolling mean over the
configured window, with the last reading retained so the projection never goes
blank when readings pause (the bug that plagued the YAML version is structurally
absent here — there is no separate statistics entity to empty out).

## Entity types

| Type | Shed | Restore |
|------|------|---------|
| `switch`, `light`, `fan`, `input_boolean` | `homeassistant.turn_off` | `homeassistant.turn_on` |
| `climate` | `climate.turn_off` (prior hvac_mode stored) | `climate.set_hvac_mode` to stored mode |
| `group` | expand, shed each on-member by its domain | restore only the members it shed |

## Tuning (options flow)

Settings → the integration → Configure: shed/restore offsets, smoothing window,
debounce, settle time, restore interval.

## Honest status

This was generated and **syntax-validated** (every Python module compiles, JSON
and YAML parse, the card passes `node --check`), but it has **not been run on a
live Home Assistant instance**. Treat it as a working first version to test:
watch the Logbook and the `peak_shaver_action` events on the first few sheds,
and confirm climate restore returns your heat pumps to the right mode. Report
anything that misbehaves and it can be corrected quickly.

## Strategic caveat (unchanged)

The per-hour kWh cap is a conservative proxy for the actual *kapasitetsledd*,
which bills on the average of the three highest hours of the month across three
days. Flattening every hour over-sheds. Confirm your DSO's bracket boundaries
(Oslo area is likely Elvia). A "correct" engine would track the running monthly
top-3 — a larger build than this v1.
