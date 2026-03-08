# backend/lambdas/govt_schemes/handler.py
# Lambda Tool: Government scheme lookup
# Owner: Manoj RS
# Endpoint: GET /schemes
# See: Detailed_Implementation_Guide.md Section 9

import json
import logging
import re
import os
from utils.response_helper import success_response, error_response
from utils.cors_helper import handle_cors_preflight

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENABLE_UNIFIED_CORS = os.environ.get('ENABLE_UNIFIED_CORS', 'false').lower() == 'true'

# ── Security: Input validation ──
MAX_SEARCH_LENGTH = 200

def _sanitize_input(value, max_len=MAX_SEARCH_LENGTH):
    """Sanitize user input: strip, truncate, remove dangerous chars."""
    if not value:
        return ''
    value = str(value).strip()[:max_len]
    value = re.sub(r'[<>{}\[\]|;`$\\]', '', value)
    return value

# Curated scheme data (could also be in DynamoDB)
SCHEMES = {
    "pm_kisan": {
        "name": "PM-KISAN",
        "full_name": "Pradhan Mantri Kisan Samman Nidhi",
        "benefit": "₹6,000 per year (₹2,000 every 4 months)",
        "eligibility": "All landholding farmer families",
        "how_to_apply": "1. Visit nearest Common Service Centre (CSC)\n2. OR Register online at https://pmkisan.gov.in\n3. Documents needed: Aadhaar card, bank account, land records\n4. Verification by state/district officials",
        "helpline": "011-23381092",
        "website": "https://pmkisan.gov.in"
    },
    "pmfby": {
        "name": "PMFBY",
        "full_name": "Pradhan Mantri Fasal Bima Yojana",
        "benefit": "Crop insurance at 2% premium (Kharif), 1.5% (Rabi)",
        "eligibility": "All farmers growing notified crops",
        "how_to_apply": "1. Through your bank (auto-enrolled if crop loan exists)\n2. Through Common Service Centre\n3. Online at https://pmfby.gov.in\n4. Deadline: Before crop sowing season cutoff date",
        "helpline": "1800-180-1551",
        "website": "https://pmfby.gov.in"
    },
    "kcc": {
        "name": "KCC",
        "full_name": "Kisan Credit Card",
        "benefit": "Short-term crop loan at 4% effective interest (with subsidy)",
        "eligibility": "All farmers — individual, joint, tenant, sharecroppers",
        "how_to_apply": "1. Visit any bank branch (SBI, cooperative, regional rural bank)\n2. Submit: Application form + land records + ID proof + photos\n3. Approved in 15 days\n4. Card valid for 5 years with annual renewal",
        "helpline": "1800-180-1551",
        "website": "https://pmkisan.gov.in"
    },
    "soil_health_card": {
        "name": "Soil Health Card",
        "full_name": "Soil Health Card Scheme",
        "benefit": "Free soil testing + fertilizer recommendations",
        "eligibility": "All farmers",
        "how_to_apply": "1. Visit nearest soil testing lab or Krishi Vigyan Kendra\n2. Provide soil sample\n3. Card issued within 2 weeks",
        "helpline": "1800-180-1551",
        "website": "https://soilhealth.dac.gov.in"
    },
    "pmksy": {
        "name": "PMKSY",
        "full_name": "Pradhan Mantri Krishi Sinchayee Yojana",
        "benefit": "55% subsidy on micro-irrigation (drip/sprinkler)",
        "eligibility": "All farmers — higher subsidy for small/marginal farmers",
        "how_to_apply": "1. Apply through state agriculture department\n2. OR through district horticulture office\n3. Submit land records + bank details",
        "helpline": "1800-180-1551",
        "website": "https://pmksy.gov.in"
    },
    "e_nam": {
        "name": "eNAM",
        "full_name": "National Agriculture Market",
        "benefit": "Online trading platform — better prices, transparent bidding",
        "eligibility": "All farmers with produce to sell",
        "how_to_apply": "1. Register at https://enam.gov.in\n2. Visit nearest eNAM mandi\n3. Get quality tested and listed",
        "helpline": "1800-270-0224",
        "website": "https://enam.gov.in"
    },
    "pkvy": {
        "name": "PKVY",
        "full_name": "Paramparagat Krishi Vikas Yojana",
        "benefit": "₹50,000/hectare over 3 years for organic farming",
        "eligibility": "Groups of 50+ farmers with 50 acres",
        "how_to_apply": "1. Form a farmer group (50+ farmers)\n2. Apply through district agriculture officer\n3. Get organic certification support",
        "helpline": "1800-180-1551",
        "website": "https://pgsindia-ncof.gov.in"
    },
    "nfsm": {
        "name": "NFSM",
        "full_name": "National Food Security Mission",
        "benefit": "Subsidized seeds, fertilizers, and farm machinery",
        "eligibility": "Farmers in identified districts growing rice, wheat, pulses, coarse cereals",
        "how_to_apply": "1. Contact block agriculture officer\n2. Register under NFSM scheme\n3. Receive subsidized inputs",
        "helpline": "1800-180-1551",
        "website": "https://nfsm.gov.in"
    },
    "agriculture_infra_fund": {
        "name": "AIF",
        "full_name": "Agriculture Infrastructure Fund",
        "benefit": "3% interest subvention on loans up to ₹2 crore",
        "eligibility": "Farmers, FPOs, PACS, startups, agri-entrepreneurs",
        "how_to_apply": "1. Apply online at https://agriinfra.dac.gov.in\n2. Loan through any scheduled bank\n3. For: cold storage, warehouses, processing units",
        "helpline": "1800-180-1551",
        "website": "https://agriinfra.dac.gov.in"
    }
}

