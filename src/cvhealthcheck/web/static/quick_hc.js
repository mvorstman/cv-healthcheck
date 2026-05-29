// ── INITIAL DATA ──
let CATS = (window.QUICK_HC_INITIAL_DATA && window.QUICK_HC_INITIAL_DATA.cats) || [];
const CC = (window.QUICK_HC_INITIAL_DATA && window.QUICK_HC_INITIAL_DATA.commcell) || {};

// ── STATE ──
let activeId = null;
let mode = 'overview'; // overview | config
let descriptionSaveState = { status: 'idle', message: '' };

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
      state[s.id] = { included: s.included, sections: secs };
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

// ── CONNECTION BADGE ──
// Badge state precedence:
//   1. Synchronous repaint from window.IS_AUTHENTICATED (server-rendered on
//      page load, updated locally after sign-in / sign-out).
//   2. Async refresh against /api/auth/status — keeps the badge accurate on
//      long-lived sessions after token expiry without reloading the page.
//   3. On fetch failure, leave the badge in its last known state rather
//      than flipping to "disconnected".

function _paintConnBadge(isAuth) {
  const dot = document.getElementById('conn-dot');
  const label = document.getElementById('conn-label');
  if (!label) return;
  if (isAuth) {
    label.textContent = 'Connected';
    if (dot) dot.className = 'conn-dot conn-dot-ok';
    const badge = document.getElementById('conn-badge');
    if (badge) badge.title = 'Connected — click to sign out';
  } else {
    label.textContent = 'Connect';
    if (dot) dot.className = 'conn-dot conn-dot-idle';
    const badge = document.getElementById('conn-badge');
    if (badge) badge.title = 'Click to connect';
  }
}

function _updateConnBadge() {
  // First, repaint synchronously from the last known value so callers like
  // renderLeft() see an immediate result.
  _paintConnBadge(!!window.IS_AUTHENTICATED);
  // Then, refresh from the server. Network errors leave the badge as is.
  fetch('/api/auth/status', { credentials: 'same-origin' })
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data || typeof data.authenticated !== 'boolean') return;
      window.IS_AUTHENTICATED = data.authenticated;
      // Track the username so the connect modal's sign-out branch can show
      // "Signed in as <user>" without an extra round-trip. Null is a valid
      // value (legacy sessions and anonymous sessions both produce null).
      window.CURRENT_USERNAME = (typeof data.username === 'string' && data.username)
        ? data.username
        : null;
      _paintConnBadge(data.authenticated);
    })
    .catch(() => { /* leave badge in last known state */ });
}

// Module-level interval handle so the 60s poll does not stack if
// _startConnBadgePolling() is invoked more than once.
let _connBadgeIntervalId = null;
function _startConnBadgePolling() {
  if (_connBadgeIntervalId !== null) return;
  _connBadgeIntervalId = setInterval(_updateConnBadge, 60000);
  window.addEventListener('focus', _updateConnBadge);
}

// ── REPORT ACTION BAR ──
function _updateReportBar() {
  const included = allSubjs().filter(s => s.included);
  const bar = document.getElementById('report-bar');
  const label = document.getElementById('report-bar-label');
  if (!bar) return;
  if (included.length > 0) {
    bar.hidden = false;
    if (label) label.textContent = included.length + ' subject' + (included.length !== 1 ? 's' : '') + ' selected for report';
  } else {
    bar.hidden = true;
  }
}

// ── SIDEBAR NAV ACTIVE STATE ──
function _setNavActive(id) {
  document.querySelectorAll('.lnav-item').forEach(el => el.classList.remove('lnav-active'));
  if (id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('lnav-active');
  }
}

