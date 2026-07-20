const form = document.querySelector('#analysis-form');
const button = document.querySelector('#submit-button');
const emptyState = document.querySelector('#empty-state');
const loadingState = document.querySelector('#loading-state');
const errorState = document.querySelector('#error-state');
const results = document.querySelector('#results');

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

const chips = (items) => `<div class="chips">${items.map(item => `<span class="chip">${escapeHtml(item)}</span>`).join('')}</div>`;
const list = (items, ordered = false) => `<${ordered ? 'ol' : 'ul'} class="clean">${items.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</${ordered ? 'ol' : 'ul'}>`;

function render(data) {
  const account = data.account;
  const hypotheses = data.ai_enrichment?.refined_opportunity_hypotheses || data.opportunity_hypotheses;
  const questions = data.ai_enrichment?.priority_discovery_questions || data.discovery_questions;
  const summary = data.ai_enrichment?.executive_summary || data.commercial_thesis;

  results.innerHTML = `
    <div class="result-header">
      <p class="eyebrow">${escapeHtml(data.solution_motion)}</p>
      <h3>${escapeHtml(account.name)} <small>${escapeHtml(account.ticker)}</small></h3>
      <p>${escapeHtml(account.role)} · ${escapeHtml(account.customer_segment)} · ${escapeHtml(account.region)}</p>
    </div>
    <section class="result-section"><h4>Commercial thesis</h4><p>${escapeHtml(summary)}</p></section>
    <section class="result-section"><h4>Account signals</h4>${chips(data.account_snapshot.commercial_signals)}</section>
    <section class="result-section"><h4>Priority workloads</h4>${chips(data.account_snapshot.priority_workloads)}</section>
    <section class="result-section"><h4>Opportunity hypotheses</h4><div class="card-grid">${hypotheses.map(h => `
      <article class="mini-card"><strong>${escapeHtml(h.business_pressure)}</strong><p>${escapeHtml(h.technical_hypothesis)}</p><span>${escapeHtml(h.solution_angle)}<br><b>Measure:</b> ${escapeHtml(h.success_metric)}</span></article>`).join('')}</div></section>
    <section class="result-section"><h4>Stakeholder map</h4><div class="card-grid">${data.stakeholder_map.map(s => `<article class="mini-card"><strong>${escapeHtml(s.role)} — ${escapeHtml(s.persona)}</strong><p>${escapeHtml(s.priority)}</p></article>`).join('')}</div></section>
    <section class="result-section"><h4>Discovery questions</h4>${list(questions, true)}</section>
    <section class="result-section"><h4>PoC acceptance criteria</h4>${list(data.poc_plan.acceptance_criteria)}<p class="provenance">Expected duration: ${escapeHtml(data.poc_plan.duration)} · Evidence: ${escapeHtml(data.poc_plan.evidence.join(', '))}</p></section>
    <section class="result-section"><h4>Objection map</h4><div class="card-grid">${data.objection_map.map(o => `<article class="mini-card"><strong>${escapeHtml(o.objection)}</strong><p>${escapeHtml(o.response)}</p></article>`).join('')}</div></section>
    <section class="result-section"><h4>Next actions</h4>${list(data.next_actions, true)}</section>
    <section class="result-section provenance"><h4>Provenance</h4><p>${escapeHtml(data.provenance.mode)} · ${escapeHtml(data.provenance.source)}</p><p>${escapeHtml(data.provenance.limitations)}</p></section>`;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  emptyState.classList.add('hidden');
  results.classList.add('hidden');
  errorState.classList.add('hidden');
  loadingState.classList.remove('hidden');

  const payload = {
    ticker: document.querySelector('#ticker').value,
    solution_motion: document.querySelector('#solution_motion').value,
    customer_segment: document.querySelector('#customer_segment').value,
    region: document.querySelector('#region').value,
    context: document.querySelector('#context').value,
    use_ai: document.querySelector('#use_ai').checked,
  };

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Analysis failed.');
    render(body);
    results.classList.remove('hidden');
  } catch (error) {
    errorState.textContent = error.message;
    errorState.classList.remove('hidden');
  } finally {
    loadingState.classList.add('hidden');
    button.disabled = false;
  }
});
