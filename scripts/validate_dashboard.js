// Headless smoke check for the generated dashboard: extract embedded JSON,
// parse it, assert required keys + view functions exist. Dev-only.
const fs = require('fs');
const path = process.argv[2] || 'cci-dashboard.html';
const h = fs.readFileSync(path, 'utf8');
const open = '<script id="data" type="application/json">';
const i = h.indexOf(open) + open.length;
const j = h.indexOf('</script>', i);
const raw = h.slice(i, j).split('<\\/').join('</');
const R = JSON.parse(raw);
const need = ['totals', 'headline', 'by_model', 'by_project', 'daily', 'sessions', 'pareto', 'projection', 'waste'];
const miss = need.filter(k => !(k in R));
const fns = ['vOverview', 'vModels', 'vSessions', 'vProjects', 'vOptimize', 'vBudget'];
const fnsOk = fns.every(f => h.includes(f));
console.log('keys ok      :', miss.length === 0, miss.length ? 'MISSING ' + miss : '');
console.log('view fns ok  :', fnsOk);
console.log('headline     :', R.headline.length, 'cards');
console.log('models       :', R.by_model.length);
console.log('sessions     :', R.sessions.length);
console.log('findings     :', R.waste.findings.length);
console.log('total spend  : $' + R.totals.cost);
console.log('recoverable  : $' + R.waste.recoverable_mid + ' (' + (R.waste.recoverable_pct * 100).toFixed(0) + '%)');
console.log('html bytes   :', h.length);
if (miss.length || !fnsOk) { console.error('VALIDATION FAILED'); process.exit(1); }
console.log('VALIDATION OK');
