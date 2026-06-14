"""HTML dashboard generator.

Renders the canonical report object into ONE self-contained ``.html`` file:
inline CSS, inline vanilla JS, data embedded as JSON. No build step, no CDN, no
network — open it in any browser, offline. Six views: Overview, Models,
Sessions, Projects, Optimization, Budget.
"""

from __future__ import annotations

import json

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Cost Intelligence</title>
<style>
:root{
  --bg:#0a0d14; --panel:#121826; --panel2:#0f1420; --line:#1f2738;
  --txt:#e6edf3; --muted:#8b98a9; --dim:#5b6678;
  --cyan:#39d0d8; --violet:#8b7bff; --green:#3fb950; --yellow:#d29922; --red:#f85149;
  --grad:linear-gradient(135deg,#39d0d8,#8b7bff);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
  font:14px/1.5 "Inter",-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
a{color:var(--cyan);text-decoration:none}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px 80px}
header{display:flex;align-items:center;gap:14px;padding:26px 22px 18px;max-width:1180px;margin:0 auto}
.logo{width:38px;height:38px;border-radius:10px;background:var(--grad);
  display:grid;place-items:center;font-weight:800;color:#06121a;font-size:18px}
h1{font-size:19px;margin:0;letter-spacing:.2px}
.sub{color:var(--muted);font-size:12.5px;margin-top:2px}
nav{display:flex;gap:4px;flex-wrap:wrap;border-bottom:1px solid var(--line);
  max-width:1180px;margin:0 auto;padding:0 22px}
nav button{background:none;border:0;color:var(--muted);padding:11px 14px;cursor:pointer;
  font-size:13.5px;border-bottom:2px solid transparent;font-weight:600}
nav button:hover{color:var(--txt)}
nav button.active{color:var(--txt);border-bottom-color:var(--cyan)}
.view{display:none;padding-top:22px}.view.active{display:block}
.grid{display:grid;gap:16px}
.kpis{grid-template-columns:repeat(4,1fr)}
@media(max-width:880px){.kpis{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
.kpi .lab{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px}
.kpi .val{font-size:27px;font-weight:800;margin:7px 0 4px;letter-spacing:.3px}
.kpi .sub{font-size:12px;color:var(--dim)}
.kpi.good{border-color:#1d3a25}.kpi.good .val{color:var(--green)}
.kpi.warn{border-color:#3a3320}.kpi.warn .val{color:var(--yellow)}
.kpi.neutral .val{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.cols{display:grid;grid-template-columns:1.3fr 1fr;gap:16px}
@media(max-width:880px){.cols{grid-template-columns:1fr}}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.7px;color:var(--muted);margin:0 0 14px}
.row{display:flex;align-items:center;gap:10px;margin:9px 0}
.row .nm{width:150px;font-size:13px;color:var(--txt);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.track{flex:1;height:9px;background:var(--panel2);border-radius:6px;overflow:hidden}
.fill{height:100%;border-radius:6px;background:var(--grad)}
.row .amt{width:78px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700;font-size:13px}
.row .pc{width:42px;text-align:right;color:var(--dim);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:11.5px;text-transform:uppercase;
  letter-spacing:.5px;padding:8px 10px;border-bottom:1px solid var(--line);cursor:pointer;user-select:none}
td{padding:9px 10px;border-bottom:1px solid var(--panel2);font-variant-numeric:tabular-nums}
tr:hover td{background:var(--panel2)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--cyan)}
.pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700}
.pill.measured{background:#10241a;color:var(--green)}
.pill.estimated{background:#2a2410;color:var(--yellow)}
.pill.na{background:#1d2330;color:var(--muted)}
.donut{display:flex;align-items:center;gap:18px}
.ring{width:140px;height:140px;border-radius:50%;flex:none;position:relative}
.ring::after{content:"";position:absolute;inset:20px;background:var(--panel);border-radius:50%}
.ring .ctr{position:absolute;inset:0;display:grid;place-items:center;text-align:center;z-index:2}
.ring .ctr b{font-size:18px}.ring .ctr span{font-size:10.5px;color:var(--muted)}
.leg{display:flex;flex-direction:column;gap:7px;font-size:12.5px}
.leg div{display:flex;align-items:center;gap:8px}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.find{border-left:3px solid var(--green);padding:14px 16px;margin-bottom:12px;
  background:var(--panel);border-radius:0 12px 12px 0;border-top:1px solid var(--line);
  border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
.find.attention{border-left-color:var(--cyan)}.find.data{border-left-color:var(--dim)}
.find h3{margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.find .save{margin-left:auto;color:var(--green);font-weight:800;font-size:15px}
.find p{margin:6px 0;color:var(--muted)}
.find .rec{color:var(--yellow);font-size:13px}
.find .ev{margin-top:8px;font-size:12px;color:var(--dim)}
.banner{background:linear-gradient(135deg,#10241a,#101a24);border:1px solid #1d3a25;
  border-radius:14px;padding:18px 20px;margin-bottom:16px}
.banner .big{font-size:30px;font-weight:800;color:var(--green)}
.spark{width:100%;height:70px}
.gauge{height:26px;background:var(--panel2);border-radius:14px;overflow:hidden;position:relative}
.gauge .g{height:100%;border-radius:14px}
.note{color:var(--dim);font-size:12px;margin-top:6px}
.foot{color:var(--dim);font-size:12px;text-align:center;margin-top:30px}
svg{display:block}
.axis{stroke:var(--line);stroke-width:1}
.tag{font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:6px;padding:1px 6px;margin-left:6px}
</style>
</head>
<body>
<header>
  <div class="logo">$</div>
  <div>
    <h1>Claude Cost Intelligence</h1>
    <div class="sub" id="metaline"></div>
  </div>
</header>
<nav id="nav"></nav>
<div class="wrap">
  <section class="view active" id="overview"></section>
  <section class="view" id="models"></section>
  <section class="view" id="sessions"></section>
  <section class="view" id="projects"></section>
  <section class="view" id="optimize"></section>
  <section class="view" id="budget"></section>
  <div class="foot">Computed locally · zero network · see <span class="mono">docs/METHODOLOGY.md</span> for every formula.</div>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const R = JSON.parse(document.getElementById('data').textContent);
const PALETTE = ['#39d0d8','#8b7bff','#3fb950','#d29922','#f85149','#6e7bff','#56d4c0','#c678dd'];
const m = x => (Math.abs(x)>=0.005? '$'+x.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : '$'+x.toFixed(4));
const num = n => n.toLocaleString('en-US');
const kt = n => n>=1e6? (n/1e6).toFixed(1)+'M' : n>=1e3? (n/1e3).toFixed(1)+'k' : ''+n;
const pc = x => (x*100).toFixed(0)+'%';
const esc = s => (''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const el = (h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstElementChild;};

function bars(items,{name,value,max,color}){
  const mx = max || Math.max(...items.map(value),1e-9);
  return items.map(it=>{
    const v=value(it), f=Math.max(0.02,v/mx);
    const bg = color? `background:${color(it)};` : '';
    return `<div class="row"><div class="nm">${esc(name(it))}</div>
      <div class="track"><div class="fill" style="${bg}width:${(f*100).toFixed(1)}%"></div></div>
      <div class="amt">${m(v)}</div><div class="pc">${pc(v/(R.totals.cost||1))}</div></div>`;
  }).join('');
}

function donut(slices){ // slices: {label,value,color}
  const tot = slices.reduce((a,s)=>a+s.value,0)||1;
  let acc=0, stops=[];
  slices.forEach((s,i)=>{const a=acc/tot*360, b=(acc+s.value)/tot*360; acc+=s.value;
    stops.push(`${s.color} ${a}deg ${b}deg`);});
  const leg = slices.map(s=>`<div><span class="dot" style="background:${s.color}"></span>
    ${esc(s.label)} <span style="color:var(--dim);margin-left:auto">${pc(s.value/tot)}</span></div>`).join('');
  return `<div class="donut"><div class="ring" style="background:conic-gradient(${stops.join(',')})">
    <div class="ctr"><div><b>${m(tot)}</b><br><span>total spend</span></div></div></div>
    <div class="leg">${leg}</div></div>`;
}

function spark(daily, key){ // mini line/area chart
  if(!daily.length) return '<div class="note">no dated events</div>';
  const W=560,H=70,p=4, xs=daily.map((_,i)=>i), ys=daily.map(d=>d[key]);
  const mx=Math.max(...ys,1e-9), nx=daily.length-1||1;
  const X=i=>p+i/nx*(W-2*p), Y=v=>H-p-(v/mx)*(H-2*p);
  let d=`M ${X(0)} ${Y(ys[0])}`; ys.forEach((v,i)=>d+=` L ${X(i)} ${Y(v)}`);
  const area=`M ${X(0)} ${H-p} `+ys.map((v,i)=>`L ${X(i)} ${Y(v)}`).join(' ')+` L ${X(nx)} ${H-p} Z`;
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
    <defs><linearGradient id="ar" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#39d0d8" stop-opacity=".35"/>
      <stop offset="1" stop-color="#39d0d8" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#ar)"/><path d="${d}" fill="none" stroke="#39d0d8" stroke-width="2"/></svg>`;
}

function pareto(rows){
  if(!rows.length) return '';
  const W=560,H=180,p=24, n=rows.length;
  const X=i=>p+i/(Math.max(1,n-1))*(W-2*p), Y=v=>H-p-v*(H-2*p);
  let line=`M ${X(0)} ${Y(rows[0].cum_share)}`;
  rows.forEach((r,i)=>line+=` L ${X(i)} ${Y(r.cum_share)}`);
  const half = `M ${p} ${Y(0.5)} L ${W-p} ${Y(0.5)}`;
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:200px">
    <line class="axis" x1="${p}" y1="${H-p}" x2="${W-p}" y2="${H-p}"/>
    <path d="${half}" stroke="#d29922" stroke-dasharray="4 4" stroke-width="1"/>
    <text x="${W-p}" y="${Y(0.5)-4}" fill="#d29922" font-size="10" text-anchor="end">50% of spend</text>
    <path d="${line}" fill="none" stroke="#8b7bff" stroke-width="2.5"/>
    <text x="${p}" y="16" fill="var(--muted)" font-size="11">cumulative spend share — sessions ranked by cost</text>
  </svg>`;
}

/* ---------- views ---------- */
function vOverview(){
  const cards = R.headline.map(c=>`<div class="card kpi ${c.tone}">
    <div class="lab">${esc(c.label)}</div><div class="val">${esc(c.value)}</div>
    <div class="sub">${esc(c.sub)}</div></div>`).join('');
  const slices = R.by_model.slice(0,6).map((b,i)=>({label:b.key.replace('claude-',''),value:b.cost,color:PALETTE[i%PALETTE.length]}));
  const sess = R.sessions.slice(0,8).map(s=>`<tr><td class="mono">${s.session_id.slice(0,8)}</td>
    <td>${esc(s.project)}</td><td>${m(s.cost)}</td><td>${s.requests}</td><td>${kt(s.tokens)}</td></tr>`).join('');
  const w=R.waste;
  return `
  <div class="grid kpis">${cards}</div>
  <div style="height:16px"></div>
  <div class="card"><h2>Daily spend</h2>${spark(R.daily,'cost')}
    <div class="note">${R.daily.length} day(s) · last point ${R.daily.length?m(R.daily[R.daily.length-1].cost):'—'}</div></div>
  <div style="height:16px"></div>
  <div class="cols">
    <div class="card"><h2>Top sessions by cost</h2>
      <table><thead><tr><th>Session</th><th>Project</th><th>Cost</th><th>Req</th><th>Tokens</th></tr></thead>
      <tbody>${sess}</tbody></table></div>
    <div class="card"><h2>Where money goes</h2>${donut(slices)}</div>
  </div>
  <div style="height:16px"></div>
  <div class="banner"><div class="lab" style="color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.6px">Estimated recoverable</div>
    <div class="big">${m(w.recoverable_mid)} <span style="font-size:15px;color:var(--muted)">(${pc(w.recoverable_pct)} of spend)</span></div>
    <div class="note">band ${m(w.recoverable_low)}–${m(w.recoverable_high)} · estimates, not guarantees · see Optimization tab</div></div>`;
}

function vModels(){
  const rows = R.by_model.map((b,i)=>{
    const eff = b.tokens? b.cost/b.tokens*1000 : 0;
    const cpr = b.requests? b.cost/b.requests : 0;
    return `<tr><td><span class="dot" style="background:${PALETTE[i%PALETTE.length]}"></span> ${esc(b.key.replace('claude-',''))}${b.unpriced?' <span class="tag">unpriced</span>':''}</td>
      <td>${m(b.cost)}</td><td>${pc(b.cost/(R.totals.cost||1))}</td><td>${b.requests}</td>
      <td>${kt(b.tokens)}</td><td>$${eff.toFixed(3)}</td><td>$${cpr.toFixed(4)}</td></tr>`;}).join('');
  return `<div class="card"><h2>Cost by model</h2>
    ${bars(R.by_model,{name:b=>b.key.replace('claude-',''),value:b=>b.cost,color:(b)=>PALETTE[R.by_model.indexOf(b)%PALETTE.length]})}</div>
    <div style="height:16px"></div>
    <div class="card"><h2>Model efficiency</h2>
    <table><thead><tr><th>Model</th><th>Cost</th><th>Share</th><th>Req</th><th>Tokens</th><th>$/1k tok</th><th>$/req</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div class="note">$/1k tok and $/req let you compare efficiency, not just totals. Lower is cheaper per unit of work.</div></div>`;
}

function vSessions(){
  window.__sess = R.sessions.slice();
  const head = ['session_id','project','cost','requests','tokens','duration_min','cache_hit_ratio','errors'];
  const t = `<table id="stbl"><thead><tr>${head.map(h=>`<th data-k="${h}">${h.replace('_',' ')}</th>`).join('')}</tr></thead><tbody></tbody></table>`;
  return `<div class="card"><h2>Spend concentration</h2>${pareto(R.pareto.rows)}
    <div class="note">${R.pareto.sessions_to_half} of ${R.pareto.sessions_total} session(s) reach 50% of spend · top session = ${pc(R.pareto.top1_share)}.</div></div>
    <div style="height:16px"></div>
    <div class="card"><h2>All sessions (click a header to sort)</h2>${t}</div>`;
}
function fillSessions(){
  const tb=document.querySelector('#stbl tbody'); if(!tb) return;
  tb.innerHTML = window.__sess.slice(0,200).map(s=>`<tr>
    <td class="mono">${s.session_id.slice(0,8)}</td><td>${esc(s.project)}</td><td>${m(s.cost)}</td>
    <td>${s.requests}</td><td>${kt(s.tokens)}</td><td>${s.duration_min}</td>
    <td>${pc(s.cache_hit_ratio)}</td><td>${s.errors||''}</td></tr>`).join('');
  document.querySelectorAll('#stbl th').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k; window.__sess.sort((a,b)=> (b[k]>a[k]?1:b[k]<a[k]?-1:0)); fillSessions();});
}

function vProjects(){
  const rows=R.by_project.map(p=>`<tr><td>${esc(p.key)}</td><td>${m(p.cost)}</td>
    <td>${pc(p.cost/(R.totals.cost||1))}</td><td>${p.sessions}</td><td>${p.requests}</td><td>${kt(p.tokens)}</td></tr>`).join('');
  return `<div class="card"><h2>Spend by project</h2>${bars(R.by_project,{name:p=>p.key,value:p=>p.cost})}</div>
    <div style="height:16px"></div>
    <div class="card"><h2>Project detail</h2>
    <table><thead><tr><th>Project</th><th>Cost</th><th>Share</th><th>Sessions</th><th>Req</th><th>Tokens</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function vOptimize(){
  const w=R.waste;
  const head=`<div class="banner"><div class="big">${m(w.recoverable_mid)}</div>
    <div class="note">estimated recoverable · ${pc(w.recoverable_pct)} of spend · band ${m(w.recoverable_low)}–${m(w.recoverable_high)}.
    Estimates use documented reduction ranges — not guarantees.</div></div>`;
  const finds = w.findings.map(f=>{
    const cls = f.kind==='savings'?'':f.kind;
    const conf = f.confidence==='n/a'?'na':f.confidence;
    const save = f.waste_mid>0? `<span class="save">~${m(f.waste_mid)}</span>`:'';
    const ev = f.evidence&&f.evidence.length? `<div class="ev">${f.evidence.slice(0,4).map(e=>esc(JSON.stringify(e))).join('<br>')}</div>`:'';
    return `<div class="find ${cls}"><h3>${esc(f.title)}
      <span class="pill ${conf}">${f.confidence}</span>${save}</h3>
      <p>${esc(f.detail)}</p><p class="rec">→ ${esc(f.recommendation)}</p>${ev}</div>`;}).join('');
  return head + (finds || '<div class="card">No waste patterns detected. 🎉</div>');
}

function vBudget(){
  const p=R.projection, b=R.budget;
  if(!p.available) return '<div class="card">Not enough dated data to project spend.</div>';
  let g='';
  if(b){
    const pctP=Math.min(1.4,b.pct_projected), col = b.state==='over'?'var(--red)':b.state==='warn'?'var(--yellow)':'var(--green)';
    g=`<div class="card"><h2>Monthly budget</h2>
      <div class="gauge"><div class="g" style="width:${Math.min(100,pctP*100).toFixed(0)}%;background:${col}"></div></div>
      <div class="note">${m(b.month_to_date)} spent · projected ${m(b.projected_month)} of ${m(b.budget)}
      (${pc(b.pct_projected)}) · headroom ${m(b.headroom)} · state <b style="color:${col}">${b.state.toUpperCase()}</b></div></div>
      <div style="height:16px"></div>`;
  } else {
    g=`<div class="card note">No budget configured. Set <span class="mono">monthly_budget</span> in cci.config.json to track it here.</div><div style="height:16px"></div>`;
  }
  return g + `<div class="grid kpis">
    <div class="card kpi neutral"><div class="lab">Daily run-rate</div><div class="val">${m(p.daily_run_rate)}</div><div class="sub">${p.window_days}-day avg</div></div>
    <div class="card kpi"><div class="lab">Month to date</div><div class="val">${m(p.month_to_date)}</div><div class="sub">current calendar month</div></div>
    <div class="card kpi warn"><div class="lab">Projected month</div><div class="val">${m(p.projected_month)}</div><div class="sub">${p.days_remaining} day(s) left</div></div>
    <div class="card kpi"><div class="lab">Requests</div><div class="val">${num(R.totals.requests)}</div><div class="sub">${R.totals.sessions} sessions</div></div>
    </div><div class="note">Projection extrapolates the trailing ${p.window_days}-day run-rate. It is an estimate.</div>`;
}

/* ---------- shell ---------- */
const VIEWS=[['overview','Overview',vOverview],['models','Models',vModels],
  ['sessions','Sessions',vSessions],['projects','Projects',vProjects],
  ['optimize','Optimization',vOptimize],['budget','Budget',vBudget]];
const nav=document.getElementById('nav');
VIEWS.forEach(([id,label],i)=>{const btn=document.createElement('button');btn.textContent=label;
  btn.className=i===0?'active':'';btn.onclick=()=>show(id,btn);nav.appendChild(btn);});
function show(id,btn){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active'); if(btn) btn.classList.add('active');
  if(id==='sessions') fillSessions();
}
const meta=R.meta;
document.getElementById('metaline').textContent =
  (meta.start? meta.start.slice(0,10)+' → '+meta.end.slice(0,10)+'  ·  ' : '')+
  `${num(R.totals.requests)} requests · ${R.totals.sessions} sessions · ${R.totals.projects} projects · generated ${R.generated_at.slice(0,10)}`;
VIEWS.forEach(([id,_l,fn])=>{document.getElementById(id).innerHTML=fn();});
</script>
</body>
</html>"""


def render(report: dict, budget: dict | None = None) -> str:
    data = dict(report)
    data["budget"] = budget
    blob = json.dumps(data, separators=(",", ":"))
    # keep the JSON from prematurely closing the <script> tag
    blob = blob.replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", blob)
