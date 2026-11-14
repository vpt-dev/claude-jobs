/**
 * Job tracker sync for the "Claude Jobs" Google Sheet.
 *
 * The job board site sends your tracker changes here and reads them back, so
 * the tracker follows you between devices. The Applications tab is the store.
 *
 * Setup: change PASSPHRASE below to something only you know (8+ characters),
 * then Deploy > New deployment > Web app > Execute as: Me, Who has access: Anyone.
 * Paste the web app URL and the same passphrase into the site's Tracker tab.
 *
 * Job alerts: run setupAlerts once from this editor (Run menu). Every hour it reads the
 * job-alert emails LinkedIn, Indeed and Glassdoor send you and lists the roles on the
 * Alerts tab, which the job board then shows. It only opens emails from those senders.
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
  return {ok: true, apps: apps, prefs: state.prefs || null, pt: num(state.pt), alerts: alertRows(ss)};
}


/* ---------------- Job alerts from your inbox ---------------- */
const ALERT_TAB = 'Alerts';
const ALERT_HEAD = ['Key', 'Company', 'Role', 'Location', 'Link', 'Source', 'First seen'];
const ALERT_QUERY = 'from:(linkedin.com OR indeed.com OR glassdoor.com OR glassdoor.co.uk) (job OR jobs OR alert) newer_than:3d';
const ALERT_KEEP_DAYS = 45;
const SITES = [
  {name: 'LinkedIn', from: /linkedin\.com/i, link: /https?:\/\/[\w.]*linkedin\.com\/(?:comm\/)?jobs\/view\/(\d+)/i,
    url: function (m) { return 'https://www.linkedin.com/jobs/view/' + m[1]; }},
  {name: 'Indeed', from: /indeed\.com/i, link: /https?:\/\/([\w.]*indeed\.com)\/[^"'\s<>]*?[?&](?:jk|vjk)=([0-9a-f]{8,20})/i,
    url: function (m) { return 'https://' + m[1].replace(/^(?:cts|click|t)\./, '') + '/viewjob?jk=' + m[2]; }},
  {name: 'Glassdoor', from: /glassdoor\./i, link: /https?:\/\/([\w.]*glassdoor\.[\w.]+)\/[^"'\s<>]*?(?:jobListingId|jl)=(\d{6,})/i,
    url: function (m) { return 'https://' + m[1] + '/job-listing/j?jl=' + m[2]; }}
];
const NOT_A_TITLE = /^(view|see|apply|save|easy apply|view job|see all|see more|unsubscribe|manage|help|learn more|new|promoted|actively recruiting|\d+ (new )?jobs?.*)$/i;

function setupAlerts() {
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'readAlerts') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('readAlerts').timeBased().everyHours(1).create();
  const n = readAlerts();
  Logger.log('Job alerts are set up. Roles found in recent alert emails: ' + n);
}

function untag(h) {
  return String(h).replace(/<(style|script)[\s\S]*?<\/\1>/gi, ' ').replace(/<br\s*\/?>|<\/(p|div|tr|td|li|h\d|table)>/gi, '\n').replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;|&#160;/g, ' ').replace(/&amp;/g, '&').replace(/&#39;|&rsquo;|&apos;/g, "'").replace(/&quot;/g, '"').replace(/&middot;|&#183;|&bull;/g, '·')
    .replace(/&[a-z]+;|&#\d+;/g, ' ').replace(/[ \t​‌﻿]+/g, ' ');
}
function lines(h) { return untag(h).split('\n').map(function (x) { return x.trim(); }).filter(function (x) { return x; }); }

/** Pull job cards out of one alert email: each job link, its title, then company and location from the text after it. */
function parseAlert(site, body) {
  const out = {}, order = [];
  const anchors = [];
  const re = /<a\b[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(body))) {
    const href = m[1].replace(/&amp;/g, '&'), hit = site.link.exec(href);
    if (hit) anchors.push({key: hit[hit.length - 1], url: site.url(hit), text: lines(m[2]).join(' '), start: m.index, end: re.lastIndex});
  }
  anchors.forEach(function (a, i) {
    let job = out[a.key];
    if (!job) { job = out[a.key] = {key: a.key, url: a.url, title: '', after: ''}; order.push(a.key); }
    if (!job.title && a.text.length >= 4 && a.text.length <= 140 && /[a-z]{3}/i.test(a.text) && !NOT_A_TITLE.test(a.text)) {
      job.title = a.text;
      let stop = body.length;
      for (let k = i + 1; k < anchors.length; k++) if (anchors[k].key !== a.key) { stop = anchors[k].start; break; }
      job.after = body.slice(a.end, Math.min(stop, a.end + 3000));
    }
  });
  return order.map(function (k) { return out[k]; }).filter(function (j) { return j.title; }).map(function (j) {
    const ls = lines(j.after).filter(function (x) { return !NOT_A_TITLE.test(x) && x !== j.title && x.length <= 120; });
    let company = '', loc = '';
    const first = ls[0] || '';
    if (first.indexOf('·') > 0) { const parts = first.split('·'); company = parts[0].trim(); loc = parts.slice(1).join(',').trim(); }
    else if (/ - /.test(first) && (!ls[1] || /[£$]|\bhour|\byear|\bago\b|\bday/i.test(ls[1]))) { const parts = first.split(' - '); company = parts[0].trim(); loc = parts.slice(1).join(' - ').trim(); }
    else { company = first; loc = ls[1] || ''; }
    return {key: site.name.toLowerCase() + ':' + j.key, company: plain(company, 120), title: plain(j.title, 160), loc: plain(loc, 120), url: j.url, source: site.name};
  }).filter(function (j) { return j.company; });
}

function readAlerts() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(ALERT_TAB);
  if (!sh) { sh = ss.insertSheet(ALERT_TAB); }
  sh.getRange(1, 1, 1, ALERT_HEAD.length).setValues([ALERT_HEAD]);
  const last = sh.getLastRow();
  const have = last > 1 ? sh.getRange(2, 1, last - 1, ALERT_HEAD.length).getDisplayValues() : [];
  const seen = {}; have.forEach(function (r) { seen[r[0]] = true; });
  const today = Utilities.formatDate(new Date(), 'UTC', 'yyyy-MM-dd');
  const fresh = [];
  GmailApp.search(ALERT_QUERY, 0, 40).forEach(function (thread) {
    thread.getMessages().forEach(function (msg) {
      const from = msg.getFrom();
      const site = SITES.filter(function (x) { return x.from.test(from); })[0];
      if (!site) return;
      parseAlert(site, msg.getBody()).forEach(function (j) {
        if (seen[j.key]) return;
        seen[j.key] = true;
        fresh.push([j.key, j.company, j.title, j.loc, j.url, j.source, today]);
      });
    });
  });
  const cutoff = Utilities.formatDate(new Date(Date.now() - ALERT_KEEP_DAYS * 864e5), 'UTC', 'yyyy-MM-dd');
  const keep = fresh.concat(have.filter(function (r) { return r[6] >= cutoff; })).slice(0, 1500);
  if (last > 1) sh.getRange(2, 1, last - 1, ALERT_HEAD.length).clearContent();
  if (keep.length) { const rng = sh.getRange(2, 1, keep.length, ALERT_HEAD.length); rng.setNumberFormat('@'); rng.setValues(keep); }
  return fresh.length;
}

