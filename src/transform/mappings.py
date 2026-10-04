"""Name and place mappings for the task 6 cleaning scripts.

Standard naming: OpenHalalan's province names.
"""

# HF memberships province names -> standard names
HF_PROVINCE_MAP = {
    "NCR, CITY OF MANILA, FIRST DISTRICT": "NCR FIRST DISTRICT",
    "NCR, SECOND DISTRICT": "NCR SECOND DISTRICT",
    "NCR, THIRD DISTRICT": "NCR THIRD DISTRICT",
    "NCR, FOURTH DISTRICT": "NCR FOURTH DISTRICT",
    "TAWI-TAWI": "TAWI TAWI",
    "COMPOSTELA VALLEY": "DAVAO DE ORO",
}

# Town names (after norm_town) -> standard names. Used for every source.
TOWN_MAP = {
    # HF typos and abbreviations
    "MAGADALENA": "MAGDALENA",
    "SAM NARCISO": "SAN NARCISO",
    "PRES CARLOS P GARCIA": "PRESIDENT CARLOS P GARCIA",
    "CORDOBA": "CORDOVA",
    # OpenHalalan variants of the same town
    "PRES C P GARCIA": "PRESIDENT CARLOS P GARCIA",
    "PRES CARLOS P GARCIA PITOGO": "PRESIDENT CARLOS P GARCIA",
    # Taguig-Pateros congressional district (House rows only)
    "PATEROS TAGUIG": "TAGUIG PATEROS",
    # OpenHalalan old-name variants (suggested by code, reviewed)
    "ALFONSO LISTA POTIA": "ALFONSO LISTA",
    "AMLAN AYUQUITAN": "AMLAN",
    "ASUNCION SAUG": "ASUNCION",
    "BALAGTAS BIGAA": "BALAGTAS",
    "BALINDONG WATU": "BALINDONG",
    "BASILISA RIZAL": "BASILISA",
    "CALANASAN BAYAG": "CALANASAN",
    "DARAGA LOCSIN": "DARAGA",
    "DATU ODIN SINSUAT DINAIG": "DATU ODIN SINSUAT",
    "DELFIN ALBANO MAGSAYSAY": "DELFIN ALBANO",
    "DON VICTORIANO CHIONGBIAN DON MARIANO MARCOS": "DON VICTORIANO CHIONGBIAN",
    "ENRIQUE B MAGALONA SARAVIA": "ENRIQUE B MAGALONA",
    "EL NIDO BACUIT": "EL NIDO",
    "GENERAL TINIO PAPAYA": "GENERAL TINIO",
    "GREGORIO DEL PILAR CONCEPCION": "GREGORIO DEL PILAR",
    "HINOBA AN ASIA": "HINOBA AN",
    "JOSE ABAD SANTOS TRINIDAD": "JOSE ABAD SANTOS",
    "JOSE DALMAN PONOT": "JOSE DALMAN",
    "KABUNTALAN TUMBAO": "KABUNTALAN",
    "LAAK SAN VICENTE": "LAAK",
    "LAMBAYONG MARIANO MARCOS": "LAMBAYONG",
    "LAPU LAPU CITY OPON": "LAPU LAPU",
    "LIBJO ALBOR": "LIBJO",
    "LICUAN BAAY LICUAN": "LICUAN BAAY",
    "LUMBA BAYABAO MAGUING": "LUMBA BAYABAO",
    "MABINI DONA ALICIA": "MABINI",
    "MAGSAYSAY LINUGOS": "MAGSAYSAY",
    "MAPUN CAGAYAN DE TAWI TAWI": "MAPUN",
    "MARAGUSAN SAN MARIANO": "MARAGUSAN",
    "MENDEZ MENDEZ NUNEZ": "MENDEZ",
    "MOISES PADILLA MAGALLON": "MOISES PADILLA",
    "PANGANIBAN PAYO": "PANGANIBAN",
    "PANGLIMA SUGALA BALIMBING": "PANGLIMA SUGALA",
    "PARANAS WRIGHT": "PARANAS",
    "PICONG SULTAN GUMANDER": "PICONG",
    "PINAN NEW PINAN": "PINAN",
    "PIO V CORPUZ LIMBUHAN": "PIO V CORPUZ",
    "POONA BAYABAO GATA": "POONA BAYABAO",
    "PRESENTACION PARUBCAN": "PRESENTACION",
    "QUIRINO ANGKAKI": "QUIRINO",
    "RAMON MAGSAYSAY LIARGO": "RAMON MAGSAYSAY",
    "RIZAL LIWAN": "RIZAL",
    "RIZAL MARCOS": "RIZAL",
    "RODRIGUEZ MONTALBAN": "RODRIGUEZ",
    "SAGBAYAN BORJA": "SAGBAYAN",
    "SAN ANDRES CALOLBON": "SAN ANDRES",
    "SAN FRANCISCO ANAO AON": "SAN FRANCISCO",
    "SAN FRANCISCO AURORA": "SAN FRANCISCO",
    "SAN LORENZO RUIZ IMELDA": "SAN LORENZO RUIZ",
    "SANTA MARIA IMELDA": "SANTA MARIA",
    "SANTA MONICA SAPAO": "SANTA MONICA",
    "SANTO DOMINGO LIBOG": "SANTO DOMINGO",
    "SANTO NINO FAIRE": "SANTO NINO",
    "SHARIFF AGUAK MAGANOY": "SHARIFF AGUAK",
    "SOMINOT DON MARIANO MARCOS": "SOMINOT",
    "SULTAN KUDARAT NULING": "SULTAN KUDARAT",
    "SULTAN SA BARONGIS LAMBAYONG": "SULTAN SA BARONGIS",
    "TOBIAS FORNIER DAO": "TOBIAS FORNIER",
    "VALENCIA LUZURRIAGA": "VALENCIA",
}

