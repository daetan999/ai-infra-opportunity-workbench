const body = document.body;
const currentAccountId = body.dataset.accountId;
const sidebar = document.querySelector('#sidebar');
const sidebarToggle = document.querySelector('[data-sidebar-toggle]');
const sidebarScrim = document.querySelector('[data-sidebar-scrim]');

function setSidebarOpen(isOpen) {
  if (!sidebar || !sidebarToggle || !sidebarScrim) return;

  body.classList.toggle('sidebar-open', isOpen);
  sidebarToggle.setAttribute('aria-expanded', String(isOpen));
  sidebarScrim.hidden = !isOpen;

  if (isOpen) {
    sidebar.querySelector('a')?.focus();
  } else {
    sidebarToggle.focus();
  }
}

sidebarToggle?.addEventListener('click', () => {
  setSidebarOpen(!body.classList.contains('sidebar-open'));
});

sidebarScrim?.addEventListener('click', () => setSidebarOpen(false));

sidebar?.addEventListener('click', (event) => {
  if (event.target.closest('a') && window.matchMedia('(max-width: 900px)').matches) {
    setSidebarOpen(false);
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && body.classList.contains('sidebar-open')) {
    setSidebarOpen(false);
  }
});

const search = document.querySelector('[data-account-search]');
const accountRows = [...document.querySelectorAll('[data-account-row]')];
const filterEmpty = document.querySelector('[data-filter-empty]');

search?.addEventListener('input', () => {
  const query = search.value.trim().toLocaleLowerCase();
  let visibleCount = 0;

  accountRows.forEach((row) => {
    const matches = row.dataset.searchValue.toLocaleLowerCase().includes(query);
    row.hidden = !matches;
    visibleCount += Number(matches);
  });

  filterEmpty?.classList.toggle('hidden', visibleCount !== 0 || accountRows.length === 0);
});

document.querySelectorAll('[data-print]').forEach((button) => {
  button.addEventListener('click', () => window.print());
});

const workflowDialog = document.querySelector('[data-workflow-dialog]');
const workflowTitle = document.querySelector('[data-workflow-title]');
const workflowDescription = document.querySelector('[data-workflow-description]');
const workflowForms = [...document.querySelectorAll('[data-workflow-form]')];
let workflowBusy = false;

function refreshWorkspace(anchor) {
  const path = `/accounts/${currentAccountId}`;
  if (window.location.pathname === path) {
    window.location.hash = anchor;
    window.location.reload();
    return;
  }
  window.location.assign(`${path}${anchor}`);
}

const workflowConfig = {
  account: {
    title: 'Create account',
    description: 'Add a governed portfolio record before capturing opportunity evidence.',
    endpoint: () => '/api/accounts',
    method: 'POST',
    loading: 'Creating account…',
    success: 'Account created. Opening its workspace…',
    complete: (result) => window.location.assign(`/accounts/${result.id}`),
  },
  signal: {
    title: 'Add evidence signal',
    description: 'Capture a dated signal with an explicit evidence label and attributable source.',
    endpoint: () => `/api/accounts/${currentAccountId}/signals`,
    method: 'POST',
    loading: 'Adding signal…',
    success: 'Signal added. Refreshing the evidence ledger…',
    complete: () => refreshWorkspace('#evidence'),
  },
  workload: {
    title: 'Define workload',
    description: 'State the workload hypothesis, constraint, business metric, and validation target.',
    endpoint: () => `/api/accounts/${currentAccountId}/workload`,
    method: 'PUT',
    loading: 'Saving workload…',
    success: 'Workload saved. Refreshing qualification context…',
    complete: () => refreshWorkspace('#workspace'),
  },
  stakeholder: {
    title: 'Add stakeholder',
    description: 'Map the buying group role, engagement level, and confidence before advancing.',
    endpoint: () => `/api/accounts/${currentAccountId}/stakeholders`,
    method: 'POST',
    loading: 'Adding stakeholder…',
    success: 'Stakeholder added. Refreshing buying group…',
    complete: () => refreshWorkspace('#workspace'),
  },
  discovery: {
    title: 'Add discovery evidence',
    description: 'Capture a specific question, answer, source, date, and provenance label.',
    endpoint: () => `/api/accounts/${currentAccountId}/discovery`,
    method: 'POST',
    loading: 'Adding discovery…',
    success: 'Discovery evidence added. Refreshing decision surfaces…',
    complete: () => refreshWorkspace('#evidence'),
  },
};

function setFormStatus(form, state = '', message = '') {
  const status = form.querySelector('[data-form-status]');
  if (!status) return;
  status.dataset.state = state;
  status.textContent = message;
}

function setFormBusy(form, isBusy) {
  workflowBusy = isBusy;
  form.setAttribute('aria-busy', String(isBusy));
  form.querySelectorAll('button, input, select, textarea').forEach((control) => {
    control.disabled = isBusy;
  });
  document.querySelectorAll('[data-dialog-close]').forEach((button) => {
    button.disabled = isBusy;
  });
}

function closeWorkflowDialog() {
  if (!workflowDialog || workflowBusy) return;
  if (typeof workflowDialog.close === 'function') workflowDialog.close();
  else workflowDialog.removeAttribute('open');
}

