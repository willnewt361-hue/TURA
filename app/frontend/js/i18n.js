/** English + Luganda-ready i18n dictionaries */
(function (global) {
  const dict = {
    en: {
      tagline: 'One Tap. One Journey.',
      getStarted: 'Get Started',
      demoMode: 'Try Demo Mode',
      book: 'Book',
      travel: 'Travel',
      explore: 'Explore',
      goodMorning: 'Good morning',
      whereGoing: 'Where are you going today?',
      from: 'From',
      to: 'To',
      date: 'Date',
      passengers: 'Passengers',
      searchBuses: 'Search Buses',
      popular: 'Popular Destinations',
      home: 'Home',
      tickets: 'Tickets',
      live: 'Live',
      more: 'More',
      selectSeat: 'Select Seat',
      next: 'Next',
      continue: 'Continue',
      payNow: 'Pay Now',
      bookingConfirmed: 'Booking Confirmed!',
      saveTicket: 'Save Ticket',
      share: 'Share',
      upcoming: 'Upcoming',
      past: 'Past',
      offline: 'Offline',
      online: 'Online',
      help: 'Help',
      logout: 'Log out',
      login: 'Log in',
    },
    lg: {
      tagline: 'Okukuba Kumwe. Olugendo Lumwe.',
      getStarted: 'Tandika',
      demoMode: 'Gezaako Demo',
      book: 'Bookinga',
      travel: 'Olugendo',
      explore: 'Kebera',
      goodMorning: 'Wasuze otya',
      whereGoing: 'Ogenda wa leero?',
      from: 'Okuva',
      to: 'Okutuuka',
      date: 'Enaku',
      passengers: 'Abagenyi',
      searchBuses: 'Noonya Bbaasi',
      popular: 'Ebifo Ebya Mubbi',
      home: 'Awaka',
      tickets: 'Tiket',
      live: 'Live',
      more: 'Ebisingawo',
      selectSeat: 'Londa Entuuyo',
      next: 'Ekiddako',
      continue: 'Genda mu maaso',
      payNow: 'Sasula Kati',
      bookingConfirmed: 'Okubookinga Kwakkakasibwa!',
      saveTicket: 'Tereka Tiket',
      share: 'Gabana',
      upcoming: 'Ejja',
      past: 'Eyawita',
      offline: 'Teri ku neti',
      online: 'Ku neti',
      help: 'Obuyambi',
      logout: 'Fuluma',
      login: 'Yingira',
    },
  };

  let lang = 'en';
  try {
    lang = localStorage.getItem('tura_lang') || 'en';
  } catch (error) {
    console.warn('TURA language preference could not be read', error);
  }

  function t(key) {
    return (dict[lang] && dict[lang][key]) || dict.en[key] || key;
  }

  function setLang(next) {
    lang = next === 'lg' ? 'lg' : 'en';
    try {
      localStorage.setItem('tura_lang', lang);
    } catch (error) {
      console.warn('TURA language preference could not be saved', error);
    }
  }

  function getLang() { return lang; }

  global.TuraI18n = { t, setLang, getLang, dict };
})(window);
