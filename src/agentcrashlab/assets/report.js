'use strict';
(() => {
 const report = JSON.parse(document.getElementById('report-data').textContent);
 const runs = report.runs;
 const scenarios = [...new Map(runs.map(r => [r.scenario.id, r.scenario])).values()];
 const $ = id => document.getElementById(id);
 const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = String(text); return n; };
 const money = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
 // Currency is illustrative fixture USD; underlying assertions always use integer cents.
 const state = {id: scenarios.some(s => s.id === 'response-loss') ? 'response-loss' : scenarios[0].id, step: 0, timer: null};
 const selected = () => runs.filter(r => r.scenario.id === state.id);
 const limit = () => Math.max(...selected().map(r => r.events.length), 1);
 const reference = runs.every(r => r.policy_kind === 'reference' && r.mode !== 'recorded-tool-calls');
 $('provenance').textContent = reference ? 'Deterministic reference policies. No LLM invoked. Values below come from executed test fixtures.' : 'User-supplied policy or recorded-call replay. These results are not a model leaderboard.';
 $('run-count').textContent = runs.length;
 $('scenario-count').textContent = scenarios.length;
 $('check-count').textContent = [...new Set(runs.map(r => r.checks.length))].join(' / ');
 $('transport-label').textContent = [...new Set(runs.map(r => r.transport.toUpperCase()))].join(' + ') + ' / LOCAL FIXTURE';
 const tabNames = {'clean':'01 / Clean control','response-loss':'02 / Response lost','pre-commit-timeout':'03 / Before commit','permission-revoked':'04 / Revoked access'};
 scenarios.forEach((s, i) => {
   const b = el('button', 'scenario-tab', tabNames[s.id] || `${i+1} / ${s.title}`);
   b.type = 'button'; b.setAttribute('role','tab'); b.dataset.scenario = s.id;
   b.addEventListener('click', () => choose(s.id));
   b.addEventListener('keydown', e => {
     if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
     e.preventDefault(); let index = scenarios.findIndex(x => x.id === state.id);
     if (e.key === 'Home') index = 0; else if (e.key === 'End') index = scenarios.length - 1;
     else index = (index + (e.key === 'ArrowRight' ? 1 : -1) + scenarios.length) % scenarios.length;
     choose(scenarios[index].id); $('scenario-tabs').children[index].focus();
   });
   $('scenario-tabs').append(b);
 });
 function stop() { if (state.timer !== null) clearInterval(state.timer); state.timer = null; $('play').textContent = '▶ Replay trace'; }
 function choose(id) {
   stop(); state.id = id; state.step = limit();
   const s = selected()[0].scenario;
   for (const b of $('scenario-tabs').children) { const active = b.dataset.scenario === id; b.setAttribute('aria-selected', active); b.tabIndex = active ? 0 : -1; }
   $('scenario-id').textContent = `SCENARIO / ${s.id.toUpperCase()}`;
   $('scenario-title').textContent = s.title;
   $('scenario-description').textContent = s.description;
   $('fault-chip').textContent = s.faults.length ? s.faults.map(f => `CALL ${f.on_call} · ${f.kind.replaceAll('_',' ').toUpperCase()}`).join(' / ') : 'CONTROL · NO INJECTED FAULT';
   $('scrubber').max = limit(); render();
   $('announcement').textContent = `${s.title} selected. Final results shown.`;
 }
 function metric(label, value, cls = '') { const n = el('div','metric'); n.append(el('span','metric-value ' + cls,value), el('span','metric-label',label)); return n; }
 function describe(e) {
   const d = e.data;
   const known = {
     'run.started': () => `Run started · ${d.agent}`,
     'tool.call': () => `create_order() · call ${d.call}${d.arguments.idempotency_key ? ' · key present' : ' · no key'}`,
     'fault.injected': () => `FAULT · ${d.fault_kind.replaceAll('_',' ')}`,
     'backend.order_created': () => `COMMITTED order #${d.order_id} · ${money(d.total_cents)}`,
     'backend.idempotent_replay': () => `REUSED order #${d.order_id} · no second write`,
     'transport.response_lost': () => `Response lost · order #${d.order_id} already committed`,
     'tool.response': () => `Response received · order #${d.order_id}`,
     'tool.error': () => `Agent sees: ${d.code}`,
     'agent.finished': () => `Agent returns: ${d.status}`,
     'agent.error': () => `Policy error: ${d.exception_type}`,
     'tool.limit_reached': () => `Tool-call limit reached: ${d.limit}`
   };
   return known[e.kind] ? known[e.kind]() : e.kind;
 }
 function panel(run, index) {
   const p = el('article','panel'); p.dataset.agent = run.agent_name;
   const top = el('div','panel-top'), titles = el('div');
   titles.append(el('p','panel-index',`${String(index+1).padStart(2,'0')} / ${run.policy_kind === 'reference' ? 'REFERENCE POLICY' : run.mode === 'recorded-tool-calls' ? 'RECORDED REPLAY' : 'CUSTOM POLICY'}`));
   titles.append(el('h4','panel-title',run.policy_kind === 'reference' && run.agent_name === 'naive' ? 'Naive retry' : run.policy_kind === 'reference' && run.agent_name === 'resilient' ? 'Stable-key retry' : run.agent_name));
   top.append(titles,el('span','badge ' + (run.passed?'pass':'fail'),run.passed ? '✓ CHECKS PASSED' : '✕ CHECKS FAILED')); p.append(top);
   const body = el('div','panel-body'), claim = el('div','claim'), claimContent = el('div','claim-content');
   claimContent.append(el('span','claim-status',run.agent_result.status.toUpperCase()),el('p','claim-text',run.agent_result.message));
   claim.append(el('span','claim-label','AGENT CLAIM'),claimContent); body.append(claim);
   const total = run.orders.reduce((a,o) => a + o.total_cents,0), metrics = el('div','metrics');
   metrics.append(metric('COMMITTED ORDERS',run.orders.length,run.orders.length > run.scenario.expect.orders ? 'fail':'pass'),
     metric('TOTAL COMMITTED',money(total),total > run.scenario.task.max_total_cents ? 'fail':''),
     metric('CHECKS PASSED',`${run.checks.filter(c=>c.passed).length}/${run.checks.length}`));
   body.append(metrics);
   const checks = el('div','checks');
   run.checks.forEach(c => {const row = el('div','check' + (c.passed?'':' failed')); row.title = c.detail + '\nExpected: ' + JSON.stringify(c.expected) + '\nActual: ' + JSON.stringify(c.actual); row.append(el('span','check-mark',c.passed?'✓':'✕'),el('span','check-title',c.title),el('small','',c.passed?'PASS':'FAIL')); checks.append(row);});
   body.append(checks);
   const evidence = el('details','evidence'); evidence.append(el('summary','',`Final backend snapshot · ${run.orders.length} order${run.orders.length===1?'':'s'}`));
   if (run.orders.length) {
     const table = el('table','evidence-table'), head = el('thead'), tr = el('tr');
     ['ID','SKU','QTY','TOTAL','AUTH'].forEach(t=>tr.append(el('th','',t))); head.append(tr); table.append(head);
     const tbody = el('tbody'); run.orders.forEach(o=>{const row = el('tr'); [o.order_id,o.sku,o.quantity,money(o.total_cents),o.authorized?'YES':'NO'].forEach(t=>row.append(el('td','',t))); tbody.append(row);}); table.append(tbody); evidence.append(table);
   } else evidence.append(el('p','mono muted','No order was committed.'));
   body.append(evidence); p.append(body);
   const trace = el('div','trace'), head = el('div','trace-head'), visible = Math.min(state.step,run.events.length);
   head.append(el('span','','RECORDED TOOL TRACE'),el('span','',`${visible} / ${run.events.length} EVENTS`)); trace.append(head);
   const events = el('div','trace-events');
   if (!visible) events.append(el('div','event empty','Ready. Advance the recorded trace.'));
   run.events.slice(0,visible).forEach(e=>{
     const cls = e.kind === 'fault.injected' || e.kind === 'transport.response_lost' ? 'fault' : e.kind === 'backend.order_created' ? 'write' : e.kind === 'backend.idempotent_replay' ? 'reuse' : '';
     const row = el('div','event '+cls), data = el('details','event-body');
     data.append(el('summary','',describe(e)),el('pre','',JSON.stringify(e.data,null,2)));
     row.append(el('span','event-num',String(e.seq).padStart(2,'0')),data); events.append(row);
   });
   trace.append(events); p.append(trace); return p;
 }
 function render() {
   const rs = selected(), panels = $('panels'); panels.replaceChildren(...rs.map(panel)); panels.classList.toggle('single',rs.length===1);
   $('scrubber').value = state.step; $('frame-counter').textContent = `${state.step} / ${limit()}`;
   document.querySelectorAll('.trace-events').forEach(n=>n.scrollTop=n.scrollHeight);
 }
 $('play').addEventListener('click', () => {
   if (state.timer !== null) {stop(); return;}
   if (state.step >= limit()) state.step = 0;
   $('play').textContent = 'Ⅱ Pause trace'; render();
   const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
   state.timer = setInterval(()=>{state.step++; render(); if (state.step>=limit()) {stop(); $('announcement').textContent = 'Recorded trace finished.';}}, reduced ? 1000 : 450);
 });
 $('reset').addEventListener('click',()=>{stop(); state.step=0; render();});
 $('scrubber').addEventListener('input',e=>{stop(); state.step=Number(e.target.value); render();});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
 choose(state.id);
})();
