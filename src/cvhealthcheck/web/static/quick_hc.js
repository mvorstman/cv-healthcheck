// ── INITIAL DATA ──
let CATS = (window.QUICK_HC_INITIAL_DATA && window.QUICK_HC_INITIAL_DATA.cats) || [];
const CC = (window.QUICK_HC_INITIAL_DATA && window.QUICK_HC_INITIAL_DATA.commcell) || {};

// ── STATE ──
let activeId = null;
let mode = 'overview'; // overview | config

// ── LOCAL STORAGE ──
const STATE_KEY = 'quickhc-state-v1';

function _loadState() {
  try { return JSON.parse(localStorage.getItem(STATE_KEY) || '{}'); } catch { return {}; }
}

function _saveState() {
  const state = {};
  for (const cat of CATS) {
    for (const s of cat.subjects) {
      const secs = {};
      for (const sec of (s.sections || [])) secs[sec.id] = sec.included;
      state[s.id] = { included: s.included, sections: secs, activeSource: s.activeSource };
    }
  }
  localStorage.setItem(STATE_KEY, JSON.stringify(state));
}

function _restoreState() {
  const saved = _loadState();
  for (const cat of CATS) {
    for (const s of cat.subjects) {
      if (!(s.id in saved)) continue;
      const sv = saved[s.id];
      if (sv.included !== undefined) s.included = sv.included;
      if (sv.activeSource !== undefined) s.activeSource = sv.activeSource;
      const secState = sv.sections || {};
      for (const sec of (s.sections || [])) {
        if (sec.id in secState) sec.included = secState[sec.id];
      }
    }
  }
}

// ── HELPERS ──
function allSubjs() { return CATS.flatMap(c => c.subjects); }
function findSubj(id) { return allSubjs().find(s => s.id === id); }
function findSec(sid, secId) { return findSubj(sid)?.sections?.find(s => s.id === secId); }

function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── LEFT NAV ──
function renderLeft() {
  const avail = allSubjs().filter(s => s.state !== 'nodata').length;
  const hdrAvail = document.getElementById('hdr-avail');
  if (hdrAvail) hdrAvail.textContent = avail + ' available';

  let h = '';
  CATS.forEach((cat, ci) => {
    h += `<div class="cat-group">
      <div class="cat-hdr" onclick="toggleCat('${cat.id}',this)">
        <span class="cat-icon">${cat.icon}</span>
        <span class="cat-label">${esc(cat.name)}</span>
        <span class="cat-chev ${cat.open ? 'open' : ''}">▶</span>
      </div>
      <div class="cat-body" id="cb-${cat.id}" style="max-height:${cat.open ? '2000px' : '0'}">`;
    cat.subjects.forEach(s => {
      const bc = s.state === 'ok' ? 'b-ok' : s.state === 'issues' ? 'b-issues' : 'b-nodata';
      const bi = s.state === 'ok' ? '✓' : s.state === 'issues' ? '!' : '';
      const isActive = s.id === activeId && mode === 'config';
      h += `<div class="subj-row${isActive ? ' active' : ''}" id="sr-${s.id}">
        <input type="checkbox" class="subj-cb" ${s.included ? 'checked' : ''} onclick="event.stopPropagation()" onchange="toggleInclude('${s.id}',this.checked)" title="Include in report">
        <span class="subj-name" onclick="openConfig('${s.id}')">${esc(s.name)}</span>
        <span class="subj-badge ${bc}">${bi}</span>
      </div>`;
    });
    h += `</div></div>`;
    if (ci < CATS.length - 1) h += `<div class="cat-div"></div>`;
  });
  document.getElementById('left-scroll').innerHTML = h;
  document.getElementById('btn-gen').disabled = !allSubjs().some(s => s.included);
}

function toggleCat(id, el) {
  const cat = CATS.find(c => c.id === id);
  cat.open = !cat.open;
  document.getElementById('cb-' + id).style.maxHeight = cat.open ? '2000px' : '0';
  el.querySelector('.cat-chev').classList.toggle('open', cat.open);
}

function toggleInclude(id, val) {
  findSubj(id).included = val;
  _saveState();
  document.getElementById('btn-gen').disabled = !allSubjs().some(s => s.included);
  if (mode === 'overview') showOverview();
  else renderLeft();
}