// ── LEFT CATALOG (no checkboxes) ──
function renderLeft() {
  _updateConnBadge();
  _updateReportBar();

  let h = '';
  CATS.forEach((cat, ci) => {
    h += `<div class="cat-group">
      <div class="cat-hdr" onclick="toggleCat('${cat.id}',this)">
        <span class="cat-chevron">${cat.open ? '▾' : '▸'}</span>
        <span class="cat-label">${esc(cat.name)}</span>
      </div>
      <div class="cat-body" id="cb-${cat.id}" style="max-height:${cat.open ? '2000px' : '0'}">`;
    cat.subjects.forEach(s => {
      const isActive = s.id === activeId && mode === 'config';
      const hasData = s.state !== 'nodata';
      const isDraft = s.status && s.status !== 'active';
      h += `<div class="subj-row${isActive ? ' active' : ''}" id="sr-${s.id}" onclick="openConfig('${s.id}')">
        <span class="subj-dot${hasData ? ' dot-ok' : ''}"></span>
        <span class="subj-name">${esc(s.name)}</span>
        ${isDraft ? `<span class="subj-badge-draft">${esc(s.status)}</span>` : ''}
      </div>`;
    });
    h += `</div></div>`;
    if (ci < CATS.length - 1) h += `<div class="cat-div"></div>`;
  });
  document.getElementById('left-catalog').innerHTML = h;
}

function toggleCat(id) {
  const cat = CATS.find(c => c.id === id);
  cat.open = !cat.open;
  document.getElementById('cb-' + id).style.maxHeight = cat.open ? '2000px' : '0';
  renderLeft();
}

function toggleInclude(id, val) {
  findSubj(id).included = val;
  _saveState();
  _updateReportBar();
  renderLeft();
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
    ? `<label class="sec-inc-label"><input type="checkbox" class="sec-inc-cb" ${sec.included ? 'checked' : ''} onchange="toggleSec('${subjId}','${sec.id}',this.checked)" title="Select section" aria-label="Select ${esc(sec.title)} section for report generation"></label>`
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

// ── ACTIVE-SUBJECT URL FRAGMENT ──
// Preserved across full-page reloads (e.g. after a Collect POST that
// redirects back to /quick-hc) so the user doesn't lose their place.
const _SUBJECT_HASH_RE = /^#subject=(.+)$/;

function _readSubjectFromHash() {
  const m = (window.location.hash || '').match(_SUBJECT_HASH_RE);
  if (!m) return null;
  try { return decodeURIComponent(m[1]); } catch { return null; }
}

function _writeSubjectToHash(id) {
  const next = id ? `#subject=${encodeURIComponent(id)}` : '';
  if ((window.location.hash || '') === next) return;
  // replaceState avoids polluting browser history; pathname+search are
  // preserved so flash-message query strings (if any) survive.
  history.replaceState(null, '', window.location.pathname + window.location.search + next);
}

// ── OVERVIEW ──
function showOverview() {
  activeId = null; mode = 'overview';
  _writeSubjectToHash(null);
  _setNavActive('nav-overview');
  renderLeft();
  document.getElementById('right-footer').style.display = 'none';

  const subtitle = CC.name ? (CC.version ? CC.name + ' · ' + CC.version : CC.name) : '';

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
    subjList = `<div class="cfg-tile" style="color:var(--text-3);font-size:12px">No subjects selected. Open a subject and toggle "Include in report".</div>`;
  }
  document.getElementById('right-body').innerHTML = `<div class="cfg-wrap">
    <div class="cfg-title">Quick HealthCheck</div>
    ${subtitle ? `<div style="font-size:12px;color:var(--text-2);margin-top:2px">${esc(subtitle)}</div>` : ''}
    <div class="cfg-sec"><div class="cfg-sec-title">Report Sections</div>${subjList}</div>
  </div>`;
}

