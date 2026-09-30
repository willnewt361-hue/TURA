/** TURA SPA — customer, operator, driver flows */
(function () {
  const { api, uuid } = TuraAPI;
  const t = (...args) => TuraI18n.t(...args);

  const state = {
    user: null,
    config: null,
    route: 'splash',
    cities: { origins: [], destinations: [] },
    citiesLoaded: false,
    search: { origin: 'Kampala', destination: 'Gulu', date: '', passengers: 1 },
    trips: [],
    selectedTrip: null,
    seats: [],
    selectedSeat: null,
    pendingCheckout: null,
    passenger: { name: '', phone: '', email: '', special: '', insurance: false, luggage: false },
    payMethod: 'mobile_money',
    lastTicket: null,
    bookings: [],
    tickets: [],
    trackingTripId: null,
    tracking: null,
    trackingOptionsLoaded: false,
    ops: null,
    opsLive: null,
    opsSetup: { buses: [], routes: [], drivers: [] },
    opsTrips: [],
    opsDiagnostics: null,
    replay: null,
    driverTrips: [],
    opsLoadError: '',
    ticketCacheMode: 'live',
    tripCacheMode: 'live',
    offlineSession: false,
    online: navigator.onLine,
    wsLive: false,
  };

  const $ = (sel, el = document) => el.querySelector(sel);
  const app = $('#app');

  function toast(msg, kind = '') {
    const box = $('#toasts') || Object.assign(document.createElement('div'), { id: 'toasts', className: 'toasts' });
    if (!box.parentNode) document.body.appendChild(box);
    const n = document.createElement('div');
    n.className = 'toast ' + kind;
    n.textContent = msg;
    box.appendChild(n);
    setTimeout(() => n.remove(), 3500);
  }

  function money(n) {
    return `UGX ${Number(n || 0).toLocaleString()}`;
  }

  function initials(name) {
    return (name || 'T').split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  }

  function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
  }

  function localDateISO(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  function setHash(route, params) {
    if (state.route === 'ops' && route !== 'ops' && state.replay && state.replay.timer) {
      clearInterval(state.replay.timer);
      state.replay.timer = null;
    }
    const q = params ? '?' + new URLSearchParams(params).toString() : '';
    location.hash = '#/' + route + q;
  }

  function parseHash() {
    const raw = location.hash.replace(/^#\/?/, '') || 'splash';
    const [path, qs] = raw.split('?');
    const params = Object.fromEntries(new URLSearchParams(qs || ''));
    return { path, params };
  }

  function statusBar() {
    const restricted = !state.online || state.offlineSession;
    const label = !state.online ? t('offline') : state.offlineSession ? 'Read-only' : t('online');
    const detail = !state.online
      ? 'Offline · saved journey only'
      : state.offlineSession
        ? 'Saved account · sign in for live actions'
        : state.wsLive ? 'Live updates' : 'Reconnecting…';
    return `<div class="status-bar">
      <span class="pill"><span class="dot ${restricted ? 'offline' : ''}"></span>${label}</span>
      <span>${detail} · TURA v1</span>
      <span>${state.user ? state.user.role : 'guest'}</span>
    </div>`;
  }

  function demoEnabled() {
    return !!(state.config && state.config.demo_mode);
  }

  function rememberOfflineUser(user) {
    try {
      localStorage.setItem('tura_offline_user', JSON.stringify({
        id: user.id,
        name: user.name,
        phone: user.phone,
      }));
    } catch (e) {
      toast('Offline identity could not be saved in this browser: ' + e.message, 'err');
    }
  }

  function readOfflineUser() {
    try {
      const user = JSON.parse(localStorage.getItem('tura_offline_user') || 'null');
      return user && Number.isInteger(user.id) && user.id > 0
        ? { id: user.id, name: user.name || 'Traveler', phone: user.phone || '', role: 'customer' }
        : null;
    } catch (e) {
      try { localStorage.removeItem('tura_offline_user'); }
      catch (storageError) { toast('Could not clear local sign-in state: ' + storageError.message, 'err'); }
      return null;
    }
  }

  function topbar(title) {
    const u = state.user;
    return `<header class="topbar">
      <div class="logo-row"><img src="/assets/logo.svg" alt="TURA — One Tap. One Journey."/><span>${escapeHtml(title || 'TURA')}</span></div>
      <button class="theme-toggle" type="button" data-theme-toggle>${document.documentElement.dataset.theme === 'dark' ? 'Light mode' : 'Dark mode'}</button>
      <button class="avatar" id="btn-profile" title="${u ? u.name : 'Account'}">${initials(u ? u.name : 'T')}</button>
    </header>`;
  }

  function bottomNav(active) {
    const items = [
      ['home', t('home'), iconHome()],
      ['tickets', t('tickets'), iconTicket()],
      ['tracking', t('live'), iconLive()],
      ['explore', t('explore'), iconExplore()],
      ['more', t('more'), iconMore()],
    ];
    return `<nav class="bottom-nav">${items.map(([id, label, icon]) =>
      `<button data-nav="${id}" class="${active === id ? 'active' : ''}">${icon}<span>${label}</span></button>`
    ).join('')}</nav>
    <button class="help-fab" id="help-fab" title="Help">?</button>`;
  }

  function iconHome(){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5z"/></svg>';}
  function iconTicket(){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4V8z"/><path d="M12 6v12"/></svg>';}
  function iconLive(){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M5 12a7 7 0 0 1 7-7m7 7a7 7 0 0 1-7 7M2 12a10 10 0 0 1 10-10m10 10a10 10 0 0 1-10 10"/></svg>';}
  function iconExplore(){return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="m8 16 2.5-6.5L17 8l-2.5 6.5L8 16z"/></svg>';}
  function iconMore(){return '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="6" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="18" cy="12" r="1.6"/></svg>';}

  function bindChrome() {
    document.querySelectorAll('[data-nav]').forEach((b) => b.onclick = () => setHash(b.dataset.nav));
    const help = $('#help-fab');
    if (help) help.onclick = () => TuraTour.openHelp();
    const profile = $('#btn-profile');
    if (profile) profile.onclick = () => setHash('more');
  }

  /* ---------- Views ---------- */
  function viewSplash() {
    return `<section class="splash">
      <div class="splash-inner">
        <div class="splash-brand"><img src="/assets/logo.svg" alt="TURA — One Tap. One Journey."/></div>
        <div class="splash-copy"><span class="eyebrow">UGANDA, YOUR WAY</span><h1>Every journey<br/>starts with one tap.</h1><p>Find your bus, choose your seat and keep your trip close — from Kampala and beyond.</p></div>
        <div class="splash-cta">
          <button class="btn btn-accent btn-block" id="btn-start">${t('getStarted')}</button>
          ${demoEnabled() ? `<button class="btn btn-ghost btn-block" id="btn-demo">${t('demoMode')}</button>` : ''}
          <a class="btn btn-ghost btn-block" href="/screens/">Browse screen previews</a>
          <div class="splash-links"><span>${t('book')}</span><span>${t('travel')}</span><span>${t('explore')}</span></div>
        </div>
      </div><div class="splash-art" role="img" aria-label="TURA coach travelling across Uganda"></div><div class="splash-footer">SAFE TRAVEL <i></i> TRUSTED OPERATORS <i></i> ONE TAP. ONE JOURNEY.</div></section>`;
  }

  function viewHome() {
    const name = (state.user && state.user.name.split(' ')[0]) || 'Traveler';
    const origins = state.cities.origins.map((c) => `<option value="${escapeHtml(c)}" ${c===state.search.origin?'selected':''}>${escapeHtml(c)}</option>`).join('');
    const dests = state.cities.destinations.map((c) => `<option value="${escapeHtml(c)}" ${c===state.search.destination?'selected':''}>${escapeHtml(c)}</option>`).join('');
    const routesAvailable = state.cities.origins.length > 0 && state.cities.destinations.length > 0;
    return `${statusBar()}${topbar()}
      <main class="page">
        <section class="home-hero">
          <div class="home-hero-copy"><span class="eyebrow">YOUR NEXT STOP</span><h1>${t('goodMorning')}, ${escapeHtml(name)}.</h1><p>${t('whereGoing')}</p></div>
          <img src="/assets/uganda-coach.svg" alt="TURA coach on a green Ugandan route"/>
        </section>
        <section class="search-panel" aria-label="Find a bus">
          <div class="search-panel-title"><div><span class="eyebrow">PLAN YOUR RIDE</span><h2>Where to today?</h2></div><span class="search-mark" aria-hidden="true">↗</span></div>
          <div class="search-fields">
            <div class="field route-field"><label for="f-origin">${t('from')}</label><select id="f-origin" ${routesAvailable?'':'disabled'}>${origins || '<option value="">Routes not set up yet</option>'}</select></div>
            <div class="route-swap" aria-hidden="true">↓</div>
            <div class="field route-field"><label for="f-dest">${t('to')}</label><select id="f-dest" ${routesAvailable?'':'disabled'}>${dests || '<option value="">Add routes in Operator dashboard</option>'}</select></div>
            <div class="field"><label for="f-date">${t('date')}</label><input type="date" id="f-date" value="${state.search.date}" min="${localDateISO(new Date())}"/></div>
            <div class="field"><label for="f-pax">${t('passengers')}</label><input type="number" id="f-pax" min="1" max="4" value="${state.search.passengers}"/></div>
          </div>
          ${!routesAvailable ? '<p class="setup-hint">No routes are published yet. Sign in as an operator and create a bus, route, and trip to enable booking.</p>' : ''}
          <button class="btn btn-primary btn-block search-submit" id="btn-search" ${routesAvailable?'':'disabled'}>${t('searchBuses')} <span aria-hidden="true">→</span></button>
        </section>
        <div class="section-title"><span>${t('popular')}</span><button class="text-link" data-nav="explore">View all <span aria-hidden="true">→</span></button></div>
        <div class="dest-scroll" id="popular-dests"></div>
        <div class="trust-strip"><span>✓ Server-checked seats</span><span>◈ Saved trip details</span><span>◎ Local Ugandan routes</span></div>
      </main>${bottomNav('home')}`;
  }

  function viewResults() {
    const trips = state.trips.map((tr) => `
      <article class="trip-card route-result-card">
        <div class="head"><span class="operator-lockup"><span class="operator-mark" aria-hidden="true">T</span><span class="op">${escapeHtml(tr.operator)}</span></span><span class="rating">★ ${Number(tr.rating || 0).toFixed(1)}</span></div>
        <div class="trip-times">
          <div><strong>${fmtTime(tr.departure)}</strong><div style="color:var(--muted);font-size:12px">${escapeHtml(tr.origin)}</div></div>
          <div class="line"></div>
          <div style="text-align:right"><strong>${fmtTime(tr.arrival)}</strong><div style="color:var(--muted);font-size:12px">${escapeHtml(tr.destination)}</div></div>
        </div>
        <div class="route-duration">${Number(tr.duration_minutes || 0) ? `${Math.floor(tr.duration_minutes / 60)}h ${tr.duration_minutes % 60 ? `${tr.duration_minutes % 60}m` : ''}` : 'Direct route'} <span>·</span> ${escapeHtml(tr.plate || 'Scheduled coach')}</div>
        <div class="amenities">${(tr.amenities||[]).map((a)=>`<span class="chip">${escapeHtml(a.toUpperCase())}</span>`).join('')}<span class="chip">${Number(tr.available_seats || 0)} seats left</span></div>
        <div class="trip-foot"><div class="price">${money(tr.fare_ugx)}</div>
          <button class="btn btn-primary" data-select-trip="${tr.id}" ${!state.online || state.tripCacheMode === 'cached' ? 'disabled' : ''}>${t('selectSeat')}</button></div>
      </article>`).join('') || '<div class="empty">No buses found for this route/date.</div>';
    return `${statusBar()}${topbar(state.search.origin + ' → ' + state.search.destination)}
      <main class="page">
        <div class="results-intro"><span class="eyebrow">YOUR ROUTE</span><h1>${escapeHtml(state.search.origin)} <span>→</span> ${escapeHtml(state.search.destination)}</h1><p>Choose a departure that works for you.</p></div>
        ${state.tripCacheMode === 'cached' ? '<div class="offline-note" role="status">Cached search results — availability and fares may be stale. Booking is disabled until you are online.</div>' : ''}
        <div class="date-strip" id="date-strip"></div>
        <div style="display:flex;justify-content:space-between;margin-bottom:10px;font-size:13px;color:var(--muted)">
          <span>Sort: Price Low to High</span><span>${state.trips.length} buses</span>
        </div>
        ${trips}
      </main>${bottomNav('home')}`;
  }

  function viewSeats() {
    const byRow = {};
    state.seats.forEach((s) => { (byRow[s.row] = byRow[s.row] || []).push(s); });
    const rows = Object.keys(byRow).sort((a,b)=>a-b).map((r) => {
      const seats = byRow[r].sort((a,b)=>a.column-b.column);
      const cells = [0,1,2,3,4].map((col) => {
        if (col === 2) return '<div></div>';
        const seat = seats.find((s) => s.column === col);
        if (!seat) return '<div></div>';
        let cls = seat.status;
        if (seat.locked_by_me || (state.selectedSeat && state.selectedSeat.id === seat.id)) cls = 'selected';
        return `<button class="seat ${cls}" data-seat="${seat.id}" ${['occupied','locked','maintenance'].includes(seat.status) && !seat.locked_by_me ? 'disabled' : ''}>${seat.label}</button>`;
      }).join('');
      return `<div class="seat-row">${cells}</div>`;
    }).join('');
    const sel = state.selectedSeat;
    const trip = state.selectedTrip;
    return `${statusBar()}${topbar(t('selectSeat'))}
      <main class="page">
        <div class="seat-trip-summary">
          <span class="eyebrow">YOUR DEPARTURE</span>
          <h1>${trip ? `${escapeHtml(trip.origin)} <span>→</span> ${escapeHtml(trip.destination)}` : 'Choose your seat'}</h1>
          <p>${trip ? `${escapeHtml(trip.operator)} · ${fmtDate(trip.departure)} · ${fmtTime(trip.departure)} · ${money(trip.fare_ugx)}` : ''}</p>
        </div>
        <div class="seat-select-title"><h2>Choose your seat</h2><span>${state.seats.filter((seat) => seat.status === 'available').length} available</span></div>
        <div class="seat-legend">
          <span><i class="legend-available"></i>Available</span>
          <span><i class="legend-selected"></i>Selected ${sel ? escapeHtml(sel.label) : ''}</span>
          <span><i class="legend-occupied"></i>Occupied</span>
        </div>
        <div class="seat-map"><div class="steering"><span aria-hidden="true">◉</span><span>FRONT OF COACH</span></div>${rows}</div>
        <div class="seat-selection-footer"><span>${sel ? `Seat ${escapeHtml(sel.label)} selected` : 'Tap an available seat'}</span><button class="btn btn-primary" id="btn-seat-next" ${sel?'':'disabled'}>${t('next')} <span aria-hidden="true">→</span></button></div>
      </main>${bottomNav('home')}`;
  }

  function viewPassenger() {
    const p = state.passenger;
    const fare = state.selectedTrip ? state.selectedTrip.fare_ugx : 40000;
    const fees = state.config ? state.config.fees : {};
    const insurance = p.insurance ? (fees.insurance_fee_ugx || 2000) : 0;
    const luggage = p.luggage ? (fees.luggage_fee_ugx || 5000) : 0;
    const bookingFee = fees.booking_fee_ugx || 500;
    const total = fare + insurance + luggage + bookingFee;
    return `${statusBar()}${topbar('Passenger Details')}
      <main class="page">
        <div class="card search-card">
          <div class="field"><label>Full Name</label><input id="p-name" value="${escapeHtml(p.name)}" required minlength="2" maxlength="120"/></div>
          <div class="field"><label>Phone Number</label><input id="p-phone" type="tel" value="${escapeHtml(p.phone)}" placeholder="+256..." required minlength="9" maxlength="32" pattern="\\+?[0-9]{9,15}"/></div>
          <div class="field"><label>Email (Optional)</label><input id="p-email" type="email" value="${escapeHtml(p.email)}" maxlength="160"/></div>
          <div class="field"><label>Special Request (Optional)</label><textarea id="p-special" rows="3" maxlength="500">${escapeHtml(p.special)}</textarea></div>
          <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="p-ins" ${p.insurance?'checked':''}/> Travel insurance (+${money(fees.insurance_fee_ugx||2000)})</label>
          <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="p-lug" ${p.luggage?'checked':''}/> Extra luggage (+${money(fees.luggage_fee_ugx||5000)})</label>
          <div class="ticket-meta">
            <div><span>Seat</span><strong>${state.selectedSeat ? state.selectedSeat.label : ''}</strong></div>
            <div><span>Fare</span><strong>${money(fare)}</strong></div>
            <div><span>Fees</span><strong>${money(bookingFee + insurance + luggage)}</strong></div>
            <div><span>Total</span><strong>${money(total)}</strong></div>
          </div>
          <button class="btn btn-primary btn-block" id="btn-pass-next">${t('continue')}</button>
        </div>
      </main>${bottomNav('home')}`;
  }

  function viewPayment() {
    const tr = state.selectedTrip;
    const method = state.payMethod;
    return `${statusBar()}${topbar('Payment')}
      <main class="page">
        <div class="pay-option ${method==='mobile_money'?'active':''}" data-pay="mobile_money">
          <strong>Mobile Money</strong>
          <div class="logos"><span class="badge-momo airtel">Airtel</span><span class="badge-momo mtn">MTN</span></div>
        </div>
        <div class="pay-option ${method==='card'?'active':''}" data-pay="card"><strong>Card Payment</strong><span class="chip">Visa / Mastercard</span></div>
        <div class="pay-option ${method==='bank'?'active':''}" data-pay="bank"><strong>Other Methods</strong><span class="chip">Bank Transfer</span></div>
        <div class="card" style="margin-top:14px">
          <h3 style="margin-bottom:10px;color:var(--navy)">Booking Summary</h3>
          <div class="ticket-meta">
            <div><span>Route</span><strong>${tr ? escapeHtml(tr.origin+' → '+tr.destination) : ''}</strong></div>
            <div><span>Date</span><strong>${tr ? fmtDate(tr.departure) : ''}</strong></div>
            <div><span>Time</span><strong>${tr ? fmtTime(tr.departure) : ''}</strong></div>
            <div><span>Operator</span><strong>${tr ? escapeHtml(tr.operator) : ''}</strong></div>
            <div><span>Seat</span><strong>${state.selectedSeat ? state.selectedSeat.label : ''}</strong></div>
          </div>
          <p style="font-size:12px;color:var(--muted);margin:10px 0">Mock provider — no real Mobile Money charge. Boundary ready for MTN/Airtel later.</p>
          <button class="btn btn-primary btn-block" id="btn-pay" ${!state.online || state.offlineSession ? 'disabled' : ''}>${state.pendingCheckout ? 'Retry mock payment' : t('payNow')}</button>
        </div>
      </main>${bottomNav('home')}`;
  }

  function viewTicket() {
    const tk = state.lastTicket;
    if (!tk) return `${statusBar()}${topbar('Ticket')}<main class="page"><div class="empty">No ticket yet.</div></main>${bottomNav('tickets')}`;
    return `${statusBar()}${topbar('QR Ticket')}
      <main class="page">
        <div class="card">
          ${state.ticketCacheMode === 'cached' ? '<div class="offline-note">Saved on this device · verify the latest ticket status when online.</div>' : ''}
          <div class="ticket-hero">
            <div class="check">✓</div>
            <h2 style="color:var(--success)">${t('bookingConfirmed')}</h2>
          </div>
          <div class="qr-box">${tk.qr_data_url
            ? `<img id="qr-img" alt="Ticket QR code" src="${escapeHtml(tk.qr_data_url)}"/>`
            : state.online && !state.offlineSession
              ? `<img id="qr-img" alt="Ticket QR code" src="/api/tickets/${Number(tk.id)}/qr.png"/>`
              : '<span class="offline-qr-note">QR not saved — open this ticket while online once to save its code.</span>'}</div>
          <div class="ticket-meta">
            <div><span>Ticket No</span><strong>${escapeHtml(tk.ticket_no)}</strong></div>
            <div><span>Seat</span><strong>${escapeHtml(tk.seat)}</strong></div>
            <div><span>Route</span><strong>${escapeHtml(tk.route)}</strong></div>
            <div><span>Date</span><strong>${fmtDate(tk.departure)}</strong></div>
            ${tk.arrival ? `<div><span>Arrival</span><strong>${fmtTime(tk.arrival)}</strong></div>` : ''}
            ${tk.stops && tk.stops.length ? `<div><span>Stops</span><strong>${escapeHtml(tk.stops.join(' · '))}</strong></div>` : ''}
            <div><span>Operator</span><strong>${escapeHtml(tk.operator)}</strong></div>
            <div><span>Expires</span><strong>${fmtDate(tk.expires_at)}</strong></div>
          </div>
          <div style="display:grid;grid-template-columns:${state.online && !state.offlineSession ? '1fr 1fr' : '1fr'};gap:10px;margin-top:14px">
            ${state.online && !state.offlineSession ? `<button class="btn btn-outline" id="btn-save-ticket">${t('saveTicket')}</button>` : ''}
            <button class="btn btn-primary" id="btn-share-ticket">${t('share')}</button>
          </div>
        </div>
      </main>${bottomNav('tickets')}`;
  }

  function viewTickets() {
    const tab = state.ticketTab || 'upcoming';
    const list = state.tickets.filter((tk) => {
      const past = tk.status === 'used' || tk.status === 'expired' || tk.status === 'cancelled';
      return tab === 'past' ? past : !past;
    });
    const cards = list.map((tk) => `
      <div class="trip-card">
        <div class="head"><strong>${escapeHtml(tk.route)}</strong><span class="chip" style="background:${tk.status==='valid'?'#e8f0ff':'var(--success-soft)'};color:var(--navy)">${escapeHtml(tk.status)}</span></div>
        <div style="color:var(--muted);font-size:13px">${fmtDate(tk.departure)} · ${fmtTime(tk.departure)} · Seat ${escapeHtml(tk.seat)}</div>
        <button class="btn btn-outline" data-view-ticket="${tk.id}">View Ticket</button>
      </div>`).join('') || '<div class="empty">No tickets in this tab.</div>';
    return `${statusBar()}${topbar('My Tickets')}
      <main class="page">
        <div class="offline-note" role="status">
          ${state.ticketCacheMode === 'cached'
            ? `Offline Journey Pack · showing saved tickets${state.tickets[0] && state.tickets[0].cached_at ? ` · saved ${fmtDate(state.tickets[0].cached_at)} ${fmtTime(state.tickets[0].cached_at)}` : ''}. Ticket and route details may be stale.`
            : 'Offline Journey Pack · tickets and itinerary are saved on this device when available.'}
        </div>
        <div class="tabs">
          <button class="${tab==='upcoming'?'active':''}" data-ttab="upcoming">${t('upcoming')}</button>
          <button class="${tab==='past'?'active':''}" data-ttab="past">${t('past')}</button>
        </div>
        ${cards}
      </main>${bottomNav('tickets')}`;
  }

  function viewTracking() {
    const pos = state.tracking && state.tracking.position;
    const progress = pos && Number.isFinite(Number(pos.progress_pct))
      ? Math.max(0, Math.min(100, Number(pos.progress_pct)))
      : 0;
    const label = pos ? pos.label : 'Awaiting departure';
    const steps = ['Departed', 'On Route', 'On Site', 'Arrived'];
    const activeIdx = progress >= 100 ? 3 : progress >= 66 ? 2 : progress >= 20 ? 1 : 0;
    return `${statusBar()}${topbar('Live Tracking')}
      <main class="page">
        <div class="tracking-intro"><span class="eyebrow">${!state.online || state.offlineSession ? 'SAVED ITINERARY' : 'TRIP STATUS'}</span><h1>${state.selectedTrip ? `${escapeHtml(state.selectedTrip.origin)} <span>→</span> ${escapeHtml(state.selectedTrip.destination)}` : 'Your journey'}</h1><p>${state.selectedTrip ? `${escapeHtml(state.selectedTrip.operator)} · ${fmtDate(state.selectedTrip.departure)}` : 'Your saved and active trips appear here.'}</p></div>
        <div class="map-stage">
          <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice">
            <defs>
              <linearGradient id="road" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#0B1F3A"/><stop offset="100%" stop-color="#3B6EA5"/>
              </linearGradient>
            </defs>
            <path d="M40 240 C 100 200, 140 160, 180 140 S 280 80, 360 60" fill="none" stroke="#ffffff" stroke-width="15" stroke-linecap="round" opacity=".8"/>
            <path d="M40 240 C 100 200, 140 160, 180 140 S 280 80, 360 60" fill="none" stroke="url(#road)" stroke-width="7" stroke-linecap="round"/>
            <circle cx="40" cy="240" r="9" fill="#fff" stroke="#0B1F3A" stroke-width="4"/>
            <circle cx="360" cy="60" r="9" fill="#F5C542" stroke="#0B1F3A" stroke-width="4"/>
            <g transform="translate(${40 + progress * 3.2},${240 - progress * 1.8})"><circle r="17" fill="#0B1F3A"/><text x="0" y="5" text-anchor="middle" font-size="15" fill="#fff">▰</text></g>
            <text x="30" y="269" font-size="11" font-weight="700" fill="#0B1F3A">${escapeHtml(state.selectedTrip ? state.selectedTrip.origin : 'Start')}</text>
            <text x="314" y="43" font-size="11" font-weight="700" fill="#0B1F3A">${escapeHtml(state.selectedTrip ? state.selectedTrip.destination : 'Destination')}</text>
          </svg>
        </div>
        ${!state.online || state.offlineSession ? `<div class="offline-note" role="status">${state.online ? 'Read-only Journey Pack' : 'Offline Journey Pack'} · this screen shows your saved trip itinerary only. Live vehicle location is unavailable.</div>` : ''}
        <div class="card track-panel">
          <div style="display:flex;justify-content:space-between;gap:10px">
            <div><div style="font-size:12px;color:var(--muted)">Estimated Arrival</div><strong style="font-size:20px;color:var(--navy)">${state.selectedTrip ? fmtTime(state.selectedTrip.arrival) : '—'}</strong></div>
            <div style="text-align:right"><div style="font-size:12px;color:var(--muted)">Current Location</div><strong>${escapeHtml(label)}</strong></div>
          </div>
          <div class="progress-dots">${steps.map((s,i)=>`<div class="step ${i<activeIdx?'done':''} ${i===activeIdx?'active':''}">${s}</div>`).join('')}</div>
          <div style="margin-top:12px;display:flex;gap:8px">
            <select id="track-trip" style="flex:1;min-height:42px;border:1px solid var(--line);border-radius:10px;padding:8px"></select>
            <button class="btn btn-outline" id="btn-refresh-track" ${!state.online || state.offlineSession ? 'disabled' : ''}>Refresh</button>
          </div>
        </div>
      </main>${bottomNav('live')}`;
  }

  function viewExplore() {
    return `${statusBar()}${topbar('Explore')}
      <main class="page">
        <div class="explore-intro"><span class="eyebrow">FIND YOUR NEXT STOP</span><h1>Explore Uganda</h1><p>Discover routes and places worth the ride.</p></div>
        <label class="field explore-search"><span class="visually-hidden">Search cities or routes</span><input id="explore-q" type="search" placeholder="⌕  Search a city or route"/></label>
        <div class="dest-scroll" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;overflow:visible" id="explore-grid"></div>
        <p class="empty hidden" id="explore-empty">No routes match your search yet.</p>
        <div class="card" style="margin-top:16px;background:linear-gradient(120deg,var(--navy),var(--navy-soft));color:#fff">
          <h3>More routes are on the way</h3>
          <p style="opacity:.85;margin:8px 0 0">Routes appear here as local operators publish scheduled journeys.</p>
        </div>
      </main>${bottomNav('explore')}`;
  }

  function viewMore() {
    const u = state.user;
    return `${statusBar()}${topbar('More')}
      <main class="page">
        <div class="card" style="margin-bottom:12px">
          <div style="display:flex;gap:12px;align-items:center">
            <div class="avatar">${initials(u ? u.name : 'G')}</div>
            <div><strong>${u ? escapeHtml(u.name) : 'Guest'}</strong><div style="color:var(--muted);font-size:13px">${u ? escapeHtml(u.phone) + ' · ' + u.role : 'Not signed in'}</div>${state.offlineSession ? '<div class="chip">Offline read-only</div>' : ''}</div>
          </div>
        </div>
        <div class="card search-card">
          <button class="btn btn-outline btn-block" id="btn-open-tour">Guided tour</button>
          <button class="btn btn-outline btn-block" id="btn-help-page">Help & demo tips</button>
          <a class="btn btn-outline btn-block" href="/screens/">Browse screen previews</a>
          <button class="btn btn-outline btn-block" id="btn-lang">${TuraI18n.getLang()==='en' ? 'Switch to Luganda' : 'Switch to English'}</button>
          ${u && (u.role==='operator'||u.role==='admin') ? '<button class="btn btn-primary btn-block" id="btn-ops">Operator dashboard</button>' : ''}
          ${u && (u.role==='driver'||u.role==='admin') ? '<button class="btn btn-primary btn-block" id="btn-driver">Driver console</button>' : ''}
          ${u ? '<button class="btn btn-danger btn-block" id="btn-logout">'+t('logout')+'</button>' : '<button class="btn btn-primary btn-block" id="btn-login">'+t('login')+'</button>' + (demoEnabled() ? '<button class="btn btn-accent btn-block" id="btn-demo2">'+t('demoMode')+'</button>' : '')}
        </div>
        <div class="sos-banner">Driver SOS is an internal <strong>Demo/Local</strong> alert only. It does not contact emergency services.</div>
      </main>${bottomNav('more')}`;
  }

  function viewOps() {
    const k = (state.ops && state.ops.kpis) || {};
    const chart = (state.ops && state.ops.revenue_chart) || [];
    const max = Math.max(1, ...chart.map((c) => c.revenue));
    const bars = chart.map((c) => {
      const h = Math.max(4, Math.round(80 * c.revenue / max));
      return `<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">
        <div style="height:80px;width:100%;display:flex;align-items:flex-end"><div style="width:100%;height:${h}px;background:linear-gradient(180deg,var(--accent),var(--navy));border-radius:6px 6px 2px 2px" title="${money(c.revenue)}"></div></div>
        <span style="font-size:10px;color:var(--muted)">${c.date.slice(5)}</span></div>`;
    }).join('');
    const audit = ((state.ops && state.ops.audit) || []).map((e) =>
      `<li><span><strong>${escapeHtml(e.event_type)}</strong> · ${escapeHtml(e.entity_type)} #${escapeHtml(e.entity_id)}</span><span style="color:var(--muted)">${new Date(e.timestamp).toLocaleString()}</span></li>`
    ).join('');
    const liveTrips = (state.opsLive && state.opsLive.trips || []).map((trip) =>
      `<article class="ops-trip">
        <div><strong>${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)}</strong><span class="chip">${escapeHtml(trip.status)}</span></div>
        <p>${escapeHtml(trip.operator)} · ${escapeHtml(trip.plate)} · ${fmtDate(trip.departure)} ${fmtTime(trip.departure)}</p>
        <p>${trip.position ? `${escapeHtml(trip.position.label)} · ${Number(trip.position.progress_pct).toFixed(0)}%` : 'Waiting for a tracking update'}</p>
        <button class="btn btn-outline" data-replay="${trip.id}">Replay trip</button>
      </article>`
    ).join('') || '<p class="empty">No active trips are scheduled.</p>';
    const incidents = (state.opsLive && state.opsLive.incidents || []).map((incident) =>
      `<article class="ops-incident">
        <div><strong>${escapeHtml(incident.reason)}</strong><span class="chip">${escapeHtml(incident.status)}</span></div>
        <p>${escapeHtml(incident.location || 'Location not provided')} · ${incident.trip_id ? `Trip #${incident.trip_id}` : 'No trip linked'} · ${fmtDate(incident.created_at)} ${fmtTime(incident.created_at)}</p>
        <small>${escapeHtml(incident.demo_note || 'Demo/Local alert')}</small>
        ${incident.status === 'open' ? `<button class="btn btn-outline" data-ack-incident="${incident.id}">Acknowledge</button>` : ''}
      </article>`
    ).join('') || '<p class="empty">No incidents recorded.</p>';
    const buses = (state.opsSetup.buses || []).map((bus) =>
      `<option value="${bus.id}">${escapeHtml(bus.operator)} · ${escapeHtml(bus.plate)} (${bus.capacity} seats)</option>`
    ).join('');
    const routes = (state.opsSetup.routes || []).map((route) =>
      `<option value="${route.id}">${escapeHtml(route.origin)} → ${escapeHtml(route.destination)}</option>`
    ).join('');
    const drivers = (state.opsSetup.drivers || []).map((driver) =>
      `<option value="${driver.id}">${escapeHtml(driver.name)}</option>`
    ).join('');
    const replay = state.replay;
    const point = replay && replay.points[replay.index];
    const replayView = replay ? `<section class="card replay-card" aria-label="Trip replay">
      <div class="section-title"><span>Trip replay · ${escapeHtml(replay.trip.origin)} → ${escapeHtml(replay.trip.destination)}</span><button class="btn btn-outline" id="btn-close-replay">Close</button></div>
      ${replay.points.length ? `<p class="replay-point" aria-live="polite">${escapeHtml(point.label)} · ${Number(point.progress_pct).toFixed(0)}% · ${fmtTime(point.timestamp)}</p>
        <input id="replay-range" type="range" min="0" max="${replay.points.length - 1}" value="${replay.index}" aria-label="Replay progress"/>
        <div class="replay-controls"><button class="btn btn-outline" id="btn-replay-prev" ${replay.index <= 0 ? 'disabled' : ''}>Previous</button><button class="btn btn-primary" id="btn-replay-play">${replay.timer ? 'Pause' : 'Play'}</button><button class="btn btn-outline" id="btn-replay-next" ${replay.index >= replay.points.length - 1 ? 'disabled' : ''}>Next</button></div>`
        : '<p class="empty">This trip has no tracking history yet. Use the assigned driver console to advance the demo tracker.</p>'}
    </section>` : '';
    const diagnostics = state.opsDiagnostics || {};
    return `${statusBar()}${topbar('Operator')}
      <main class="page page-wide">
        <div class="kpi-grid">
          <div class="kpi"><div class="label">Revenue today</div><div class="value">${money(k.revenue_today)}</div></div>
          <div class="kpi"><div class="label">Bookings today</div><div class="value">${k.bookings_today||0}</div></div>
          <div class="kpi"><div class="label">Valid tickets</div><div class="value">${k.tickets_valid||0}</div></div>
          <div class="kpi"><div class="label">Active trips</div><div class="value">${k.active_trips||0}</div></div>
        </div>
        <div class="chart-box"><h3 style="margin-bottom:12px;color:var(--navy)">7-day revenue</h3><div class="revenue-bars" role="img" aria-label="Revenue for the last seven days">${bars}</div></div>
        <div class="ops-grid">
          <section class="card">
            <div class="section-title"><span>Live trips</span><div class="ops-actions"><span class="chip">${state.online && state.wsLive ? 'Live' : 'Cached / reconnecting'}</span><button class="btn btn-outline" id="btn-refresh-ops">Refresh</button></div></div>
            <div class="ops-list">${liveTrips}</div>
          </section>
          <section class="card">
            <div class="section-title"><span>Incident feed</span><span class="chip">Demo/Local alerts</span></div>
            <div class="ops-list">${incidents}</div>
          </section>
        </div>
        ${replayView}
        <details class="card ops-setup" open>
          <summary>Fleet and schedule setup</summary>
          <div class="ops-grid">
            <form id="bus-form" class="ops-form">
              <h3>Add a bus</h3>
              <label class="field">Operator<input name="operator" required minlength="2" maxlength="80"/></label>
              <label class="field">Plate<input name="plate" required minlength="3" maxlength="32"/></label>
              <label class="field">Seats<input name="capacity" type="number" min="4" max="80" value="40" required/></label>
              <label class="field">Amenities (comma separated)<input name="amenities" placeholder="wifi,ac,power"/></label>
              <button class="btn btn-primary" type="submit">Save bus</button>
            </form>
            <form id="route-form" class="ops-form">
              <h3>Add a route</h3>
              <label class="field">Origin<input name="origin" required minlength="2" maxlength="80"/></label>
              <label class="field">Destination<input name="destination" required minlength="2" maxlength="80"/></label>
              <label class="field">Stops (comma separated)<input name="stops" placeholder="Town A, Town B"/></label>
              <div class="field-row">
                <label class="field">Distance km<input name="distance_km" type="number" min="1" max="3000" required/></label>
                <label class="field">Duration minutes<input name="duration_minutes" type="number" min="1" max="2880" required/></label>
              </div>
              <div class="field-row">
                <label class="field">Base fare UGX<input name="base_fare_ugx" type="number" min="1" required/></label>
                <label class="field">Image category<input name="image_slug" value="default" maxlength="40" required/></label>
              </div>
              <button class="btn btn-primary" type="submit">Save route</button>
            </form>
            <form id="trip-form" class="ops-form">
              <h3>Publish a trip</h3>
              <label class="field">Bus<select name="bus_id" required>${buses || '<option value="">Add a bus first</option>'}</select></label>
              <label class="field">Route<select name="route_id" required>${routes || '<option value="">Add a route first</option>'}</select></label>
              <label class="field">Driver<select name="driver_id"><option value="">Unassigned</option>${drivers}</select></label>
              <div class="field-row">
                <label class="field">Departure (local time)<input name="departure" type="datetime-local" required/></label>
                <label class="field">Arrival (local time)<input name="arrival" type="datetime-local" required/></label>
              </div>
              <label class="field">Fare override (optional)<input name="fare_ugx" type="number" min="1"/></label>
              <button class="btn btn-primary" type="submit" ${!buses || !routes ? 'disabled' : ''}>Publish trip</button>
            </form>
            ${state.user && state.user.role === 'admin' ? `<form id="staff-form" class="ops-form">
              <h3>Create operator or driver</h3>
              <label class="field">Full name<input name="name" required minlength="2" maxlength="120"/></label>
              <label class="field">Phone<input name="phone" required minlength="9" maxlength="32"/></label>
              <label class="field">Temporary password<input name="password" type="password" required minlength="12" maxlength="72" autocomplete="new-password"/></label>
              <label class="field">Role<select name="role"><option value="driver">Driver</option><option value="operator">Operator</option></select></label>
              <button class="btn btn-primary" type="submit">Create staff account</button>
            </form>` : ''}
          </div>
          <p class="form-note">Trip times are entered in your local timezone and stored as UTC. The tracker is a demo simulator, not vehicle GPS.</p>
        </details>
        ${state.opsLoadError ? `<div class="offline-note" role="alert">Dashboard data is stale: ${escapeHtml(state.opsLoadError)}. Use Refresh to retry.</div>` : ''}
        <div class="section-title"><span>Audit log</span><div class="ops-actions">
          <button class="btn btn-outline" id="btn-settlements">Prepare mock settlements</button>
          <button class="btn btn-outline" id="btn-backup">Backup DB</button>
          <button class="btn btn-outline" id="btn-download-backup">Download backup</button>
        </div></div>
        <div class="card"><ul class="audit-list">${audit || '<li>No events yet</li>'}</ul></div>
        <div class="system-status"><span>Database: ${escapeHtml(diagnostics.database || 'unknown')}</span><span>WebSocket clients: ${Number(diagnostics.websocket_connections || 0)}</span><span>Last refresh: ${state.opsLive ? fmtTime(state.opsLive.updated_at) : '—'}</span></div>
        <div style="margin-top:12px"><button class="btn btn-outline btn-block" id="btn-back-more">Back</button></div>
      </main>`;
  }

  function viewDriver() {
    return `${statusBar()}${topbar('Driver')}
      <main class="page">
        <div class="card search-card">
          <h3 style="color:var(--navy)">Validate QR ticket</h3>
          <div class="offline-note">Online validation checks current use and revocation status. A saved ticket image may be displayed offline, but it cannot be securely validated offline.</div>
          <div class="field"><label>Paste signed token or ticket payload</label><textarea id="val-token" rows="3" placeholder="Paste QR token…"></textarea></div>
          <button class="btn btn-primary btn-block" id="btn-validate" ${!state.online ? 'disabled' : ''}>Validate online</button>
          <div id="val-result" style="margin-top:10px"></div>
        </div>
        <div class="card search-card" style="margin-top:12px">
          <h3 style="color:var(--navy)">Trip controls</h3>
          ${!state.online ? '<div class="offline-note">Driver actions need a live connection.</div>' : ''}
          <div class="field"><label>Assigned trip</label><select id="drv-trip" ${!state.online ? 'disabled' : ''}>${state.driverTrips.map((trip) => `<option value="${trip.id}">${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)} · ${fmtDate(trip.departure)} ${fmtTime(trip.departure)}</option>`).join('') || '<option value="">No active assigned trips</option>'}</select></div>
          <button class="btn btn-accent btn-block" id="btn-advance" ${!state.online ? 'disabled' : ''}>Advance tracking</button>
          <button class="btn btn-outline btn-block" id="btn-passengers" ${!state.online ? 'disabled' : ''}>Passenger list</button>
          <div id="drv-passengers"></div>
        </div>
        <div class="card search-card" style="margin-top:12px">
          <h3 style="color:var(--navy)">Luggage scan</h3>
          <div class="field-row">
            <div class="field"><label>Tag ID</label><input id="lug-tag" placeholder="LUG-…"/></div>
            <div class="field"><label>Status</label>
              <select id="lug-status"><option>loaded</option><option>received</option><option>claimed</option><option>lost</option></select>
            </div>
          </div>
          <button class="btn btn-outline btn-block" id="btn-lug" ${!state.online ? 'disabled' : ''}>Scan luggage</button>
        </div>
        <div class="card search-card" style="margin-top:12px">
          <h3 style="color:var(--navy)">SOS (Demo/Local)</h3>
          <div class="sos-banner">Does NOT contact police. Creates an internal TURA alert only.</div>
          <div class="field"><label>Reason</label><input id="sos-reason" placeholder="Medical / security / breakdown"/></div>
          <button class="btn btn-danger btn-block" id="btn-sos" ${!state.online ? 'disabled' : ''}>Send Demo SOS</button>
        </div>
        <button class="btn btn-outline btn-block" id="btn-back-more2" style="margin-top:12px">Back</button>
      </main>`;
  }

  function viewHelp() {
    return `${statusBar()}${topbar('Help')}
      <main class="page">
        <div class="card">
          <h3 style="color:var(--navy);margin-bottom:8px">How to use TURA</h3>
          <ol style="margin:0;padding-left:18px;color:var(--muted);line-height:1.6">
            <li>Demo login as Customer → search Kampala → Gulu → select seat → pay (mock).</li>
            <li>Open My Tickets to see the signed QR. Save it and its itinerary for offline display.</li>
            <li>Demo login as Driver → select an assigned trip, paste a ticket token, and validate online. Advance the demo tracker to push live map updates.</li>
            <li>Demo login as Operator → manage fleet/routes/trips, watch the wallboard and incident feed, replay a trip, and create/download a database backup.</li>
            <li>The Offline Journey Pack is read-only. Seat reservations, payment, ticket validation, driver actions, and live location require a connection.</li>
          </ol>
          ${demoEnabled() ? `<p style="margin-top:14px"><strong>Demo accounts</strong><br>
          Customer +256700000001 / demo1234<br>
          Operator +256700000010 / ops1234<br>
          Driver +256700000020 / driver1234</p>` : ''}
          <button class="btn btn-primary btn-block" id="btn-restart-tour" style="margin-top:12px">Start interactive tour</button>
        </div>
      </main>${bottomNav('more')}`;
  }

  function authModal(mode) {
    if (mode === 'demo' && !demoEnabled()) {
      toast('Demo mode is disabled on this service', 'err');
      return;
    }
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    backdrop.innerHTML = `<div class="modal">
      <h3>${mode === 'demo' ? 'Demo Mode' : 'Sign in to TURA'}</h3>
      ${mode === 'demo' ? `
        <p style="color:var(--muted);font-size:14px">Pick a role to explore the full journey.</p>
        <div class="demo-roles">
          <button class="btn btn-primary" data-demo="customer">Customer — Mike</button>
          <button class="btn btn-outline" data-demo="driver">Driver — Kato</button>
          <button class="btn btn-outline" data-demo="operator">Operator</button>
          <button class="btn btn-outline" data-demo="admin">Admin</button>
        </div>` : `
        <div class="field"><label>Phone</label><input id="login-phone" value="${demoEnabled() ? '+256700000001' : ''}" autocomplete="username"/></div>
        <div class="field" style="margin-top:8px"><label>Password</label><input id="login-pass" type="password" value="${demoEnabled() ? 'demo1234' : ''}" autocomplete="current-password"/></div>
        <button class="btn btn-primary btn-block" id="login-submit" style="margin-top:12px">Log in</button>
        ${demoEnabled() ? '<button class="btn btn-outline btn-block" id="login-demo" style="margin-top:8px">Use demo instead</button>' : ''}`}
      <button class="btn btn-ghost btn-block" id="auth-close" style="margin-top:8px;color:var(--muted)">Close</button>
    </div>`;
    document.body.appendChild(backdrop);
    $('#auth-close', backdrop).onclick = () => backdrop.remove();
    backdrop.querySelectorAll('[data-demo]').forEach((b) => b.onclick = async () => {
      try {
        const res = await api('/api/auth/demo-login', { method: 'POST', body: { role: b.dataset.demo } });
        state.user = res.user;
        state.offlineSession = false;
        state.tickets = [];
        state.bookings = [];
        state.trackingOptionsLoaded = false;
        state.trackingTripId = null;
        state.tracking = null;
        rememberOfflineUser(res.user);
        backdrop.remove();
        toast('Signed in as ' + res.user.name, 'ok');
        TuraWS.connect([]);
        setHash(res.user.role === 'operator' || res.user.role === 'admin' ? 'ops' : res.user.role === 'driver' ? 'driver' : 'home');
        TuraTour.start();
      } catch (e) { toast(e.message, 'err'); }
    });
    const submit = $('#login-submit', backdrop);
    if (submit) submit.onclick = async () => {
      try {
        const res = await api('/api/auth/login', { method: 'POST', body: { phone: $('#login-phone', backdrop).value, password: $('#login-pass', backdrop).value } });
        state.user = res.user;
        state.offlineSession = false;
        state.tickets = [];
        state.bookings = [];
        state.trackingOptionsLoaded = false;
        state.trackingTripId = null;
        state.tracking = null;
        rememberOfflineUser(res.user);
        backdrop.remove();
        TuraWS.connect([]);
        setHash('home');
      } catch (e) { toast(e.message, 'err'); }
    };
    const d = $('#login-demo', backdrop);
    if (d) d.onclick = () => { backdrop.remove(); authModal('demo'); };
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  /* ---------- Render + bind ---------- */
  async function render() {
    const { path, params } = parseHash();
    const previousRoute = state.route;
    state.route = path || 'splash';
    if (state.route === 'tracking' && previousRoute !== 'tracking') {
      state.trackingOptionsLoaded = false;
    }
    if ((state.route === 'ops' || state.route === 'driver') && !state.user) {
      setHash('splash');
      authModal('login');
      return;
    }
    if (state.route === 'ops' && !['operator', 'admin'].includes(state.user.role)) {
      toast('Operator access is required', 'err');
      setHash('more');
      return;
    }
    if (state.route === 'driver' && !['driver', 'operator', 'admin'].includes(state.user.role)) {
      toast('Driver access is required', 'err');
      setHash('more');
      return;
    }
    if (['seats', 'passenger', 'payment'].includes(state.route) && (
      !state.user
      || state.offlineSession
      || !state.online
      || state.tripCacheMode === 'cached'
      || !state.selectedTrip
      || (state.route !== 'seats' && !state.selectedSeat)
    )) {
      toast('Select a live trip and seat while online before checkout.', 'err');
      setHash('home');
      return;
    }
    let html = '';
    if (state.route === 'splash') html = viewSplash();
    else if (state.route === 'home') html = viewHome();
    else if (state.route === 'results') html = viewResults();
    else if (state.route === 'seats') html = viewSeats();
    else if (state.route === 'passenger') html = viewPassenger();
    else if (state.route === 'payment') html = viewPayment();
    else if (state.route === 'ticket') html = viewTicket();
    else if (state.route === 'tickets') html = viewTickets();
    else if (state.route === 'tracking') html = viewTracking();
    else if (state.route === 'explore') html = viewExplore();
    else if (state.route === 'more') html = viewMore();
    else if (state.route === 'ops') html = viewOps();
    else if (state.route === 'driver') html = viewDriver();
    else if (state.route === 'help') html = viewHelp();
    else html = viewHome();

    app.innerHTML = html;
    bindChrome();
    try {
      await bindView(state.route, params);
    } catch (e) {
      if (e.status === 401) {
        state.user = null;
        state.offlineSession = false;
        TuraWS.disconnect();
        try { localStorage.removeItem('tura_offline_user'); }
        catch (storageError) { toast('Could not clear local sign-in state: ' + storageError.message, 'err'); }
        toast('Your session has expired. Please sign in again.', 'err');
        setHash('splash');
        authModal('login');
      } else {
        if (!e.status) state.online = false;
        toast('This screen could not load: ' + e.message, 'err');
      }
    }
  }

  async function bindView(route) {
    if (route === 'splash') {
      const start = $('#btn-start');
      if (start) start.onclick = () => { if (state.user) setHash('home'); else authModal('login'); };
      const demo = $('#btn-demo');
      if (demo) demo.onclick = () => authModal('demo');
    }
    if (route === 'home') {
      if (!state.citiesLoaded) {
        let cities;
        if (state.online && !state.offlineSession) {
          try { cities = await api('/api/trips/cities'); }
          catch (e) {
            if (e.status && e.status < 500) throw e;
            if (!e.status) state.online = false;
            else toast('Loading saved routes after a server error: ' + e.message, 'err');
          }
        }
        if (!cities) {
          const cached = await TuraStore.get('meta', 'cities');
          cities = cached?.value || { origins: [], destinations: [] };
          if (!cached) toast('Route list unavailable offline. Open the app online to cache routes.', 'err');
        } else if (state.online && !state.offlineSession) {
          try { await TuraStore.put('meta', { key: 'cities', value: cities }); }
          catch (e) { toast('Routes loaded, but could not be saved for offline use: ' + e.message, 'err'); }
        }
        state.cities = cities;
        state.citiesLoaded = true;
        await render();
        return;
      }
      let pop;
      if (state.online && !state.offlineSession) {
        try { pop = await api('/api/trips/popular'); }
        catch (e) {
          if (e.status && e.status < 500) throw e;
          if (!e.status) state.online = false;
          else toast('Loading saved destinations after a server error: ' + e.message, 'err');
        }
      }
      if (!pop) {
        const cached = await TuraStore.get('meta', 'popular');
        if (cached) pop = cached.value;
        else {
          const trips = await TuraStore.getAll('trips');
          const uniqueRoutes = new Map();
          trips.forEach((trip) => {
            const key = `${trip.origin}|${trip.destination}`;
            if (!uniqueRoutes.has(key)) uniqueRoutes.set(key, {
              origin: trip.origin, destination: trip.destination,
              fare_ugx: trip.fare_ugx, image_slug: 'default',
            });
          });
          pop = { routes: [...uniqueRoutes.values()] };
        }
      } else if (state.online && !state.offlineSession) {
        try { await TuraStore.put('meta', { key: 'popular', value: pop }); }
        catch (e) { toast('Popular routes loaded, but could not be saved for offline use: ' + e.message, 'err'); }
      }
      const box = $('#popular-dests');
      if (box) {
        box.innerHTML = pop.routes.slice(0, 6).map((r) =>
          `<button class="dest-card ${escapeHtml(r.image_slug || 'default')}" data-dest="${escapeHtml(r.destination)}" data-origin="${escapeHtml(r.origin)}">
            <div class="bg"></div><div class="meta"><strong>${escapeHtml(r.destination)}</strong><span>from ${money(r.fare_ugx)}</span></div></button>`
        ).join('');
        box.querySelectorAll('[data-dest]').forEach((el) => el.onclick = () => {
          state.search.origin = el.dataset.origin;
          state.search.destination = el.dataset.dest;
          doSearch();
        });
      }
      $('#btn-search').onclick = () => {
        state.search.origin = $('#f-origin').value;
        state.search.destination = $('#f-dest').value;
        state.search.date = $('#f-date').value;
        state.search.passengers = Number($('#f-pax').value || 1);
        doSearch();
      };
    }
    if (route === 'results') {
      document.querySelectorAll('[data-select-trip]').forEach((b) => b.onclick = () => openSeats(Number(b.dataset.selectTrip)));
      const strip = $('#date-strip');
      if (strip) {
        const base = state.search.date ? new Date(`${state.search.date}T12:00:00`) : new Date();
        const today = localDateISO(new Date());
        strip.innerHTML = Array.from({ length: 7 }, (_, i) => {
          const d = new Date(base); d.setDate(base.getDate() + i);
          const iso = localDateISO(d);
          const active = iso === (state.search.date || today);
          return `<button class="date-pill ${active?'active':''}" data-date="${iso}"><strong>${d.getDate()}</strong>${d.toLocaleDateString([], { weekday: 'short' })}</button>`;
        }).join('');
        strip.querySelectorAll('[data-date]').forEach((el) => el.onclick = () => { state.search.date = el.dataset.date; doSearch(); });
      }
    }
    if (route === 'seats') {
      document.querySelectorAll('[data-seat]').forEach((b) => b.onclick = () => lockSeat(Number(b.dataset.seat)));
      const next = $('#btn-seat-next');
      if (next) next.onclick = () => {
        if (!state.user) return authModal('demo');
        state.passenger.name = state.user.name;
        state.passenger.phone = state.user.phone;
        setHash('passenger');
      };
    }
    if (route === 'passenger') {
      const refresh = () => {
        state.passenger = {
          name: $('#p-name').value,
          phone: $('#p-phone').value,
          email: $('#p-email').value,
          special: $('#p-special').value,
          insurance: $('#p-ins').checked,
          luggage: $('#p-lug').checked,
        };
      };
      ['p-ins','p-lug'].forEach((id) => { const el = $('#'+id); if (el) el.onchange = () => { refresh(); render(); }; });
      $('#btn-pass-next').onclick = () => {
        if (!$('#p-name').reportValidity() || !$('#p-phone').reportValidity() || !$('#p-email').reportValidity()) return;
        refresh();
        setHash('payment');
      };
    }
    if (route === 'payment') {
      document.querySelectorAll('[data-pay]').forEach((el) => el.onclick = () => { state.payMethod = el.dataset.pay; render(); });
      $('#btn-pay').onclick = () => payFlow();
    }
    if (route === 'ticket') {
      if (state.lastTicket && state.online && !state.lastTicket.qr_data_url && !state.offlineSession) {
        try {
          const saved = await cacheTicket(state.lastTicket, true);
          if (saved.qr_data_url) {
            state.lastTicket = saved;
            await render();
            return;
          }
        } catch (e) { toast('Could not save the QR image for offline use: ' + e.message, 'err'); }
      }
      const save = $('#btn-save-ticket');
      if (save) save.onclick = async () => {
        if (state.lastTicket) {
          try {
            state.lastTicket = await cacheTicket(state.lastTicket, true);
            const complete = state.lastTicket.cached_offline && state.lastTicket.qr_data_url;
            toast(complete ? 'Ticket and QR saved offline' : 'Ticket details saved; QR or local storage needs attention', complete ? 'ok' : 'err');
            render();
          } catch (e) { toast('Could not save ticket: ' + e.message, 'err'); }
        }
      };
      const share = $('#btn-share-ticket');
      if (share) share.onclick = async () => {
        const text = `TURA ticket ${state.lastTicket.ticket_no} · ${state.lastTicket.route} · Seat ${state.lastTicket.seat}`;
        try {
          if (navigator.share) await navigator.share({ title: 'TURA Ticket', text });
          else if (navigator.clipboard) { await navigator.clipboard.writeText(text); toast('Copied ticket summary', 'ok'); }
          else toast('Sharing is not available in this browser', 'err');
        } catch (e) { if (e.name !== 'AbortError') toast('Could not share ticket: ' + e.message, 'err'); }
      };
    }
    if (route === 'tickets') {
      if (state.user) {
        if (state.online && !state.offlineSession) {
          try {
            const res = await api('/api/tickets/mine');
            state.tickets = res.tickets || [];
            state.ticketCacheMode = 'live';
            await Promise.all(state.tickets.map((tk) => cacheTicket(tk, false)));
          } catch (e) {
              if (e.status && e.status < 500) throw e;
              if (!e.status) state.online = false;
              else toast('Ticket service is unavailable; showing saved tickets: ' + e.message, 'err');
              state.tickets = await TuraStore.getAll('tickets', state.user.id);
              state.ticketCacheMode = 'cached';
            if (!state.tickets.length) toast('No saved tickets are available on this device', 'err');
          }
        } else {
          state.tickets = await TuraStore.getAll('tickets', state.user.id);
          state.ticketCacheMode = 'cached';
        }
      }
      document.querySelectorAll('[data-ttab]').forEach((b) => b.onclick = () => { state.ticketTab = b.dataset.ttab; render(); });
      document.querySelectorAll('[data-view-ticket]').forEach((b) => b.onclick = () => {
        state.lastTicket = state.tickets.find((t) => t.id === Number(b.dataset.viewTicket));
        state.ticketCacheMode = state.lastTicket && state.lastTicket.owner_id ? 'cached' : 'live';
        setHash('ticket');
      });
      // re-render list if first load emptied
      if (state.user && !document.querySelector('.trip-card') && state.tickets.length) render();
    }
    if (route === 'tracking') {
      await loadTrackingOptions();
      const btn = $('#btn-refresh-track');
      if (btn) btn.onclick = () => loadTracking(state.trackingTripId);
      const sel = $('#track-trip');
      if (sel) sel.onchange = () => loadTracking(Number(sel.value));
    }
    if (route === 'explore') {
      let pop;
      if (state.online && !state.offlineSession) {
        try { pop = await api('/api/trips/popular'); }
        catch (e) {
          if (e.status && e.status < 500) throw e;
          if (!e.status) state.online = false;
          else toast('Loading saved destinations after a server error: ' + e.message, 'err');
        }
      }
      if (!pop) {
        const cached = await TuraStore.get('meta', 'popular');
        if (cached) pop = cached.value;
        else {
          const cachedTrips = await TuraStore.getAll('trips');
          const routes = new Map();
          cachedTrips.forEach((trip) => {
            const key = `${trip.origin}|${trip.destination}`;
            if (!routes.has(key)) routes.set(key, {
              origin: trip.origin, destination: trip.destination,
              fare_ugx: trip.fare_ugx, image_slug: 'default',
            });
          });
          pop = { routes: [...routes.values()] };
        }
        if (!pop.routes.length) toast('No saved destinations are available offline', 'err');
      } else if (state.online && !state.offlineSession) {
        try { await TuraStore.put('meta', { key: 'popular', value: pop }); }
        catch (e) { toast('Popular routes loaded, but could not be saved for offline use: ' + e.message, 'err'); }
      }
      const grid = $('#explore-grid');
      if (grid) {
        grid.innerHTML = pop.routes.map((r) =>
          `<button class="dest-card ${escapeHtml(r.image_slug || 'default')}" style="min-width:0;width:100%" data-origin="${escapeHtml(r.origin)}" data-dest="${escapeHtml(r.destination)}">
            <div class="bg"></div><div class="meta"><strong>${escapeHtml(r.origin)} → ${escapeHtml(r.destination)}</strong><span>${money(r.fare_ugx)}</span></div></button>`
        ).join('');
        grid.querySelectorAll('button').forEach((el) => el.onclick = () => {
          state.search.origin = el.dataset.origin;
          state.search.destination = el.dataset.dest;
          doSearch();
        });
      }
      const query = $('#explore-q');
      if (query && grid) query.oninput = () => {
        const value = query.value.trim().toLocaleLowerCase();
        let visible = 0;
        grid.querySelectorAll('button').forEach((el) => {
          const matches = `${el.dataset.origin} ${el.dataset.dest}`.toLocaleLowerCase().includes(value);
          el.classList.toggle('hidden', !matches);
          if (matches) visible += 1;
        });
        const empty = $('#explore-empty');
        if (empty) empty.classList.toggle('hidden', visible > 0);
      };
    }
    if (route === 'more') {
      const tour = $('#btn-open-tour'); if (tour) tour.onclick = () => TuraTour.openHelp();
      const help = $('#btn-help-page'); if (help) help.onclick = () => setHash('help');
      const lang = $('#btn-lang'); if (lang) lang.onclick = () => { TuraI18n.setLang(TuraI18n.getLang()==='en'?'lg':'en'); render(); };
      const ops = $('#btn-ops'); if (ops) ops.onclick = () => setHash('ops');
      const drv = $('#btn-driver'); if (drv) drv.onclick = () => setHash('driver');
      const lo = $('#btn-logout'); if (lo) lo.onclick = async () => {
        try {
          if (!state.online || state.offlineSession) {
            localStorage.setItem('tura_logout_pending', '1');
            localStorage.removeItem('tura_offline_user');
          } else {
            await api('/api/auth/logout', { method: 'POST' });
            localStorage.removeItem('tura_logout_pending');
            localStorage.removeItem('tura_offline_user');
            state.trackingOptionsLoaded = false;
            state.trackingTripId = null;
            state.tracking = null;
          }
          try { await TuraStore.clearStore('tickets'); }
          catch (storageError) { toast('Could not clear saved tickets on this device: ' + storageError.message, 'err'); }
          TuraWS.disconnect();
          state.user = null;
          state.offlineSession = false;
          state.tickets = [];
          state.bookings = [];
          setHash('splash');
        } catch (e) { toast('Could not finish logout: ' + e.message, 'err'); }
      };
      const li = $('#btn-login'); if (li) li.onclick = () => authModal('login');
      const d2 = $('#btn-demo2'); if (d2) d2.onclick = () => authModal('demo');
    }
    if (route === 'ops') {
      TuraWS.subscribe('ops');
      if (!state._opsLoaded) {
        try {
          await loadOpsData();
          state.opsLoadError = '';
        } catch (e) {
          if (!e.status) state.online = false;
          state.opsLoadError = e.message;
          toast('Operator dashboard could not refresh: ' + e.message, 'err');
        }
        state._opsLoaded = true;
        await render();
        return;
      }
      const refresh = $('#btn-refresh-ops');
      if (refresh) refresh.onclick = () => { state._opsLoaded = false; render(); };
      const bak = $('#btn-backup');
      if (bak) bak.onclick = async () => {
        try { const r = await api('/api/reports/backup', { method: 'POST' }); toast(`Backup created: ${r.name} (${Number(r.size_bytes).toLocaleString()} bytes)`, 'ok'); }
        catch (e) { toast(e.message, 'err'); }
      };
      const downloadBackup = $('#btn-download-backup');
      if (downloadBackup) downloadBackup.onclick = async () => {
        try {
          const backup = await api('/api/reports/backup/download');
          const url = URL.createObjectURL(backup);
          const link = document.createElement('a');
          link.href = url;
          link.download = 'tura-backup.db';
          link.click();
          URL.revokeObjectURL(url);
        } catch (e) { toast('Backup download failed: ' + e.message, 'err'); }
      };
      const settlements = $('#btn-settlements');
      if (settlements) settlements.onclick = async () => {
        try {
          const result = await api('/api/reports/settlements/run', { method: 'POST' });
          toast(`Prepared ${result.created_for_trips.length} mock settlements`, 'ok');
          state._opsLoaded = false;
          render();
        } catch (e) { toast(e.message, 'err'); }
      };
      document.querySelectorAll('[data-ack-incident]').forEach((button) => {
        button.onclick = async () => {
          try {
            await api(`/api/sos/${button.dataset.ackIncident}/acknowledge`, { method: 'POST' });
            state._opsLoaded = false;
            await render();
          } catch (e) { toast(e.message, 'err'); }
        };
      });
      document.querySelectorAll('[data-replay]').forEach((button) => {
        button.onclick = async () => {
          try {
            const id = Number(button.dataset.replay);
            const result = await api(`/api/operations/trips/${id}/replay`);
            if (state.replay && state.replay.timer) clearInterval(state.replay.timer);
            state.replay = { trip: result.trip, points: result.points || [], index: 0, timer: null };
            render();
          } catch (e) { toast(e.message, 'err'); }
        };
      });
      const closeReplay = $('#btn-close-replay');
      if (closeReplay) closeReplay.onclick = () => {
        if (state.replay && state.replay.timer) clearInterval(state.replay.timer);
        state.replay = null;
        render();
      };
      const replayRange = $('#replay-range');
      if (replayRange) replayRange.oninput = () => {
        state.replay.index = Number(replayRange.value);
        render();
      };
      const replayPrev = $('#btn-replay-prev');
      if (replayPrev) replayPrev.onclick = () => {
        state.replay.index = Math.max(0, state.replay.index - 1);
        render();
      };
      const replayNext = $('#btn-replay-next');
      if (replayNext) replayNext.onclick = () => {
        state.replay.index = Math.min(state.replay.points.length - 1, state.replay.index + 1);
        render();
      };
      const replayPlay = $('#btn-replay-play');
      if (replayPlay) replayPlay.onclick = () => {
        if (state.replay.timer) {
          clearInterval(state.replay.timer);
          state.replay.timer = null;
        } else if (state.replay.points.length > 1) {
          if (state.replay.index >= state.replay.points.length - 1) state.replay.index = 0;
          state.replay.timer = setInterval(() => {
            if (state.replay.index >= state.replay.points.length - 1) {
              clearInterval(state.replay.timer);
              state.replay.timer = null;
            } else {
              state.replay.index += 1;
            }
            render();
          }, 1000);
        }
        render();
      };
      const busForm = $('#bus-form');
      if (busForm) busForm.onsubmit = async (event) => {
        event.preventDefault();
        const values = new FormData(busForm);
        try {
          await api('/api/operations/buses', { method: 'POST', body: {
            operator: values.get('operator'), plate: values.get('plate'),
            capacity: Number(values.get('capacity')),
            amenities: String(values.get('amenities') || '').split(',').map((x) => x.trim()).filter(Boolean),
          } });
          toast('Bus and seats saved', 'ok');
          busForm.reset();
          state._opsLoaded = false;
          await render();
        } catch (e) { toast(e.message, 'err'); }
      };
      const routeForm = $('#route-form');
      if (routeForm) routeForm.onsubmit = async (event) => {
        event.preventDefault();
        const values = new FormData(routeForm);
        try {
          await api('/api/operations/routes', { method: 'POST', body: {
            origin: values.get('origin'), destination: values.get('destination'),
            stops: String(values.get('stops') || '').split(',').map((x) => x.trim()).filter(Boolean),
            distance_km: Number(values.get('distance_km')),
            duration_minutes: Number(values.get('duration_minutes')),
            base_fare_ugx: Number(values.get('base_fare_ugx')),
            image_slug: values.get('image_slug'),
          } });
          toast('Route saved', 'ok');
          routeForm.reset();
          state._opsLoaded = false;
          await render();
        } catch (e) { toast(e.message, 'err'); }
      };
      const tripForm = $('#trip-form');
      if (tripForm) tripForm.onsubmit = async (event) => {
        event.preventDefault();
        const values = new FormData(tripForm);
        try {
          await api('/api/operations/trips', { method: 'POST', body: {
            bus_id: Number(values.get('bus_id')),
            route_id: Number(values.get('route_id')),
            driver_id: values.get('driver_id') ? Number(values.get('driver_id')) : null,
            departure: new Date(values.get('departure')).toISOString(),
            arrival: new Date(values.get('arrival')).toISOString(),
            fare_ugx: values.get('fare_ugx') ? Number(values.get('fare_ugx')) : null,
          } });
          toast('Trip published', 'ok');
          tripForm.reset();
          state._opsLoaded = false;
          await render();
        } catch (e) { toast(e.message, 'err'); }
      };
      const staffForm = $('#staff-form');
      if (staffForm) staffForm.onsubmit = async (event) => {
        event.preventDefault();
        const values = new FormData(staffForm);
        try {
          await api('/api/operations/staff', { method: 'POST', body: {
            name: values.get('name'), phone: values.get('phone'),
            password: values.get('password'), role: values.get('role'),
          } });
          toast('Staff account created', 'ok');
          staffForm.reset();
          state._opsLoaded = false;
          await render();
        } catch (e) { toast(e.message, 'err'); }
      };
      const back = $('#btn-back-more'); if (back) back.onclick = () => setHash('more');
    }
    if (route === 'driver') {
      try {
        const result = await api('/api/operations/my-trips');
        state.driverTrips = result.trips || [];
        const tripSelect = $('#drv-trip');
        if (tripSelect) {
          tripSelect.innerHTML = state.driverTrips.map((trip) =>
            `<option value="${trip.id}">${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)} · ${fmtDate(trip.departure)} ${fmtTime(trip.departure)}</option>`
          ).join('') || '<option value="">No active assigned trips</option>';
          tripSelect.value = String(state.driverTrips[0]?.id || '');
        }
      } catch (e) {
        if (!e.status) state.online = false;
        toast('Assigned trips could not be loaded: ' + e.message, 'err');
      }
      $('#btn-validate').onclick = async () => {
        try {
          const r = await api('/api/tickets/validate', {
            method: 'POST',
            body: { token: $('#val-token').value.trim() },
          });
          const valid = r.valid === true;
          const resultStyle = valid
            ? 'background:var(--success-soft);color:var(--success);border-color:#b6e6cd'
            : 'background:var(--danger-soft);color:var(--danger);border-color:#f2b9b9';
          $('#val-result').innerHTML = `<div class="sos-banner" role="${valid ? 'status' : 'alert'}" style="${resultStyle}">${escapeHtml(r.message)} ${r.ticket_no ? '· ' + escapeHtml(r.ticket_no) : ''} ${r.seat ? '· Seat ' + escapeHtml(r.seat) : ''}</div>`;
        } catch (e) {
          $('#val-result').innerHTML = `<div class="sos-banner">${escapeHtml(e.message)}</div>`;
        }
      };
      $('#btn-advance').onclick = async () => {
        try {
          const id = Number($('#drv-trip').value);
          const r = await api(`/api/trips/${id}/tracking/advance`, { method: 'POST' });
          toast(`Tracking @ ${r.label} (${r.progress_pct}%)`, 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      $('#btn-passengers').onclick = async () => {
        try {
          const id = Number($('#drv-trip').value);
          const r = await api(`/api/trips/${id}/passengers`);
          $('#drv-passengers').innerHTML = (r.passengers || []).map((p) =>
            `<div style="padding:8px 0;border-bottom:1px solid var(--line)">${escapeHtml(p.name)} · Seat ${escapeHtml(p.seat)} · ${escapeHtml(p.ticket_status || '')}</div>`
          ).join('') || '<div class="empty">No passengers</div>';
        } catch (e) { toast(e.message, 'err'); }
      };
      $('#btn-lug').onclick = async () => {
        try {
          await api('/api/luggage/scan', { method: 'POST', body: { tag_id: $('#lug-tag').value, status: $('#lug-status').value } });
          toast('Luggage updated', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      $('#btn-sos').onclick = async () => {
        try {
          const r = await api('/api/sos', { method: 'POST', body: { reason: $('#sos-reason').value || 'Demo alert', trip_id: Number($('#drv-trip').value) || null, location: 'Coach cabin' } });
          toast(r.notice || 'SOS sent', 'ok');
        } catch (e) { toast(e.message, 'err'); }
      };
      const back = $('#btn-back-more2'); if (back) back.onclick = () => setHash('more');
    }
    if (route === 'help') {
      const b = $('#btn-restart-tour'); if (b) b.onclick = () => TuraTour.openHelp();
    }
  }

  async function doSearch() {
    let res;
    try {
      const q = new URLSearchParams({ origin: state.search.origin, destination: state.search.destination, sort: 'price' });
      if (state.search.date) q.set('date', state.search.date);
      res = await api('/api/trips/search?' + q);
    } catch (e) {
      if (e.status && e.status < 500) {
        state.trips = [];
        state.tripCacheMode = 'live';
        toast(e.message, 'err');
        setHash('results');
        return;
      }
      if (!e.status) state.online = false;
      let cached = [];
      try { cached = await TuraStore.getAll('trips'); }
      catch (storageError) { toast('Could not read saved trips: ' + storageError.message, 'err'); }
      const date = state.search.date;
      state.trips = cached.filter((trip) =>
        trip.origin.toLowerCase() === state.search.origin.toLowerCase()
        && trip.destination.toLowerCase() === state.search.destination.toLowerCase()
        && (!date || String(trip.departure).slice(0, 10) === date)
      );
      state.tripCacheMode = 'cached';
      if (!state.trips.length) toast(`No cached trips for this route (${e.message})`, 'err');
      setHash('results');
      return;
    }
    state.trips = res.trips || [];
    state.tripCacheMode = 'live';
    try {
      await Promise.all(state.trips.map((tr) => TuraStore.put('trips', { ...tr, cached_at: new Date().toISOString() })));
    } catch (e) {
      toast('Trips loaded, but could not be saved for offline use: ' + e.message, 'err');
    }
    setHash('results');
  }

  async function loadOpsData() {
    const [dashboard, live, setup, trips, diagnostics] = await Promise.all([
      api('/api/reports/dashboard'),
      api('/api/operations/live'),
      api('/api/operations/setup'),
      api('/api/operations/trips'),
      api('/api/reports/health'),
    ]);
    state.ops = dashboard;
    state.opsLive = live;
    state.opsSetup = setup;
    state.opsTrips = trips.trips || [];
    state.opsDiagnostics = diagnostics;
  }

  function scheduleOpsRefresh() {
    if (state.route !== 'ops' || state._opsRefreshTimer) return;
    state._opsRefreshTimer = setTimeout(() => {
      state._opsRefreshTimer = null;
      state._opsLoaded = false;
      render();
    }, 500);
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error || new Error('Could not read QR image'));
      reader.readAsDataURL(blob);
    });
  }

  async function cacheTicket(ticket, includeQr) {
    if (!state.user || state.offlineSession) throw new Error('Sign in online to save this ticket');
    const ownerId = state.user.id;
    const saved = { ...ticket, owner_id: ownerId };
    if (includeQr && !saved.qr_data_url && state.online && saved.id) {
      try {
        const image = await api(`/api/tickets/${Number(saved.id)}/qr.png`);
        saved.qr_data_url = await blobToDataUrl(image);
      } catch (e) { toast('QR image could not be cached: ' + e.message, 'err'); }
    }
    try {
      return { ...(await TuraStore.put('tickets', saved, ownerId)), cached_offline: true };
    } catch (e) {
      toast('Ticket remains available in this view, but local offline storage failed: ' + e.message, 'err');
      return { ...saved, cached_offline: false };
    }
  }

  async function openSeats(tripId) {
    if (!state.user) { authModal('demo'); return; }
    if (state.offlineSession || !state.online) {
      toast('You can view saved journeys offline, but seats cannot be reserved without a live connection', 'err');
      return;
    }
    state.selectedTrip = state.trips.find((t) => t.id === tripId) || (await api('/api/trips/' + tripId)).trip;
    TuraWS.subscribe('trip:' + tripId);
    const res = await api(`/api/trips/${tripId}/seats`);
    state.seats = res.seats;
    state.selectedSeat = state.seats.find((s) => s.locked_by_me) || null;
    setHash('seats');
  }

  async function lockSeat(seatId) {
    try {
      const tripId = state.selectedTrip.id;
      if (!state.online) {
        toast('Seat availability must be confirmed by the server. Reconnect to lock a seat.', 'err');
        return;
      }
      const res = await api(`/api/trips/${tripId}/seats/lock`, { method: 'POST', body: { seat_id: seatId } });
      state.seats = res.seats;
      state.selectedSeat = state.seats.find((s) => s.id === seatId);
      render();
    } catch (e) { toast(e.message, 'err'); }
  }

  async function payFlow() {
    try {
      if (!state.user) return authModal('demo');
      if (!state.online || state.offlineSession) {
        toast('Payments are unavailable offline. Your saved Journey Pack is read-only.', 'err');
        return;
      }
      if (!state.pendingCheckout) {
        state.pendingCheckout = { booking_key: uuid(), payment_key: uuid(), booking_id: null };
      }
      if (!state.pendingCheckout.booking_id) {
        const bookingRes = await api('/api/bookings', {
          method: 'POST',
          body: {
            trip_id: state.selectedTrip.id,
            seat_id: state.selectedSeat.id,
            passenger_name: state.passenger.name,
            passenger_phone: state.passenger.phone,
            passenger_email: state.passenger.email || null,
            special_request: state.passenger.special || null,
            include_insurance: !!state.passenger.insurance,
            include_luggage: !!state.passenger.luggage,
            idempotency_key: state.pendingCheckout.booking_key,
            client_operation_id: state.pendingCheckout.booking_key,
          },
        });
        state.pendingCheckout.booking_id = bookingRes.booking.id;
      }
      const payRes = await api('/api/payments/charge', {
        method: 'POST',
        body: {
          booking_id: state.pendingCheckout.booking_id,
          method: state.payMethod,
          idempotency_key: state.pendingCheckout.payment_key,
        },
      });
      if (payRes.payment.status === 'failed') {
        state.pendingCheckout = null;
        toast('Mock payment was declined. Choose another seat or try a different passenger phone number.', 'err');
        await render();
        return;
      }
      if (!payRes.ticket) throw new Error('No ticket was issued; retry using the same payment attempt or contact support.');
      state.pendingCheckout = null;
      state.lastTicket = await cacheTicket(payRes.ticket, true);
      state.tickets = [state.lastTicket, ...state.tickets.filter((ticket) => ticket.id !== state.lastTicket.id)];
      state.trackingOptionsLoaded = false;
      if (payRes.luggage_tag) toast('Luggage tag ' + payRes.luggage_tag, 'ok');
      setHash('ticket');
      toast('Booking confirmed', 'ok');
    } catch (e) {
      if (e.status >= 400 && e.status < 500 && state.pendingCheckout && !state.pendingCheckout.booking_id) {
        state.pendingCheckout = null;
      }
      toast(e.message, 'err');
    }
  }

  async function loadTrackingOptions() {
    if (!state.user) return;
    const sel = $('#track-trip');
    if (!sel) return;
    if (state.trackingOptionsLoaded) {
      const trips = (!state.online || state.offlineSession)
        ? [...new Map(state.tickets.filter((ticket) => ticket.trip_id).map((ticket) => [
          ticket.trip_id,
          { trip_id: ticket.trip_id, origin: ticket.origin, destination: ticket.destination },
        ])).values()]
        : state.bookings
          .filter((booking) => booking.status === 'paid' || booking.status === 'completed')
          .map((booking) => ({ trip_id: booking.trip_id, origin: booking.origin, destination: booking.destination }));
      sel.innerHTML = trips.map((trip) => `<option value="${trip.trip_id}">${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)}</option>`).join('')
        || `<option value="">${state.online ? 'No active trips' : 'No saved itineraries'}</option>`;
      if (state.trackingTripId) sel.value = String(state.trackingTripId);
      return;
    }
    if (!state.online || state.offlineSession) {
      state.tickets = await TuraStore.getAll('tickets', state.user.id);
      const trips = [...new Map(state.tickets.filter((ticket) => ticket.trip_id).map((ticket) => [
        ticket.trip_id,
        { trip_id: ticket.trip_id, origin: ticket.origin, destination: ticket.destination, departure: ticket.departure, arrival: ticket.arrival },
      ])).values()];
      sel.innerHTML = trips.map((trip) => `<option value="${trip.trip_id}">${escapeHtml(trip.origin)} → ${escapeHtml(trip.destination)}</option>`).join('')
        || '<option value="">No saved itineraries</option>';
      if (trips[0]) {
        state.trackingTripId = trips[0].trip_id;
        state.selectedTrip = trips[0];
      }
      state.trackingOptionsLoaded = true;
      await render();
      return;
    }
    try {
      const res = await api('/api/bookings/mine');
      state.bookings = res.bookings || [];
      const paid = state.bookings.filter((b) => b.status === 'paid' || b.status === 'completed');
      sel.innerHTML = paid.map((b) => `<option value="${b.trip_id}">${escapeHtml(b.origin)} → ${escapeHtml(b.destination)} (#${b.trip_id})</option>`).join('')
        || '<option value="">No active trips</option>';
      state.trackingOptionsLoaded = true;
      if (paid[0]) {
        state.trackingTripId = paid[0].trip_id;
        state.selectedTrip = {
          departure: paid[0].departure,
          arrival: paid[0].arrival,
          origin: paid[0].origin,
          destination: paid[0].destination,
        };
        await loadTracking(paid[0].trip_id);
      }
    } catch (e) {
      if (!e.status) {
        state.online = false;
        await loadTrackingOptions();
        return;
      }
      if (e.status === 401) throw e;
      toast('Trip list could not be loaded: ' + e.message, 'err');
    }
  }

  async function loadTracking(tripId) {
    if (!tripId) return;
    if (!state.online || state.offlineSession) {
      const ticket = state.tickets.find((item) => item.trip_id === Number(tripId));
      if (ticket) {
        state.trackingTripId = ticket.trip_id;
        state.selectedTrip = {
          departure: ticket.departure,
          arrival: ticket.arrival,
          origin: ticket.origin,
          destination: ticket.destination,
        };
        state.tracking = null;
        await render();
      }
      return;
    }
    state.trackingTripId = tripId;
    TuraWS.subscribe('trip:' + tripId);
    try {
      state.tracking = await api(`/api/trips/${tripId}/tracking`);
    } catch (e) {
      if (e.status === 401) {
        state.user = null;
        state.offlineSession = false;
        TuraWS.disconnect();
        try { localStorage.removeItem('tura_offline_user'); }
        catch (storageError) { toast('Could not clear local sign-in state: ' + storageError.message, 'err'); }
        toast('Your session has expired. Please sign in again.', 'err');
        setHash('splash');
        authModal('login');
        return;
      }
      if (!e.status) state.online = false;
      toast('Live tracking could not be loaded: ' + e.message, 'err');
    }
    render();
  }

  async function boot() {
    try {
      state.config = await api('/api/config');
    } catch (e) {
      state.config = { fees: {}, features: {}, demo_mode: false };
      if (!e.status) state.online = false;
      toast('Configuration could not be loaded: ' + e.message, 'err');
    }

    let logoutPending = false;
    try { logoutPending = localStorage.getItem('tura_logout_pending') === '1'; }
    catch (e) { toast('Could not read local sign-in state: ' + e.message, 'err'); }
    if (logoutPending && state.online) {
      try {
        await api('/api/auth/logout', { method: 'POST' });
        localStorage.removeItem('tura_logout_pending');
      } catch (e) {
        state.online = false;
        toast('Pending logout will finish after reconnecting: ' + e.message, 'err');
      }
    }
    if (!logoutPending) {
      try {
        const me = await api('/api/auth/me');
        state.user = me.user;
        rememberOfflineUser(me.user);
      } catch (e) {
        if (!e.status) state.online = false;
        state.user = readOfflineUser();
        state.offlineSession = !!state.user;
        if (!state.user && !e.status) toast('Sign-in could not be checked while offline', 'err');
      }
    }

    window.addEventListener('online', async () => {
      state.online = true;
      state.trackingOptionsLoaded = false;
      try {
        if (localStorage.getItem('tura_logout_pending') === '1') {
          await api('/api/auth/logout', { method: 'POST' });
          localStorage.removeItem('tura_logout_pending');
          state.user = null;
          state.offlineSession = false;
          localStorage.removeItem('tura_offline_user');
          try { await TuraStore.clearStore('tickets'); }
          catch (storageError) { toast('Could not clear saved tickets on this device: ' + storageError.message, 'err'); }
          state.trackingOptionsLoaded = false;
          state.trackingTripId = null;
          state.tracking = null;
          TuraWS.disconnect();
          toast('Logged out', 'ok');
          render();
          return;
        }
        if (state.offlineSession) {
          const me = await api('/api/auth/me');
          state.user = me.user;
          state.offlineSession = false;
          rememberOfflineUser(me.user);
          TuraWS.connect([]);
        }
        if (!state.user) {
          render();
          return;
        }
      } catch (e) { toast('Could not reconnect to TURA: ' + e.message, 'err'); }
      render();
    });
    window.addEventListener('offline', () => {
      state.online = false;
      state.trackingOptionsLoaded = false;
      render();
    });
    window.addEventListener('hashchange', render);

    if (state.user && !state.offlineSession) TuraWS.connect([]);
    TuraWS.onEvent((msg) => {
      if (msg.event === '_open') { state.wsLive = true; render(); }
      if (msg.event === '_close') { state.wsLive = false; render(); }
      if (msg.event === '_error') toast(msg.data.detail, 'err');
      if (msg.event === 'seat.locked' || msg.event === 'seat.released' || msg.event === 'seat.booked') {
        if (state.route === 'seats' && state.selectedTrip && msg.data.trip_id === state.selectedTrip.id) {
          api(`/api/trips/${state.selectedTrip.id}/seats`).then((r) => { state.seats = r.seats; render(); });
        }
      }
      if (msg.event === 'trip.position' && state.route === 'tracking' && msg.data.trip_id === state.trackingTripId) {
        state.tracking = state.tracking || {};
        state.tracking.position = msg.data;
        render();
      }
      if (msg.event === 'sos.created') toast('SOS (Demo/Local): ' + (msg.data.reason || ''), 'err');
      if ([
        'trip.position', 'sos.created', 'sos.acknowledged', 'booking.updated',
        'ticket.validated', 'luggage.scanned', 'operations.updated',
      ].includes(msg.event)) scheduleOpsRefresh();
    });

    if (!location.hash || location.hash === '#') {
      location.hash = state.user ? '#/home' : '#/splash';
    } else {
      await render();
    }

    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch((e) => {
        toast('Offline app shell could not be installed: ' + e.message, 'err');
      });
    }
  }

  boot();
})();
