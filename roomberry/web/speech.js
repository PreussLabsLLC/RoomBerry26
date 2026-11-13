// @(#)speech.js 3.2 2026/11/09 21:00:00
'use strict';
(() => {
  const form = document.getElementById('speech-form');
  const result = document.getElementById('speech-result');
  const button = document.getElementById('speech-test');
  let pending = false;
  async function status(id) {
    const response = await fetch(`/speech.json${id ? `?id=${encodeURIComponent(id)}` : ''}`, {cache: 'no-store', signal: AbortSignal.timeout(5000)});
    if (!response.ok) throw Error(`Speech status HTTP ${response.status}`);
    const state = await response.json();
    const imu = state.imu_received ? `IMU sample received${state.imu_age_s == null ? '' : ` ${state.imu_age_s.toFixed(1)} s ago`}.` : 'No IMU sample in the latest phone health snapshot.';
    document.getElementById('speech-connection').textContent = `${state.detail} ${state.received} telemetry packets recorded, ${state.rejected} rejected. ${imu}`;
    return state;
  }
  async function refresh() {
    try { await status(); }
    catch (error) { document.getElementById('speech-connection').textContent = `Speech status unavailable: ${error.message}`; }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    const text = document.getElementById('speech-text').value;
    if (!text.trim() || [...text].length > 500) { result.textContent = 'Enter 1–500 characters.'; return; }
    pending = true; button.disabled = true;
    result.textContent = 'Submitting speech test…';
    let submitted = false;
    try {
      const response = await fetch('/speech', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text}), signal: AbortSignal.timeout(5000)});
      const job = await response.json();
      if (!response.ok) throw Error(job.detail || `HTTP ${response.status}`);
      submitted = true;
      result.textContent = `${job.status}: ${job.detail} · ID ${job.id}`;
      const deadline = Date.now() + 50000;
      while (Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 1000));
        const state = await status(job.id);
        if (!state.job) throw Error('Speech result is no longer available; outcome unknown.');
        result.textContent = `${state.job.status}: ${state.job.detail} · ID ${job.id}`;
        if (['completed', 'failed', 'unavailable', 'dropped', 'unknown'].includes(state.job.status)) return;
      }
      result.textContent = `Outcome unknown: no final result for ${job.id}. Check the phone and logs before sending again.`;
    } catch (error) {
      result.textContent = `${submitted ? 'Speech outcome unknown' : 'Speech test not confirmed'}: ${error.message}`;
    } finally { pending = false; button.disabled = false; }
  });
  document.getElementById('speech-refresh').addEventListener('click', refresh);
  document.getElementById('refresh-all').addEventListener('click', refresh);
  refresh();
})();
