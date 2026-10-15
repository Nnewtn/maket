// Outbound workspace: parse, dedupe, render, send, backup.
(function () {
  if (!window.Outreach) return;

  let state = { leads: [], templates: [], filter: { q:'', status:'all', only_new:false } };

  function safeCall(fn, ...args) { try { return fn(...args); } catch(_){ return null; } }

  async function fetchLeads() {
    const q = encodeURIComponent(state.filter.q || '');
    const params = new URLSearchParams();
    if (state.filter.q) params.set('q', state.filter.q);
    if (state.filter.status && state.filter.status !== 'all') params.set('status', state.filter.status);
    if (state.filter.only_new) params.set('only_new', 'true');
    state.leads = await Outreach.api('/api/outbound/leads?' + params.toString());
  }
  async function fetchTemplates() {
    state.templates = await Outreach.api('/api/outbound/templates');
    if (!state.templates.length) {
      // ensure default exists
      await Outreach.api('/api/outbound/templates/1', { method: 'PUT', body: { name:'Default', body:'Hi {name}! Quick preview for your {niche}: {link}' } });
      state.templates = await Outreach.api('/api/outbound/templates');
    }
  }

  function renderLeads() {
    const tbody = document.getElementById('lead-rows');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!state.leads.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="muted" style="padding:18px;text-align:center">No leads yet — paste a base into the import box and click "Parse base".</td></tr>';
      return;
    }
    for (const l of state.leads) {
      const tr = document.createElement('tr');
      tr.dataset.id = l.id;
      tr.innerHTML = `
        <td>${escape(l.name)}</td>
        <td><span class="tag tag-${l.niche}">${l.niche}</span></td>
        <td>
          <a class="muted" href="${contactHref(l)}" target="_blank" rel="noopener" data-action="contact">${escape(l.contact)}</a>
        </td>
        <td><span class="tag tag-${l.status}">${l.status}</span></td>
        <td><small class="muted">${escape((l.updated_at||'').slice(0,16))}</small></td>
        <td>
          <div class="row-actions">
            <a href="#" data-action="wa" class="btn-ghost">WhatsApp</a>
            <a href="#" data-action="copy" class="btn-ghost">Copy</a>
            <a href="#" data-action="preview" class="btn-ghost">Preview link</a>
            <button class="btn-ghost" data-action="status">Next status</button>
            <button class="btn-ghost" data-action="del" title="Remove">×</button>
          </div>
        </td>`;
      tbody.appendChild(tr);
    }
  }

  function contactHref(l) {
    if (l.contact_kind === 'tg' || l.contact.startsWith('@')) {
      const h = l.contact.replace(/^@/, ''); return `https://t.me/${h}`;
    }
    const digits = (l.contact || '').replace(/\D/g, '');
    if (l.contact_kind === 'wa' || digits.length >= 9) return `https://wa.me/${digits}`;
    return `tel:${l.contact.replace(/\s/g, '')}`;
  }

  function escape(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

  function nextStatus(cur) {
    const order = ['New','Contacted','Replied','Converted','Lost'];
    const i = order.indexOf(cur); return order[(i+1) % order.length];
  }

  async function refresh() {
    await fetchLeads();
    renderLeads();
    renderStatus();
  }

  function renderStatus() {
    const el = document.getElementById('out-status');
    if (el) el.textContent = `${state.leads.length} lead${state.leads.length === 1 ? '' : 's'} loaded · workspace shared between team members.`;
  }

  async function login() {
    const pw = (document.getElementById('out-pw')?.value || '');
    try { await Outreach.api('/api/outbound/login', { method:'POST', body:{ password: pw } }); }
    catch (e) { alert(e.message || 'Bad password'); return; }
    document.getElementById('out-login').style.display = 'none';
    document.getElementById('out-main').style.display = '';
    await refresh(); await fetchTemplates();
    renderTemplateSelect();
  }

  async function logout() {
    try { await Outreach.api('/api/outbound/logout', { method:'POST' }); } catch(_){}
    document.getElementById('out-login').style.display = ''; document.getElementById('out-main').style.display='none';
  }

  function renderTemplateSelect() {
    const sel = document.getElementById('tpl-select');
    if (!sel) return;
    sel.innerHTML = ''; state.templates.forEach(t => {
      const o = document.createElement('option'); o.value = t.id; o.textContent = t.name; sel.appendChild(o);
    });
    if (state.templates[0]) {
      document.getElementById('tpl-body').value = state.templates[0].body;
      document.getElementById('tpl-name').value = state.templates[0].name;
    }
  }

  function renderPreview(lead) {
    const tpl = (document.getElementById('tpl-body')?.value || '');
    const linkField = document.getElementById('preview-link').value.trim();
    const link = Outreach._safeUrl(linkField) || ('https://YOURSITE/d/' + ((lead.name||'').toLowerCase().replace(/[^a-z0-9]+/g,'-').slice(0,20) || 'preview'));
    const text = Outreach.detectAndRender(tpl, lead, link);
    document.getElementById('render-preview').textContent = text;
    document.getElementById('render-wa').setAttribute('href', Outreach.waLink(lead.contact) + '?text=' + encodeURIComponent(text));
    document.getElementById('render-copy').onclick = async (e) => {
      e.preventDefault();
      try { await Outreach.copy(text); e.target.textContent = 'Copied ✓'; setTimeout(() => e.target.textContent='Copy text',1100); }
      catch (err) { alert(err.message); }
    };
  }

  async function parse() {
    const text = (document.getElementById('import-text').value || '');
    const status = document.getElementById('import-status');
    try {
      const out = Outreach.parse(text);
      status.style.color = '#6fd06c';
      status.textContent = `Parsed ${out.rows.length} rows · ${out.skipped_dupes} duplicates skipped · ${out.bad} invalid.`;
      // send to server
      const r = await Outreach.api('/api/outbound/leads/bulk', { method:'POST', body:{ rows: out.rows } });
      status.textContent += ` · server inserted ${r.inserted}, skipped ${r.skipped}.`;
      await refresh();
    } catch (e) {
      status.style.color = '#ff8a8a';
      status.textContent = e.message;
    }
  }

  async function saveTemplate() {
    const id = parseInt(document.getElementById('tpl-select').value || '1', 10) || 1;
    const name = (document.getElementById('tpl-name').value || 'Default').slice(0,120);
    const body = document.getElementById('tpl-body').value;
    try {
      await Outreach.api(`/api/outbound/templates/${id}`, { method:'PUT', body:{ name, body } });
      await fetchTemplates(); renderTemplateSelect();
    } catch (e) { alert(e.message); }
  }

  async function importLocal() {
    const text = (document.getElementById('import-text').value || '');
    if (!text.trim()) return;
    try {
      const out = Outreach.parse(text);
      await Outreach.api('/api/outbound/import-backup', { method: 'POST', body: { leads: out.rows } });
      await refresh();
    } catch (e) { alert(e.message); }
  }

  async function doExport() {
    const data = await Outreach.api('/api/outbound/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `outbound-${new Date().toISOString().slice(0,10)}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  function bindRowActions(tbody) {
    tbody.addEventListener('click', async (ev) => {
      const tr = ev.target.closest('tr[data-id]'); if (!tr) return;
      const id = parseInt(tr.dataset.id, 10);
      const lead = state.leads.find(l => l.id === id); if (!lead) return;
      const act = ev.target.dataset.action;
      if (act === 'wa') {
        renderPreview(lead);
        const wa = document.getElementById('render-wa');
        if (wa && wa.href) window.open(wa.href, '_blank');
        await Outreach.api('/api/outbound/send', { method:'POST', body:{ lead_id: id, template_name: document.getElementById('tpl-select').options[document.getElementById('tpl-select').selectedIndex]?.text || 'Default', channel:'wa', rendered: document.getElementById('render-preview').textContent } });
        await refresh();
      } else if (act === 'copy') {
        renderPreview(lead);
        await Outreach.copy(document.getElementById('render-preview').textContent);
        ev.target.textContent = 'Copied ✓'; setTimeout(() => ev.target.textContent='Copy',1100);
      } else if (act === 'preview') {
        renderPreview(lead);
      } else if (act === 'status') {
        const ns = nextStatus(lead.status);
        await Outreach.api(`/api/outbound/leads/${id}`, { method:'PATCH', body:{ status: ns } });
        await refresh();
      } else if (act === 'del') {
        if (!confirm(`Delete lead "${lead.name}"? This cannot be undone.`)) return;
        await Outreach.api(`/api/outbound/leads/${id}`, { method:'DELETE' });
        await refresh();
      } else if (act === 'contact') {
        // analytics ping only
        await Outreach.api('/api/outbound/send', { method:'POST', body:{ lead_id: id, template_name:'opened', channel:'copy', rendered:'contact_opened' } });
      }
    });
  }

  async function init() {
    if (!document.getElementById('out-pw')) return;
    bindRowActions(document.getElementById('lead-rows'));
    document.getElementById('login-btn')?.addEventListener('click', login);
    document.getElementById('logout-btn')?.addEventListener('click', logout);
    document.getElementById('parse-btn')?.addEventListener('click', parse);
    document.getElementById('import-local-btn')?.addEventListener('click', importLocal);
    document.getElementById('save-tpl-btn')?.addEventListener('click', saveTemplate);
    document.getElementById('export-btn')?.addEventListener('click', doExport);
    document.getElementById('only-new')?.addEventListener('change', async (e) => { state.filter.only_new = e.target.checked; await refresh(); });
    document.getElementById('search-q')?.addEventListener('input', async (e) => { state.filter.q = e.target.value; await refresh(); });
    document.getElementById('status-filter')?.addEventListener('change', async (e) => { state.filter.status = e.target.value; await refresh(); });
    document.getElementById('tpl-body')?.addEventListener('input', () => {
      const sel = document.querySelector('#lead-rows tr[data-id]');
      if (sel) renderPreview(state.leads.find(l => l.id === parseInt(sel.dataset.id,10)));
    });
    // poll + focus refresh — safe pull-based sync
    setInterval(refresh, 15000);
    window.addEventListener('focus', refresh);
    // precheck if already authenticated
    try {
      const me = await Outreach.api('/api/outbound/me');
      if (me && me.ok) {
        document.getElementById('out-login').style.display='none';
        document.getElementById('out-main').style.display='';
        await refresh(); await fetchTemplates(); renderTemplateSelect();
      }
    } catch(_){}
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
