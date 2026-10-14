/* Site i18n — EN / PL with full hand-written Polish translations.
   data-i18n="key" on elements, data-i18n-ph="key" for placeholders. */
const I18N = {
  en: {
    nav_book: "Book now",
    my_bookings: "My bookings",
    hero_l1: "Look sharp.", hero_l2: "Feel amazing.",
    hero_cta: "Reserve your slot",
    open_daily: "Open daily",
    gallery: "Our work",
    services: "Services",
    team: "Our masters",
    book_t: "Book an appointment",
    book_s: "Free slots update in real time. No prepayment.",
    name_ph: "Your name",
    phone_ph: "Phone, e.g. +48 500 100 200",
    choose_master: "Choose a master",
    any_master: "Any available master",
    slots_l: "Available time",
    pick_date: "Pick a date and master first",
    no_slots: "Fully booked this day.",
    contact_l: "How should we contact you?",
    c_call: "Phone call", c_wa: "WhatsApp", c_tg: "Telegram",
    handle_ph: "@username",
    wa_hint: "We will text this number on WhatsApp",
    submit: "Book now",
    sending: "Sending…",
    ok_t: "You're booked!",
    ok_master: "Your master:",
    ok_s: "We will contact you shortly to confirm. See you soon!",
    footer: "Powered by an independent booking engine — zero commissions, your data stays yours.",
    min: "min",
    wl_join: "Notify me when a slot opens",
    wl_ok: "Done! We will contact you as soon as a slot frees up.",
    my_t: "My bookings",
    my_s: "Enter the phone number you booked with — no account needed.",
    my_lookup: "Find my bookings",
    my_none: "No upcoming bookings found for this number.",
    my_cancel: "Cancel visit",
    my_cancelled: "Cancelled. The salon has been notified.",
    close: "Close",
  },
  pl: {
    nav_book: "Zarezerwuj",
    my_bookings: "Moje wizyty",
    hero_l1: "Wyglądaj świetnie.", hero_l2: "Czuj się doskonale.",
    hero_cta: "Zarezerwuj termin",
    open_daily: "Otwarte codziennie",
    gallery: "Nasze prace",
    services: "Usługi",
    team: "Nasi mistrzowie",
    book_t: "Umów wizytę",
    book_s: "Wolne terminy aktualizowane na żywo. Bez przedpłat.",
    name_ph: "Twoje imię i nazwisko",
    phone_ph: "Telefon, np. +48 500 100 200",
    choose_master: "Wybierz mistrza",
    any_master: "Dowolny wolny mistrz",
    slots_l: "Dostępne godziny",
    pick_date: "Najpierw wybierz datę i mistrza",
    no_slots: "Brak wolnych terminów tego dnia.",
    contact_l: "Jak mamy się z Tobą skontaktować?",
    c_call: "Telefon", c_wa: "WhatsApp", c_tg: "Telegram",
    handle_ph: "@nazwa_użytkownika",
    wa_hint: "Napiszemy na ten numer w WhatsApp",
    submit: "Zarezerwuj",
    sending: "Wysyłanie…",
    ok_t: "Zarezerwowano!",
    ok_master: "Twój mistrz:",
    ok_s: "Skontaktujemy się wkrótce, aby potwierdzić wizytę. Do zobaczenia!",
    footer: "Niezależny system rezerwacji — zero prowizji, Twoje dane należą do Ciebie.",
    min: "min",
    wl_join: "Powiadom mnie, gdy zwolni się termin",
    wl_ok: "Gotowe! Skontaktujemy się, gdy tylko zwolni się termin.",
    my_t: "Moje wizyty",
    my_s: "Podaj numer telefonu użyty przy rezerwacji — bez zakładania konta.",
    my_lookup: "Znajdź moje wizyty",
    my_none: "Nie znaleziono nadchodzących wizyt dla tego numeru.",
    my_cancel: "Odwołaj wizytę",
    my_cancelled: "Odwołano. Salon został powiadomiony.",
    close: "Zamknij",
  },
};

function currentLang() {
  return localStorage.getItem("site-lang") ||
    ((navigator.language || "").toLowerCase().startsWith("pl") ? "pl" : "en");
}

function t(key) {
  const lang = currentLang();
  return (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
}

function applyLang(lang) {
  localStorage.setItem("site-lang", lang);
  document.querySelectorAll("[data-i18n]").forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-ph]").forEach(el => {
    el.placeholder = t(el.dataset.i18nPh);
  });
  document.querySelectorAll("[data-lang-opt]").forEach(b => {
    b.classList.toggle("dd-active", b.dataset.langOpt === lang);
  });
  const lbl = document.getElementById("lang-current");
  if (lbl) lbl.textContent = lang.toUpperCase();
  document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
}