# ── State-specific schemes (curated from official state portals) ──
# Each scheme includes: name, benefit, eligibility, how_to_apply, documents, deadline
STATE_SCHEMES = {
    "Tamil Nadu": [
        {"name": "Tamil Nadu State Crop Insurance", "benefit": "Additional state-funded crop insurance beyond PMFBY for special crops (banana, coconut, etc.)", "eligibility": "Farmers growing notified special crops in Tamil Nadu", "how_to_apply": "Through district agriculture office or cooperative banks", "documents": "Patta (land record), Aadhaar card, crop sowing certificate, bank passbook, passport-size photo", "deadline": "Before crop sowing season (Kharif: June–July, Rabi: Oct–Nov)", "website": "https://www.tnagrisnet.tn.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Electricity for Agriculture", "benefit": "Free electricity for pump sets up to 10 HP motor", "eligibility": "All Tamil Nadu farmers with agricultural pump sets", "how_to_apply": "Apply at TNEB office with patta and farming proof", "documents": "Patta, pump set registration, Aadhaar card, proof of agricultural activity", "deadline": "Year-round (new connections subject to availability)", "website": "https://www.tnpdcl.org", "helpline": "1912"},
        {"name": "Uzhavar Sandhai (Farmers' Market)", "benefit": "Direct-to-consumer markets eliminating middlemen — 180+ markets across the state", "eligibility": "All farmers with produce to sell", "how_to_apply": "Register at nearest Uzhavar Sandhai market through district agriculture officer", "documents": "Aadhaar card, patta or tenant farming proof, produce details", "deadline": "Year-round registration; market days vary by location", "website": "https://www.tnagrisnet.tn.gov.in", "helpline": "1800-180-1551"},
        {"name": "Special Subsidy for Micro-Irrigation", "benefit": "100% subsidy for drip irrigation for small/marginal farmers (up to 5 acres)", "eligibility": "Small and marginal farmers in Tamil Nadu", "how_to_apply": "Apply through district horticulture department or tnagrisnet.tn.gov.in", "documents": "Patta, Aadhaar card, land survey sketch, bank passbook, caste certificate (if SC/ST)", "deadline": "Apply before March 31 each financial year (subject to fund availability)", "website": "https://www.tnagrisnet.tn.gov.in", "helpline": "1800-180-1551"},
        {"name": "TN IAMP (Irrigated Agriculture Modernization Project)", "benefit": "World Bank-assisted modernization of irrigation systems", "eligibility": "Farmers in project-covered sub-basins", "how_to_apply": "Through Water Resources Department and district agriculture office", "documents": "Patta, Aadhaar card, bank passbook, sub-basin location proof", "deadline": "Project-based; contact district agriculture office for current phase deadlines", "website": "https://www.tnagrisnet.tn.gov.in", "helpline": "1800-180-1551"},
    ],
    "Andhra Pradesh": [
        {"name": "YSR Rythu Bharosa", "benefit": "₹13,500/year per farmer family (₹7,500 state + ₹6,000 PM-KISAN combined)", "eligibility": "All registered farmer families in AP", "how_to_apply": "Auto-enrolled if registered in AP farmer database; verify at nearest MRO office", "documents": "Aadhaar card, land records (1B/adangal), bank passbook linked to Aadhaar", "deadline": "Continuous enrollment; payments in May, Oct, Jan installments", "website": "https://agriculture.ap.gov.in", "helpline": "1800-180-1551"},
        {"name": "YSR Free Crop Insurance", "benefit": "State pays farmer premium share of PMFBY — effectively free crop insurance", "eligibility": "All AP farmers growing notified crops", "how_to_apply": "Auto-enrolled through banks/cooperative societies during crop loan", "documents": "Aadhaar, crop loan documents, e-crop booking registration", "deadline": "Kharif: before July 31; Rabi: before December 31", "website": "https://agriculture.ap.gov.in", "helpline": "1800-180-1551"},
        {"name": "E-Crop Registration", "benefit": "Mandatory digital crop booking for accessing all scheme benefits", "eligibility": "All AP farmers", "how_to_apply": "Register at village/ward secretariat or through Meeseva centres", "documents": "Aadhaar, land records (1B), mobile number", "deadline": "Within 2 weeks of crop sowing each season", "website": "https://agriculture.ap.gov.in", "helpline": "1800-180-1551"},
    ],
    "Telangana": [
        {"name": "Rythu Bandhu", "benefit": "₹10,000/acre/year (₹5,000 Kharif + ₹5,000 Rabi) — direct investment support", "eligibility": "All land-owning farmers (no income/land size limit)", "how_to_apply": "Auto-credited to registered farmers' bank accounts; register at agriculture department", "documents": "Pattadar passbook, Aadhaar card, bank passbook linked to Aadhaar", "deadline": "Kharif: credited by June; Rabi: credited by December", "website": "https://agriculture.telangana.gov.in", "helpline": "1800-180-1551"},
        {"name": "Rythu Bima", "benefit": "Free life insurance of ₹5 lakh for farmer families (age 18–59)", "eligibility": "All registered farmer families in Telangana", "how_to_apply": "Auto-enrolled; premium paid by state government; register at agriculture office", "documents": "Aadhaar, pattadar passbook, age proof, bank passbook, nominee details", "deadline": "Continuous enrollment; coverage renewed annually by state", "website": "https://agriculture.telangana.gov.in", "helpline": "1800-180-1551"},
        {"name": "E-Crop Registration", "benefit": "Mandatory digital crop booking for all scheme benefits", "eligibility": "All Telangana farmers", "how_to_apply": "Register at village agriculture office or through agriculture.telangana.gov.in", "documents": "Aadhaar, pattadar passbook, mobile number, crop details", "deadline": "Within 15 days of crop sowing each season", "website": "https://agriculture.telangana.gov.in", "helpline": "1800-180-1551"},
    ],
    "Karnataka": [
        {"name": "Raitha Siri", "benefit": "Input subsidy for farmer groups practicing integrated farming", "eligibility": "Farmer groups registered with agriculture department", "how_to_apply": "Through Raitha Samparka Kendra (RSK) at taluk level", "documents": "Group registration certificate, member Aadhaar cards, land records (RTC), bank account", "deadline": "Before Kharif sowing season (typically April–May)", "website": "https://raitamitra.karnataka.gov.in", "helpline": "1800-180-1551"},
        {"name": "Krishi Bhagya Scheme", "benefit": "80% subsidy for farm ponds and polyethylene lining for rainwater harvesting (up to ₹1 lakh)", "eligibility": "All Karnataka farmers (priority: small/marginal in dry zones)", "how_to_apply": "Apply at district agriculture office or raitamitra.karnataka.gov.in", "documents": "RTC (land record), Aadhaar, caste certificate (if applicable), bank passbook, land survey map", "deadline": "Year-round applications; approval subject to annual budget allocation", "website": "https://raitamitra.karnataka.gov.in", "helpline": "1800-180-1551"},
        {"name": "Bhoochetana", "benefit": "Soil health improvement in partnership with ICRISAT — free micronutrient supply", "eligibility": "Farmers in identified districts", "how_to_apply": "Through district agriculture office and Krishi Vigyan Kendra", "documents": "RTC, Aadhaar, soil test report (if available)", "deadline": "Before sowing season; district-wise schedule announced annually", "website": "https://raitamitra.karnataka.gov.in", "helpline": "1800-180-1551"},
        {"name": "Karnataka Raitha Suraksha", "benefit": "₹2 lakh insurance + ₹1 lakh accidental cover for registered farmers", "eligibility": "All registered farmers in Karnataka", "how_to_apply": "Register through Raitha Samparka Kendra at taluk level", "documents": "RTC, Aadhaar, bank passbook, passport-size photo, nominee details", "deadline": "Continuous enrollment; coverage renewed annually", "website": "https://raitamitra.karnataka.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Electricity for Agriculture", "benefit": "Free power for pump sets up to 10 HP", "eligibility": "All Karnataka farmers with agricultural pump connections", "how_to_apply": "Apply at BESCOM/HESCOM/GESCOM/MESCOM office with RTC and farming proof", "documents": "RTC, Aadhaar, pump set details, existing electricity connection proof", "deadline": "Year-round (new connections subject to transformer/infrastructure availability)", "website": "https://raitamitra.karnataka.gov.in", "helpline": "1800-180-1551"},
    ],
    "Maharashtra": [
        {"name": "Mahatma Jyotirao Phule Shetkari Karj Mukti Yojana", "benefit": "Farm loan waiver up to ₹2 lakh (cooperative bank crop loans)", "eligibility": "Farmers with crop loans from cooperative banks in Maharashtra", "how_to_apply": "Auto-waiver for eligible accounts; check at bank or mahadbt.maharashtra.gov.in", "documents": "Aadhaar, bank loan account details, 7/12 extract (land record), 8A certificate", "deadline": "As per government notification; check mahadbt.maharashtra.gov.in", "website": "https://mahadbt.maharashtra.gov.in", "helpline": "1800-180-1551"},
        {"name": "Gopinath Munde Shetkari Apghat Vima Yojana", "benefit": "₹2 lakh accidental death insurance + ₹1 lakh partial disability (age 10–75)", "eligibility": "All registered farmers in Maharashtra", "how_to_apply": "Claim through district agriculture officer; documents: death/disability certificate, land records", "documents": "7/12 extract, Aadhaar, death/disability certificate, FIR (if applicable), bank passbook, nominee Aadhaar", "deadline": "Claim within 90 days of incident", "website": "https://krishi.maharashtra.gov.in", "helpline": "1800-180-1551"},
        {"name": "Nanaji Deshmukh Krishi Sanjivani Yojana", "benefit": "World Bank-assisted climate-resilient agriculture — ₹4,000 crore project covering 5,142 villages", "eligibility": "Farmers in identified climate-vulnerable villages", "how_to_apply": "Through Krushi Vibhag (agriculture department) at village level", "documents": "7/12 extract, Aadhaar, bank passbook, village eligibility confirmation", "deadline": "Project phase-wise; contact local agriculture office for current phase", "website": "https://mahadbt.maharashtra.gov.in", "helpline": "1800-180-1551"},
        {"name": "Magel Tyala Shettale (Farm Pond)", "benefit": "50–75% subsidy for farm ponds; priority for drought-prone areas", "eligibility": "All Maharashtra farmers (priority: drought-prone talukas)", "how_to_apply": "Apply at district agriculture office or through mahadbt.maharashtra.gov.in", "documents": "7/12 extract, Aadhaar, bank passbook, caste certificate (if SC/ST), farm survey sketch", "deadline": "Year-round; apply on MahaDBT portal when applications open", "website": "https://mahadbt.maharashtra.gov.in", "helpline": "1800-180-1551"},
        {"name": "Bhausaheb Fundkar Falbag Lagan Yojana", "benefit": "Subsidy for fruit orchard plantation — ₹40,000–₹60,000/ha", "eligibility": "Farmers willing to plant fruit orchards", "how_to_apply": "Apply through district horticulture department", "documents": "7/12 extract, Aadhaar, bank passbook, orchard planting plan", "deadline": "Before planting season; check with district horticulture office", "website": "https://mahadbt.maharashtra.gov.in", "helpline": "1800-180-1551"},
    ],
    "Punjab": [
        {"name": "Diversification of Paddy", "benefit": "₹17,500/acre incentive for shifting from paddy to maize/cotton/other crops", "eligibility": "Punjab farmers willing to switch from paddy cultivation", "how_to_apply": "Register at block agriculture office before sowing season", "documents": "Jamabandi (land record), Aadhaar, bank passbook, crop declaration form", "deadline": "Before Kharif sowing season (April–May)", "website": "https://agri.punjab.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Power for Tube Wells", "benefit": "Highly subsidized/free electricity for agricultural tube wells", "eligibility": "All Punjab farmers with agricultural tube well connections", "how_to_apply": "Apply at PSPCL office with tube well documents", "documents": "Jamabandi, Aadhaar, tube well registration, PSPCL connection proof", "deadline": "Year-round (new connections subject to availability)", "website": "https://agri.punjab.gov.in", "helpline": "1800-180-1551"},
        {"name": "Custom Hiring Centres", "benefit": "State-subsidized tractor and harvester rental at every block", "eligibility": "All Punjab farmers", "how_to_apply": "Visit nearest Custom Hiring Centre or contact block agriculture officer", "documents": "Aadhaar, land record, advance booking form", "deadline": "Book before peak season (harvest: Oct–Nov for paddy, April for wheat)", "website": "https://agri.punjab.gov.in", "helpline": "1800-180-1551"},
        {"name": "Direct MSP Procurement", "benefit": "Over 95% of wheat and rice procured at MSP through government agencies", "eligibility": "All Punjab farmers with produce", "how_to_apply": "Register at nearest mandi or through Punjab Mandi Board portal", "documents": "Aadhaar, Jamabandi, bank passbook, crop arrival slip at mandi", "deadline": "Wheat: April–May; Paddy: Oct–Nov (procurement window announced yearly)", "website": "https://agri.punjab.gov.in", "helpline": "1800-180-1551"},
    ],
    "Haryana": [
        {"name": "Mera Pani Meri Virasat", "benefit": "₹7,000/acre incentive for switching from paddy + ₹2 lakh subsidy for micro-irrigation", "eligibility": "Haryana farmers willing to switch from paddy to alternative crops", "how_to_apply": "Register through Meri Fasal Mera Byora portal (fasal.haryana.gov.in)", "documents": "Jamabandi, Aadhaar, bank passbook, Meri Fasal Mera Byora registration", "deadline": "Before Kharif sowing (May–June); register on portal when window opens", "website": "https://fasal.haryana.gov.in", "helpline": "1800-180-2117"},
        {"name": "Free Power for Tube Wells", "benefit": "Highly subsidized electricity for agricultural use", "eligibility": "All Haryana farmers with agricultural connections", "how_to_apply": "Apply at UHBVN/DHBVN office with land and farming documents", "documents": "Jamabandi, Aadhaar, tube well registration, electricity connection proof", "deadline": "Year-round (new connections subject to infrastructure availability)", "website": "https://agriharyana.gov.in", "helpline": "1800-180-2117"},
        {"name": "Direct MSP Procurement", "benefit": "Over 95% of wheat and rice procured at MSP", "eligibility": "All Haryana farmers", "how_to_apply": "Register at nearest mandi or through agriharyana.gov.in", "documents": "Aadhaar, Jamabandi, bank passbook, Meri Fasal Mera Byora registration", "deadline": "Wheat: April–May; Paddy: Oct–Nov", "website": "https://agriharyana.gov.in", "helpline": "1800-180-2117"},
    ],
    "Uttar Pradesh": [
        {"name": "Kisan Rath App", "benefit": "Government app connecting farmers with transport vehicles during harvest — reduces post-harvest losses", "eligibility": "All UP farmers with produce to transport", "how_to_apply": "Download Kisan Rath App from Google Play Store", "documents": "Mobile number, Aadhaar (for registration), produce details", "deadline": "Year-round; most useful during harvest seasons", "website": "https://upagripardarshi.gov.in", "helpline": "1800-180-1551"},
        {"name": "Mukhyamantri Krishak Vriksh Dhan Yojana", "benefit": "₹30,000–₹50,000 per farmer for planting fruit trees on farmland", "eligibility": "UP farmers willing to plant fruit/timber trees on farmland", "how_to_apply": "Apply through district horticulture and forest department", "documents": "Khatauni (land record), Aadhaar, bank passbook, planting plan", "deadline": "Before monsoon planting season (June–July)", "website": "https://upagripardarshi.gov.in", "helpline": "1800-180-1551"},
        {"name": "UP Solar Pump Scheme", "benefit": "70% subsidy on solar water pumps (2 HP to 5 HP) for irrigation", "eligibility": "All UP farmers; priority for small/marginal", "how_to_apply": "Apply through upagripardarshi.gov.in or district agriculture office", "documents": "Khatauni, Aadhaar, bank passbook, passport-size photo, caste certificate (if applicable)", "deadline": "Apply when portal opens; limited slots per district per year", "website": "https://upagripardarshi.gov.in", "helpline": "1800-180-1551"},
        {"name": "Pardarshi Kisan Seva Yojana", "benefit": "Subsidized seeds, fertilizer distribution, and mini-kit program", "eligibility": "All registered farmers in UP", "how_to_apply": "Through single-window portal upagripardarshi.gov.in", "documents": "Khatauni, Aadhaar, bank passbook, mobile number", "deadline": "Before each crop season; register on portal for allocation", "website": "https://upagripardarshi.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Boring Scheme", "benefit": "Free boring of tube wells for SC/ST/small/marginal farmers (up to 70m depth)", "eligibility": "SC/ST/small/marginal farmers in UP", "how_to_apply": "Apply at block development office or Minor Irrigation Department", "documents": "Khatauni, Aadhaar, caste certificate, income certificate, bank passbook", "deadline": "Year-round; apply at block office (first-come allocation)", "website": "https://upagripardarshi.gov.in", "helpline": "1800-180-1551"},
    ],
    "Odisha": [
        {"name": "KALIA (Krushak Assistance for Livelihood and Income Augmentation)", "benefit": "₹10,000/year for small/marginal farmers; ₹12,500/year for landless households", "eligibility": "Small/marginal farmers and landless agricultural households in Odisha", "how_to_apply": "Register at kalia.odisha.gov.in or through GP-level functionaries", "documents": "Aadhaar, land records (ROR), bank passbook, mobile number", "deadline": "Continuous enrollment; payments in Kharif and Rabi installments", "website": "https://agri.odisha.gov.in", "helpline": "1800-180-1551"},
        {"name": "Balaram Yojana", "benefit": "Up to ₹1 lakh crop loan without collateral for landless cultivators", "eligibility": "Landless cultivators and sharecroppers in Odisha", "how_to_apply": "Apply through Primary Agricultural Cooperative Societies (PACS)", "documents": "Aadhaar, sharecropper certificate from gram panchayat, bank passbook", "deadline": "Before each crop season; apply at nearest PACS", "website": "https://agri.odisha.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Crop Insurance", "benefit": "Odisha pays PMFBY farmer premium from state funds — effectively free insurance", "eligibility": "All Odisha farmers growing notified crops", "how_to_apply": "Auto-enrolled through banks during crop loan; register at agriculture office", "documents": "Aadhaar, land records (ROR), crop loan documents, crop sowing details", "deadline": "Kharif: before July 31; Rabi: before December 31", "website": "https://agri.odisha.gov.in", "helpline": "1800-180-1551"},
    ],
    "Rajasthan": [
        {"name": "Mukhyamantri Krishak Sathi Yojana", "benefit": "₹2 lakh assistance for farmer death/disability during farming operations", "eligibility": "All farmers in Rajasthan (age 5–70)", "how_to_apply": "Claim through district agriculture officer; documents: FIR/medical report, land records, Aadhaar", "documents": "Aadhaar, Jamabandi, FIR/medical report, death/disability certificate, bank passbook of nominee", "deadline": "Claim within 6 months of incident", "website": "https://rajkisan.rajasthan.gov.in", "helpline": "1800-180-1551"},
        {"name": "Tarbandi Yojana", "benefit": "50% or up to ₹48,000 for barbed wire fencing (400 running meters) to protect crops", "eligibility": "Farmers with minimum 1.5 hectares (SC/ST: 0.5 hectares)", "how_to_apply": "Apply at e-mitra centre or through rajkisan.rajasthan.gov.in", "documents": "Jamabandi (land record), Aadhaar, bank passbook, caste certificate (if SC/ST), land map", "deadline": "Year-round; apply on Raj Kisan portal when funds available", "website": "https://rajkisan.rajasthan.gov.in", "helpline": "1800-180-1551"},
        {"name": "Micro-Irrigation Subsidy", "benefit": "70% subsidy on drip/sprinkler systems for small farmers", "eligibility": "Small and marginal farmers in Rajasthan", "how_to_apply": "Apply through district horticulture department or rajkisan.rajasthan.gov.in", "documents": "Jamabandi, Aadhaar, bank passbook, quotation from approved irrigation supplier", "deadline": "Year-round; subject to annual budget allocation per district", "website": "https://rajkisan.rajasthan.gov.in", "helpline": "1800-180-1551"},
    ],
    "Kerala": [
        {"name": "Haritashree", "benefit": "₹50/seedling for tree planting and agroforestry on farmlands", "eligibility": "All Kerala farmers", "how_to_apply": "Apply through Krishi Bhavan (village-level agriculture office)", "documents": "Aadhaar, land records (thandaper), bank passbook, planting proposal", "deadline": "Before monsoon planting season (June–July)", "website": "https://keralaagriculture.gov.in", "helpline": "1800-180-1551"},
        {"name": "Subhiksha Keralam", "benefit": "Input subsidies for rice, vegetable, and tuber cultivation", "eligibility": "All Kerala farmers promoting food security crops", "how_to_apply": "Register through Krishi Bhavan or krishibhavan.kerala.gov.in", "documents": "Aadhaar, land records, bank passbook, crop plan declaration", "deadline": "Before each cropping season; register at Krishi Bhavan", "website": "https://keralaagriculture.gov.in", "helpline": "1800-180-1551"},
        {"name": "Jeevani", "benefit": "Free crop insurance for paddy, banana, and pepper farmers", "eligibility": "Paddy, banana, and pepper farmers in Kerala", "how_to_apply": "Apply through Krishi Bhavan before sowing season", "documents": "Aadhaar, land records (thandaper), crop details, bank passbook", "deadline": "Before sowing season (varies by crop: paddy June/Oct, banana year-round)", "website": "https://keralaagriculture.gov.in", "helpline": "1800-180-1551"},
    ],
    "Madhya Pradesh": [
        {"name": "Bhavantar Bhugtan Yojana", "benefit": "Price deficiency payment — government pays difference if market price falls below MSP", "eligibility": "All MP farmers selling notified crops", "how_to_apply": "Register on mpeuparjan.nic.in before harvest season", "documents": "Aadhaar, Khasra/B1 (land record), bank passbook, mobile number", "deadline": "Register 7 days before selling; check mpeuparjan.nic.in for crop-wise windows", "website": "https://mpeuparjan.nic.in", "helpline": "1800-180-1551"},
        {"name": "Mukhyamantri Kisan Kalyan Yojana", "benefit": "₹4,000/year on top of PM-KISAN (total ₹10,000/year)", "eligibility": "All PM-KISAN beneficiaries in Madhya Pradesh", "how_to_apply": "Auto-enrolled for PM-KISAN beneficiaries; register at agriculture office if not yet enrolled", "documents": "Same as PM-KISAN: Aadhaar, Khasra/B1, bank passbook linked to Aadhaar", "deadline": "Continuous; auto-credited along with PM-KISAN installments", "website": "https://mpkrishi.mp.gov.in", "helpline": "1800-180-1551"},
        {"name": "Chief Minister Solar Pump Scheme", "benefit": "90% subsidy on solar pumps for farmers", "eligibility": "MP farmers needing irrigation; priority for small/marginal", "how_to_apply": "Apply through cmsolarpump.mp.gov.in or district agriculture office", "documents": "Khasra/B1, Aadhaar, bank passbook, electricity bill (if existing connection), caste certificate (if applicable)", "deadline": "Apply on portal when applications open; limited slots per year", "website": "https://cmsolarpump.mp.gov.in", "helpline": "1800-180-1551"},
    ],
    "Puducherry": [
        {"name": "Puducherry Crop Insurance", "benefit": "State-subsidized crop insurance with minimal farmer premium for paddy, sugarcane, and banana", "eligibility": "All farmers in Puducherry growing notified crops", "how_to_apply": "Apply through district agriculture office or cooperative banks", "documents": "Aadhaar card, land records (patta), bank passbook, crop sowing certificate", "deadline": "Kharif: before July 31; Rabi: before December 31", "website": "https://agri.py.gov.in", "helpline": "1800-180-1551"},
        {"name": "Free Electricity for Agriculture", "benefit": "Free electricity for agricultural pump sets", "eligibility": "All Puducherry farmers with agricultural pump connections", "how_to_apply": "Apply at Electricity Department office with land and farming proof", "documents": "Patta (land record), Aadhaar card, pump set registration, farming activity proof", "deadline": "Year-round (new connections subject to availability)", "website": "https://agri.py.gov.in", "helpline": "1800-180-1551"},
        {"name": "Subsidy for Farm Mechanization", "benefit": "50-75% subsidy on agricultural machinery (power tillers, sprayers, harvesters)", "eligibility": "Small and marginal farmers in Puducherry", "how_to_apply": "Apply through district agriculture department", "documents": "Patta, Aadhaar card, bank passbook, quotation from approved vendor", "deadline": "Year-round; subject to annual budget allocation", "website": "https://agri.py.gov.in", "helpline": "1800-180-1551"},
    ],
}


