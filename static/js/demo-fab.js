/* Demo mode: floating DESIGN switcher, enabled ONLY via ?demo=1.
   7 structurally different layouts x 4 color themes = 28 distinct sites.
   URL params ?theme= & ?layout= force a preset (used by preview links). */
(function () {
  const params = new URLSearchParams(location.search);
  const cfg=window.__DEMO_CONFIG__||{};
  const branded=!!window.__DEMO_CONFIG__||params.has("niche");

  const THEMES = ["light", "dark", "gold", "rose"];
  const LAYOUTS = ["classic", "split", "bold", "minimal", "glass", "poster", "cards"];

  // priority: URL param > saved choice > default
  const urlTheme = cfg.theme || params.get("theme");
  const urlLayout = cfg.layout || params.get("layout");
  const savedTheme = branded ? null : localStorage.getItem("demo-theme");
  const savedLayout = branded ? null : localStorage.getItem("demo-layout");

  if (urlTheme && THEMES.includes(urlTheme)) {
    document.documentElement.setAttribute("data-theme", urlTheme);
    localStorage.setItem("demo-theme", urlTheme);
  } else if (savedTheme) {
    document.documentElement.setAttribute("data-theme", savedTheme);
  }
  if (urlLayout && LAYOUTS.includes(urlLayout)) {
    document.documentElement.setAttribute("data-layout", urlLayout);
    localStorage.setItem("demo-layout", urlLayout);
  } else if (savedLayout) {
    document.documentElement.setAttribute("data-layout", savedLayout);
  }

  if (params.get("demo") !== "1" && !cfg.demo) return;

  const layouts = [
    ["classic", "Classic"], ["split", "Split"], ["bold", "Bold"],
    ["minimal", "Minimal"], ["glass", "Glass"], ["poster", "Poster"], ["cards", "Cards"],
  ];
  const themes = [
    ["light", "#faf9f7", "Minimalist White"],
    ["dark", "#0c0a09", "Dark Mode"],
    ["gold", "#d4af37", "Luxury Gold"],
    ["rose", "#ffe4e6", "Rose Beauty"],
  ];

  const wrap = document.createElement("div");
  wrap.id = "demo-fab";
  wrap.style.display = "flex";
  wrap.innerHTML = `
    <div class="fab-panel">
      <div class="fab-label">DESIGN</div>
      <div class="fab-row fab-wrap-row">
        ${layouts.map(([l, label]) =>
          `<button class="layout-btn" data-l="${l}">${label}</button>`).join("")}
      </div>
      <div class="fab-label">COLORS</div>
      <div class="fab-row">
        ${themes.map(([th, c, label]) =>
          `<div class="swatch" data-t="${th}" title="${label}" style="background:${c}"></div>`).join("")}
      </div>
    </div>
    <div class="fab-btn" title="Demo designs">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/>
        <circle cx="8.5" cy="10" r="1" fill="currentColor"/>
        <circle cx="12" cy="7.5" r="1" fill="currentColor"/>
        <circle cx="15.5" cy="10" r="1" fill="currentColor"/>
        <path d="M12 21a9 9 0 0 0 9-9c0-1.5-1-2.5-2.5-2.5H16a2 2 0 0 1-2-2c0-1.1-.9-2-2-2a9 9 0 0 0 0 18z"/>
      </svg>
    </div>`;
  document.body.appendChild(wrap);

  const panel = wrap.querySelector(".fab-panel");
  wrap.querySelector(".fab-btn").addEventListener("click", () => {
    panel.style.display = panel.style.display === "flex" ? "none" : "flex";
    markActive();
  });

  function markActive() {
    const curL = document.documentElement.getAttribute("data-layout") || "classic";
    const curT = document.documentElement.getAttribute("data-theme") || "light";
    wrap.querySelectorAll(".layout-btn").forEach(b =>
      b.classList.toggle("layout-active", b.dataset.l === curL));
    wrap.querySelectorAll(".swatch").forEach(s =>
      s.style.outline = s.dataset.t === curT ? "2px solid var(--accent)" : "none");
  }

  wrap.querySelectorAll(".layout-btn").forEach(el =>
    el.addEventListener("click", () => {
      document.documentElement.setAttribute("data-layout", el.dataset.l);
      localStorage.setItem("demo-layout", el.dataset.l);
      markActive();
    }));

  wrap.querySelectorAll(".swatch").forEach(el =>
    el.addEventListener("click", () => {
      manualTheme=true;
      document.documentElement.style.removeProperty("--accent");
      document.documentElement.style.removeProperty("--accent-ink");
      document.documentElement.setAttribute("data-theme", el.dataset.t);
      localStorage.setItem("demo-theme", el.dataset.t);
      markActive();
    }));
})();
