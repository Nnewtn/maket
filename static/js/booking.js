/* Public booking flow + currency/language dropdowns + client self-service
   + waitlist + NICHE presets + personalized brand preview via URL params:
   ?brand=Salon+Name&logo=https://…&niche=barber — per-visitor, DB untouched. */
const $ = (s) => document.querySelector(s);

const state = {
  settings: {}, services: [], staff: [],
  rates: { PLN: 1, USD: 0.25, EUR: 0.23 },
  currency: "PLN", slot: null, waitlistOffered: false,
  previewName: "", previewLogo: "",
};
const SYM = { PLN: "zł", USD: "$", EUR: "€" };

/* Preview context is isolated to THIS URL or immutable /d/ record. */
const params = new URLSearchParams(location.search);
const previewConfig = window.__DEMO_CONFIG__ || {
  brand:params.get('brand')||'', logo:params.get('logo')||'', niche:params.get('niche')||'',
  theme:params.get('theme')||'', layout:params.get('layout')||'', demo:params.get('demo')==='1'
};
const isPreview = !!window.__DEMO_CONFIG__ || ['beauty','barber','auto','detailing'].includes(previewConfig.niche);
let manualTheme=false;
function applyPreviewParams() {
  state.previewName=String(previewConfig.brand||'').slice(0,120);
  state.previewLogo=/^(https?:\/\/|\/static\/uploads\/)/.test(previewConfig.logo||'')?previewConfig.logo:'';
  if(isPreview){
    NicheContent.set(previewConfig.niche||'beauty');
    const root=document.documentElement,preset=NicheContent.preset;
    root.setAttribute('data-theme',previewConfig.theme||preset.theme);
    root.setAttribute('data-layout',previewConfig.layout||preset.layout);
    const banner=document.createElement('div');banner.id='preview-banner';banner.className='preview-banner';
    document.body.prepend(banner);updatePreviewBanner();
    document.querySelector('#my-open').hidden=true;
    // Browser-side logo sampling: no arbitrary server-side URL fetching.
    // CORS-protected logos still display; sampling falls back to niche palette.
    if(state.previewLogo&&!previewConfig.theme){
      const img=new Image();img.crossOrigin='anonymous';img.referrerPolicy='no-referrer';
      img.onload=()=>{try{
        if(manualTheme)return;
        const canvas=document.createElement('canvas');canvas.width=canvas.height=32;
        const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0,32,32);
        const data=ctx.getImageData(0,0,32,32).data;let best=null,score=0;
        for(let i=0;i<data.length;i+=4){const r=data[i],g=data[i+1],b=data[i+2],mx=Math.max(r,g,b),mn=Math.min(r,g,b),sat=mx?(mx-mn)/mx:0,lum=(r*.2126+g*.7152+b*.0722)/255;
          const rank=sat*(1-Math.abs(lum-.5));if(data[i+3]>180&&lum>.12&&lum<.9&&rank>score){score=rank;best=[r,g,b];}}
        if(best&&score>.15){const lum=(best[0]*.2126+best[1]*.7152+best[2]*.0722)/255;
          root.style.setProperty('--accent','#'+best.map(v=>v.toString(16).padStart(2,'0')).join(''));
          root.style.setProperty('--accent-ink',lum>.45?'#101218':'#fff');}
      }catch{/* tainted canvas: retain safe preset */}};
      img.src=state.previewLogo;
    }
  }
}
function updatePreviewBanner(){const pl=currentLang()==='pl',el=document.getElementById('preview-banner');if(el)el.textContent=pl?'Wersja demonstracyjna • przykładowe ceny • rezerwacje testowe nie trafiają do salonu.':'Personalized demo • illustrative prices • test bookings are not sent to the business.';}
function escapeHTML(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function trackPreview(){
  if(!previewConfig.code||params.get('inspect')==='1'||window.self!==window.top)return;
  const send=()=>{if(document.visibilityState!=='visible')return;
    document.removeEventListener('visibilitychange',send);
    let visit;try{const key='demo-visit:'+previewConfig.code;visit=sessionStorage.getItem(key);if(!visit){visit=crypto.randomUUID().replaceAll('-','');sessionStorage.setItem(key,visit);}}catch{visit=crypto.randomUUID().replaceAll('-','');}
    fetch('/api/demo-links/'+previewConfig.code+'/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({visit_id:visit}),keepalive:true}).catch(()=>{});
  };if(document.visibilityState==='visible')send();else document.addEventListener('visibilitychange',send);
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3500);
}

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function money(basePrice) {
  const v = basePrice * (state.rates[state.currency] ?? 1);
  const rounded = v % 1 ? v.toFixed(2) : v.toFixed(0);
  return state.currency === "PLN" ? `${rounded} ${SYM.PLN}` : `${SYM[state.currency]}${rounded}`;
}

/* ---------- dropdowns ---------- */
function initDropdown(btnId, menuId) {
  const btn = $(btnId), menu = $(menuId);
  if (!btn || !menu) return;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    document.querySelectorAll(".dd-menu").forEach(m => { if (m !== menu) m.classList.add("hidden"); });
    menu.classList.toggle("hidden");
  });
}
document.addEventListener("click", () =>
  document.querySelectorAll(".dd-menu").forEach(m => m.classList.add("hidden")));

