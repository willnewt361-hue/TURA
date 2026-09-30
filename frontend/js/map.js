/* Shared Google Maps route widget for the demo and connected tracking views. */
(() => {
  let mapsPromise;
  let configPromise;
  const routeCache = new Map();
  const widgets = new Set();

  function config() {
    if (!configPromise) {
      configPromise = fetch('/api/config', {
        cache: 'no-store',
        headers: { Accept: 'application/json' },
      })
        .then((response) => {
          if (!response.ok) throw new Error(`Map settings could not be loaded (${response.status}).`);
          return response.json();
        })
        .catch((error) => {
          configPromise = null;
          throw error;
        });
    }
    return configPromise;
  }

  function loadMaps() {
    if (window.google && window.google.maps) return Promise.resolve(window.google.maps);
    if (!mapsPromise) {
      mapsPromise = config().then((settings) => {
        const key = String(settings.google_maps_api_key || '').trim();
        if (!key) throw new Error('Google Maps is not configured. Add GOOGLE_MAPS_API_KEY to your .env file or Render environment.');
        return new Promise((resolve, reject) => {
          window.__turaMapsReady = () => resolve(window.google.maps);
          window.gm_authFailure = () => {
            widgets.forEach((widget) => widget.setStatus('Google Maps rejected this key. Check API access, billing and HTTP referrer restrictions.', true));
            reject(new Error('Google Maps authentication failed.'));
          };
          const script = document.createElement('script');
          script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=__turaMapsReady&loading=async`;
          script.async = true;
          script.onerror = () => reject(new Error('Google Maps could not be loaded. Check your network and API key configuration.'));
          document.head.appendChild(script);
        });
      }).catch((error) => {
        mapsPromise = null;
        throw error;
      });
    }
    return mapsPromise;
  }

  function formatDuration(seconds) {
    if (!Number.isFinite(seconds) || seconds <= 0) return 'Unavailable';
    let minutes = Math.round(seconds / 60);
    const hours = Math.floor(minutes / 60);
    minutes %= 60;
    if (!hours) return `${Math.max(1, minutes)} min`;
    return `${hours} hr${hours === 1 ? '' : 's'}${minutes ? ` ${minutes} min` : ''}`;
  }

  function routeError(error) {
    const message = String(error && error.message ? error.message : error);
    if (/REQUEST_DENIED|PERMISSION_DENIED|not enabled|API key|billing/i.test(message)) {
      return 'Google Routes rejected the request. Enable Routes API, check billing, and allow this website origin in the key restrictions.';
    }
    if (/ZERO_RESULTS|no route/i.test(message)) {
      return 'No driving route was found. Check the place names and try again.';
    }
    return 'The route could not be calculated. Check the place names and Google Routes API configuration.';
  }

  function readableError(error) {
    const message = routeError(error);
    return message.length > 240 ? `${message.slice(0, 237)}…` : message;
  }

  function mount(root) {
    if (!root || root.dataset.mapMounted === 'true') return;
    root.dataset.mapMounted = 'true';
    const canvas = root.querySelector('[data-map-canvas]');
    const status = root.querySelector('[data-map-status]');
    const originField = root.querySelector('[data-map-origin]');
    const destinationField = root.querySelector('[data-map-destination]');
    const routeLabel = root.querySelector('[data-map-route]');
    const distanceLabel = root.querySelector('[data-map-distance]');
    const etaLabel = root.querySelector('[data-map-eta]');
    const arrivalLabel = root.querySelector('[data-map-arrival]');
    if (!canvas) return;

    let map;
    let routePolylines = [];
    let routeMarkers = [];
    let busMarker;
    const widget = {
      root,
      setStatus(message, isError = false) {
        if (!status) return;
        status.replaceChildren(document.createTextNode(message));
        status.classList.toggle('map-error', isError);
        status.hidden = !message;
        if (message && isError) {
          const reload = document.createElement('button');
          reload.type = 'button';
          reload.className = 'map-retry';
          reload.textContent = 'Reload map';
          reload.addEventListener('click', () => window.location.reload());
          status.append(' ', reload);
        }
      },
    };
    widgets.forEach((activeWidget) => {
      if (!activeWidget.root.isConnected) widgets.delete(activeWidget);
    });
    widgets.add(widget);

    function setRouteLabel(origin, destination) {
      if (routeLabel) routeLabel.textContent = `${origin} → ${destination}`;
    }

    function setVehiclePosition() {
      if (!map || !window.google || !window.google.maps) return;
      const rawLat = root.dataset.liveLat;
      const rawLng = root.dataset.liveLng;
      const lat = Number(rawLat);
      const lng = Number(rawLng);
      if (!rawLat || !rawLng || !Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
        if (busMarker) busMarker.setMap(null);
        return;
      }
      const position = { lat, lng };
      if (!busMarker) {
        busMarker = new google.maps.Marker({
          map,
          position,
          title: 'Reported TURA vehicle position (simulated)',
          label: { text: 'BUS', color: '#ffffff', fontWeight: '700' },
        });
      } else {
        busMarker.setPosition(position);
        busMarker.setMap(map);
      }
    }

    async function showRoute(origin, destination) {
      const cleanOrigin = origin.trim();
      const cleanDestination = destination.trim();
      if (!cleanOrigin || !cleanDestination) {
        widget.setStatus('Enter both the departure and destination.', true);
        return;
      }
      if (cleanOrigin.length > 160 || cleanDestination.length > 160) {
        widget.setStatus('Each location must be 160 characters or fewer.', true);
        return;
      }
      setRouteLabel(cleanOrigin, cleanDestination);
      widget.setStatus('Finding the route…');
      if (distanceLabel) distanceLabel.textContent = '—';
      if (etaLabel) etaLabel.textContent = '—';
      try {
        const maps = await loadMaps();
        if (!map) {
          map = new maps.Map(canvas, {
            center: { lat: 1.3733, lng: 32.2903 },
            zoom: 7,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
            gestureHandling: 'cooperative',
          });
        }
        const cacheKey = `${cleanOrigin.toLocaleLowerCase()}|${cleanDestination.toLocaleLowerCase()}`;
        let routeData = routeCache.get(cacheKey);
        if (!routeData) {
          const { Route } = await maps.importLibrary('routes');
          const response = await Route.computeRoutes({
            origin: cleanOrigin,
            destination: cleanDestination,
            travelMode: 'DRIVING',
            fields: ['path', 'distanceMeters', 'durationMillis'],
          });
          routeData = response.routes && response.routes[0];
          if (!routeData) throw new Error('No driving route was found. Check the place names and try again.');
          routeCache.set(cacheKey, routeData);
        }
        routePolylines.forEach((polyline) => polyline.setMap(null));
        routeMarkers.forEach((marker) => marker.setMap(null));
        routePolylines = routeData.createPolylines();
        routePolylines.forEach((polyline) => {
          polyline.setOptions({ strokeColor: '#0b1f3a', strokeOpacity: 0.88, strokeWeight: 6 });
          polyline.setMap(map);
        });
        if (routePolylines.length) {
          const bounds = new maps.LatLngBounds();
          routePolylines.forEach((polyline) => polyline.getPath().forEach((point) => bounds.extend(point)));
          map.fitBounds(bounds, 48);
          const points = routePolylines[0].getPath();
          if (points.getLength()) {
            [points.getAt(0), points.getAt(points.getLength() - 1)].forEach((position) => {
              routeMarkers.push(new maps.Marker({ map, position }));
            });
          }
        }
        const durationSeconds = Number(routeData.durationMillis) / 1000;
        if (distanceLabel) {
          distanceLabel.textContent = Number.isFinite(routeData.distanceMeters)
            ? routeData.distanceMeters >= 1000
              ? `${(routeData.distanceMeters / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} km`
              : `${Math.round(routeData.distanceMeters)} m`
            : 'Unavailable';
        }
        if (etaLabel) etaLabel.textContent = formatDuration(durationSeconds);
        if (arrivalLabel && durationSeconds && !root.dataset.liveLat) {
          arrivalLabel.textContent = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
            .format(new Date(Date.now() + durationSeconds * 1000));
        }
        if (originField) originField.value = cleanOrigin;
        if (destinationField) destinationField.value = cleanDestination;
        setVehiclePosition();
        widget.setStatus('');
      } catch (error) {
        widget.setStatus(readableError(error), true);
      }
    }

    const query = new URLSearchParams(window.location.search);
    const initialOrigin = query.get('from') || (originField ? originField.value : (root.dataset.origin || 'Kampala, Uganda'));
    const initialDestination = query.get('to') || (destinationField ? destinationField.value : (root.dataset.destination || 'Gulu, Uganda'));
    if (originField) originField.value = initialOrigin;
    if (destinationField) destinationField.value = initialDestination;
    if (originField) originField.addEventListener('input', () => { root.dataset.origin = originField.value; });
    if (destinationField) destinationField.addEventListener('input', () => { root.dataset.destination = destinationField.value; });
    const form = root.querySelector('[data-map-form]');
    if (form) form.addEventListener('submit', (event) => {
      event.preventDefault();
      showRoute(
        originField ? originField.value : root.dataset.origin,
        destinationField ? destinationField.value : root.dataset.destination
      );
    });

    const locationButton = root.querySelector('[data-map-location]');
    if (locationButton) locationButton.addEventListener('click', () => {
      if (!navigator.geolocation) {
        widget.setStatus('Location is not supported by this browser.', true);
        return;
      }
      locationButton.disabled = true;
      widget.setStatus('Finding your location…');
      navigator.geolocation.getCurrentPosition((position) => {
        const value = `${position.coords.latitude},${position.coords.longitude}`;
        if (originField) originField.value = value;
        root.dataset.origin = value;
        locationButton.disabled = false;
        showRoute(value, destinationField ? destinationField.value : root.dataset.destination, false);
      }, (error) => {
        locationButton.disabled = false;
        widget.setStatus(error.code === error.PERMISSION_DENIED
          ? 'Location permission was denied. Enter your departure manually.'
          : 'Could not determine your location. Enter your departure manually.', true);
      }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
    });

    showRoute(initialOrigin, initialDestination);
  }

  function mountAll() {
    document.querySelectorAll('[data-tura-map]').forEach(mount);
  }

  window.TuraMap = { mount: mountAll };
  document.addEventListener('DOMContentLoaded', mountAll);
})();