// ── CONFIG VIEW ──
function openConfig(id) {
  activeId = id; mode = 'config';
  _writeSubjectToHash(id);
  descriptionSaveState = { status: 'idle', message: '' };
  _setNavActive(null);
  renderLeft();
  const s = findSubj(id);
  if (!s) return;

  // Footer (source attribution)
  const rf = document.getElementById('right-footer');
  const srcName = {
    rest_command_center_api:'REST / Command Center API',
    rest_reports_plus:'REST / Reports Plus',
    json_import:'JSON import',
    csv_import:'CSV import',
    html_import:'HTML import',
  };
  rf.style.display = 'flex';
  document.getElementById('rf-source').textContent = s.activeSource ? 'Source: ' + (srcName[s.activeSource] || s.activeSource) : '';

  // ADR 0004: provenance rows for the Data Source section — last-collected
  // timestamp (UTC) and the template-version dropdown. The dropdown lists the
  // subject family's versions; selecting one pins it for the next collection.
  // Today every family has one version, so the dropdown shows a single option.
  const vi = s.version_info || {};
  const versions = vi.versions || [];
  const activeVer = vi.active || s.id;
  let provRows = '';
  if (s.last_collected) {
    provRows += `<div class="src-meta-row"><span>Last collected</span><span>${esc(fmtUtc(s.last_collected))}</span></div>`;
  }
  if (versions.length) {
    const opts = versions.map(v =>
      `<option value="${esc(v)}"${v === activeVer ? ' selected' : ''}>${esc(v)}</option>`
    ).join('');
    provRows += `<div class="src-meta-row"><span>Template</span><span>`
      + `<select class="version-dropdown" onchange="setVersion('${esc(s.id)}', this.value)"${versions.length < 2 ? ' disabled' : ''}>${opts}</select>`
      + `</span></div>`;
  }
  const provBlock = provRows ? `<div class="src-provenance" style="margin-top:8px">${provRows}</div>` : '';

  // Source buttons
  const sl = {v:'● Validated', a:'● Available', n:'○ Not configured', ni:'○ Not implemented'};
  const sc = {v:'ss-v', a:'ss-v', n:'ss-n', ni:'ss-n'};
  const srcBtns = (s.sources || []).map(src =>
    `<button class="src-btn${s.activeSource === src.id ? ' src-active' : ''}" data-src="${src.id}" data-subj="${s.id}" onclick="setActiveSrc(this.dataset.subj,this.dataset.src)">${esc(src.name)}</button>`
  ).join('');

  const activeSrc = (s.sources || []).find(src => src.id === s.activeSource);
  let srcPanel = '';
  if (activeSrc) {
    srcPanel = `<div class="src-meta-panel"><span class="src-status ${sc[activeSrc.status] || 'ss-n'}">${sl[activeSrc.status] || '○ Not configured'}</span>`;
    if (activeSrc.desc) {
      srcPanel += `<div class="src-meta-desc">${esc(activeSrc.desc)}</div>`;
    }
    if (activeSrc.meta && activeSrc.meta.length) {
      srcPanel += `<div style="margin-top:8px">${activeSrc.meta.map(m => `<div class="src-meta-row"><span>${esc(m.k)}</span><span>${esc(m.v)}</span></div>`).join('')}</div>`;
    } else {
      srcPanel += `<div class="src-meta-empty">No source metadata is available yet.</div>`;
    }

    // Upload action (inline — no page navigation)
    const uploadAction = (activeSrc.actions || []).find(action => action.kind === 'upload' && action.importUrl);
    if (uploadAction) {
      const fid = 'file-' + s.id.replace(/[^a-z0-9]/g, '_');
      srcPanel += `<div class="src-upload" id="src-upload-${esc(s.id)}">
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <label class="btn-sm btn-sm-s" style="cursor:pointer">
            Choose File
            <input type="file" id="${fid}" name="${esc(uploadAction.importField || 'file')}" hidden
              accept="${esc(uploadAction.accept || '.html,.htm,.csv,.json')}"
              onchange="document.getElementById('fn-${esc(s.id)}').textContent=this.files[0]?this.files[0].name:''">
          </label>
          <span class="src-filename" id="fn-${esc(s.id)}"></span>
          <button type="button" class="btn-sm btn-sm-p"
            onclick="submitImport('${esc(s.id)}','${esc(uploadAction.importUrl)}','${esc(uploadAction.importField || 'file')}')">
            ${esc(uploadAction.label || 'Import')}
          </button>
        </div>
        <div class="import-result" id="import-result-${esc(s.id)}" hidden></div>
      </div>`;
    }

    // Collect action (REST)
    const collectAction = (activeSrc.actions || []).find(action => action.kind === 'collect' && action.collectUrl);
    if (collectAction) {
      srcPanel += `<div class="src-upload">
        <form method="post" action="${esc(collectAction.collectUrl)}" style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button type="submit" class="btn-sm btn-sm-p">${esc(collectAction.label || 'Collect')}</button>
        </form>
      </div>`;
    }
    srcPanel += `</div>`;
  }

  // CommCell identity (environment subject only)
  let identityRows = '';
  if (s.id === 'environment' && CC.exists) {
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

  const includeToggle = `<div class="include-row">
    <span class="include-label">Include in report</span>
    <label class="toggle-wrap">
      <input type="checkbox" class="toggle-cb" ${s.included ? 'checked' : ''} onchange="toggleInclude('${s.id}',this.checked)">
      <span class="toggle-track"><span class="toggle-thumb"></span></span>
    </label>
  </div>`;

  // Danger zone (non-system subjects only)
  const deleteSection = s.created_by !== 'system' ? `
    <div class="cfg-sec">
      <div class="cfg-sec-title">Danger Zone</div>
      <div class="cfg-tile" style="border-color:var(--c-crit-bd)">
        <form method="post" action="/quick-hc/${encodeURIComponent(s.id)}/delete" onsubmit="return confirm('Remove \\'${s.name.replace(/'/g, "\\'")}\\'  from the catalog?\\nThis will also delete any imported data. This cannot be undone.')">
          <button type="submit" class="btn-danger">Delete Subject</button>
        </form>
      </div>
    </div>` : '';

  // Draft badge (non-active subjects)
  const draftBadge = (s.status && s.status !== 'active')
    ? `<span class="cfg-badge-draft">${esc(s.status)}</span>`
    : '';

  document.getElementById('right-body').innerHTML = `<div class="cfg-wrap">
    <div class="cfg-title-row">
      <div class="cfg-title">${esc(s.name)}${draftBadge}</div>
      ${includeToggle}
    </div>
    <div class="cfg-sec">
      <div class="cfg-sec-title">Description</div>
      <div class="cfg-tile">
        <textarea id="cfg-desc-edit" class="cfg-desc-edit" placeholder="Add a description for this subject…" rows="2" oninput="autoResizeDescription(this)">${esc(s.description || '')}</textarea>
        <div class="cfg-desc-actions">
          <button type="button" class="btn-sm btn-sm-p" onclick="saveDescription('${s.id}')">Save</button>
          <span class="cfg-desc-status${descriptionSaveState.status === 'saved' ? ' cfg-desc-status-saved' : ''}${descriptionSaveState.status === 'error' ? ' cfg-desc-status-error' : ''}">${esc(descriptionSaveState.message || 'Saved description overrides are stored separately from source artifacts.')}</span>
        </div>
      </div>
    </div>
    ${(s.sources || []).length > 0 ? `<div class="cfg-sec">
      <div class="cfg-sec-title">Data Source</div>
      <div class="src-selector-row"><span class="src-selector-label">Select source</span>${srcBtns}</div>
      ${srcPanel}
      ${provBlock}
    </div>` : ''}
    <div class="cfg-sec">
      <div class="cfg-sec-title">Report Sections</div>
      ${identityRows ? `<div class="cfg-tile">${identityRows}</div>` : ''}
      ${secTiles}
    </div>
    ${deleteSection}
  </div>`;
  requestAnimationFrame(bindDescriptionEditor);
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

// ADR 0004: persist the source-tile version-dropdown selection. POSTs to the
// pin route, which records the choice for the active customer + subject
// family; the next collection of this family uses the chosen template.
function setVersion(subjId, version) {
  const f = document.createElement('form');
  f.method = 'POST';
  f.action = '/quick-hc/' + encodeURIComponent(subjId) + '/pin-version';
  const inp = document.createElement('input');
  inp.type = 'hidden';
  inp.name = 'version';
  inp.value = version;
  f.appendChild(inp);
  document.body.appendChild(f);
  f.submit();
}

// Format an ISO timestamp as "YYYY-MM-DD HH:MM UTC" for the source tile.
function fmtUtc(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = n => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} `
       + `${p(d.getUTCHours())}:${p(d.getUTCMinutes())} UTC`;
}

function setDescriptionStatus(status, message) {
  const el = document.querySelector('.cfg-desc-status');
  if (!el) return;
  el.className = 'cfg-desc-status';
  if (status === 'saved') el.classList.add('cfg-desc-status-saved');
  if (status === 'error') el.classList.add('cfg-desc-status-error');
  el.textContent = message;
}

function autoResizeDescription(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

function bindDescriptionEditor() {
  const input = document.getElementById('cfg-desc-edit');
  if (!input) return;
  autoResizeDescription(input);
}

async function saveDescription(subjId) {
  const s = findSubj(subjId);
  if (!s) return;
  const input = document.querySelector('.cfg-desc-edit');
  if (!input) return;
  const description = input.value;
  descriptionSaveState = { status: 'saving', message: 'Saving…' };
  setDescriptionStatus('saving', 'Saving…');
  try {
    const response = await fetch(`/api/quick-hc/subject/${encodeURIComponent(subjId)}/description`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const saved = await response.json();
    s.description = saved.description || description;
    descriptionSaveState = { status: 'saved', message: 'Description saved.' };
    autoResizeDescription(input);
    setDescriptionStatus('saved', 'Description saved.');
  } catch (_err) {
    descriptionSaveState = { status: 'error', message: 'Description save failed.' };
    setDescriptionStatus('error', 'Description save failed.');
  }
}

// ── INLINE FILE IMPORT ──
async function submitImport(subjId, importUrl, fieldName) {
  const safeId = subjId.replace(/[^a-z0-9_]/gi, '_');
  const fileInput = document.getElementById('file-' + safeId);
  const resultEl = document.getElementById('import-result-' + subjId);

  if (!fileInput || !fileInput.files[0]) {
    _showImportResult(resultEl, 'error', 'Please select a file first.');
    return;
  }

  _showImportResult(resultEl, 'loading', 'Importing…');

  const formData = new FormData();
  formData.append(fieldName, fileInput.files[0]);

  try {
    const resp = await fetch(importUrl, {
      method: 'POST',
      headers: { 'X-Inline': '1' },
      body: formData,
    });
    const data = await resp.json();
    if (data.success) {
      _showImportResult(resultEl, 'success', data.message || 'Import successful.');
      // Reload subject data from the API to reflect new artifact
      _reloadSubject(subjId);
    } else {
      _showImportResult(resultEl, 'error', data.error || 'Import failed.');
    }
  } catch (err) {
    _showImportResult(resultEl, 'error', 'Import failed: ' + err.message);
  }
}

function _showImportResult(el, status, message) {
  if (!el) return;
  el.hidden = false;
  el.className = 'import-result import-' + status;
  el.textContent = message;
}

async function _reloadSubject(subjId) {
  try {
    const resp = await fetch(`/api/quick-hc/subject/${encodeURIComponent(subjId)}`);
    if (!resp.ok) return;
    const updated = await resp.json();
    // Patch into CATS so subsequent renders reflect new artifact
    for (const cat of CATS) {
      const idx = cat.subjects.findIndex(s => s.id === subjId);
      if (idx !== -1) {
        const prev = cat.subjects[idx];
        cat.subjects[idx] = Object.assign({}, prev, updated, {
          included: prev.included,
          activeSource: prev.activeSource,
        });
        break;
      }
    }
    renderLeft();
  } catch (_) {
    // Non-critical: subject panel still shows success message
  }
}

// ── CONNECT MODAL ──
function openConnectModal() {
  const modal = document.getElementById('connect-modal');
  if (!modal) return;
  const signin = document.getElementById('connect-modal-signin');
  const signout = document.getElementById('connect-modal-signout');
  const title = document.getElementById('connect-modal-title');
  const signinErr = document.getElementById('connect-error');
  const signoutErr = document.getElementById('signout-error');
  if (signinErr) signinErr.hidden = true;
  if (signoutErr) signoutErr.hidden = true;

  if (window.IS_AUTHENTICATED) {
    // Sign-out branch — populate username from the cached value (kept in
    // sync by _updateConnBadge's polling fetch). Falls back to a generic
    // sentence if username is unknown (legacy session pre-username field).
    if (signin) signin.hidden = true;
    if (signout) signout.hidden = false;
    if (title) title.textContent = 'Sign out of Commvault';
    const nameEl = document.getElementById('signout-username');
    if (nameEl) {
      nameEl.textContent = window.CURRENT_USERNAME || 'this Commvault session';
    }
  } else {
    if (signin) signin.hidden = false;
    if (signout) signout.hidden = true;
    if (title) title.textContent = 'Connect to Commvault';
    const uInput = document.getElementById('connect-username');
    if (uInput) uInput.focus();
  }

  modal.hidden = false;
}

function closeConnectModal() {
  const modal = document.getElementById('connect-modal');
  if (modal) modal.hidden = true;
}

async function submitConnect() {
  const username = (document.getElementById('connect-username') || {}).value || '';
  const password = (document.getElementById('connect-password') || {}).value || '';
  const errEl = document.getElementById('connect-error');
  const btn = document.getElementById('connect-submit');

  if (errEl) errEl.hidden = true;
  if (btn) { btn.disabled = true; btn.textContent = 'Connecting…'; }

  try {
    const resp = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (data.success) {
      window.IS_AUTHENTICATED = true;
      window.CURRENT_USERNAME = username.trim() || null;
      closeConnectModal();
      _updateConnBadge();
    } else {
      if (errEl) { errEl.textContent = data.error || 'Login failed.'; errEl.hidden = false; }
    }
  } catch (err) {
    if (errEl) { errEl.textContent = 'Connection error: ' + err.message; errEl.hidden = false; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Connect'; }
  }
}

async function submitSignOut() {
  const errEl = document.getElementById('signout-error');
  const btn = document.getElementById('signout-submit');

  if (errEl) errEl.hidden = true;
  if (btn) { btn.disabled = true; btn.textContent = 'Signing out…'; }

  try {
    const resp = await fetch('/logout', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
      redirect: 'manual',
    });
    // /logout returns a 302 redirect to /login. Browser's `redirect: manual`
    // surfaces that as resp.type === 'opaqueredirect' with status 0; either
    // that or any 2xx/3xx means the session was cleared.
    const ok = resp.ok || resp.status === 0 || (resp.status >= 200 && resp.status < 400);
    if (ok) {
      window.IS_AUTHENTICATED = false;
      window.CURRENT_USERNAME = null;
      closeConnectModal();
      _updateConnBadge();
    } else {
      if (errEl) { errEl.textContent = 'Sign out failed (' + resp.status + ').'; errEl.hidden = false; }
    }
  } catch (err) {
    if (errEl) { errEl.textContent = 'Connection error: ' + err.message; errEl.hidden = false; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Sign out'; }
  }
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
_startConnBadgePolling();
// Restore the subject the user was on before a full-page reload (e.g.
// after a Collect POST) via the URL fragment, falling back to the
// CommCell Details default.
const _hashSubjectId = _readSubjectFromHash();
const _hashSubj = _hashSubjectId ? allSubjs().find(s => s.id === _hashSubjectId) : null;
const _firstSubj = _hashSubj || allSubjs().find(s => s.id === 'environment') || allSubjs()[0];
if (_firstSubj) openConfig(_firstSubj.id);
else showOverview();