function setCurrency(cur) {
  state.currency = cur;
  localStorage.setItem("site-currency", cur);
  $("#cur-current").textContent = cur;
  document.querySelectorAll("[data-cur-opt]").forEach(b =>
    b.classList.toggle("dd-active", b.dataset.curOpt === cur));
  renderServices();
}

/* ---------- rendering ---------- */
function renderServices() {
  const previous=$("#service").value;
  if(isPreview)state.services=NicheContent.services();
  $("#service").innerHTML = state.services.map(s =>
    `<option value="${s.id}">${escapeHTML(s.name)} — ${money(s.price)} (${s.duration_min} ${t("min")})</option>`
  ).join("");
  if(previous)$("#service").value=previous;
  $("#services-grid").innerHTML = state.services.map(s => `
    <div class="surface rounded-2xl p-6 border brd svc-card">
      <div class="text-lg font-semibold">${escapeHTML(s.name)}</div>
      <p class="dim text-sm mt-2">${escapeHTML(s.description || "")}</p>
      <div class="mt-4 flex justify-between items-center">
        <span class="accent font-bold text-xl">${money(s.price)}</span>
        <span class="dim text-sm">${s.duration_min} ${t("min")}</span>
      </div>
    </div>`).join("");
}

function renderStaff() {
  const previous=$("#master").value;
  if(isPreview)state.staff=NicheContent.staff();
  const opts = [`<option value="0">${t("any_master")}</option>`]
    .concat(state.staff.map(s => `<option value="${s.id}">${escapeHTML(s.name)}</option>`));
  $("#master").innerHTML = opts.join("");
  if(previous)$("#master").value=previous;
  $("#team-grid").innerHTML = state.staff.map(s => `
    <div class="surface rounded-2xl p-5 border brd text-center team-card">
      ${s.avatar_url
        ? `<img src="${escapeHTML(s.avatar_url)}" class="avatar" style="object-fit:cover" alt="${escapeHTML(s.name)}" />`
        : `<div class="avatar">${s.name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()}</div>`}
      <div class="font-semibold mt-3">${escapeHTML(s.name)}</div>
      <div class="dim text-xs mt-1">${escapeHTML(s.role || "")}</div>
    </div>`).join("");
}

function renderSettings() {
  const s = state.settings;
  const name = state.previewName || s.company_name;
  const logo = state.previewLogo || s.logo_url;
  document.title = name;
  $("#brand-name").textContent = name;
  $("#footer-name").textContent = name;
  $("#hero-desc").textContent = isPreview ? NicheContent.description() : s.description;
  updatePreviewBanner();
  $("#hours-line").textContent = t("open_daily") + " " + s.opening_hours;
  if (logo) {
    $("#brand-logo").onerror=()=>$("#brand-logo").classList.add("hidden");
    $("#brand-logo").referrerPolicy="no-referrer";
    $("#brand-logo").src = logo;
    $("#brand-logo").classList.remove("hidden");
  }
}

