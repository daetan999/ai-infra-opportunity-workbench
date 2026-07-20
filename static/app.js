const body = document.body;
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