// ── SECTION BODY RENDERER ──
function secBody(sec) {
  const lm = {crit:'Critical',warn:'Warning',info:'Info',good:'Good'};
  const bm = {crit:'b-crit',warn:'b-warn',info:'b-info',good:'b-good'};
  const cm = {crit:'fc-crit',warn:'fc-warn',info:'fc-info',good:'fc-good'};

  if (sec.type === 'meta') {
    const gc = sec.rows.length > 4 ? 'meta-grid-3' : 'meta-grid-4';
    return `<div class="meta-grid ${gc}">${sec.rows.map(r =>
      `<div class="meta-card"><div class="meta-lbl">${esc(r.k)}</div><div class="meta-val ${r.cls || ''}">${esc(r.v)}</div></div>`
    ).join('')}</div>`;
  }

  if (sec.type === 'counters') {
    const cc = {Critical:'cc-crit',Warning:'cc-warn',Info:'cc-info',Good:'cc-good'};
    const total = Object.values(sec.counters).reduce((a, b) => a + b, 0);
    return `<div class="counter-chips">${Object.entries(sec.counters).map(([k, v]) =>
      `<div class="counter-chip"><div class="cc-n ${cc[k] || ''}">${v}</div><div class="cc-l">${k}</div></div>`
    ).join('')}<div class="counter-chip"><div class="cc-n" style="color:var(--text-2)">${total}</div><div class="cc-l">Total</div></div></div>`;
  }

  if (sec.type === 'findings_grid') {
    if (!sec.findings || !sec.findings.length) return `<div style="font-size:12px;color:var(--text-3)">No findings.</div>`;
    return `<div class="finding-grid">${sec.findings.map(f =>
      `<div class="finding-card"><div class="fc-top ${cm[f.sev]}">${lm[f.sev]}</div><div class="fc-body"><div class="fc-title">${esc(f.title)}</div><div class="fc-rem">${esc(f.rem)}</div></div></div>`
    ).join('')}</div>`;
  }

  if (sec.type === 'findings_list') {
    if (!sec.findings || !sec.findings.length) return `<div style="font-size:12px;color:var(--text-3)">No findings.</div>`;
    return sec.findings.map(f =>
      `<div class="finding-row"><span class="f-badge ${bm[f.sev]}">${lm[f.sev]}</span><div class="f-body"><div class="f-ttl">${esc(f.title)}</div><div class="f-rem">${esc(f.rem)}</div></div></div>`
    ).join('');
  }

  if (sec.type === 'workload') {
    return sec.workload.map(ws =>
      `<div class="wl-sec-name">${esc(ws.name)}</div>
      <table class="wl-table"><thead><tr><th>License</th><th>Entitlement</th><th>Used</th><th>Utilisation</th></tr></thead><tbody>
      ${ws.rows.map(r => {
        const col = r.pct >= 90 ? 'uf-r' : r.pct >= 80 ? 'uf-a' : 'uf-g';
        return `<tr><td>${esc(r.license)}</td><td style="font-family:var(--mono);font-size:11px">${esc(r.ent)}</td><td style="font-family:var(--mono);font-size:11px">${esc(r.used)}</td><td><div class="usage-wrap"><div class="usage-fill ${col}" style="width:${r.pct}%"></div></div><span style="font-size:10px;color:var(--text-2)">${r.pct}%</span></td></tr>`;
      }).join('')}</tbody></table>`
    ).join('');
  }

  if (sec.type === 'table') {
    if (!sec.rows || !sec.rows.length) return `<div style="font-size:12px;color:var(--text-3)">No data.</div>`;
    const hdrs = (sec.columns || []).map(c => `<th>${esc(c)}</th>`).join('');
    const body = sec.rows.map(r =>
      `<tr>${r.map(v => `<td style="font-family:var(--mono);font-size:11px">${esc(v != null ? v : '—')}</td>`).join('')}</tr>`
    ).join('');
    return `<table class="wl-table"><thead><tr>${hdrs}</tr></thead><tbody>${body}</tbody></table>`;
  }

  if (sec.type === 'chart_growth') {
    const cd = sec.chart;
    const mT = Math.max(...cd.totals, 1);
    const mA = Math.max(...cd.added, 1);
    const bars = cd.months.map((m, i) => {
      const th = Math.round((cd.totals[i] / mT) * 62) + 4;
      const ah = Math.round((cd.added[i] / mA) * 44) + 4;
      return `<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end" title="${esc(m)}: ${cd.totals[i]}, +${cd.added[i]}"><div style="background:rgba(34,197,94,.35);height:${th}px;border-radius:2px 2px 0 0;position:relative"><div style="position:absolute;bottom:0;left:0;right:0;height:${ah}px;background:rgba(79,142,247,.85);border-radius:2px 2px 0 0"></div></div></div>`;
    }).join('');
    const latest = cd.latest_total != null ? String(cd.latest_total) : '';
    const yoy = cd.yoy_pct ? ` · YoY: <strong style="color:var(--green)">${esc(cd.yoy_pct)}</strong>` : '';
    return `<div class="mini-chart">${bars}</div><div class="chart-legend"><div class="legend-item"><div class="legend-dot" style="background:rgba(79,142,247,.85)"></div>Added</div><div class="legend-item"><div class="legend-dot" style="background:rgba(34,197,94,.35)"></div>Total</div>${latest ? `<span style="margin-left:auto;font-size:11px;color:var(--text-2)">Latest: <strong style="color:var(--text-1)">${latest}</strong>${yoy}</span>` : ''}</div>`;
  }

  if (sec.type === 'chart_capacity') {
    const cd = sec.chart;
    const purchased = cd.purchased || 1;
    const bars = cd.months.map((m, i) => {
      const pct = cd.used[i] / purchased;
      const col = pct > 0.9 ? 'rgba(239,68,68,.8)' : pct > 0.75 ? 'rgba(245,158,11,.8)' : 'rgba(59,130,246,.7)';
      return `<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end" title="${esc(m)}: ${cd.used[i]}"><div style="background:var(--border-hi);height:66px;border-radius:2px 2px 0 0;position:relative;overflow:hidden"><div style="position:absolute;bottom:0;left:0;right:0;height:${Math.round(pct * 66)}px;background:${col}"></div></div></div>`;
    }).join('');
    const utilPct = cd.utilisation_pct != null ? cd.utilisation_pct + '%' : '';
    const purchasedLabel = cd.purchased != null ? cd.purchased + ' TB' : '';
    return `<div class="mini-chart">${bars}</div><div class="chart-legend"><div class="legend-item"><div class="legend-dot" style="background:rgba(59,130,246,.7)"></div>Used</div>${purchasedLabel ? `<div class="legend-item"><div class="legend-dot" style="background:var(--border-hi)"></div>Purchased (${esc(purchasedLabel)})</div>` : ''}${utilPct ? `<span style="margin-left:auto;font-size:11px;color:var(--text-2)">Utilisation: <strong style="color:var(--text-1)">${esc(utilPct)}</strong></span>` : ''}</div>`;
  }

  if (sec.type === 'text') return `<div style="font-size:12px;color:var(--text-2)">${esc(sec.text || '')}</div>`;
  return '';
}

