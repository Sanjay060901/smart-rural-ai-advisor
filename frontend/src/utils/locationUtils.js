// src/utils/locationUtils.js
// Shared location utilities — Nominatim place name cleaning & name normalisation

/**
 * Clean location names from Nominatim that OpenWeatherMap doesn't understand.
 * Strips administrative suffixes like "Tahsil", "Block", "Mandal", "Taluk", etc.
 */
export function cleanLocationName(name) {
    if (!name) return name;
    return name
        .replace(/\b(Tahsil|Tehsil|Block|Mandal|Taluk[ua]?|Sub-?district|District|Division|Sub-?Division|Municipality|Corporation|Cantonment|Nagar Panchayat|Town|Circle|Range|Panchayat|Samiti|Gram|Assembly|Constituency|Revenue|Hobli|Firka|Community Development)\b/gi, '')
        .replace(/\s{2,}/g, ' ')
        .trim();
}

// ═══════════════════════════════════════════════════════════════════════
// Bidirectional name mapping:
//   DISTRICT_MAP names ↔ Nominatim / OpenWeatherMap names
// ═══════════════════════════════════════════════════════════════════════

/**
 * Maps DISTRICT_MAP canonical names → API/map-friendly names
 * (for Nominatim geocoding and OpenWeatherMap lookups)
 */
const DISTRICT_TO_API = {
    // Tamil Nadu
    'Kancheepuram': 'Kanchipuram',
    'Viluppuram': 'Villupuram',
    'Nilgiris': 'Nilgiris',
    'Thoothukudi': 'Thoothukudi',
    'Tiruchirappalli': 'Tiruchirappalli',
    'Tirupathur': 'Tirupattur',
    // Karnataka
    'Bangalore Urban': 'Bengaluru',
    'Bangalore Rural': 'Bengaluru',
    'Tumkur': 'Tumakuru',
    'Mysore': 'Mysuru',
    'Shimoga': 'Shivamogga',
    'Belgaum': 'Belagavi',
    'Bellary': 'Ballari',
    'Kalaburagi': 'Kalaburagi',
    'Vijayapura': 'Vijayapura',
    'Dakshina Kannada': 'Mangalore',
    'Uttara Kannada': 'Karwar',
    'Kodagu': 'Madikeri',
    // Andhra Pradesh
    'East Godavari': 'Kakinada',
    'West Godavari': 'Eluru',
    'YSR Kadapa': 'Kadapa',
    'Konaseema': 'Amalapuram',
    'NTR': 'Vijayawada',
    'Palnadu': 'Narasaraopet',
    'Alluri Sitharama Raju': 'Paderu',
    'Parvathipuram Manyam': 'Parvathipuram',
    'Sri Sathya Sai': 'Puttaparthi',
    // Telangana
    'Medchal-Malkajgiri': 'Hyderabad',
    'Rangareddy': 'Hyderabad',
    'Mahbubnagar': 'Mahabubnagar',
    'Jayashankar Bhupalpally': 'Bhupalpally',
    'Jogulamba Gadwal': 'Gadwal',
    'Komaram Bheem': 'Asifabad',
    'Bhadradri Kothagudem': 'Kothagudem',
    'Yadadri Bhuvanagiri': 'Bhongir',
    'Rajanna Sircilla': 'Sircilla',
    'Warangal Urban': 'Warangal',
    'Warangal Rural': 'Warangal',
    'Hanumakonda': 'Warangal',
    'Kamrup Metropolitan': 'Guwahati',
    // West Bengal
    'North 24 Parganas': 'Barasat',
    'South 24 Parganas': 'Baruipur',
    'Purba Medinipur': 'Tamluk',
    'Paschim Medinipur': 'Midnapore',
    'Purba Bardhaman': 'Bardhaman',
    'Paschim Bardhaman': 'Asansol',
    'Uttar Dinajpur': 'Raiganj',
    'Dakshin Dinajpur': 'Balurghat',
    // Bihar
    'East Champaran': 'Motihari',
    'West Champaran': 'Bettiah',
    'Vaishali': 'Hajipur',
    'Saran': 'Chapra',
    // Gujarat
    'Kutch': 'Bhuj',
    'Devbhumi Dwarka': 'Dwarka',
    'Gir Somnath': 'Veraval',
    'Chhota Udaipur': 'Chhota Udaipur',
    // Odisha
    'Khordha': 'Bhubaneswar',
    'Ganjam': 'Berhampur',
    'Sundargarh': 'Rourkela',
    'Mayurbhanj': 'Baripada',
    // Maharashtra
    'Mumbai City': 'Mumbai',
    'Mumbai Suburban': 'Mumbai',
    'Raigad': 'Alibag',
    // Kerala
    'Ernakulam': 'Kochi',
    'Wayanad': 'Kalpetta',
    // Punjab
    'Shaheed Bhagat Singh Nagar': 'Nawanshahr',
    // Rajasthan
    'Sri Ganganagar': 'Ganganagar',
    // Jharkhand
    'East Singhbhum': 'Jamshedpur',
    'West Singhbhum': 'Chaibasa',
    'Seraikela Kharsawan': 'Seraikela',
    // Haryana
    'Gurugram': 'Gurgaon',
    'Gautam Buddha Nagar': 'Noida',
    'Nuh': 'Nuh',
    // UP
    'Kanpur Nagar': 'Kanpur',
    'Kanpur Dehat': 'Kanpur',
    'Gautam Buddha Nagar': 'Noida',
    'Sant Kabir Nagar': 'Khalilabad',
    'Ambedkar Nagar': 'Akbarpur',
    // Puducherry
    'Puducherry': 'Pondicherry',
    // Chhattisgarh
    'Janjgir-Champa': 'Janjgir',
    // Meghalaya
    'East Khasi Hills': 'Shillong',
    'East Garo Hills': 'Williamnagar',
    'West Garo Hills': 'Tura',
    'Ri Bhoi': 'Nongpoh',
    'South West Khasi Hills': 'Mawkyrwat',
    'South West Garo Hills': 'Ampati',
    'West Khasi Hills': 'Nongstoin',
    'East Jaintia Hills': 'Khliehriat',
    'West Jaintia Hills': 'Jowai',
    'South Garo Hills': 'Baghmara',
    'North Garo Hills': 'Resubelpara',
};

