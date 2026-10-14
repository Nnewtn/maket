/* Preview-only catalogs. Prices are illustrative PLN, never alter production services. */
window.NicheContent = (() => {
  const photo = (id) => `https://images.unsplash.com/${id}?w=1400&q=80`;
  const beauty = ['photo-1560066984-138dadb4c035','photo-1522337660859-02fbefca4702','photo-1605497788044-5a32c7078486','photo-1521590832167-7bcbfaa6381f'];
  const barber = ['photo-1503951914875-452162b0f3f1','photo-1585747860715-2ba37e788b70','photo-1521590832167-7bcbfaa6381f','photo-1560066984-138dadb4c035'];
  const auto = ['photo-1492144534655-ae79c964c9d7','photo-1503376780353-7e6692767b70','photo-1552519507-da3b142c6e3d','photo-1542362567-b07e54358753'];
  // [English name, Polish name, English description, Polish description, PLN, minutes]
  const catalogs = {
    beauty: {images:beauty, layout:'glass', theme:'rose', team:['Beauty Specialist','Stylistka'],
      en:{hero_l1:'Your beauty.',hero_l2:'Our expertise.',hero_cta:'Find your beauty ritual',gallery:'Inside our studio',services:'Treatments & styling',team:'Your beauty team',book_t:'Book your treatment'},
      pl:{hero_l1:'Twoje piękno.',hero_l2:'Nasza pasja.',hero_cta:'Wybierz swój rytuał',gallery:'Nasze studio',services:'Zabiegi i stylizacja',team:'Nasz zespół',book_t:'Umów się na zabieg'},
      desc:['Thoughtful beauty rituals, expert styling and time dedicated entirely to you. Book directly with our studio.','Przemyślane rytuały pielęgnacyjne, profesjonalna stylizacja i czas tylko dla Ciebie. Zarezerwuj wizytę bezpośrednio w naszym studio.'],
      services:[['Cut & blow-dry','Strzyżenie i modelowanie','Consultation, wash and professional finish.','Konsultacja, mycie i profesjonalne modelowanie.',180,60],['Gel manicure','Manicure hybrydowy','Nail shaping, cuticle care and long-lasting colour.','Opracowanie paznokci, pielęgnacja skórek i trwały kolor.',140,60],['Facial treatment','Zabieg na twarz','A personalised cleansing and hydration ritual.','Indywidualny rytuał oczyszczania i nawilżania.',220,75],['Brow styling','Stylizacja brwi','Shape and tint tailored to your features.','Regulacja i koloryzacja dopasowane do Twojej urody.',90,30]]},
    barber: {images:barber,layout:'poster',theme:'dark',team:['Barber','Barber'],
      en:{hero_l1:'Precision cuts.',hero_l2:'Real character.',hero_cta:'Book your chair',gallery:'Cuts. Craft. Character.',services:'The barber menu',team:'Meet your barbers',book_t:'Reserve your chair'},
      pl:{hero_l1:'Precyzyjne cięcie.',hero_l2:'Twój charakter.',hero_cta:'Zarezerwuj fotel',gallery:'Cięcie. Rzemiosło. Charakter.',services:'Usługi barberskie',team:'Poznaj naszych barberów',book_t:'Zarezerwuj swój fotel'},
      desc:['Sharp fades, perfectly shaped beards and a relaxed atmosphere. Your barber, your style — book direct.','Precyzyjne cieniowanie, doskonale wystylizowana broda i swobodna atmosfera. Twój barber, Twój styl — rezerwuj bezpośrednio.'],
      services:[["Men’s haircut",'Strzyżenie męskie','Consultation, wash, cut and styling.','Konsultacja, mycie, strzyżenie i stylizacja.',100,45],['Beard trim & shape','Strzyżenie i modelowanie brody','Precision shaping with a hot-towel finish.','Precyzyjne modelowanie i gorący ręcznik na zakończenie.',70,30],['Hair & beard combo','Strzyżenie włosów i brody','The complete grooming experience in one visit.','Kompleksowa pielęgnacja podczas jednej wizyty.',155,75],['Skin fade','Skin fade','A clean fade with detailed finishing.','Precyzyjne cieniowanie z dopracowanym wykończeniem.',120,60]]},
    auto: {images:auto,layout:'split',theme:'light',team:['Service Advisor','Doradca serwisowy'],
      en:{hero_l1:'Drive with confidence.',hero_l2:'We handle the rest.',hero_cta:'Schedule a service',gallery:'Our automotive world',services:'Workshop & showroom',team:'Your automotive team',book_t:'Schedule your visit',any_master:'Any available advisor',choose_master:'Choose an advisor',ok_master:'Your advisor:'},
      pl:{hero_l1:'Jedź bez obaw.',hero_l2:'Resztą zajmiemy się my.',hero_cta:'Umów wizytę w serwisie',gallery:'Nasz motoryzacyjny świat',services:'Serwis i salon',team:'Twój zespół motoryzacyjny',book_t:'Umów wizytę',any_master:'Dowolny dostępny doradca',choose_master:'Wybierz doradcę',ok_master:'Twój doradca:'},
      desc:['From routine maintenance to your next test drive. Clear appointments, knowledgeable advisors and personal service.','Od regularnego serwisu po kolejną jazdę próbną. Wygodne terminy, doświadczeni doradcy i indywidualna obsługa.'],
      services:[['Oil & filter change','Wymiana oleju i filtra','Labour from 180 PLN; oil and parts quoted separately.','Robocizna od 180 zł; olej i części wyceniane osobno.',180,60],['Computer diagnostics','Diagnostyka komputerowa','Fault-code scan and technician consultation.','Odczyt błędów i konsultacja z technikiem.',150,45],['Interior deep clean','Pranie tapicerki i czyszczenie wnętrza','Fabric and interior cleaning; price varies by vehicle.','Czyszczenie tapicerki i wnętrza; cena zależy od pojazdu.',450,180],['Test drive appointment','Jazda próbna','Meet your advisor and explore the selected vehicle.','Spotkanie z doradcą i jazda wybranym samochodem.',0,45]]},
    detailing: {images:[auto[2],auto[0],auto[3],auto[1]],layout:'bold',theme:'dark',team:['Detailing Specialist','Specjalista detailingu'],
      en:{hero_l1:'Beyond clean.',hero_l2:'Showroom perfection.',hero_cta:'Choose your detail',gallery:'A finish worth a closer look',services:'Care. Correct. Protect.',team:'Your detailing specialists',book_t:'Book a detailing session',any_master:'Any available specialist',ok_master:'Your specialist:'},
      pl:{hero_l1:'Więcej niż czystość.',hero_l2:'Perfekcja w każdym detalu.',hero_cta:'Wybierz pakiet',gallery:'Wykończenie warte uwagi',services:'Pielęgnacja. Korekta. Ochrona.',team:'Specjaliści detailingu',book_t:'Umów detailing',any_master:'Dowolny dostępny specjalista',ok_master:'Twój specjalista:'},
      desc:['Meticulous hand care, paint correction and lasting protection. Premium detailing with transparent booking.','Staranna pielęgnacja ręczna, korekta lakieru i trwała ochrona. Profesjonalny detailing z wygodną rezerwacją.'],
      services:[['Premium hand wash','Mycie detailingowe','Safe contact wash, wheels and finishing touches.','Bezpieczne mycie ręczne, felgi i wykończenie.',180,90],['Interior detailing','Detailing wnętrza','Deep cleaning, fabrics, leather and trim care.','Dokładne czyszczenie tapicerki, skóry i elementów wnętrza.',550,240],['One-step paint correction','Jednoetapowa korekta lakieru','Paint enhancement; final quote after inspection.','Odświeżenie lakieru; ostateczna wycena po oględzinach.',1000,360],['Ceramic coating consultation','Konsultacja powłoki ceramicznej','Inspect the paintwork and build your protection plan.','Ocena lakieru i dobór planu ochrony.',0,45]]}
  };
  let active = '';
  const originalT = window.t;
  window.t = function(key) {
    const lang = currentLang() === 'pl' ? 'pl' : 'en';
    return catalogs[active]?.[lang]?.[key] ?? originalT(key);
  };
  function set(niche) {
    if (!catalogs[niche]) return;
    active = niche;
    const n = catalogs[active];
    document.documentElement.style.setProperty('--hero-img', `url("${photo(n.images[0])}")`);
    n.images.forEach((id,i) => {const el=document.getElementById(`gal-${i+1}`);if(el) el.src=photo(id);});
    const media=document.getElementById('hero-media-img');if(media) media.src=photo(n.images[0]);
  }
  function services() {
    const pl=currentLang()==='pl';
    return catalogs[active].services.map((s,i)=>({id:i+1,name:s[pl?1:0],description:s[pl?3:2],price:s[4],duration_min:s[5]}));
  }
  function staff() {
    return ['Alex Morgan','Jamie Taylor'].map((name,i)=>({id:i+1,name,role:catalogs[active].team[currentLang()==='pl'?1:0],avatar_url:''}));
  }
  function description() {return catalogs[active]?.desc[currentLang()==='pl'?1:0] || '';}
  return {set,services,staff,description,get preset(){return catalogs[active];},get active(){return active;}};
})();