// ── SECTION TILE ──
function secTile(subjId, sec, showCheckbox) {
  const body = sec.included ? secBody(sec) : '';
  const right = showCheckbox
    ? `<label class="sec-inc-label"><span style="color:var(--text-2)">Include in report</span><input type="checkbox" class="sec-inc-cb" ${sec.included ? 'checked' : ''} onchange="toggleSec('${subjId}','${sec.id}',this.checked)"></label>`
    : (sec.included ? `<span class="inc-pill-yes">Included</span>` : `<span class="inc-pill-no">Not included</span>`);
  return `<div class="sec-tile${sec.included ? '' : ' excluded'}">
    <div class="sec-tile-hdr${body ? ' sec-tile-hdr-border' : ''}">
      <span class="sec-title">${esc(sec.title)}</span>
      <span class="sec-meta">${esc(sec.meta || '')}</span>
      ${right}
    </div>
    ${body ? `<div class="sec-tile-body">${body}</div>` : ''}
  </div>`;
}

// ── OVERVIEW ──
function showOverview() {
  activeId = null; mode = 'overview';
  renderLeft();
  document.getElementById('right-footer').style.display = 'none';
  const subtitle = CC.name ? (CC.version ? CC.name + ' · ' + CC.version : CC.name) : '';
  const hdrSub = document.getElementById('hdr-subtitle');
  if (hdrSub) hdrSub.textContent = subtitle;

  const bycat = CATS.map(cat => ({cat, subjects: cat.subjects.filter(s => s.included)})).filter(c => c.subjects.length);
  let subjList = '';
  if (bycat.length) {
    bycat.forEach(({cat, subjects}) => {
      subjList += `<div style="font-size:11px;font-weight:600;color:var(--text-3);font-family:var(--mono);text-transform:uppercase;letter-spacing:.06em;margin:10px 0 4px">${esc(cat.name)}</div>`;
      subjects.forEach(s => {
        const bc = s.state === 'ok' ? 'b-ok' : s.state === 'issues' ? 'b-issues' : 'b-nodata';
        const bi = s.state === 'ok' ? '✓' : s.state === 'issues' ? '!' : '';
        subjList += `<div class="cfg-tile" style="display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;margin-bottom:6px" onclick="openConfig('${s.id}')" onmouseenter="this.style.borderColor='var(--border-hi)'" onmouseleave="this.style.borderColor='var(--border)'"><span class="subj-badge ${bc}" style="flex-shrink:0">${bi}</span><span style="font-size:13px;font-weight:500;flex:1">${esc(s.name)}</span><span style="font-size:11px;color:var(--text-3)">${esc(s.subtitle || '')}</span></div>`;
      });
    });
  } else {
    subjList = `<div class="cfg-tile" style="color:var(--text-3);font-size:12px">No subjects included. Use the checkboxes on the left.</div>`;
  }
  document.getElementById('right-body').innerHTML = `<div class="cfg-wrap">
    <div class="cfg-title">Quick HealthCheck</div>
    ${subtitle ? `<div style="font-size:12px;color:var(--text-2);margin-top:2px">${esc(subtitle)}</div>` : ''}
    <div class="cfg-sec"><div class="cfg-sec-title">Report Sections</div>${subjList}</div>
    <div class="cfg-sec"><div class="cfg-sec-title">Compliance Status</div>
      <div class="placeholder-tile">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <span style="font-size:13px;font-weight:600">Compliance overview</span>
          <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:8px;background:rgba(136,136,160,.1);color:var(--text-3);font-family:var(--mono)">Not yet implemented</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);line-height:1.6">Pass/fail compliance status across all included subjects will appear here once compliance rules are configured.</div>
      </div>
    </div>
  </div>`;
}