function openWorkflowDialog(workflowName) {
  if (!workflowDialog || !workflowConfig[workflowName]) return;
  const form = workflowForms.find((candidate) => candidate.dataset.workflowForm === workflowName);
  if (!form) return;

  workflowForms.forEach((candidate) => { candidate.hidden = candidate !== form; });
  form.reset();
  setFormStatus(form);
  const dateInput = form.querySelector('input[type="date"]');
  if (dateInput && !dateInput.value) {
    const localNow = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
    dateInput.value = localNow.toISOString().slice(0, 10);
  }
  workflowTitle.textContent = workflowConfig[workflowName].title;
  workflowDescription.textContent = workflowConfig[workflowName].description;

  if (typeof workflowDialog.showModal === 'function') workflowDialog.showModal();
  else workflowDialog.setAttribute('open', '');
  form.querySelector('input, select, textarea')?.focus();
}

function payloadFromForm(form) {
  const payload = {};
  new FormData(form).forEach((value, key) => { payload[key] = value; });
  form.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    payload[input.name] = input.checked;
  });
  form.querySelectorAll('[data-number]').forEach((input) => {
    payload[input.name] = Number(input.value);
  });
  return payload;
}

function responseError(body) {
  if (!body) return 'The request could not be completed.';
  if (Array.isArray(body.detail)) return body.detail.map((item) => item.msg).join(' ');
  return body.detail || 'The request could not be completed.';
}

document.querySelectorAll('[data-open-workflow]').forEach((button) => {
  button.addEventListener('click', () => openWorkflowDialog(button.dataset.openWorkflow));
});

document.querySelectorAll('[data-dialog-close]').forEach((button) => {
  button.addEventListener('click', closeWorkflowDialog);
});

workflowDialog?.addEventListener('cancel', (event) => {
  if (workflowBusy) event.preventDefault();
});

workflowForms.forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const config = workflowConfig[form.dataset.workflowForm];
    if (!config || workflowBusy) return;

    const payload = payloadFromForm(form);
    setFormBusy(form, true);
    setFormStatus(form, 'loading', config.loading);
    let succeeded = false;

    try {
      const response = await fetch(config.endpoint(), {
        method: config.method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(responseError(result));

      succeeded = true;
      setFormStatus(form, 'success', config.success);
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      config.complete(result);
    } catch (error) {
      setFormStatus(form, 'error', error.message || 'The request could not be completed.');
    } finally {
      if (!succeeded) setFormBusy(form, false);
    }
  });
});

function setActionStatus(element, state = '', message = '') {
  if (!element) return;
  element.dataset.state = state;
  element.textContent = message;
}

const qualificationButton = document.querySelector('[data-run-qualification]');
const qualificationStatus = document.querySelector('[data-qualification-status]');

qualificationButton?.addEventListener('click', async () => {
  qualificationButton.disabled = true;
  setActionStatus(qualificationStatus, 'loading', 'Running evidence-based qualification…');
  let succeeded = false;

  try {
    const response = await fetch(`/api/accounts/${currentAccountId}/qualification`);
    const result = await response.json().catch(() => null);
    if (!response.ok) throw new Error(responseError(result));

    succeeded = true;
    setActionStatus(
      qualificationStatus,
      'success',
      `Qualification complete. ${result.total}/100 · ${result.recommendation}. Refreshing…`,
    );
    await new Promise((resolve) => window.setTimeout(resolve, 250));
    refreshWorkspace('#decision');
  } catch (error) {
    setActionStatus(qualificationStatus, 'error', error.message || 'Qualification failed.');
  } finally {
    if (!succeeded) qualificationButton.disabled = false;
  }
});

const exportButtons = [...document.querySelectorAll('[data-export-format]')];
const exportStatus = document.querySelector('[data-export-status]');
let exportBusy = false;

exportButtons.forEach((button) => {
  button.addEventListener('click', async (event) => {
    if (!currentAccountId) return;
    event.preventDefault();
    if (exportBusy) return;
    exportBusy = true;
    exportButtons.forEach((candidate) => candidate.setAttribute('aria-disabled', 'true'));
    const format = button.dataset.exportFormat;
    setActionStatus(exportStatus, 'loading', `Preparing ${format.toUpperCase()} export…`);

    try {
      const response = await fetch(`/api/accounts/${currentAccountId}/export?format=${format}`);
      if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        throw new Error(responseError(errorBody));
      }

      const exportBlob = await response.blob();
      const objectUrl = URL.createObjectURL(exportBlob);
      const download = document.createElement('a');
      download.href = objectUrl;
      download.download = `account-${currentAccountId}-handoff.${format === 'json' ? 'json' : 'md'}`;
      document.body.append(download);
      download.click();
      download.remove();
      URL.revokeObjectURL(objectUrl);
      setActionStatus(exportStatus, 'success', 'Export ready.');
    } catch (error) {
      setActionStatus(exportStatus, 'error', error.message || 'Export failed.');
    } finally {
      exportBusy = false;
      exportButtons.forEach((candidate) => candidate.removeAttribute('aria-disabled'));
    }
  });
});

const sectionLinks = [...document.querySelectorAll('.nav-link[href^="#"]')];
const observedSections = sectionLinks
  .map((link) => document.querySelector(link.getAttribute('href')))
  .filter(Boolean);

if ('IntersectionObserver' in window && observedSections.length > 0) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];

    if (!visible) return;

    sectionLinks.forEach((link) => {
      const isCurrent = link.getAttribute('href') === `#${visible.target.id}`;
      link.classList.toggle('is-active', isCurrent);
      if (isCurrent) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }, { rootMargin: '-18% 0px -68%', threshold: [0, 0.2, 0.5] });

  observedSections.forEach((section) => observer.observe(section));
}
