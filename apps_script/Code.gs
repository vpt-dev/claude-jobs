/**
 * Job tracker sync for the "Claude Jobs" Google Sheet.
 *
 * The job board site sends your tracker changes here and reads them back, so
 * the tracker follows you between devices. The Applications tab is the store.
 *
 * Setup: change PASSPHRASE below to something only you know (8+ characters),
 * then Deploy > New deployment > Web app > Execute as: Me, Who has access: Anyone.
 * Paste the web app URL and the same passphrase into the site's Tracker tab.
 */
const PASSPHRASE = 'change-me';

const TAB = 'Applications';
const META = 'Sync';
const HEAD = ['Company', 'Role', 'Type', 'Location', 'Status', 'Date applied', 'Last updated', 'Notes', 'Link', 'Board ID', 'Sync stamp'];
const STATUS = ['Saved', 'Applied', 'Online test', 'Interview', 'Offer', 'Rejected', 'Not interested'];
const MAX_APPS = 3000;

function doGet() {
  return out({ok: true, note: 'Job tracker sync is running. Open the job board to use it.'});
}

function doPost(e) {
  let req;
  try { req = JSON.parse(e.postData.contents); } catch (err) { return out({ok: false, error: 'bad_request'}); }
  if (PASSPHRASE === 'change-me' || PASSPHRASE.length < 8) return out({ok: false, error: 'not_set_up'});
  if (!req || req.pass !== PASSPHRASE) { Utilities.sleep(1500); return out({ok: false, error: 'wrong_passphrase'}); }
  const lock = LockService.getScriptLock();
  try { lock.waitLock(20000); } catch (err) { return out({ok: false, error: 'busy'}); }
  try { return out(sync(req)); }
  catch (err) { return out({ok: false, error: 'server', detail: String(err).slice(0, 200)}); }
  finally { lock.releaseLock(); }
}

function out(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}

// Text that came from a job listing must never be read as a formula.
function plain(v, max) {
  return String(v == null ? '' : v).replace(/[\r\n\t]+/g, ' ').replace(/^[=+@\-\s]+/, '').slice(0, max || 300);
}
function note(v) { return String(v == null ? '' : v).replace(/[\r\t]+/g, ' ').slice(0, 2000); }
function day(v) { v = String(v || ''); return /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : ''; }
function num(v) { v = Number(v); return isFinite(v) && v > 0 ? Math.floor(v) : 0; }

function clean(a) {
  return {
    c: plain(a.c), t: plain(a.t), ty: plain(a.ty, 40), l: plain(a.l),
    s: STATUS.indexOf(a.s) >= 0 ? a.s : 'Saved',
    ad: day(a.ad), up: day(a.up), n: note(a.n),
    u: /^https?:\/\//i.test(String(a.u || '')) ? String(a.u).slice(0, 1000) : '',
    ts: num(a.ts)
  };
}

function sync(req) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(TAB) || ss.insertSheet(TAB);
  let meta = ss.getSheetByName(META);
  if (!meta) { meta = ss.insertSheet(META); meta.hideSheet(); }

  // What the sheet holds now.
  const last = sh.getLastRow();
  const rows = last > 1 ? sh.getRange(2, 1, last - 1, HEAD.length).getDisplayValues() : [];
  const apps = {}, extra = [];
  rows.forEach(function (r) {
    const id = String(r[9] || '').trim();
    if (!id) { if (r.join('').trim()) extra.push(r); return; } // rows you typed by hand are kept as they are
    apps[id] = {c: r[0], t: r[1], ty: r[2], l: r[3], s: r[4], ad: r[5], up: r[6], n: r[7], u: r[8], ts: num(r[10])};
  });
  let state = {};
  try { state = JSON.parse(meta.getRange(1, 1).getValue() || '{}'); } catch (err) { state = {}; }
  const gone = state.gone || {};
  let changed = false;

  // Merge what the site sent. The newer change wins.
  const inApps = req.apps || {}, inGone = req.gone || {};
  Object.keys(inApps).slice(0, MAX_APPS).forEach(function (id) {
    if (!/^[\w-]{4,40}$/.test(id)) return;
    const a = clean(inApps[id]), cur = apps[id];
    if (cur ? a.ts > cur.ts : !(num(gone[id]) >= a.ts && a.ts > 0)) { apps[id] = a; delete gone[id]; changed = true; }
  });
  Object.keys(inGone).slice(0, MAX_APPS).forEach(function (id) {
    const ts = num(inGone[id]);
    if (apps[id] && ts > apps[id].ts) { delete apps[id]; gone[id] = ts; changed = true; }
    else if (!apps[id] && ts > num(gone[id])) { gone[id] = ts; changed = true; }
  });
  if (req.prefs && num(req.pt) > num(state.pt)) {
    state.prefs = {
      saved: (req.prefs.saved || []).slice(0, 12),
      lastVisit: day(req.prefs.lastVisit), prevVisit: day(req.prefs.prevVisit)
    };
    state.pt = num(req.pt); changed = true;
  }

  if (changed) {
    const ids = Object.keys(apps).sort(function (x, y) {
      return STATUS.indexOf(apps[x].s) - STATUS.indexOf(apps[y].s) || String(apps[y].up).localeCompare(String(apps[x].up));
    });
    const table = ids.map(function (id) {
      const a = apps[id];
      return [a.c, a.t, a.ty, a.l, a.s, a.ad, a.up, a.n, a.u, id, String(a.ts || '')];
    }).concat(extra);
    sh.getRange(1, 1, 1, HEAD.length).setValues([HEAD]);
    if (last > 1) sh.getRange(2, 1, last - 1, HEAD.length).clearContent();
    if (table.length) {
      const rng = sh.getRange(2, 1, table.length, HEAD.length);
      rng.setNumberFormat('@'); // plain text, so dates and IDs are not reinterpreted
      rng.setValues(table);
    }
    // Keep only the most recent removals.
    const keep = Object.keys(gone).sort(function (x, y) { return gone[y] - gone[x]; }).slice(0, 400);
    const trimmed = {}; keep.forEach(function (id) { trimmed[id] = gone[id]; });
    state.gone = trimmed;
    meta.getRange(1, 1).setValue(JSON.stringify(state));
  }
  return {ok: true, apps: apps, prefs: state.prefs || null, pt: num(state.pt)};
}