/* ---------- slots + waitlist ---------- */
async function loadSlots() {
  const date = $("#date").value;
  const staffId = Number($("#master").value || 0);
  state.slot = null;
  state.waitlistOffered = false;
  $("#submit-btn").disabled = true;
  const grid = $("#slot-grid");
  if (!date) {
    grid.innerHTML = `<span class="dim text-sm">${t("pick_date")}</span>`;
    return;
  }
  try {
    let slots;
    if(isPreview){
      const duration=state.services.find(x=>x.id===Number($("#service").value))?.duration_min||60;
      slots=[];for(let minute=9*60;minute+duration<=20*60;minute+=30){
        const time=String(Math.floor(minute/60)).padStart(2,'0')+':'+String(minute%60).padStart(2,'0');
        if(new Date(date+'T'+time)>new Date())slots.push(time);
      }
    }else({slots}=await api(`/api/availability?date=${date}&staff_id=${staffId}`));
    if (slots.length) {
      grid.innerHTML = slots.map(tm =>
        `<button type="button" class="slot" data-t="${tm}">${tm}</button>`).join("");
      grid.querySelectorAll(".slot").forEach(b =>
        b.addEventListener("click", () => {
          grid.querySelectorAll(".slot").forEach(x => x.classList.remove("active"));
          b.classList.add("active");
          state.slot = b.dataset.t;
          $("#submit-btn").disabled = false;
        }));
    } else {
      state.waitlistOffered = true;
      grid.innerHTML = `
        <div class="w-full">
          <span class="dim text-sm">${t("no_slots")}</span>
          <button type="button" id="wl-btn" class="btn-accent mt-3 px-5 py-2.5 rounded-xl text-sm font-semibold">${t("wl_join")}</button>
        </div>`;
      $("#wl-btn").addEventListener("click", joinWaitlist);
    }
  } catch (e) {
    grid.innerHTML = `<span class="dim text-sm">${escapeHTML(e.message)}</span>`;
  }
}

async function joinWaitlist() {
  if(isPreview){toast(currentLang()==='pl'?'Lista oczekujących: tryb demonstracyjny, dane nie zostały wysłane.':'Demo waitlist only — no data was sent.');return;}
  try {
    await api("/api/waitlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: $("#name").value.trim() || "Waitlist client",
        phone: $("#phone").value.trim(),
        contact_method: document.querySelector('input[name="contact"]:checked').value,
        contact_handle: $("#handle").value.trim(),
        service_id: Number($("#service").value || 0),
        staff_id: Number($("#master").value || 0),
        date_pref: $("#date").value || "",
      }),
    });
    toast(t("wl_ok"));
  } catch (e) { toast(e.message); }
}

function syncContactUI() {
  const m = document.querySelector('input[name="contact"]:checked').value;
  $("#handle-row").classList.toggle("hidden", m === "Call");
  $("#handle").placeholder = m === "Telegram" ? t("handle_ph") : t("phone_ph");
  $("#handle-hint").textContent = m === "WhatsApp" ? t("wa_hint") : "";
}

async function submitBooking(ev) {
  ev.preventDefault();
  if (!state.slot) return;
  const btn = $("#submit-btn");
  btn.disabled = true;
  btn.textContent = t("sending");
  try {
    const r = isPreview ? {staff_name:state.staff.find(x=>x.id===Number($("#master").value))?.name||state.staff[0]?.name} : await api("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: $("#name").value.trim(),
        phone: $("#phone").value.trim(),
        service_id: Number($("#service").value),
        staff_id: Number($("#master").value || 0),
        start_time: `${$("#date").value}T${state.slot}`,
        contact_method: document.querySelector('input[name="contact"]:checked').value,
        contact_handle: $("#handle").value.trim(),
      }),
    });
    $("#booking-form").classList.add("hidden");
    $("#booking-success").classList.remove("hidden");
    if(isPreview){$("#booking-success h3").textContent=currentLang()==='pl'?'Rezerwacja testowa zakończona':'Demo booking complete';$("#booking-success p:last-child").textContent=currentLang()==='pl'?'To tylko demonstracja. Żadna rezerwacja nie została wysłana.':'This is a simulation. No real appointment was created.';}
    $("#ok-master").textContent = r.staff_name ? `${t("ok_master")} ${r.staff_name}` : "";
  } catch (e) {
    toast(e.message);
    if (e.message.toLowerCase().includes("slot") || e.message.toLowerCase().includes("booked")) loadSlots();
    btn.disabled = false;
    btn.textContent = t("submit");
  }
}

