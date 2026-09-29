/** Interactive guided tour / demo help */
(function (global) {
  const STEPS = [
    {
      title: 'Welcome to TURA',
      body: 'Book buses across Uganda with server-checked seats, signed QR tickets, and an offline Journey Pack for saved itinerary details. This short tour shows the key flows.',
    },
    {
      title: 'Search & seat map',
      body: 'Pick From/To/Date, search buses, then lock a seat. Seats are server-authoritative — yellow means your selection.',
    },
    {
      title: 'Mock payments',
      body: 'Pay with Mobile Money, Card, or Bank (mock). Retries are idempotent so you never get duplicate tickets.',
    },
    {
      title: 'QR tickets & driver scan',
      body: 'Your ticket carries a signed payload (not secrets). Save its image and itinerary for offline display. Drivers must be online to check whether a ticket is used or revoked.',
    },
    {
      title: 'Live tracking & SOS',
      body: 'View your trip tracker (a demo simulator, not GPS). SOS creates a Demo/Local alert for operators — it never pretends to call police.',
    },
    {
      title: 'Roles & demo login',
      body: 'Use Demo Mode as Customer, Driver, Operator, or Admin. Operators manage fleet/routes/trips and see the live wallboard; drivers work on assigned trips.',
    },
  ];

  let index = 0;
  let open = false;

  function markDone() {
    try { localStorage.setItem('tura_tour_done', '1'); }
    catch (error) { console.warn('TURA tour completion could not be saved', error); }
  }

  function render() {
    let el = document.getElementById('tour-overlay');
    if (!open) {
      if (el) el.remove();
      return;
    }
    const step = STEPS[index];
    if (!el) {
      el = document.createElement('div');
      el.id = 'tour-overlay';
      el.className = 'tour-overlay';
      document.body.appendChild(el);
    }
    el.innerHTML = `
      <div class="tour-card" role="dialog" aria-modal="true">
        <h3>${step.title}</h3>
        <p>${step.body}</p>
        <div style="font-size:12px;color:var(--muted);margin-bottom:10px">Step ${index + 1} of ${STEPS.length}</div>
        <div class="tour-actions">
          <button class="btn btn-outline" id="tour-skip">Skip</button>
          <button class="btn btn-primary" id="tour-next" style="flex:1">${index === STEPS.length - 1 ? 'Finish' : 'Next'}</button>
        </div>
      </div>`;
    el.querySelector('#tour-skip').onclick = () => { open = false; markDone(); render(); };
    el.querySelector('#tour-next').onclick = () => {
      if (index >= STEPS.length - 1) {
        open = false;
        markDone();
      } else index += 1;
      render();
    };
  }

  function start(force) {
    try {
      if (!force && localStorage.getItem('tura_tour_done')) return;
    } catch (error) {
      console.warn('TURA tour completion could not be read', error);
    }
    index = 0;
    open = true;
    render();
  }

  function openHelp() {
    index = 0;
    open = true;
    render();
  }

  global.TuraTour = { start, openHelp, STEPS };
})(window);