def _filter_state_schemes(farmer_state):
    """Return state-specific schemes when a farmer state is provided."""
    normalized_state = (farmer_state or '').strip().lower()
    if not normalized_state:
        return STATE_SCHEMES

    for state_name, schemes in STATE_SCHEMES.items():
        if state_name.lower() == normalized_state:
            return {state_name: schemes}

    return {}


def lambda_handler(event, context):
    """Returns government scheme information."""
    try:
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            if ENABLE_UNIFIED_CORS:
                return handle_cors_preflight(methods='GET,POST,OPTIONS')
            return success_response({}, message='OK')

        if 'parameters' in event:
            # Legacy Bedrock format (fallback)
            params = {p['name']: p['value'] for p in event['parameters']}
            scheme_name = _sanitize_input(params.get('scheme_name', 'all')).lower()
            farmer_state = _sanitize_input(params.get('farmer_state', ''))
        else:
            # API Gateway GET: read from query string; POST: read from body
            qs = event.get('queryStringParameters') or {}
            if qs:
                scheme_name = _sanitize_input(qs.get('query', qs.get('name', qs.get('search', 'all')))).lower()
                farmer_state = _sanitize_input(qs.get('state', qs.get('farmer_state', '')))
            else:
                body = json.loads(event.get('body', '{}')) if event.get('body') else {}
                scheme_name = _sanitize_input(body.get('scheme_name', 'all')).lower()
                farmer_state = _sanitize_input(body.get('farmer_state', ''))

        if scheme_name == 'all':
            result = SCHEMES
        elif scheme_name in SCHEMES:
            result = SCHEMES[scheme_name]
        else:
            # Search by keyword across name, full_name, and benefit
            result = {k: v for k, v in SCHEMES.items()
                     if scheme_name in v['name'].lower()
                     or scheme_name in v['full_name'].lower()
                     or scheme_name in v.get('benefit', '').lower()}

        result_data = {
            'schemes': result,
            'state_schemes': _filter_state_schemes(farmer_state),
            'note': 'Contact Kisan Call Centre at 1800-180-1551 for more details'
        }

        return success_response(result_data)

    except Exception as e:
        logger.error(f"Schemes error: {str(e)}", exc_info=True)
        # Security: never expose internal error details
        return error_response("Government schemes service is temporarily unavailable. Please try again.", 500)