/* ---------- client self-service ---------- */
function openMy() { if(isPreview){toast('Client portal is disabled in demo previews.');return;} $("#my-modal").classList.remove("hidden"); $("#my-phone").focus(); }
function closeMy() { $("#my-modal").classList.add("hidden"); }

async function lookupMy() {
  const phone = $("#my-phone").value.trim();
  const box = $("#my-results");
  box.innerHTML = `<span class="dim text-sm">…</span>`;
  try {
    const rows = await api("/api/my-bookings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone }),
    });
    box.innerHTML = rows.length ? rows.map(b => `
      <div class="surface-2 border brd rounded-xl p-4 flex items-center justify-between gap-3">
        <div>
          <div class="font-semibold">${escapeHTML(b.service_name)} · ${escapeHTML(b.staff_name)}</div>
          <div class="dim text-xs mt-1">${new Date(b.start_time).toLocaleString(
            currentLang() === "pl" ? "pl-PL" : "en-GB",
            { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
            · <span class="badge b-${b.status}">${b.status}</span></div>
        </div>
        ${(b.status === "New" || b.status === "Confirmed")
          ? `<button onclick="cancelMy(${b.id})" class="text-red-400 text-sm font-semibold whitespace-nowrap">${t("my_cancel")}</button>` : ""}
      </div>`).join("")
      : `<span class="dim text-sm">${t("my_none")}</span>`;
  } catch (e) { box.innerHTML = `<span class="dim text-sm">${escapeHTML(e.message)}</span>`; }
}

async function cancelMy(id) {
  try {
    await api(`/api/bookings/${id}/cancel`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: $("#my-phone").value.trim() }),
    });
    toast(t("my_cancelled"));
    lookupMy();
  } catch (e) { toast(e.message); }
}

/* ---------- boot ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  try {
    applyPreviewParams();
    trackPreview();

    const [settings, services, staff] = isPreview ? [{company_name:previewConfig.brand||"Demo Studio",description:"",opening_hours:"09:00-20:00",currency:"PLN",logo_url:""},NicheContent.services(),NicheContent.staff()] : await Promise.all([
      api("/api/settings/public"), api("/api/services"), api("/api/staff")]);
    state.settings = settings;
    state.services = services;
    state.staff = staff;
    state.currency = settings.currency || "PLN";

    try {
      const fx = await api("/api/fx");
      if (fx && fx.rates) state.rates = fx.rates;
    } catch { /* fallback rates stay */ }

    initDropdown("#cur-btn", "#cur-menu");
    initDropdown("#lang-btn", "#lang-menu");
    document.querySelectorAll("[data-cur-opt]").forEach(b =>
      b.addEventListener("click", () => setCurrency(b.dataset.curOpt)));
    document.querySelectorAll("[data-lang-opt]").forEach(b =>
      b.addEventListener("click", () => applyLang(b.dataset.langOpt)));

    const savedCur = localStorage.getItem("site-currency");
    if (savedCur && SYM[savedCur]) state.currency = savedCur;
    $("#cur-current").textContent = state.currency;
    document.querySelectorAll("[data-cur-opt]").forEach(b =>
      b.classList.toggle("dd-active", b.dataset.curOpt === state.currency));

    applyLang(currentLang());
    renderSettings();
    renderServices();
    renderStaff();

    const d = $("#date");
    const now=new Date();d.min=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10);
    d.addEventListener("change", loadSlots);
    $("#master").addEventListener("change", loadSlots);
    $("#service").addEventListener("change", loadSlots);
    document.querySelectorAll('input[name="contact"]').forEach(r =>
      r.addEventListener("change", syncContactUI));
    syncContactUI();
    $("#booking-form").addEventListener("submit", submitBooking);
    $("#my-open").addEventListener("click", openMy);
    $("#my-close").addEventListener("click", closeMy);
    $("#my-lookup").addEventListener("click", lookupMy);
    $("#my-modal").addEventListener("click", (e) => { if (e.target.id === "my-modal") closeMy(); });

    document.addEventListener("langchange", () => {
      renderSettings(); renderServices(); renderStaff(); syncContactUI(); loadSlots();
      $("#submit-btn").textContent = t("submit");
      $("#lang-current").textContent = currentLang().toUpperCase();
    });
  } catch (e) {
    toast("Failed to load page data: " + e.message);
  }
});