# Province-specific town fixes, for names that are valid in other provinces
PROVINCE_TOWN_MAP = {
    ("LANAO DEL SUR", "TAGOLOAN"): "TAGOLOAN II",
}


# PSA poverty district keys -> standard province names
PSA_AREA_MAP = {
    "1ST DISTRICT": "NCR FIRST DISTRICT",
    "2ND DISTRICT": "NCR SECOND DISTRICT",
    "3RD DISTRICT": "NCR THIRD DISTRICT",
    "4TH DISTRICT": "NCR FOURTH DISTRICT",
}

# Cities that PSA reports like provinces: area_key -> (province, town)
PSA_CITY_MAP = {
    "COTABATO CITY": ("MAGUINDANAO", "COTABATO"),
    "ISABELA CITY": ("BASILAN", "ISABELA"),
}


# Roster period names: typo fixes (applied as text replacements)
PERIOD_TYPO_MAP = {
    "Philipine": "Philippine",
    "Pamabansa": "Pambansa",
    "Pambasa": "Pambansa",
    "Congresss": "Congress",
    "Asssembly": "Assembly",
    "thCongress": "th Congress",
    "Legislative": "Legislature",
    "Batasan Pambansa": "Batasang Pambansa",
    "Commenwealth": "Commonwealth",
}

# Ordinal words at the start of a period name -> numbers
ORDINAL_WORDS = {
    "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6,
    "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9, "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12,
    "THIRTEENTH": 13, "FOURTEENTH": 14, "FIFTEENTH": 15, "SIXTEENTH": 16,
    "SEVENTEENTH": 17, "EIGHTEENTH": 18, "NINETEENTH": 19, "TWENTIETH": 20,
}

# Remaining period variants -> one standard name
PERIOD_MAP = {
    "1st National Assembly Commonwealth": "1st Commonwealth National Assembly",
    "1st Congress Commonwealth": "1st Congress of Commonwealth",
}


# Roster region_province (uppercased, no asterisks) -> standard province, or a city for the lookup
ROSTER_PROVINCE_MAP = {
    # Typos
    "COMPOSTELLA VALLEY": "DAVAO DE ORO",
    "SOUTH COTOBATO": "SOUTH COTABATO",
    "NUEVA VISCAYA": "NUEVA VIZCAYA",
    "ZAMBOAGA SIBUGAY": "ZAMBOANGA SIBUGAY",
    # Old or alternate names
    "COMPOSTELA VALLEY": "DAVAO DE ORO",
    "WESTERN SAMAR": "SAMAR",
    "DINAGAT ISLAND": "DINAGAT ISLANDS",
    "TAWI-TAWI": "TAWI TAWI",
    # Shared districts -> one of their places, resolved by the city lookup
    "TAGUIG-PATEROS": "TAGUIG CITY",
    "TAGUIG CITY-PATEROS": "TAGUIG CITY",
    "TAGUIG CITY/PATEROS": "TAGUIG CITY",
    "MALABON / NAVOTAS": "MALABON CITY",
    "MALABON-NAVOTAS": "MALABON CITY",
    "MALABON-NAVOTAS CITY": "MALABON CITY",
    "SOUTH COTABATO AND GENERAL SANTOS CITY": "SOUTH COTABATO",
    "MAGUINDANAO AND COTABATO CITY": "MAGUINDANAO",
    "MAGUINDANAO WITH COTABATO CITY": "MAGUINDANAO",
    "SHARIFF KABUNSUAN WITH COTABATO CITY": "MAGUINDANAO",
    # Found in testing
    "NORTH COTABATO": "COTABATO",
    "NORTH COTOBATO": "COTABATO",
    "PATEROS/TAGUIG": "TAGUIG CITY",
    "LAS PIÑAS-MUNTINLUPA CITY": "LAS PIÑAS CITY",
    "LAS PIÑAS/MUNTINLUPA": "LAS PIÑAS CITY",
    "SAN JUAN-MANDALUYONG": "MANDALUYONG CITY",
}


# Roster city names that exist in several provinces: name -> (province, town)
ROSTER_CITY_MAP = {
    "QUEZON CITY": ("NCR SECOND DISTRICT", "QUEZON"),
    "BACOLOD CITY": ("NEGROS OCCIDENTAL", "BACOLOD"),
    "SAN JUAN CITY": ("NCR SECOND DISTRICT", "SAN JUAN"),
    "SAN JUAN": ("NCR SECOND DISTRICT", "SAN JUAN"),
}

# Roster rows with a blank province, recovered from OpenHalalan House records: name -> province
ROSTER_MISSING_PROVINCE = {
    "DIMAPORO, IMELDA Q.": "LANAO DEL NORTE",
    "FLORES, FLORENCIO JR. T.": "BUKIDNON",
}