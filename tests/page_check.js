// Runs the page's own script against a built site, without a browser, and checks what it draws.
// Usage: node tests/page_check.js site_dir [--tracked '{"id":{...}}']
const fs = require('fs'), path = require('path'), vm = require('vm');
const dir = process.argv[2] || 'site';
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
const inline = html.split('<script>').pop().split('</script>')[0];
const els = {}, handlers = {};
function el(id) {
  if (els[id]) return els[id];
  const o = {id, innerHTML: '', textContent: '', hidden: false, checked: true, value: '', open: false, dataset: {}, style: {}, href: '',
    classList: {toggle() {}, add() {}, remove() {}},
    addEventListener(type, fn) { (handlers[id + ':' + type] = handlers[id + ':' + type] || []).push(fn); },
    setAttribute() {}, removeAttribute() {}, scrollIntoView() {}, closest() { return null; }, querySelectorAll() { return []; }, focus() {}};
  return (els[id] = o);
}
const store = {};
const ctx = {
  window: {}, console, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, URL, Date, Math, JSON, Intl, Promise,
  localStorage: {getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; }},
  document: {getElementById: el, querySelectorAll: () => [], addEventListener() {}, hidden: false, activeElement: null},
  location: {hash: process.env.HASH || '#for-you', reload() {}}, addEventListener() {}, innerWidth: 1200, navigator: {},
  fetch: () => Promise.reject(new Error('offline')),
};
ctx.window = ctx; ctx.window.matchMedia = () => ({matches: true});
if (process.env.TRACKED) store['ecj-tracker-v1'] = process.env.TRACKED;
if (process.env.FY) store['ecj-fy-v2'] = process.env.FY;
vm.createContext(ctx);
for (const f of ['data.js', 'elig.js']) vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), ctx, {filename: f});
vm.runInContext(inline + '\n;globalThis.__t = {D, C, EL, fyAll, fyLists, fyJudge, store, filtered, st, render, paintFY, paintTracker, paintCharts, rehome, setCheck, myCheck, BYID};', ctx, {filename: 'index.html'});
const t = ctx.__t, fails = [];
const check = (ok, label, detail) => { if (!ok) fails.push(label + (detail ? ' -> ' + detail : '')); };
const L = t.fyLists();
const count = g => L[g].length;
console.log(`roles ${t.D.length} | in scope ${t.fyAll.length} | match ${count('M')} conditional ${count('C')} unknown ${count('U')} ruled out ${count('X')} | other fields ${L.offField} other places ${L.offPlace}`);
check(t.D.length > 5000, 'dataset loaded');
check(t.D.every(r => r.length >= 24), 'every row has the new columns');
check(t.fyAll.length > 500, 'For you has roles in scope', String(t.fyAll.length));
check(L.M.length + L.C.length + L.U.length + L.X.length > 100, 'For you lists something by default');
check(t.fyAll.every(r => r.fp.size > 0), 'every in-scope role has a place group');
check(L.X.every(r => r.j.why && r.j.why.length > 10), 'every ruled-out role states its reason');
check(L.M.every(r => r.j.quote || r.j.badge === 'Confirmed by you' || /title|list/.test(r.j.why)), 'every match shows the sentence it rests on');
const groups = els['fy-groups'].innerHTML;
check(/Published match/.test(groups) && /Ruled out, with the reason/.test(groups), 'four groups are drawn');
check(!/undefined|NaN|\[object/.test(groups), 'no broken values in For you', (groups.match(/.{40}(undefined|NaN|\[object).{40}/) || [''])[0]);
check(/Not shown above/.test(els['fy-audit'].innerHTML), 'audit table is drawn');
check(els['fy-facts'].innerHTML.includes('Right to work'), 'profile facts are shown');
t.render();
check(!/undefined|NaN|\[object/.test(els['list'].innerHTML), 'no broken values on the Board', (els['list'].innerHTML.match(/.{40}(undefined|NaN|\[object).{40}/) || [''])[0]);
check(/roles$/.test(els['count'].textContent), 'Board count is drawn', els['count'].textContent);
t.paintCharts();
check(els['health'].innerHTML.length > 50 && !/undefined|NaN/.test(els['health'].innerHTML), 'data check is drawn', els['health'].innerHTML.slice(0, 200));
// each sort and a few filters run without error
for (const sort of ['new', 'pay', 'co']) { t.st.sort = sort; check(t.filtered().length === t.D.filter(() => true).length || t.filtered().length > 0, 'sort ' + sort); }
t.st.country = ['??']; const unk = t.filtered().length; t.st.country = [];
console.log(`board rows with country not stated: ${unk}`);
// your own check with the employer moves a role between groups
const someU = L.U[0];
if (someU) { t.setCheck(someU[t.C.id], 'Employer said no'); const L2 = t.fyLists();
  check(L2.X.some(r => r === someU) && someU.j.badge === 'Ruled out by you', 'a recorded "no" rules the role out');
  t.setCheck(someU[t.C.id], 'Employer confirmed'); const L3 = t.fyLists();
  check(L3.M.some(r => r === someU), 'a recorded confirmation makes it a match');
  t.setCheck(someU[t.C.id], ''); }
if (process.env.EXPECT_REHOMED) { const ids = Object.keys(t.store.apps);
  check(ids.every(id => t.BYID.has(id)) === (process.env.EXPECT_REHOMED === 'all'), 'tracked roles follow their role to its new id', ids.filter(id => !t.BYID.has(id)).join(',')); }
if (process.argv.includes('--show')) for (const g of 'MCUX') for (const r of L[g].slice(0, 4)) console.log(g, '|', r[0], '|', r[1].slice(0, 50), '|', r.j.badge, '|', r.j.why.slice(0, 90));
if (fails.length) { console.log('FAILED:\n  ' + fails.join('\n  ')); process.exit(1); }
console.log('page checks passed');
