(() => {
  const root = document.documentElement;
  const key = 'tura-demo-theme';
  try {
    const savedTheme = localStorage.getItem(key);
    if (savedTheme === 'dark' || savedTheme === 'light') root.dataset.theme = savedTheme;
  } catch (error) {
    console.error('Theme preference could not be loaded:', error);
  }

  const updateLabels = () => {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.textContent = root.dataset.theme === 'dark' ? 'Light mode' : 'Dark mode';
      button.setAttribute('aria-pressed', String(root.dataset.theme === 'dark'));
    });
  };
  updateLabels();

  document.addEventListener('click', (event) => {
    const button = event.target instanceof Element ? event.target.closest('[data-theme-toggle]') : null;
    if (!button) return;
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem(key, root.dataset.theme);
    } catch (error) {
      console.error('Theme preference could not be saved:', error);
    }
    updateLabels();
  });
})();
