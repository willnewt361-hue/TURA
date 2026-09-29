/** IndexedDB cache for read-only offline journey details. */
(function (global) {
  const DB_NAME = 'tura_offline_v1';
  const DB_VERSION = 2;
  let dbPromise = null;

  function openDB() {
    if (!dbPromise) {
      dbPromise = new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, DB_VERSION);
        req.onupgradeneeded = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains('tickets')) db.createObjectStore('tickets', { keyPath: 'id' });
          if (!db.objectStoreNames.contains('trips')) db.createObjectStore('trips', { keyPath: 'id' });
          if (db.objectStoreNames.contains('queue')) db.deleteObjectStore('queue');
          if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta', { keyPath: 'key' });
        };
        req.onsuccess = () => {
          const db = req.result;
          db.onversionchange = () => {
            db.close();
            dbPromise = null;
          };
          resolve(db);
        };
        req.onerror = () => reject(req.error || new Error('Could not open offline storage'));
        req.onblocked = () => reject(new Error('Offline storage upgrade is blocked by another open tab'));
      });
      dbPromise.catch(() => { dbPromise = null; });
    }
    return dbPromise;
  }

  async function put(store, value, ownerId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, 'readwrite');
      const entry = store === 'tickets'
        ? { ...value, owner_id: ownerId, cached_at: new Date().toISOString() }
        : value;
      t.objectStore(store).put(entry);
      t.oncomplete = () => resolve(entry);
      t.onerror = () => reject(t.error);
      t.onabort = () => reject(t.error || new Error('Offline storage transaction aborted'));
    });
  }

  async function getAll(store, ownerId) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, 'readonly');
      const req = t.objectStore(store).getAll();
      req.onsuccess = () => {
        const values = req.result || [];
        const scoped = store === 'tickets' && ownerId != null
          ? values.filter((value) => value.owner_id === ownerId)
          : values;
        resolve(store === 'tickets'
          ? scoped.sort((a, b) => String(b.cached_at || '').localeCompare(String(a.cached_at || '')))
          : scoped);
      };
      req.onerror = () => reject(req.error);
      t.onabort = () => reject(t.error || new Error('Offline storage read aborted'));
    });
  }

  async function get(store, key) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, 'readonly');
      const req = t.objectStore(store).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function clearStore(store) {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const t = db.transaction(store, 'readwrite');
      t.objectStore(store).clear();
      t.oncomplete = () => resolve();
      t.onerror = () => reject(t.error);
    });
  }

  global.TuraStore = { put, get, getAll, clearStore };
})(window);
