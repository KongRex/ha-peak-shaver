class PeakShaverCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: config.title || "Load Shed Priority",
      // Auto-detected if omitted (looks for the integration's priority sensor)
      priority_entity: config.priority_entity || null,
      limit_entity: config.limit_entity || null,
      domains: config.domains || ["switch", "climate", "group"],
    };
    this._sig = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._resolveEntities();
    const sig = this._signature();
    if (sig === this._sig) return;
    this._sig = sig;
    this._render();
  }

  _resolveEntities() {
    if (!this._config.priority_entity) {
      const found = Object.keys(this._hass.states).find(
        (e) =>
          e.startsWith("sensor.") &&
          this._hass.states[e].attributes?.integration === "peak_shaver"
      );
      if (found) this._config.priority_entity = found;
    }
    if (!this._config.limit_entity) {
      const found = Object.keys(this._hass.states).find(
        (e) => e.startsWith("number.") && e.includes("hourly_limit")
      );
      if (found) this._config.limit_entity = found;
    }
  }

  _loads() {
    const st = this._hass?.states[this._config.priority_entity];
    return st?.attributes?.loads || [];
  }

  _shed() {
    const st = this._hass?.states[this._config.priority_entity];
    return st?.attributes?.shed || [];
  }

  _intervals() {
    const st = this._hass?.states[this._config.priority_entity];
    return st?.attributes?.toggle_intervals || {};
  }

  _defaultToggle() {
    const d = this._hass?.states[this._config.priority_entity]?.attributes?.default_toggle;
    return typeof d === "number" ? d : 300;
  }

  _limit() {
    return this._hass?.states[this._config.limit_entity]?.state ?? "5";
  }

  _signature() {
    const loads = this._loads();
    const stateSig = loads
      .map((e) => {
        const st = this._hass.states[e];
        if (!st) return e + ":missing";
        const members = st.attributes?.entity_id || [];
        return e + ":" + st.state + ":" + members.join("+");
      })
      .join("|");
    return (
      loads.join(",") +
      "#" + this._shed().join(",") +
      "#" + this._limit() +
      "#" + JSON.stringify(this._intervals()) +
      "#" + stateSig
    );
  }

  _isActive(e) {
    const st = this._hass.states[e];
    if (!st) return false;
    const d = e.split(".")[0];
    if (d === "climate") return !["off", "unavailable", "unknown"].includes(st.state);
    if (d === "group") {
      const members = st.attributes?.entity_id || [];
      return members.some((m) => this._isActive(m));
    }
    return st.state === "on";
  }

  _stateLabel(e) {
    const st = this._hass.states[e];
    if (!st) return "unavailable";
    const d = e.split(".")[0];
    if (d === "group") {
      const members = st.attributes?.entity_id || [];
      return members.length + (members.length === 1 ? " entity" : " entities");
    }
    return st.state;
  }

  _ctrlGroup(e) {
    const ctrl = new Set(["switch", "light", "fan", "input_boolean", "climate"]);
    const members = this._hass.states[e]?.attributes?.entity_id || [];
    return members.some((m) => ctrl.has(m.split(".")[0]));
  }

  _svc(service, data) {
    this._hass.callService("peak_shaver", service, data);
  }

  _render() {
    const hass = this._hass;
    const loads = this._loads();
    const shed = this._shed();
    const limit = this._limit();

    if (!this._config.priority_entity) {
      this.innerHTML =
        '<ha-card header="Load Shed Priority"><div style="padding:16px;color:var(--secondary-text-color)">Peak Shaver integration not found. Add it under Settings → Devices & Services.</div></ha-card>';
      return;
    }

    const inList = new Set(loads);
    const intervals = this._intervals();
    const defToggle = this._defaultToggle();
    const avail = Object.keys(hass.states)
      .filter((e) => this._config.domains.includes(e.split(".")[0]))
      .filter((e) => !inList.has(e))
      .filter((e) => (e.split(".")[0] === "group" ? this._ctrlGroup(e) : true))
      .sort();

    const rows = loads
      .map((e, i) => {
        const st = hass.states[e];
        const name = st?.attributes?.friendly_name || e;
        const isShed = shed.includes(e);
        const live = this._isActive(e);
        const label = this._stateLabel(e);
        const badge = isShed
          ? `<span class="badge shed">SHED</span>`
          : `<span class="badge ${live ? "on" : "off"}">${label}</span>`;
        const secs = typeof intervals[e] === "number" ? intervals[e] : defToggle;
        const mins = secs / 60;
        const mdisp = Number.isInteger(mins) ? mins : Math.round(mins * 10) / 10;
        return `
          <div class="row">
            <span class="rank">${i + 1}</span>
            <span class="name" title="${e}">${name}</span>
            ${badge}
            <span class="iv" title="Minimum minutes between switching this device on/off">
              <span class="ivc">&#9201;</span>
              <input type="number" class="ival" data-e="${e}" min="0" max="60" step="0.5" value="${mdisp}">
              <span class="ivu">min</span>
            </span>
            <span class="btns">
              <button class="ic up"   data-e="${e}" ${i === 0 ? "disabled" : ""} title="Shed sooner">&#9650;</button>
              <button class="ic down" data-e="${e}" ${i === loads.length - 1 ? "disabled" : ""} title="Shed later">&#9660;</button>
              <button class="ic rm"   data-e="${e}" title="Remove (restores if shed)">&#10005;</button>
            </span>
          </div>`;
      })
      .join("");

    const options = ['<option value="">+ add load&hellip;</option>']
      .concat(
        avail.map((e) => {
          const n = hass.states[e].attributes.friendly_name || e;
          const tag = e.split(".")[0];
          return `<option value="${e}">${n} (${tag})</option>`;
        })
      )
      .join("");

    this.innerHTML = `
      <ha-card header="${this._config.title}">
        <style>
          .card-content { padding: 8px 16px 16px; }
          .limit { display:flex; align-items:center; gap:8px; padding:4px 0 10px; margin-bottom:6px;
                   border-bottom:1px solid var(--divider-color); color:var(--secondary-text-color); font-size:13px; }
          .limit input { width:70px; padding:6px 8px; border-radius:8px; border:1px solid var(--divider-color);
                         background:var(--card-background-color); color:var(--primary-text-color); }
          .hint { color:var(--secondary-text-color); font-size:12px; margin-bottom:8px; }
          .row { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--divider-color); }
          .row:last-of-type { border-bottom:none; }
          .rank { width:20px; text-align:center; color:var(--secondary-text-color); font-variant-numeric:tabular-nums; }
          .name { flex:1; color:var(--primary-text-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .badge { font-size:11px; font-weight:600; padding:2px 6px; border-radius:8px; letter-spacing:.3px; text-transform:lowercase; }
          .badge.on { color:var(--success-color,#43a047); background:rgba(67,160,71,.12); }
          .badge.off { color:var(--secondary-text-color); background:var(--secondary-background-color); }
          .badge.shed { color:var(--error-color); background:rgba(229,57,53,.12); text-transform:none; }
          .iv { display:flex; align-items:center; gap:3px; color:var(--secondary-text-color); font-size:11px; }
          .iv .ivc { font-size:13px; line-height:1; }
          .iv input { width:44px; padding:4px 5px; border-radius:6px; border:1px solid var(--divider-color);
                      background:var(--card-background-color); color:var(--primary-text-color);
                      font-size:12px; text-align:right; }
          .iv .ivu { color:var(--secondary-text-color); }
          .btns { display:flex; gap:4px; }
          button.ic { width:30px; height:30px; border:none; border-radius:6px; cursor:pointer;
                      background:var(--secondary-background-color); color:var(--primary-text-color); font-size:13px; line-height:1; }
          button.ic:hover:not(:disabled) { background:var(--primary-color); color:var(--text-primary-color,#fff); }
          button.ic:disabled { opacity:.3; cursor:default; }
          button.rm:hover:not(:disabled) { background:var(--error-color); color:#fff; }
          .empty { color:var(--secondary-text-color); padding:8px 0; }
          .add { margin-top:12px; }
          select.picker { width:100%; padding:8px; border-radius:8px; border:1px solid var(--divider-color);
                          background:var(--card-background-color); color:var(--primary-text-color); }
        </style>
        <div class="card-content">
          <div class="limit">
            <span>Hourly limit</span>
            <input type="number" class="lim" min="1" max="15" step="0.1" value="${limit}" ${this._config.limit_entity ? "" : "disabled"}>
            <span>kWh</span>
          </div>
          <div class="hint">Top = shed first &middot; &#9201; min minutes between on/off per device &middot; &#9650; sooner &middot; &#9660; later &middot; &#10005; remove</div>
          ${rows || '<div class="empty">No loads configured.</div>'}
          <div class="add"><select class="picker">${options}</select></div>
        </div>
      </ha-card>`;

    this.querySelectorAll("button.up").forEach((b) =>
      b.addEventListener("click", () => this._svc("move_load", { item: b.dataset.e, direction: "up" }))
    );
    this.querySelectorAll("button.down").forEach((b) =>
      b.addEventListener("click", () => this._svc("move_load", { item: b.dataset.e, direction: "down" }))
    );
    this.querySelectorAll("button.rm").forEach((b) =>
      b.addEventListener("click", () => this._svc("remove_load", { item: b.dataset.e }))
    );
    this.querySelectorAll("input.ival").forEach((inp) =>
      inp.addEventListener("change", () => {
        const m = parseFloat(inp.value);
        if (!isNaN(m)) {
          const secs = Math.max(0, Math.min(3600, Math.round(m * 60)));
          this._svc("set_toggle_interval", { item: inp.dataset.e, seconds: secs });
        }
      })
    );
    const picker = this.querySelector("select.picker");
    if (picker)
      picker.addEventListener("change", () => {
        if (picker.value) this._svc("add_load", { item: picker.value });
      });
    const lim = this.querySelector("input.lim");
    if (lim && this._config.limit_entity)
      lim.addEventListener("change", () => {
        const v = parseFloat(lim.value);
        if (!isNaN(v))
          this._hass.callService("number", "set_value", {
            entity_id: this._config.limit_entity,
            value: v,
          });
      });
  }

  getCardSize() {
    return 3;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: 4 };
  }
}

if (!customElements.get("peak-shaver-card")) {
  customElements.define("peak-shaver-card", PeakShaverCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "peak-shaver-card")) {
  window.customCards.push({
    type: "peak-shaver-card",
    name: "Peak Shaver Card",
    description: "Reorder load-shed priority, set the kWh limit, and tune the per-device minimum toggle interval for the Peak Shaver integration",
  });
}
