// @(#)maps.js 3.2.maps.4 2026/11/10 11:24:31
'use strict';
(() => {
  const el = id => document.getElementById(id);
  const text = (tag, value) => { const n = document.createElement(tag); n.textContent = value; return n; };
  let state = null, robotIdle = false, pending = false;
  const choice = () => state?.maps?.find(m => m.id === el('maps-choice').value);
  const size = bytes => `${((bytes || 0) / 1048576).toFixed(2)} MiB`;
  async function read(url) {
    const response = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(12000)});
    const body = await response.json();
    if (!response.ok) throw Error(body.detail || `HTTP ${response.status}`);
    return body;
  }
  function controls() {
    const busy = pending || state?.busy;
    const ready = state?.enabled && state?.connected && robotIdle && !busy;
    const m = choice(), p = state?.phone;
    for (const id of ['maps-fresh', 'maps-stop', 'maps-auto']) el(id).disabled = !ready;
    for (const id of ['maps-select', 'maps-resume', 'maps-rename']) el(id).disabled = !ready || !m;
    const effective = state?.selection?.map_id || state?.selection?.seed_map_id;
    el('maps-delete').disabled = !ready || !m || m.id === effective || (p?.running && p.map_id === m.id);
    el('maps-save').disabled = !ready || !p?.running || !p?.can_amend;
    el('maps-keep').disabled = !ready || !p?.running || p?.mode !== 'survey';
    el('maps-choice').disabled = !!busy;
    el('maps-refresh').disabled = !!busy;
  }
  function render(s) {
    state = s;
    if (!s.enabled) { el('maps-connection').textContent = s.detail; controls(); return; }
    const p = s.phone || {}, selected = s.selection?.map_id;
    const label = id => s.maps.find(m => m.id === id)?.name || id || 'none';
    el('maps-connection').textContent = `${s.connected ? 'Phone status received' : 'Phone status unavailable — refresh to retry'}${s.age_s != null ? ` · snapshot ${s.age_s.toFixed(0)} seconds old` : ''}${robotIdle ? '' : ' · Stop / idle Rosie to manage maps.'}`;
    el('maps-selection').textContent = s.selection?.error || (selected ? `Next run: ${label(selected)} (${selected}). Exact selection${s.selection.persistent ? ' saved on Pi' : ''}.` : `Next run: automatic kitchen selection. Configured seed: ${label(s.selection?.seed_map_id)}.`);
    const summary = el('maps-summary'); summary.replaceChildren();
    const tracking = {'2:0': 'Normal', '1:1': 'Initializing', '1:2': 'Excessive motion', '1:3': 'Insufficient features', '1:4': 'Relocalizing', '3:5': 'Interrupted'}[p.tracking] || p.tracking || '—';
    const lock = {notNeeded: 'fresh survey', relocalizing: 'waiting for map lock', localized: 'map candidate found', lost: 'map lock lost'}[p.relocalization] || p.relocalization || '—';
    for (const [name, value] of [['Phone session', p.running ? `${p.mode} · ${p.session}` : 'Stopped'], ['Active phone map', !p.running ? 'None (stopped)' : label(p.map_id) === 'none' ? 'Fresh survey' : label(p.map_id)], ['Tracking / map lock', p.running ? `${tracking} / ${lock}` : 'Stopped'], ['World mapping', p.running ? p.mapping || '—' : '—']]) {
      const n = text('div', ''); n.className = 'metric';
      const a = text('span', name), b = text('span', value); a.className = 'metric-label'; b.className = 'metric-value'; n.append(a, b); summary.append(n);
    }
    let saveHint;
    if (!s.connected) saveHint = 'Save unavailable: refresh the phone connection.';
    else if (!robotIdle) saveHint = 'Stop / idle Rosie, then refresh before saving. The survey kept for steering will continue.';
    else if (!p.running) saveHint = 'Save unavailable: start a fresh survey or resume a saved map.';
    else if (p.mode !== 'survey') saveHint = 'Save unavailable: the phone must be in Surveyor mode.';
    else if (p.error) saveHint = `Save unavailable: ${p.error}`;
    else if (!['mapped', 'extending'].includes(p.mapping)) saveHint = `Save unavailable: world mapping is ${p.mapping || 'unknown'}. Normal tracking alone is not enough. Keep this survey for steering, use the steering pad to collect more viewpoints, Stop / idle, then refresh.`;
    else if (!p.can_amend) saveHint = `Save unavailable: tracking must be fresh and normal${p.map_id ? ', with a saved-map lock' : ''}. Refresh to check again.`;
    else saveHint = 'Ready to save. Saving creates a new file; use it for the next run with the selection button.';
    el('maps-save-hint').textContent = saveHint;
    el('maps-steering-hint').textContent = s.operator_survey ? 'Survey kept: steering, Return to tag 15 and Stop / idle preserve the phone session. Save or stop the phone session before starting WALL.' : 'Steering-pad moves and Return to tag 15 preserve the current phone session. Keep the survey to also prevent a mapping mission from replacing it before you save.';
    const previous = el('maps-choice').value;
    el('maps-choice').replaceChildren(...s.maps.map(m => { const o = text('option', `${m.name} · r${m.revision} · ${m.id.slice(0, 8)}`); o.value = m.id; return o; }));
    if (!s.maps.length) el('maps-choice').append(text('option', 'No saved maps'));
    el('maps-choice').value = s.maps.some(m => m.id === previous) ? previous : s.maps.some(m => m.id === selected) ? selected : s.maps[0]?.id || '';
    if (el('maps-rename-name').dataset.mapId !== el('maps-choice').value) {
      el('maps-rename-name').value = choice()?.name || '';
      el('maps-rename-name').dataset.mapId = el('maps-choice').value;
    }
    el('maps-rows').replaceChildren(...s.maps.map(m => {
      const row = document.createElement('tr'); row.dataset.chosen = String(m.id === selected);
      const name = text('td', m.name + (m.id === selected ? ' · next run' : '') + (p.running && p.map_id === m.id ? ' · active' : ''));
      name.append(text('small', m.id));
      row.append(name, text('td', new Date(m.created * 1000).toLocaleString()), text('td', `r${m.revision} · ${m.mapping} · ${m.features < 0 ? 'unknown' : m.features} features`), text('td', size(m.bytes))); return row;
    }));
    el('maps-storage').textContent = `${s.maps.length} saved maps · ${size(s.storage_bytes)}.${s.inventory_errors ? ` ${s.inventory_errors} unreadable map packages; preserved on phone.` : ''}`;
    if (s.job) el('maps-job').textContent = `${s.job.action}: ${s.job.status} · ${s.job.detail}`;
    controls();
  }
  async function snapshot() {
    const [s, robot] = await Promise.all([read('/roomtrek/maps.json'), read('/status.json')]);
    robotIdle = robot.mission_mode === 'idle'; render(s); return s;
  }
  async function act(action, args = {}) {
    if (pending || state?.busy) return;
    pending = true; controls();
    el('maps-job').textContent = `${action}: contacting phone…`;
    try {
      const response = await fetch('/roomtrek/maps', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action, ...args}), signal: AbortSignal.timeout(12000)});
      const job = await response.json();
      if (!response.ok) throw Error(job.detail || `HTTP ${response.status}`);
      const deadline = Date.now() + 180000;
      while (Date.now() < deadline) {
        const s = await snapshot();
        if (s.job?.id === job.id && ['completed', 'failed'].includes(s.job.status)) return;
        await new Promise(resolve => setTimeout(resolve, 750));
      }
      throw Error('Still waiting. Refresh status before submitting another operation.');
    } catch (error) { el('maps-job').textContent = `${action}: ${error.message}`; }
    finally { pending = false; controls(); }
  }
  el('maps-refresh').onclick = () => act('refresh');
  el('maps-stop').onclick = () => act('stop');
  el('maps-keep').onclick = () => act('keep');
  el('maps-fresh').onclick = () => {
    if (!state?.phone?.running || window.confirm('Stop the current phone session and start fresh? Unsaved survey changes will be discarded. Saved files are preserved.')) act('fresh');
  };
  el('maps-select').onclick = () => act('select', {map_id: choice()?.id});
  el('maps-auto').onclick = () => act('select', {map_id: null});
  el('maps-resume').onclick = () => {
    if (!state?.phone?.running || window.confirm('Stop the current phone session and resume this saved map? Unsaved changes will be discarded.')) act('resume', {map_id: choice()?.id});
  };
  el('maps-choice').onchange = () => { el('maps-rename-name').value = choice()?.name || ''; el('maps-rename-name').dataset.mapId = el('maps-choice').value; controls(); };
  el('maps-save-form').onsubmit = event => { event.preventDefault(); act('save', {name: el('maps-save-name').value}); };
  el('maps-rename-form').onsubmit = event => { event.preventDefault(); act('rename', {map_id: choice()?.id, name: el('maps-rename-name').value}); };
  el('maps-delete').onclick = () => { const m = choice(); if (m && window.confirm(`Permanently delete “${m.name}” (${m.id}) from the iPhone?`)) act('delete', {map_id: m.id, confirm: true}); };
  el('refresh-all').addEventListener('click', () => act('refresh'));
  snapshot().then(s => { if (s.enabled && !s.busy) return act('refresh'); }).catch(error => { el('maps-connection').textContent = error.message; controls(); });
})();