// ── CONFIG VIEW ──
function openConfig(id) {
  activeId = id; mode = 'config';
  renderLeft();
  const s = findSubj(id);
  if (!s) return;

  // Footer
  const rf = document.getElementById('right-footer');
  const srcName = {rest_api:'Direct REST API', rest_report:'REST Report', import:'Import File'};
  rf.style.display = 'flex';
  document.getElementById('rf-source').textContent = s.activeSource ? 'Source: ' + (srcName[s.activeSource] || s.activeSource) : '';
  const lnk = document.getElementById('rf-link');
  if (s.fullUrl) { lnk.href = s.fullUrl; lnk.style.display = ''; } else { lnk.style.display = 'none'; }

  // Source buttons
  const sl = {v:'● Validated', n:'○ Not configured'};
  const sc = {v:'ss-v', n:'ss-n'};
  const srcBtns = (s.sources || []).map(src =>
    `<button class="src-btn${s.activeSource === src.id ? ' src-active' : ''}" data-src="${src.id}" data-subj="${s.id}" onclick="setActiveSrc(this.dataset.subj,this.dataset.src)">${esc(src.name)}</button>`
  ).join('');

  const activeSrc = (s.sources || []).find(src => src.id === s.activeSource);
  let srcPanel = '';
  if (activeSrc) {
    srcPanel = `<div class="src-meta-panel"><span class="src-status ${sc[activeSrc.status] || 'ss-n'}">${sl[activeSrc.status] || '○ Not configured'}</span>`;
    if (activeSrc.meta && activeSrc.meta.length) {
      srcPanel += `<div style="margin-top:8px">${activeSrc.meta.map(m => `<div class="src-meta-row"><span>${esc(m.k)}</span><span>${esc(m.v)}</span></div>`).join('')}</div>`;
    }
    if (activeSrc.hasUpload && activeSrc.importUrl) {
      srcPanel += `<div class="src-upload">
        <form method="post" action="${esc(activeSrc.importUrl)}" enctype="multipart/form-data" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <label class="btn-sm btn-sm-s" style="cursor:pointer">
            Choose File
            <input type="file" name="${esc(activeSrc.importField || 'file')}" hidden accept=".html,.htm,.csv,.json" onchange="this.closest('.src-upload').querySelector('.src-filename').textContent=this.files[0]?this.files[0].name:''">
          </label>
          <span class="src-filename"></span>
          <button type="submit" class="btn-sm btn-sm-p">Import</button>
        </form>
      </div>`;
    } else if (activeSrc.hasUpload && s.fullUrl) {
      srcPanel += `<div class="src-upload" style="margin-top:10px"><a href="${esc(s.fullUrl)}" class="btn-sm btn-sm-s" style="text-decoration:none">Import via detail page →</a></div>`;
    }
    srcPanel += `</div>`;
  }

  // Identity tile (CommCell context, shown for all subjects)
  let identityRows = '';
  if (CC.exists) {
    const rows = [
      {k:'CommCell Name', v: CC.name || '—'},
      {k:'Version', v: CC.version || '—'},
      {k:'Timezone', v: CC.timezone || null},
      {k:'CommCell ID', v: CC.id || null},
    ].filter(r => r.v);
    if (rows.length) {
      const lastIdx = rows.length - 1;
      identityRows = `<div style="display:grid;gap:0;margin-top:10px">${rows.map((r, i) =>
        `<div class="src-meta-row"${i === lastIdx ? ' style="border-bottom:none"' : ''}><span>${esc(r.k)}</span><span>${esc(r.v)}</span></div>`
      ).join('')}</div>`;
    }
  }

  // Section tiles
  const secTiles = (s.sections || []).map(sec => secTile(s.id, sec, true)).join('');

  document.getElementById('right-body').innerHTML = `<div class="cfg-wrap">
    <div class="cfg-title">${esc(s.name)}</div>
    <div class="cfg-sec">
      <div class="cfg-sec-title">Description</div>
      <div class="cfg-tile">
        <textarea class="cfg-desc-edit" placeholder="Add a description for this subject…" rows="2">${esc(s.subtitle || '')}</textarea>
        <div class="cfg-tile-hint">Not yet persisted — placeholder only</div>
      </div>
    </div>
    ${(s.sources || []).length > 0 ? `<div class="cfg-sec">
      <div class="cfg-sec-title">Data Source</div>
      <div class="src-selector-row"><span class="src-selector-label">Select source</span>${srcBtns}</div>
      ${srcPanel}
    </div>` : ''}
    <div class="cfg-sec">
      <div class="cfg-sec-title">Report Sections</div>
      <div class="cfg-tile">
        <div style="display:flex;align-items:flex-start;justify-content:space-between${identityRows ? ';margin-bottom:0' : ''}">
          <div>
            <div style="font-size:13px;font-weight:600">${esc(s.name)}</div>
            <div style="font-size:11px;color:var(--text-2);margin-top:2px">${s.sections && s.sections.length ? s.sections.length + ' section' + (s.sections.length === 1 ? '' : 's') + ' below' : 'No report sections configured'}</div>
          </div>
          <label class="sec-inc-label">
            Include in report
            <input type="checkbox" class="sec-inc-cb" ${s.included ? 'checked' : ''} onchange="toggleInclude('${s.id}',this.checked)">
          </label>
        </div>
        ${identityRows}
      </div>
      ${secTiles}
    </div>
    <div class="cfg-sec">
      <div class="cfg-sec-title">Compliance</div>
      <div class="placeholder-tile">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
          <span style="font-size:13px;font-weight:600">Compliance rules</span>
          <span style="font-size:10px;font-weight:600;padding:2px 8px;border-radius:8px;background:rgba(136,136,160,.1);color:var(--text-3);font-family:var(--mono)">Not yet implemented</span>
        </div>
        <div style="font-size:12px;color:var(--text-2);line-height:1.6">Compliance rules for this subject will be configurable here.</div>
      </div>
    </div>
  </div>`;
}

function toggleSec(sid, secId, val) {
  const sec = findSec(sid, secId);
  if (sec) sec.included = val;
  _saveState();
  openConfig(sid);
}

function setActiveSrc(subjId, srcId) {
  findSubj(subjId).activeSource = srcId;
  _saveState();
  openConfig(subjId);
}

// ── GENERATE REPORT ──
document.getElementById('btn-gen').addEventListener('click', () => {
  const form = document.getElementById('report-form');
  form.querySelectorAll('input[name="selection_ids"]').forEach(el => el.remove());
  for (const cat of CATS) {
    for (const s of cat.subjects) {
      if (!s.included) continue;
      const inp = document.createElement('input');
      inp.type = 'hidden'; inp.name = 'selection_ids'; inp.value = s.id;
      form.appendChild(inp);
      for (const sec of (s.sections || [])) {
        if (!sec.included) continue;
        const si = document.createElement('input');
        si.type = 'hidden'; si.name = 'selection_ids'; si.value = sec.id;
        form.appendChild(si);
      }
    }
  }
  form.submit();
});

// ── INIT ──
_restoreState();
renderLeft();
showOverview();
