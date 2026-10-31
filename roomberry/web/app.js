// @(#)app.js 3.1.web.1 2026/10/31 14:00:00
'use strict';
const $ = id => document.getElementById(id);
const node = (tag, text = '', cls = '') => { const n = document.createElement(tag); n.textContent = text; if (cls) n.className = cls; return n; };
const fmt = (v, digits = 1) => typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';
const deg = v => typeof v === 'number' ? v * 180 / Math.PI : null;
const bit = (r, b) => r && (r.flags & b) !== 0;
const age = r => r && typeof r.receive_age_s === 'number' ? `${fmt(r.receive_age_s)} s since receipt` : 'No packets received';
function metric(label, value, sub) { const n = node('div', '', 'metric'); n.append(node('span', label, 'metric-label'), node('span', value, 'metric-value')); if (sub) n.append(node('span', sub, 'metric-sub')); return n; }
function badge(id, text, bad = false, muted = false) { const n = $(id); n.textContent = text; n.className = `badge${bad ? ' bad' : ''}${muted ? ' muted' : ''}`; }
async function getJSON(url) { const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 8000); try { const r = await fetch(url, {cache: 'no-store', signal: controller.signal}); if (!r.ok) throw Error(`HTTP ${r.status}`); return await r.json(); } finally { clearTimeout(timer); } }
async function robot() {
  try {
    const s = await getJSON('/status.json');
    $('connection').textContent = 'ROBOT ONLINE'; $('connection').className = 'connection';
    $('robot-summary').replaceChildren(metric('Mission', s.mission_mode || 'unavailable'), metric('Sensors', s.ready ? 'Ready' : 'Not ready', `Poll age ${fmt(s.age, 2)} s`), metric('Roomba battery', s.battery_status || '—'), metric('Safety', s.oi_stopped ? 'OI stopped' : (s.hard_hazard_reasons || []).join(', ') || 'Clear'));
    const c = s.calibration; const box = $('calibration'); box.replaceChildren();
    if (c) {
      box.append(node('strong', `Calibration: ${c.stage}${c.waiting_for_sensors ? ' · waiting for sensor poll' : ''}`));
      if (c.result) box.append(node('p', `${c.result.status}: ${c.result.reason || 'Finished'}`));
      box.append(node('p', `${c.checkpoints} checkpoint(s) recorded`));
      if (c.latest_checkpoint) { const details = node('details'); details.append(node('summary', `Latest checkpoint: ${c.latest_checkpoint.checkpoint}`), node('pre', JSON.stringify(c.latest_checkpoint, null, 2))); box.append(details); }
    }
  } catch (e) { $('connection').textContent = `ROBOT OFFLINE · ${e.message}`; $('connection').className = 'connection bad'; }
}
async function phone() {
  try {
    const s = await getJSON('/groundhog.json'); const m = s.motion, h = s.health, c = s.compass;
    $('phone-status').textContent = s.enabled ? `${s.received} NavLink packets recorded · ${s.rejected} rejected. Motion: ${age(m)}.` : 'NavLink is disabled in Roomberry configuration.';
    const reasons = ['none', 'initializing', 'excessive motion', 'tilt / IMU / timestamp', 'stale frame', 'interrupted', 'Vision error', 'insufficient texture / agreement'];
    badge('motion-state', m ? !m.fresh ? 'STALE' : m.usable ? 'TRACKING' : 'NO LOCK' : 'NO DATA', !!m && !m.usable, !m);
    const usable = m && m.usable;
    $('motion').replaceChildren(metric('Segment X', usable ? `${fmt(m.segment_x_mm)} mm` : '—'), metric('Segment Y', usable ? `${fmt(m.segment_y_mm)} mm` : '—'), metric('Segment yaw', usable ? `${fmt(deg(m.segment_yaw_rad))}°` : '—'), metric('Continuity segment', m ? String(m.continuity) : '—', m ? reasons[m.reason] || 'unknown state' : ''), metric('Flow processing', m ? `${fmt(m.processing_us / 1000)} ms` : '—'), metric('Fit residual', usable ? `${fmt(m.residual_mm, 3)} mm` : '—'), metric('Forward / left speed', usable ? `${fmt(m.forward_mm_s)} / ${fmt(m.left_mm_s)} mm/s` : '—'), metric('Accepted / rejected frames', m ? `${m.accepted_frames} / ${m.rejected_frames}` : '—'));
    badge('health-state', h ? h.fresh ? 'LIVE' : 'STALE' : 'NO DATA', !!h && !h.fresh, !h);
    const live = h && h.fresh; const states = ['unknown', 'unplugged', 'charging', 'full']; const thermal = ['nominal', 'fair', 'serious', 'critical'];
    $('health').replaceChildren(metric('Phone battery', live && bit(h, 32) ? `${h.battery_pct}%` : '—', live ? states[h.battery_state] : age(h)), metric('Impact episodes', live ? String(h.bump_count) : '—', live ? `Last peak ${fmt(h.last_bump_peak_mm_s2 / 9806.65, 2)} g` : ''), metric('App CPU', live && bit(h, 4) ? `${fmt(h.app_cpu_pct)}%` : '—', '100% = one CPU core'), metric('App memory', live && bit(h, 8) ? `${fmt(h.app_footprint_bytes / 1048576)} MiB` : '—'), metric('Thermal state', live ? thermal[h.thermal_state] || 'unknown' : '—'), metric('Delivered image', live && bit(h, 64) ? `${h.image_width} × ${h.image_height}` : '—'));
    const imu = live && bit(h, 1); const vector = (r, keys, digits = 2) => keys.map(k => fmt(r[k], digits)).join(' / ');
    $('imu').replaceChildren(metric('Acceleration X / Y / Z', imu ? vector(h, ['device_ax_mm_s2', 'device_ay_mm_s2', 'device_az_mm_s2'], 0) : '—', 'mm/s² · native phone axes'), metric('Gyro X / Y / Z', imu ? vector(h, ['device_wx_rad_s', 'device_wy_rad_s', 'device_wz_rad_s'], 3) : '—', 'rad/s · native phone axes'), metric('Gravity X / Y / Z', imu ? vector(h, ['gravity_x_g', 'gravity_y_g', 'gravity_z_g']) : '—', 'g · native phone axes'), metric('Robot magnetic bearing', c && c.usable ? `${fmt(deg(c.robot_magnetic_bearing_rad))}°` : '—', c ? `${['unsupported', 'acquiring', 'usable', 'unreliable', 'stale', 'error'][c.compass_state] || 'unknown'} · ${age(c)}` : 'No compass data'), metric('Heading accuracy', c && c.usable ? `±${fmt(deg(c.heading_accuracy_rad))}°` : '—'), metric('Magnetic field X / Y / Z', c && c.fresh && bit(c, 2) ? vector(c, ['magnetic_x_ut', 'magnetic_y_ut', 'magnetic_z_ut']) : '—', 'µT · native phone axes'));
    $('raw-phone').textContent = JSON.stringify(s, null, 2);
  } catch (e) {
    $('phone-status').textContent = `GroundHog feed unavailable: ${e.message}. Last displayed data may be old.`;
    badge('motion-state', 'OFFLINE', true); badge('health-state', 'OFFLINE', true);
    $('raw-phone').textContent = 'Feed unavailable; no current snapshot.';
    for (const id of ['motion', 'health', 'imu']) $(id).replaceChildren(node('p', 'Telemetry unavailable.', 'note'));
  }
}
function safeArchiveURL(value) { if (typeof value !== 'string') return null; return /^\/cam\/scans\/[0-9]{8}\/[0-9]{8}-[0-9]{6}-[0-9]{6}\.(jpg|json)$/.test(value) ? value : null; }
async function scans() {
  try {
    const only = $('tags-only').checked;
    const s = await getJSON(`/cam/${only ? 'tags' : 'scans'}.json?limit=8`);
    $('scan-status').textContent = `${s.scans.length} recent ${only ? 'tag ' : ''}scan(s) · refreshes every 15 seconds`;
    const list = $('scan-list'); list.replaceChildren();
    if (!s.scans.length) list.append(node('div', 'No archived scans available yet.', 'empty'));
    for (const scan of s.scans) {
      const card = node('article', '', 'scan'); const imageURL = safeArchiveURL(scan.image_url); const reportURL = safeArchiveURL(scan.report_url);
      if (imageURL) { const a = node('a'); a.href = imageURL; a.target = '_blank'; a.rel = 'noopener'; const img = document.createElement('img'); img.src = imageURL; img.loading = 'lazy'; img.alt = 'Archived camera scan'; a.append(img); card.append(a); }
      const body = node('div', '', 'scan-body'); body.append(node('h3', scan.captured_at ? new Date(scan.captured_at * 1000).toLocaleString() : 'Unknown capture time'));
      const tags = node('div', '', 'tag-list'); for (const tag of scan.tags || []) tags.append(node('span', `Tag ${tag.id}`, 'badge')); if (!tags.childElementCount) tags.append(node('span', 'No tags', 'badge muted')); body.append(tags);
      for (const tag of scan.tags || []) body.append(node('p', `Tag ${tag.id}: ${fmt(tag.distance_mm, 0)} mm · margin ${fmt(tag.decision_margin)} · hamming ${tag.hamming ?? '—'}`));
      body.append(node('p', scan.detector_error ? `Detector error: ${scan.detector_error}` : scan.detection_skipped ? 'Detection skipped during motion' : `Detection ${fmt(scan.timings_ms && scan.timings_ms.detect, 0)} ms · ${scan.paused ? 'stationary scan' : 'unpaused scan'}`));
      const links = node('div', '', 'scan-links'); for (const [url, label] of [[imageURL, 'Full image ↗'], [reportURL, 'Scan report ↗']]) if (url) { const a = node('a', label); a.href = url; a.target = '_blank'; a.rel = 'noopener'; links.append(a); } body.append(links); card.append(body); list.append(card);
    }
  } catch (e) { $('scan-status').textContent = `Scans unavailable: ${e.message}`; }
}
let commands = [];
function renderCommands() {
  const query = $('command-search').value.toLowerCase(); const list = $('command-list'); list.replaceChildren();
  for (const c of commands.filter(c => JSON.stringify(c).toLowerCase().includes(query))) {
    const row = node('div', '', 'command'); const name = node('div', c.name, 'command-name'); name.append(node('small', c.group)); const detail = node('div'); detail.append(node('p', c.description));
    if (!c.mutates) { const a = node('a', c.url); a.href = c.url; detail.append(a); } else detail.append(node('code', c.url));
    if (c.aliases.length) detail.append(node('p', `Aliases: ${c.aliases.join(', ')}`, 'note'));
    if (c.parameters.length) detail.append(node('p', c.parameters.map(p => `${p.name}${p.required ? ' (required)' : ` = ${p.default}`}`).join(' · '), 'note'));
    row.append(name, detail); list.append(row);
  }
  if (!list.childElementCount) list.append(node('div', 'No matching commands.', 'empty'));
}
async function loadCommands() {
  try { const s = await getJSON('/commands.json'); commands = s.commands; renderCommands(); const a = s.calibration_acceptance; $('acceptance').textContent = `Calibration acceptance: heading/drift ±${fmt(deg(a.heading_rad))}° · lateral ±${a.lateral_mm} mm · return error ${a.return_error_mm} mm · starting gap ${a.start_gap_mm.join('–')} mm.`; }
  catch (e) { $('command-list').textContent = `Command index unavailable: ${e.message}`; }
}
for (const button of document.querySelectorAll('[data-command]')) button.addEventListener('click', async () => {
  button.disabled = true; $('action-status').textContent = 'Sending command…';
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 8000);
  try { const r = await fetch(button.dataset.command, {cache: 'no-store', signal: controller.signal}); if (!r.ok) throw Error(`HTTP ${r.status}: ${(await r.text()).replace(/<[^>]*>/g, ' ').slice(0, 240)}`); $('action-status').textContent = `${button.textContent}: accepted.`; await robot(); }
  catch (e) { $('action-status').textContent = `Command failed: ${e.message}`; }
  finally { clearTimeout(timer); button.disabled = false; }
});
$('command-search').addEventListener('input', renderCommands); $('refresh-scans').addEventListener('click', scans); $('tags-only').addEventListener('change', scans);
async function loop(fn, interval) { await fn(); setTimeout(() => loop(fn, interval), interval); }
loop(robot, 2000); loop(phone, 2000); loop(scans, 15000); loadCommands();