/**
 * Build reverse map: Nominatim/OWM name → DISTRICT_MAP canonical name.
 * First entry wins when multiple districts map to the same API name.
 */
const API_TO_DISTRICT = {};
for (const [district, api] of Object.entries(DISTRICT_TO_API)) {
    // Only store if not already present (first mapping wins)
    if (!API_TO_DISTRICT[api] || api === district) {
        // skip identity mappings in reverse
    }
    if (!API_TO_DISTRICT[api]) {
        API_TO_DISTRICT[api] = district;
    }
}
// Explicit reverse overrides (Nominatim returns these → map to DISTRICT_MAP key)
Object.assign(API_TO_DISTRICT, {
    'Kanchipuram': 'Kancheepuram',
    'Villupuram': 'Viluppuram',
    'Bengaluru': 'Bangalore Urban',
    'Tumakuru': 'Tumkur',
    'Mysuru': 'Mysore',
    'Shivamogga': 'Shimoga',
    'Belagavi': 'Belgaum',
    'Ballari': 'Bellary',
    'Mangalore': 'Dakshina Kannada',
    'Mangaluru': 'Dakshina Kannada',
    'Kadapa': 'YSR Kadapa',
    'Mahabubnagar': 'Mahbubnagar',
    'Gurgaon': 'Gurugram',
    'Pondicherry': 'Puducherry',
    'Kochi': 'Ernakulam',
    'Cochin': 'Ernakulam',
    'Mumbai': 'Mumbai City',
    'Jamshedpur': 'East Singhbhum',
    'Noida': 'Gautam Buddha Nagar',
    'Greater Noida': 'Gautam Buddha Nagar',
    'Guwahati': 'Kamrup Metropolitan',
    'Bhubaneswar': 'Khordha',
    'Rourkela': 'Sundargarh',
    'Midnapore': 'Paschim Medinipur',
    'Bardhaman': 'Purba Bardhaman',
    'Asansol': 'Paschim Bardhaman',
    'Shillong': 'East Khasi Hills',
    'Tirupattur': 'Tirupathur',
    'Tuticorin': 'Thoothukudi',
});

/**
 * Convert a DISTRICT_MAP name to an API/geocoding-friendly name.
 * Use before calling Nominatim or OpenWeatherMap.
 */
export function toApiName(name) {
    if (!name) return name;
    return DISTRICT_TO_API[name] || name;
}

/**
 * Convert a Nominatim / OpenWeatherMap name back to the DISTRICT_MAP canonical
 * name so that getDistrictName() can find translations.
 * Use after receiving place names from Nominatim reverseGeocode.
 */
export function toDistrictMapName(name) {
    if (!name) return name;
    return API_TO_DISTRICT[name] || name;
}
