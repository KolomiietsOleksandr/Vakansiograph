window.COUNTRY_META = {
  ALL: { name: 'All Countries',          flag: '🌍' },
  US:  { name: 'United States',          flag: '🇺🇸' },
  GB:  { name: 'United Kingdom',         flag: '🇬🇧' },
  DE:  { name: 'Germany',                flag: '🇩🇪' },
  FR:  { name: 'France',                 flag: '🇫🇷' },
  IT:  { name: 'Italy',                  flag: '🇮🇹' },
  AT:  { name: 'Austria',                flag: '🇦🇹' },
  BE:  { name: 'Belgium',                flag: '🇧🇪' },
  NL:  { name: 'Netherlands',            flag: '🇳🇱' },
  PL:  { name: 'Poland',                 flag: '🇵🇱' },
  CH:  { name: 'Switzerland',            flag: '🇨🇭' },
  CZ:  { name: 'Czech Republic',         flag: '🇨🇿' },
  RO:  { name: 'Romania',                flag: '🇷🇴' },
  SE:  { name: 'Sweden',                 flag: '🇸🇪' },
  EL:  { name: 'Greece',                 flag: '🇬🇷' },
  GR:  { name: 'Greece',                 flag: '🇬🇷' },
  SP:  { name: 'Spain',                  flag: '🇪🇸' },
  IC:  { name: 'Iceland',                flag: '🇮🇸' },
  IS:  { name: 'Israel',                 flag: '🇮🇱' },
  AU:  { name: 'Australia',              flag: '🇦🇺' },
  NZ:  { name: 'New Zealand',            flag: '🇳🇿' },
  SG:  { name: 'Singapore',              flag: '🇸🇬' },
  IN:  { name: 'India',                  flag: '🇮🇳' },
  JP:  { name: 'Japan',                  flag: '🇯🇵' },
  CA:  { name: 'Canada',                 flag: '🇨🇦' },
  BR:  { name: 'Brazil',                 flag: '🇧🇷' },
  MX:  { name: 'Mexico',                 flag: '🇲🇽' },
  AR:  { name: 'Argentina',              flag: '🇦🇷' },
  CO:  { name: 'Colombia',               flag: '🇨🇴' },
  PE:  { name: 'Peru',                   flag: '🇵🇪' },
  UR:  { name: 'Uruguay',                flag: '🇺🇾' },
  DO:  { name: 'Dominican Republic',     flag: '🇩🇴' },
  CU:  { name: 'Cuba',                   flag: '🇨🇺' },
  HO:  { name: 'Honduras',               flag: '🇭🇳' },
  ZA:  { name: 'South Africa',           flag: '🇿🇦' },
  MA:  { name: 'Morocco',                flag: '🇲🇦' },
  SA:  { name: 'Saudi Arabia',           flag: '🇸🇦' },
  JO:  { name: 'Jordan',                 flag: '🇯🇴' },
  KU:  { name: 'Kuwait',                 flag: '🇰🇼' },
  TU:  { name: 'Turkey',                 flag: '🇹🇷' },
  BA:  { name: 'Bosnia & Herzegovina',   flag: '🇧🇦' },
  SO:  { name: 'South Africa',           flag: '🇿🇦' },
  UA:  { name: 'Ukraine',                flag: '🇺🇦' },
  UN:  { name: 'Unknown',                flag: '🏳️'  },
};

window.countryName = function(code) {
  return (window.COUNTRY_META[code] || {}).name || code;
};

window.countryFlag = function(code) {
  return (window.COUNTRY_META[code] || {}).flag || '';
};

window.countryLabel = function(code) {
  const m = window.COUNTRY_META[code];
  if (!m) return code;
  return `${m.flag} ${m.name}`;
};
