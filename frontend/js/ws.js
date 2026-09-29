/** Authenticated WebSocket client with bounded reconnect behavior. */
(function (global) {
  let ws = null;
  let rooms = [];
  let handlers = [];
  let retry = 0;
  let retryTimer = null;
  let heartbeatTimer = null;
  let shouldReconnect = false;

  function url() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const q = new URLSearchParams();
    if (rooms.length) q.set('rooms', rooms.join(','));
    const query = q.toString();
    return `${proto}://${location.host}/ws${query ? '?' + query : ''}`;
  }

  function openSocket() {
    const socket = new WebSocket(url());
    ws = socket;
    socket.onopen = () => {
      retry = 0;
      handlers.forEach((h) => h({ event: '_open', data: {} }));
      rooms.forEach((room) => socket.send(JSON.stringify({ type: 'subscribe', room })));
    };
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        handlers.forEach((h) => h(msg));
      } catch (_) {
        handlers.forEach((h) => h({ event: '_error', data: { detail: 'Invalid server message' } }));
      }
    };
    socket.onclose = (ev) => {
      handlers.forEach((h) => h({ event: '_close', data: { code: ev.code } }));
      if (ws !== socket || !shouldReconnect || ev.code === 4401 || ev.code === 4403) return;
      const wait = Math.min(10000, 1000 * Math.pow(1.5, retry++));
      retryTimer = setTimeout(openSocket, wait);
    };
  }

  function connect(nextRooms) {
    if (nextRooms) rooms = [...new Set(nextRooms)];
    shouldReconnect = true;
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    if (ws && ws.readyState === WebSocket.OPEN) return;
    if (ws && ws.readyState === WebSocket.CONNECTING) return;
    openSocket();
    if (!heartbeatTimer) {
      heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25000);
    }
  }

  function disconnect() {
    shouldReconnect = false;
    if (retryTimer) clearTimeout(retryTimer);
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    retryTimer = null;
    heartbeatTimer = null;
    if (ws) ws.close(1000, 'session ended');
    ws = null;
    rooms = [];
  }

  function onEvent(fn) {
    handlers.push(fn);
    return () => { handlers = handlers.filter((h) => h !== fn); };
  }

  function subscribe(room) {
    if (!rooms.includes(room)) rooms.push(room);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'subscribe', room }));
    }
  }

  global.TuraWS = { connect, disconnect, onEvent, subscribe };
})(window);
