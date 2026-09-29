(() => {
  const selected = document.querySelectorAll('[data-seat-select]');
  selected.forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-seat-select]').forEach((item) => item.classList.remove('selected'));
      button.classList.add('selected');
      const label = document.querySelector('[data-selected-seat]');
      if (label) label.textContent = `Selected seat: ${button.textContent}`;
    });
  });

  const search = document.querySelector('[data-route-search]');
  const routes = document.querySelectorAll('[data-route-card]');
  if (search) {
    search.addEventListener('input', () => {
      const query = search.value.trim().toLowerCase();
      let count = 0;
      routes.forEach((route) => {
        const matches = route.textContent.toLowerCase().includes(query);
        route.hidden = !matches;
        if (matches) count += 1;
      });
      const empty = document.querySelector('[data-empty-state]');
      if (empty) empty.hidden = count !== 0;
    });
  }

  document.querySelectorAll('[data-preview-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const next = form.getAttribute('data-next');
      if (next) location.href = next;
    });
  });
})();