/** Alert roles in the job board's own row format. */
function alertRows(ss) {
  const sh = ss.getSheetByName(ALERT_TAB);
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, Math.min(sh.getLastRow() - 1, 600), ALERT_HEAD.length).getDisplayValues().filter(function (r) { return r[0] && r[2] && r[4]; }).map(function (r) {
    const t = r[2].toLowerCase(), l = r[3].toLowerCase();
    const type = /intern|placement|co-?op|summer 20|working student|industrial/.test(t) ? 'Internship' : 'New Grad';
    const cat = /quant|trader|trading/.test(t) ? 'Quant' : /data|machine learning|\bml\b|\bai\b|analyst|scien|statist/.test(t) ? 'Data, AI & Stats'
      : /hardware|electrical|embedded|fpga|firmware/.test(t) ? 'Hardware' : /software|engineer|developer|\bswe\b|technolog|devops|cloud|security|stack|backend|frontend|web|mobile|\bit\b/.test(t) ? 'Software' : 'Other';
    const ctry = /united kingdom|\buk\b|england|scotland|wales|london/.test(l) && !/ontario|, on\b/.test(l) ? 'UK' : /canada|ontario|, on\b|quebec|british columbia|alberta|toronto|vancouver|montreal/.test(l) ? 'CA' : 'US';
    const hex = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_1, r[0]).map(function (b) { return ('0' + (b & 255).toString(16)).slice(-2); }).join('').slice(0, 10);
    return [r[1], r[2], r[3] ? [r[3]] : [], [ctry], type, cat, r[4], r[6], '', 0, '', '', [r[5] + ' alert'], 0, 0, 0, 0, [], 'al' + hex];
  });
}
