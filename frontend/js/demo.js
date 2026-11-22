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

  const routeForm = document.querySelector('[data-route-search]');
  if (routeForm) {
    const originSelect = routeForm.querySelector('[data-route-origin]');
    const destinationSelect = routeForm.querySelector('[data-route-destination]');
    const dateField = routeForm.elements.date;
    const submitButton = routeForm.querySelector('[data-route-submit]');
    const routeStatus = routeForm.querySelector('[data-route-status]');
    const routeGrid = document.querySelector('[data-route-grid]');
    let origins = [];
    let destinations = [];

    const setStatus = (message, isError = false) => {
      routeStatus.textContent = message;
      routeStatus.classList.toggle('error', isError);
    };
    const fillSelect = (select, values, preferred, placeholder) => {
      select.replaceChildren();
      const empty = document.createElement('option');
      empty.value = '';
      empty.textContent = values.length ? placeholder : 'No routes available';
      select.appendChild(empty);
      values.forEach((value) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      });
      select.disabled = values.length === 0;
      select.value = values.includes(preferred) ? preferred : values[0] || '';
    };

    const loadRouteOptions = async () => {
      try {
        if (!window.TuraAPI) throw new Error('TURA API client is unavailable');
        const cities = await TuraAPI.api('/api/trips/cities');
        origins = Array.isArray(cities.origins) ? cities.origins.filter((city) => typeof city === 'string') : [];
        destinations = Array.isArray(cities.destinations)
          ? cities.destinations.filter((city) => typeof city === 'string')
          : [];
        const query = new URLSearchParams(location.search);
        fillSelect(originSelect, origins, query.get('origin') || 'Kampala', 'Choose an origin');
        fillSelect(destinationSelect, destinations, query.get('destination') || 'Gulu', 'Choose a destination');
        submitButton.disabled = !origins.length || !destinations.length;
        setStatus(
          submitButton.disabled
            ? 'No routes are published yet. Please check back later.'
            : 'Choose a route and date to continue in the connected app.'
        );

        routeGrid.replaceChildren();
        try {
          const popular = await TuraAPI.api('/api/trips/popular');
          const routes = Array.isArray(popular.routes) ? popular.routes : [];
          routes.forEach((route) => {
            if (typeof route.origin !== 'string' || typeof route.destination !== 'string') return;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'route-card';
            button.setAttribute('aria-label', `Search departures from ${route.origin} to ${route.destination}`);
            const label = document.createElement('span');
            label.textContent = 'Configured route';
            const name = document.createElement('strong');
            name.textContent = `${route.origin} → ${route.destination}`;
            const action = document.createElement('em');
            action.textContent = 'Check departures →';
            button.append(label, name, action);
            button.addEventListener('click', () => {
              if (origins.includes(route.origin)) originSelect.value = route.origin;
              if (destinations.includes(route.destination)) destinationSelect.value = route.destination;
              document.querySelector('#route-search').scrollIntoView({ behavior: 'smooth', block: 'center' });
            });
            routeGrid.appendChild(button);
          });
          if (!routes.length) routeGrid.textContent = 'No routes have been configured yet.';
        } catch (error) {
          routeGrid.textContent = `Route suggestions are unavailable: ${error.message}`;
        }
      } catch (error) {
        if (routeStatus) setStatus(`Could not load route options: ${error.message}`, true);
        if (routeGrid) routeGrid.textContent = `Route suggestions are unavailable: ${error.message}`;
        originSelect.disabled = true;
        destinationSelect.disabled = true;
        submitButton.disabled = true;
      }
    };

    routeForm.addEventListener('submit', (event) => {
      event.preventDefault();
      if (!routeForm.reportValidity()) return;
      if (originSelect.value.toLowerCase() === destinationSelect.value.toLowerCase()) {
        setStatus('Choose two different cities.', true);
        destinationSelect.focus();
        return;
      }
      const params = new URLSearchParams({
        origin: originSelect.value,
        destination: destinationSelect.value,
        date: dateField.value,
      });
      location.assign(`/app/?${params.toString()}`);
    });

    const swap = routeForm.querySelector('[data-route-swap]');
    if (swap) {
      swap.addEventListener('click', () => {
        const origin = originSelect.value;
        const destination = destinationSelect.value;
        if (!origins.includes(destination) || !destinations.includes(origin)) {
          setStatus('The reverse route is not configured. Choose a different route.', true);
          return;
        }
        originSelect.value = destination;
        destinationSelect.value = origin;
        setStatus('Route directions swapped.');
      });
    }

    loadRouteOptions();
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
