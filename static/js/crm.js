// CRM dashboard JS
(function(){
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const api = async (path, opts={}) => {
    opts = Object.assign({ credentials:'include', headers:{'Content-Type':'application/json'} }, opts);
    if (opts.body && typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
    let r; try { r = await fetch(path, opts); } catch(_){ throw new Error('Network error'); }
    if (r.status === 401) throw new Error('Sign in required');
    if (!r.ok) { let m='Failed'; try{const j=await r.json(); m=j.detail||m;}catch(_){}; throw new Error(m); }
    return r.json();
  };

  async function ensureAuth() {
    try {
      await api('/api/admin/settings');
      $('#login-panel').style.display='none';
      $('#main-panel').style.display='';
      return true;
    } catch (_) {
      $('#login-panel').style.display='';
      $('#main-panel').style.display='none';
      return false;
    }
  }

  async function login() {
    const pw = $('#login-pw').value;
    try {
      await api('/api/admin/login', { method:'POST', body:{ password:pw } });
      $('#login-panel').style.display='none';
      $('#main-panel').style.display='';
      await boot();
    } catch (e) { $('#login-msg').textContent = e.message; }
  }

  function showSection(sec) {
    $$('.sec').forEach(s => s.classList.remove('on'));
    $('#sec-' + sec)?.classList.add('on');
    $$('.crm-nav button').forEach(b => b.classList.toggle('on', b.dataset.show === sec));
    if (sec === 'dashboard') loadDashboard();
    if (sec === 'bookings') loadBookings();
    if (sec === 'team') loadTeam();
    if (sec === 'services') loadServices();
    if (sec === 'settings') loadSettings();
    if (sec === 'outreach') loadOutreach();
  }

  async function loadDashboard() {
    let stats;
    try { stats = await api('/api/admin/stats'); } catch(e) { return; }
    const tiles = [
      ['Today', stats.today],
      ['Upcoming 7 days', stats.upcoming_7d],
      ['Revenue 30 d', stats.revenue_30d + ' ' + stats.currency],
      ['Repeat rate', stats.repeat_rate + '%'],
      ['Unique clients (90d)', stats.unique_clients_90d],
    ];
    $('#stats-tiles').innerHTML = tiles.map(([k,v]) => `<div class="tile"><div class="l">${k}</div><div class="v">${v}</div></div>`).join('');

    const sc = stats.status_counts;
    $('#status-mix').innerHTML = ['New','Confirmed','Completed','Cancelled'].map(k => `<div>${k}: <b>${sc[k]||0}</b></div>`).join('');

    const ph = Object.entries(stats.peak_hours).sort((a,b)=>b[1]-a[1]).slice(0,5);
    $('#peak-hours').innerHTML = ph.map(([h,c]) => `<div>${h}:00 — ${c}</div>`).join('') || '—';

    $('#top-services').innerHTML = (stats.top_services||[]).map(s => `<div>${s.name} — ${s.count}</div>`).join('') || '—';
    $('#staff-board').innerHTML = (stats.staff_board||[]).map(s => {
      const max = Math.max(...stats.staff_board.map(x=>x.count), 1);
      return `<div>${s.name} <div class="bar"><i style="width:${(s.count/max*100).toFixed(0)}%"></i></div> ${s.count}</div>`;
    }).join('') || '—';

    // 14-day chart
    draw14dChart();
  }

  async function draw14dChart() {
    const c = $('#chart-14d'); if (!c) return;
    const ctx = c.getContext('2d');
    ctx.clearRect(0,0,c.width,c.height);
    const today = new Date();
    const days = [];
    for (let i=13;i>=0;i--) {
      const d = new Date(today); d.setDate(d.getDate()-i);
      days.push(d.toISOString().slice(0,10));
    }
    let counts = {};
    try {
      const bookings = await api('/api/admin/bookings');
      for (const b of bookings) {
        const k = (b.starts_at || '').slice(0,10);
        if (days.includes(k)) counts[k] = (counts[k]||0) + 1;
      }
    } catch(_){}
    const vals = days.map(d => counts[d]||0);
    const maxv = Math.max(1, ...vals);
    const w = 60;
    const h = 160;
    days.forEach((day,i) => {
      const x = 30 + i*w;
      const v = vals[i];
      const y = h - (v/maxv)*(h-20);
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() || '#c9a14a';
      ctx.fillRect(x, y, w-16, h - y + 10);
      ctx.fillStyle = '#8a93a3';
      ctx.font = '11px sans-serif';
      ctx.fillText(day.slice(5), x, h+24);
      ctx.fillStyle = '#e8ecf2';
      ctx.fillText(v, x + 8, y - 6);
    });
  }

  async function loadBookings() {
    try {
      const q = encodeURIComponent($('#b-q').value || '');
      const st = $('#b-status').value;
      let url = `/api/admin/bookings?q=${q}&status=${st}`;
      const rows = await api(url);
      $('#b-rows').innerHTML = rows.map(b => {
        const contactBits = [];
        if (b.phone) contactBits.push(`<span class="tag">📞 ${escape(b.phone)}</span>`);
        if (b.contact_method === 'wa' && b.contact_value) contactBits.push(`<a class="tag" href="https://wa.me/${(b.contact_value||'').replace(/\D/g,'')}" target="_blank" rel="noopener">WhatsApp</a>`);
        if (b.contact_method === 'tg' && b.contact_value) contactBits.push(`<a class="tag" href="https://t.me/${(b.contact_value||'').replace(/^@/,'')}" target="_blank" rel="noopener">Telegram</a>`);
        return `<tr>
          <td>${(b.starts_at||'').replace('T',' ')}</td>
          <td><b>${escape(b.client_name)}</b><br><span class="muted text-sm">${escape(b.phone)}</span></td>
          <td>${contactBits.join(' ')}</td>
          <td>${escape(b.service)}</td>
          <td>${escape(b.master||'')}</td>
          <td>${b.price} ${b.currency}</td>
          <td><span class="tag tag-${b.status}">${b.status}</span></td>
          <td>
            <select data-bid="${b.id}" data-bstatus>
              <option>New</option><option>Confirmed</option><option>Completed</option><option>Cancelled</option><option>NoShow</option>
            </select>
          </td>
        </tr>`;
      }).join('') || '<tr><td colspan=8 class="muted">No bookings yet.</td></tr>';
      // sync selects
      $$('#b-rows [data-bstatus]').forEach(s => {
        const r = rows.find(x => x.id === parseInt(s.dataset.bid,10));
        if (r) s.value = r.status;
        s.addEventListener('change', async () => {
          await api(`/api/admin/bookings/${s.dataset.bid}`, { method:'PATCH', body:{ status: s.value } });
          loadBookings();
          loadDashboard();
        });
      });
    } catch (e) { $('#b-rows').innerHTML = `<tr><td colspan=8>${e.message}</td></tr>`; }
  }

  async function loadTeam() {
    const staff = await api('/api/staff');
    $('#staff-list').innerHTML = staff.map(s => `
      <div class="tile flex-row" style="margin-bottom:8px;display:flex;align-items:center;gap:14px">
        <img src="${s.avatar||''}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;background:var(--line)" onerror="this.style.background='var(--line)'">
        <div class="flex-1">
          <div><b>${escape(s.name)}</b> — ${escape(s.role||'')}</div>
          <div class="muted text-sm">${escape(s.bio||'')}</div>
          <div class="muted text-sm">Hours: ${escape(s.work_hours||'—')} · TG: ${escape(s.telegram_chat_id||'—')}</div>
        </div>
        <button class="btn-ghost" data-st-edit="${s.id}">Edit</button>
        <button class="btn-ghost" data-st-del="${s.id}">×</button>
      </div>`).join('');
    $$('#staff-list [data-st-edit]').forEach(b => b.addEventListener('click', () => openStaffEdit(parseInt(b.dataset.stEdit,10))));
    $$('#staff-list [data-st-del]').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('Deactivate this master?')) return;
      await api(`/api/admin/staff/${b.dataset.stDel}`, { method:'DELETE' });
      loadTeam();
    }));
  }

  async function openStaffEdit(id) {
    const staff = await api('/api/staff');
    const s = staff.find(x => x.id === id); if (!s) return;
    $('#st-edit-name').value = s.name;
    $('#st-edit-role').value = s.role||'';
    $('#st-edit-bio').value = s.bio||'';
    $('#st-edit-hours').value = s.work_hours||'';
    $('#st-edit-tg').value = s.telegram_chat_id||'';
    $('#st-edit-avatar').src = s.avatar||'';
    $('#staff-edit').classList.add('on');
    $('#staff-edit').dataset.id = id;
  }

  async function loadServices() {
    const svcs = await api('/api/services');
    $('#service-list').innerHTML = svcs.map(s => `
      <div class="tile flex-row" style="margin-bottom:8px">
        <div class="flex-1">
          <div><b>${escape(s.name)}</b> <span class="muted">— ${s.price} PLN · ${s.duration_min} min</span></div>
          <div class="muted text-sm">${escape(s.description||'')}</div>
        </div>
        <button class="btn-ghost" data-sv-del="${s.id}">×</button>
      </div>
    `).join('');
    $$('#service-list [data-sv-del]').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('Deactivate this service?')) return;
      await api(`/api/admin/services/${b.dataset.svDel}`, { method:'DELETE' });
      loadServices();
    }));
  }

  async function loadOutreach() {
    try {
      const rows = await api('/api/admin/demo-links/stats');
      $('#dl-rows').innerHTML = rows.map(r => `
        <tr>
          <td><a href="/d/${r.code}" target="_blank" rel="noopener">/${r.code.slice(0,8)}…</a></td>
          <td>${escape((r.config||{}).brand||'—')}</td>
          <td>${r.views}</td>
          <td class="muted text-sm">${(r.first_view_at||'').slice(0,16)}</td>
          <td class="muted text-sm">${(r.last_view_at||'').slice(0,16)}</td>
          <td><a class="btn-ghost" href="/d/${r.code}" target="_blank">Open</a></td>
        </tr>
      `).join('') || '<tr><td colspan=6 class="muted">No codes yet.</td></tr>';
    } catch(e) {}
  }

  async function loadSettings() {
    const s = await api('/api/admin/settings');
    $('#s-name').value = s.site_name||'';
    $('#s-desc').value = s.site_description||'';
    $('#s-currency').value = s.default_currency||'PLN';
    $('#s-language').value = s.default_language||'en';
    $('#s-hours').value = s.working_hours||'09:00-20:00';
    $('#s-step').value = s.slot_step_min||30;
    $('#s-tg-token').value = s.telegram_bot_token||'';
    $('#s-tg-chat').value = s.telegram_chat_id||'';
    $('#s-logo').src = s.logo_path||'';
  }

  async function saveSettings() {
    const payload = {
      site_name: $('#s-name').value,
      site_description: $('#s-desc').value,
      default_currency: $('#s-currency').value,
      default_language: $('#s-language').value,
      working_hours: $('#s-hours').value,
      slot_step_min: parseInt($('#s-step').value||'30',10),
      telegram_bot_token: $('#s-tg-token').value,
      telegram_chat_id: $('#s-tg-chat').value,
    };
    try { await api('/api/admin/settings', { method:'PATCH', body: payload });
      alert('Saved'); loadSettings();
    } catch(e) { alert(e.message); }
  }

  async function uploadLogo() {
    const f = $('#s-logo-file').files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await fetch('/api/admin/logo', { method:'POST', body: fd, credentials:'include' });
      if (!r.ok) throw new Error('Upload failed: ' + r.status);
      const j = await r.json();
      $('#s-logo').src = j.logo_path + '?_=' + Date.now();
      alert('Logo uploaded and normalized to 512×512');
    } catch (e) { alert(e.message); }
  }

  async function addService() {
    await api('/api/admin/services', { method:'POST', body:{
      name: $('#sv-name').value,
      description: $('#sv-desc').value,
      price: parseFloat($('#sv-price').value||'0'),
      duration_min: parseInt($('#sv-duration').value||'30',10),
      niche: $('#sv-niche').value,
    } });
    $('#service-modal').classList.remove('on');
    loadServices();
  }
  async function addStaff() {
    await api('/api/admin/staff', { method:'POST', body:{
      name: $('#st-name').value,
      role: $('#st-role').value,
      bio: $('#st-bio').value,
      work_hours: $('#st-hours').value,
      telegram_chat_id: $('#st-tg').value,
    } });
    $('#staff-modal').classList.remove('on');
    loadTeam();
  }
  async function saveStaffEdit() {
    const id = parseInt($('#staff-edit').dataset.id, 10);
    await api(`/api/admin/staff/${id}`, { method:'PATCH', body:{
      name: $('#st-edit-name').value,
      role: $('#st-edit-role').value,
      bio: $('#st-edit-bio').value,
      work_hours: $('#st-edit-hours').value,
      telegram_chat_id: $('#st-edit-tg').value,
    } });
    $('#staff-edit').classList.remove('on');
    loadTeam();
  }
  async function uploadStaffAvatar() {
    const id = parseInt($('#staff-edit').dataset.id, 10);
    const f = $('#st-edit-avatar-file').files[0]; if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    try {
      const r = await fetch(`/api/admin/staff/${id}/avatar`, { method:'POST', body: fd, credentials:'include' });
      if (!r.ok) throw new Error('Upload failed: ' + r.status);
      const j = await r.json();
      $('#st-edit-avatar').src = j.avatar + '?_=' + Date.now();
      loadTeam();
    } catch (e) { alert(e.message); }
  }

  function escape(s){ return String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

  async function boot() {
    loadDashboard();
    loadTeam();
    loadServices();
    loadSettings();
    setInterval(loadDashboard, 30000);
    window.addEventListener('focus', loadDashboard);
  }

  function bind() {
    $$('.crm-nav button[data-show]').forEach(b => b.addEventListener('click', () => showSection(b.dataset.show)));
    $('#login-btn').addEventListener('click', login);
    $('#logout-btn').addEventListener('click', async () => { await api('/api/admin/logout', { method:'POST' }); location.href = '/'; });
    $('#b-refresh').addEventListener('click', loadBookings);
    $('#b-q').addEventListener('input', debounce(loadBookings, 250));
    $('#b-status').addEventListener('change', loadBookings);
    $('#s-save').addEventListener('click', saveSettings);
    $('#s-logo-upload').addEventListener('click', uploadLogo);
    $('#sv-add').addEventListener('click', addService);
    $('#st-add').addEventListener('click', addStaff);
    $('#st-edit-save').addEventListener('click', saveStaffEdit);
    $('#st-edit-avatar-upload').addEventListener('click', uploadStaffAvatar);
  }
  function debounce(fn, ms) { let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a),ms); }; }

  document.addEventListener('DOMContentLoaded', async () => {
    bind();
    const ok = await ensureAuth();
    if (ok) await boot();
  });
})();
