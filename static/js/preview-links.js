// Live preview-links builder. Saved automatically as you type.
(function () {
  if (!window.Outreach) return;
  const fieldIds = ['pv-name','pv-logo','pv-niche','pv-layout','pv-theme'];
  const sel = (id) => document.getElementById(id);
  const state = { serial: 0, ready: null, pending: null };

  function cfg() {
    const logoRaw = (sel('pv-logo').value || '').trim();
    return {
      brand: (sel('pv-name').value || '').trim().slice(0,60),
      logo: Outreach._safeUrl(logoRaw) || null,
      niche: sel('pv-niche').value || 'beauty',
      layout: sel('pv-layout').value || 'auto',
      theme: sel('pv-theme').value || 'auto',
      demo: sel('pv-demo').checked,
    };
  }

  function renderStatus(text, kind) {
    const st = sel('pv-status');
    if (!st) return;
    st.textContent = text;
    st.style.color = kind === 'err' ? '#ff8a8a' : (kind === 'ok' ? '#6fd06c' : '#8a93a3');
  }

  function setReady(ready) {
    state.ready = ready;
    const urlEl = sel('pv-url');
    const open = sel('pv-open');
    const copy = sel('pv-copy');
    if (!ready) {
      urlEl.value = '';
      copy.disabled = true; open.setAttribute('href', '#');
      renderStatus('Saving your short link…', 'idle');
      return;
    }
    const full = location.origin + ready.path;
    urlEl.value = full;
    open.setAttribute('href', full + '?inspect=1');
    copy.disabled = false;
    renderStatus('Ready · changes are saved automatically', 'ok');
  }

  async function persist() {
    const serial = ++state.serial;
    const data = cfg();
    setReady(null);
    Outreach.save('preview-builder-v6', data);
    try {
      const r = await Outreach.api('/api/admin/demo-links', { method: 'POST', body: data });
      if (serial !== state.serial) return; // ignore stale
      if (!r.path) throw new Error('Server returned no link.');
      setReady(r);
    } catch (e) {
      if (serial !== state.serial) return;
      renderStatus('Could not save short link: ' + e.message, 'err');
      setReady(null); // do not trash a previously generated link
    }
  }

  function debounce(fn, ms) {
    let t = null;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  }

  function init() {
    if (!sel('pv-name')) return;
    const draft = Outreach.load('preview-builder-v6') || {};
    sel('pv-name').value = draft.brand || '';
    sel('pv-logo').value = draft.logo || '';
    sel('pv-niche').value = draft.niche || 'beauty';
    sel('pv-layout').value = draft.layout || 'auto';
    sel('pv-theme').value = draft.theme || 'auto';
    sel('pv-demo').checked = draft.demo !== false;
    const debounced = debounce(persist, 220);
    fieldIds.forEach(id => {
      const el = sel(id); if (!el) return;
      el.addEventListener('input', debounced);
      el.addEventListener('change', debounced);
    });
    sel('pv-copy').addEventListener('click', async (ev) => {
      ev.preventDefault();
      const url = sel('pv-url').value;
      if (!url) return;
      try {
        await Outreach.copy(url);
        const old = sel('pv-copy').textContent;
        sel('pv-copy').textContent = '✓ Copied';
        setTimeout(() => { sel('pv-copy').textContent = old; }, 1300);
      } catch (e) {
        renderStatus(e.message, 'err');
      }
    });
    if (!draft.brand) persist();
    else persist(); // rehydrate saved path
  }

  Outreach._safeUrl = function (v) {
    if (!v) return '';
    v = v.trim();
    if (/^(javascript|data|vbscript):/i.test(v)) return '';
    if (!/^https?:\/\//i.test(v)) return '';
    return v.slice(0, 500);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
