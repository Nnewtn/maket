// Niche presets: services per niche + EN/PL names + prices + durations
const NICHES = {
  barber: {
    hero_image: "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=1600&q=80",
    gallery: [
      "https://images.unsplash.com/photo-1599351431202-10e1b29be4c4?w=900&q=80",
      "https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=900&q=80",
      "https://images.unsplash.com/photo-1622286342621-4bd786c2447c?w=900&q=80",
      "https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=900&q=80",
    ],
    services: [
      { name: { en: "Men's classic haircut", pl: "Strzyżenie męskie klasyczne" }, price: 80, duration_min: 45 },
      { name: { en: "Beard trim & shape",   pl: "Strzyżenie i modelowanie brody" }, price: 50, duration_min: 30 },
      { name: { en: "Hot towel shave",      pl: "Golenie na gorąco z ręcznikiem" }, price: 70, duration_min: 45 },
      { name: { en: "Kids cut (ages 5–12)", pl: "Strzyżenie dziecięce (5–12 lat)" }, price: 40, duration_min: 30 },
      { name: { en: "Hair wash & finish",   pl: "Mycie i stylizacja" }, price: 35, duration_min: 20 },
    ],
  },
  beauty: {
    hero_image: "https://images.unsplash.com/photo-1560066984-138dadb4c035?w=1600&q=80",
    gallery: [
      "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=900&q=80",
      "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=900&q=80",
      "https://images.unsplash.com/photo-1604654894610-df63bc536371?w=900&q=80",
      "https://images.unsplash.com/photo-1519415948534-76f9c6f8e9df?w=900&q=80",
    ],
    services: [
      { name: { en: "Gel manicure",     pl: "Manicure hybrydowy" }, price: 120, duration_min: 60 },
      { name: { en: "Pedicure deluxe",  pl: "Pedicure deluxe" }, price: 160, duration_min: 75 },
      { name: { en: "Haircut & color",  pl: "Strzyżenie i koloryzacja" }, price: 220, duration_min: 90 },
      { name: { en: "Blow-dry style",   pl: "Modelowanie i suszenie" }, price: 90, duration_min: 45 },
      { name: { en: "Eyebrow shaping",  pl: "Regulacja brwi" }, price: 50, duration_min: 20 },
    ],
  },
  auto: {
    hero_image: "https://images.unsplash.com/photo-1486006420552-cdba8b4aa9ee?w=1600&q=80",
    gallery: [
      "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&q=80",
      "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=900&q=80",
      "https://images.unsplash.com/photo-1623869675781-80aa31012b5c?w=900&q=80",
      "https://images.unsplash.com/photo-1486754735734-325b5831c3ad?w=900&q=80",
    ],
    services: [
      { name: { en: "Oil & filter change", pl: "Wymiana oleju i filtra" }, price: 220, duration_min: 45 },
      { name: { en: "Brake inspection",    pl: "Przegląd hamulców" }, price: 180, duration_min: 60 },
      { name: { en: "Tire change (set of 4)", pl: "Wymiana opon (komplet)" }, price: 320, duration_min: 60 },
      { name: { en: "Diagnostics full scan", pl: "Pełna diagnostyka komputerowa" }, price: 150, duration_min: 45 },
      { name: { en: "AC service",           pl: "Serwis klimatyzacji" }, price: 280, duration_min: 90 },
    ],
  },
  detailing: {
    hero_image: "https://images.unsplash.com/photo-1605618826115-fb9e1c2d2bd3?w=1600&q=80",
    gallery: [
      "https://images.unsplash.com/photo-1520340356584-f9917d1eea6f?w=900&q=80",
      "https://images.unsplash.com/photo-1601362840469-51e4d8d58785?w=900&q=80",
      "https://images.unsplash.com/photo-1583121274602-3e2820c69888?w=900&q=80",
      "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=900&q=80",
    ],
    services: [
      { name: { en: "One-step paint correction", pl: "Jednoetapowa korekta lakieru" }, price: 1200, duration_min: 360 },
      { name: { en: "Interior deep clean",       pl: "Głębokie czyszczenie wnętrza" }, price: 600, duration_min: 180 },
      { name: { en: "Ceramic coating (basic)",   pl: "Powłoka ceramiczna (podstawowa)" }, price: 1800, duration_min: 480 },
      { name: { en: "Headlight restoration",     pl: "Renowacja reflektorów" }, price: 220, duration_min: 60 },
      { name: { en: "Engine bay detail",         pl: "Czyszczenie komory silnika" }, price: 280, duration_min: 60 },
    ],
  },
};

function getNicheCfg() {
  const url = new URL(location.href);
  const q = (url.searchParams.get("niche") || localStorage.getItem("site-niche") || "barber").toLowerCase();
  return NICHES[q] || NICHES.barber;
}
function applyNicheImages(cfg) {
  const hero = document.querySelector("[data-niche-hero]");
  if (hero && cfg.hero_image) hero.style.backgroundImage = `linear-gradient(rgba(0,0,0,.45), rgba(0,0,0,.55)), url('${cfg.hero_image}')`;
  const gal = document.getElementById("niche-gallery");
  if (gal) {
    gal.innerHTML = "";
    cfg.gallery.forEach(src => {
      const f = document.createElement("figure");
      f.className = "gal-card";
      f.innerHTML = `<img loading="lazy" src="${src}" alt="">`;
      f.querySelector("img").onerror = e => { e.target.hidden = true; f.classList.add("image-placeholder"); };
      gal.appendChild(f);
    });
  }
}
window.NICHES = NICHES;
window.getNicheCfg = getNicheCfg;
window.applyNicheImages = applyNicheImages;
