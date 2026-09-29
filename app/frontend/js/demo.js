(() => {
  const root = document.documentElement;
  const appUrl = (user) => {
    const route = user.role === 'operator' || user.role === 'admin'
      ? 'ops'
      : user.role === 'driver' ? 'driver' : 'home';
    return `/app/#/${route}`;
  };
  let storedTheme = '';
  try {
    storedTheme = localStorage.getItem('tura-demo-theme') || '';
  } catch (error) {
    console.error('Theme preference could not be loaded:', error);
  }
  if (storedTheme === 'dark' || storedTheme === 'light') root.dataset.theme = storedTheme;

  document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
    const updateLabel = () => {
      button.textContent = root.dataset.theme === 'dark' ? 'Light mode' : 'Dark mode';
      button.setAttribute('aria-pressed', String(root.dataset.theme === 'dark'));
    };
    updateLabel();
    button.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem('tura-demo-theme', root.dataset.theme);
      } catch (error) {
        console.error('Theme preference could not be saved:', error);
      }
      updateLabel();
    });
  });

  const todayField = document.querySelector('[data-default-today]');
  if (todayField) {
    const today = new Date();
    const localToday = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-');
    todayField.min = localToday;
    if (!todayField.value) todayField.value = localToday;
  }

  const routeQuery = new URLSearchParams(location.search);
  ['from', 'to', 'date'].forEach((name) => {
    const target = document.querySelector(`[data-query="${name}"]`);
    const value = routeQuery.get(name);
    if (target && value) target.textContent = value;
  });

  const seatStatus = document.querySelector('[data-seat-status]');
  let selectedSeat = '';
  document.querySelectorAll('[data-seat]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedSeat = button.textContent.trim();
      document.querySelectorAll('[data-seat]').forEach((seat) => {
        seat.setAttribute('aria-pressed', String(seat === button));
      });
      document.querySelectorAll('[data-seat-next]').forEach((link) => {
        link.href = `/pages/passenger.html?seat=${encodeURIComponent(selectedSeat)}`;
      });
      if (seatStatus) seatStatus.textContent = `Selected seat ${selectedSeat}. Continue to passenger details.`;
      document.querySelectorAll('[data-selected-seat]').forEach((node) => { node.textContent = selectedSeat; });
    });
  });

  document.querySelectorAll('[data-seat-next]').forEach((link) => {
    link.addEventListener('click', (event) => {
      if (!selectedSeat) {
        event.preventDefault();
        if (seatStatus) seatStatus.textContent = 'Choose an available seat before continuing.';
      }
    });
  });

  const passengerForm = document.querySelector('[data-passenger-form]');
  if (passengerForm) {
    passengerForm.addEventListener('submit', (event) => {
      event.preventDefault();
      location.assign('/pages/payment.html');
    });
    const seat = new URLSearchParams(location.search).get('seat') || '';
    if (/^\d{1,2}[A-F]$/.test(seat)) {
      document.querySelectorAll('[data-selected-seat]').forEach((node) => { node.textContent = seat; });
    }
  }

  const filter = document.querySelector('[data-filter]');
  const filterItems = document.querySelectorAll('[data-filter-item]');
  if (filter) {
    filter.addEventListener('input', () => {
      let count = 0;
      filterItems.forEach((item) => {
        const shown = item.textContent.toLowerCase().includes(filter.value.trim().toLowerCase());
        item.hidden = !shown;
        if (shown) count += 1;
      });
      const empty = document.querySelector('[data-filter-empty]');
      if (empty) empty.hidden = count > 0;
    });
  }

  const loginForm = document.querySelector('[data-demo-login]');
  if (loginForm) {
    const status = document.querySelector('[data-login-status]');
    const submit = loginForm.querySelector('[type="submit"]');
    const setStatus = (message, isError = false) => {
      status.textContent = message;
      status.classList.toggle('error', isError);
    };
    loginForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      submit.disabled = true;
      setStatus('Signing in…');
      try {
        const result = await TuraAPI.api('/api/auth/login', {
          method: 'POST',
          body: {
            phone: loginForm.elements.phone.value.trim(),
            password: loginForm.elements.password.value,
          },
        });
        setStatus(`Welcome, ${result.user.name}. Opening the live TURA app…`);
        location.assign(appUrl(result.user));
      } catch (error) {
        setStatus(
          error.status ? error.message : 'TURA could not reach the server. Start it with python main.py and try again.',
          true
        );
      } finally {
        submit.disabled = false;
      }
    });
  }

  document.querySelectorAll('[data-demo-role]').forEach((demoLogin) => {
    demoLogin.addEventListener('click', async () => {
      demoLogin.disabled = true;
      const status = document.querySelector('[data-login-status]');
      status.textContent = 'Signing in with the demo account…';
      status.classList.remove('error');
      try {
        const result = await TuraAPI.api('/api/auth/demo-login', {
          method: 'POST',
          body: { role: demoLogin.dataset.demoRole },
        });
        status.textContent = `Welcome, ${result.user.name}. Opening the live TURA app…`;
        location.assign(appUrl(result.user));
      } catch (error) {
        status.textContent = error.status ? error.message : 'TURA could not reach the server. Start it with python main.py and try again.';
        status.classList.add('error');
      } finally {
        demoLogin.disabled = false;
      }
    });
  });
})();
