// Shared Outreach module for both builder and workspace pages.
(function () {
  const EXPORTS = {};
  EXPORTS._safeUrl = v => {try {let u=new URL(v);return ['https:','http:'].includes(u.protocol)?u.href:'';}catch(_){return '';}};

  EXPORTS.csvSplit = function (line) {
    // Supports `|`, `;`, tab, or comma. Quoted fields OK.
    const out = []; let cur = ''; let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (c === '"') { if (inQ && line[i+1] === '"') { cur += '"'; i++; } else inQ = !inQ; continue; }
      if (!inQ && (c === '|' || c === ';' || c === '\t' || c === ',')) {
        out.push(cur); cur = ''; continue;
      }
      cur += c;
    }
    out.push(cur);
    return out.map(s => s.trim());
  };

  EXPORTS.parse = function (text) {
    if (text.length > 500 * 1024) { const e = new Error("Import is too large. Maximum 500 KB."); e.code="TOO_LARGE"; throw e; }
    const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
    const rows = []; const seen = new Set();
    let bad = 0;
    for (let i = 0; i < lines.length; i++) {
      const cols = EXPORTS.csvSplit(lines[i]);
      if (cols.length < 3) { bad++; continue; }
      const [name, niche, contact, notes] = cols;
      if (!name || !niche || !contact) { bad++; continue; }
      const nicheOk = ['beauty','barber','auto','detailing'].includes(niche.toLowerCase());
      if (!nicheOk) { bad++; continue; }
      const normDigits = (contact || '').replace(/\D/g,'');
      if (normDigits.length >= 7 && seen.has(normDigits)) continue;
      if (normDigits.length) seen.add(normDigits);
      const kind = contact.startsWith('@') ? 'tg'
                 : (/^\+?\d[\d\s\-()]+$/.test(contact) && normDigits.length >= 9) ? 'wa'
                 : 'phone';
      if (rows.length >= 500) { const e = new Error("Maximum 500 valid contacts per browser workspace."); e.code="CAP"; throw e; }
      rows.push({ name: name.slice(0,120), niche: niche.toLowerCase(), contact: contact.slice(0,200), contact_kind: kind, notes: (notes||'').slice(0,600) });
    }
    return { rows, bad, skipped_dupes: lines.length - bad - rows.length };
  };

  EXPORTS.detectAndRender = function (template, lead, link) {
    return (template || '')
      .replaceAll('{name}', lead.name || '')
      .replaceAll('{niche}', lead.niche || '')
      .replaceAll('{contact}', lead.contact || '')
      .replaceAll('{link}', link || '');
  };

  EXPORTS.waLink = function (contact) {
    const digits = (contact || '').replace(/\D/g,'');
    return digits ? `https://wa.me/${digits}` : '';
  };

  EXPORTS.tgLink = function (contact) {
    let h = (contact || '').trim();
    if (h.startsWith('@')) h = h.slice(1);
    return h ? `https://t.me/${h}` : '';
  };

  EXPORTS.phoneLink = function (contact) {
    return `tel:${(contact || '').replace(/\s/g,'')}`;
  };

  EXPORTS.api = async function (url, opts = {}) {
    const opt = Object.assign({
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      signal: undefined,
    }, opts);
    if (opt.body && typeof opt.body !== 'string') opt.body = JSON.stringify(opt.body);
    let res;
    try {
      res = await fetch(url, opt);
    } catch (e) {
      throw new Error('Network error, please retry.');
    }
    if (res.status === 401) {
      const e = new Error('Sign in to the CRM first. Your local draft has not been deleted.'); e.code=401; throw e;
    }
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status}).`);
    return data;
  };

  EXPORTS.copy = async function (text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // fallback for old/mobile WebViews
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly',''); ta.style.position='absolute'; ta.style.left='-9999px';
      document.body.appendChild(ta); ta.select();
      const ok = document.execCommand('copy'); document.body.removeChild(ta);
      if (!ok) throw new Error('Clipboard blocked. Select and copy the text manually.');
      return true;
    }
  };

  EXPORTS.save = function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch(_){} };
  EXPORTS.load = function (k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch(_){ return null; } };

  // Browser-only globals
  if (typeof window !== 'undefined') {
    Object.assign(window, EXPORTS);
    window.Outreach = EXPORTS;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = EXPORTS;
  }
})();
