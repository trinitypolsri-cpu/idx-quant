"""Universe saham IDX.

Daftar kandidat ticker (tanpa suffix). Ticker yang tidak mengembalikan data
akan otomatis di-drop oleh loader, jadi daftar boleh lebih luas dari kenyataan.
"""

BENCHMARK = "^JKSE"

# ~260 kandidat: LQ45 + IDX80 + mid/small cap likuid lintas sektor.
CANDIDATES = [
    # Perbankan & keuangan
    "BBCA", "BBRI", "BMRI", "BBNI", "BRIS", "BBTN", "BJBR", "BJTM", "BNGA",
    "NISP", "PNBN", "MEGA", "BBKP", "ARTO", "BTPS", "BTPN", "BFIN", "ADMF",
    "BNLI", "MAYA", "AGRO", "BABP", "BBHI", "BBYB", "AMAR", "BANK", "PNLF",
    "PNIN", "ASRM", "LPGI", "TUGU", "AMAG", "VICO", "TRIM", "PANS", "RELI",
    # Consumer & ritel
    "UNVR", "ICBP", "INDF", "MYOR", "KLBF", "SIDO", "ULTJ", "ROTI", "CLEO",
    "GGRM", "HMSP", "WIIM", "AMRT", "MIDI", "ACES", "MAPI", "MAPA", "RALS",
    "LPPF", "ERAA", "CSAP", "HERO", "DMND", "CAMP", "GOOD", "KEJU", "PANI",
    "TSPC", "PEHA", "PYFA", "DVLA", "MERK", "KAEF", "INAF", "SOHO", "MIKA",
    "HEAL", "SILO", "SRAJ", "PRDA", "BMHS", "CARE",
    # Telekomunikasi, teknologi, media
    "TLKM", "EXCL", "ISAT", "FREN", "TOWR", "TBIG", "MTEL", "LINK", "JAST",
    "GOTO", "BUKA", "EMTK", "MNCN", "SCMA", "VIVA", "MSIN", "FILM", "IATA",
    "DCII", "EDGE", "MLPT", "WIFI", "TFAS", "KIOS", "DIVA", "MCAS", "NFCX",
    # Energi & tambang
    "ADRO", "PTBA", "ITMG", "HRUM", "BUMI", "BYAN", "GEMS", "INDY", "DOID",
    "MBAP", "TOBA", "ABMM", "KKGI", "SMMT", "BOSS", "DEWA", "ARII", "PTRO",
    "MEDC", "PGAS", "ELSA", "ENRG", "RAJA", "AKRA", "APEX", "WINS", "MITI",
    "ANTM", "INCO", "MDKA", "TINS", "PSAB", "BRMS", "ARCI", "ZINC", "NCKL",
    "HRTA", "MBMA", "IFSH", "CITA", "DKFT", "SMRU", "TRAM", "CUAN", "BREN",
    # Industri dasar & kimia
    "SMGR", "INTP", "SMCB", "WTON", "WSBP", "BRPT", "TPIA", "ESSA", "AGII",
    "INKP", "TKIM", "FASW", "SPMA", "ALDO", "ISSP", "GDST", "KRAS", "NIKL",
    "CPIN", "JPFA", "MAIN", "SIPD", "AALI", "LSIP", "SIMP", "SSMS", "DSNG",
    "TAPG", "BWPT", "ANJT", "SGRO", "PALM", "TBLA", "SMAR", "CEKA", "MGRO",
    # Properti, konstruksi, infrastruktur
    "PWON", "BSDE", "CTRA", "SMRA", "ASRI", "LPKR", "DMAS", "MTLA", "APLN",
    "JRPT", "GMTD", "DILD", "BEST", "SSIA", "RDTX", "PPRO", "KIJA", "MDLN",
    "WIKA", "WSKT", "PTPP", "ADHI", "TOTL", "NRCA", "ACST", "IDPR", "JSMR",
    "META", "CMNP", "PTPS",
    # Otomotif, industri, aneka
    "ASII", "UNTR", "AUTO", "GJTL", "IMAS", "MASA", "SMSM", "BRAM", "INDS",
    "SELL", "LPIN", "ARNA", "TOTO", "KIAS", "MLIA", "CAKK", "IKAI",
    "TRIS", "SRIL", "PBRX", "MYTX", "ERTX", "STAR", "BELL", "UCID", "CINT",
    # Transportasi, logistik, pariwisata
    "GIAA", "GMFI", "CASS", "SMDR", "TMAS", "IPCM", "IPCC", "PTIS", "BIRD",
    "ASSA", "TAXI", "SAFE", "NELY", "HITS", "BULL", "PSSI", "LEAD", "SOCI",
    "PJAA", "PANR", "PGJO", "HOTL", "SHID", "INPP", "JIHD", "BAYU", "FAST",
    "PZZA", "ENAK", "MAPB", "CSMI",
    # Utilitas & lain-lain
    "POWR", "KEEN", "ARKO", "TGRA", "BIPI", "MPOW", "KOPI", "SURE",
    "ADMR", "AMMN", "BLES", "STAA", "MSTI", "AXIO", "TECH", "LUCK", "IPTV",
]

# Peta sektor kasar (untuk laporan; bukan klasifikasi resmi IDX-IC).
SECTOR = {}
def _tag(names, sector):
    for n in names:
        SECTOR[n] = sector

_tag(["BBCA","BBRI","BMRI","BBNI","BRIS","BBTN","BJBR","BJTM","BNGA","NISP",
      "PNBN","MEGA","BBKP","ARTO","BTPS","BTPN","BFIN","ADMF","BNLI","MAYA",
      "AGRO","BABP","BBHI","BBYB","AMAR","BANK","PNLF","PNIN","ASRM","LPGI",
      "TUGU","AMAG","VICO","TRIM","PANS","RELI"], "Keuangan")
_tag(["UNVR","ICBP","INDF","MYOR","KLBF","SIDO","ULTJ","ROTI","CLEO","GGRM",
      "HMSP","WIIM","AMRT","MIDI","ACES","MAPI","MAPA","RALS","LPPF","ERAA",
      "CSAP","HERO","DMND","CAMP","GOOD","KEJU","PANI","TSPC","PEHA","PYFA",
      "DVLA","MERK","KAEF","INAF","SOHO","MIKA","HEAL","SILO","SRAJ","PRDA",
      "BMHS","CARE"], "Konsumer & Kesehatan")
_tag(["TLKM","EXCL","ISAT","FREN","TOWR","TBIG","MTEL","LINK","JAST","GOTO",
      "BUKA","EMTK","MNCN","SCMA","VIVA","MSIN","FILM","IATA","DCII","EDGE",
      "MLPT","WIFI","TFAS","KIOS","DIVA","MCAS","NFCX"], "Telko & Teknologi")
_tag(["ADRO","PTBA","ITMG","HRUM","BUMI","BYAN","GEMS","INDY","DOID","MBAP",
      "TOBA","ABMM","KKGI","SMMT","BOSS","DEWA","ARII","PTRO","MEDC","PGAS",
      "ELSA","ENRG","RAJA","AKRA","APEX","WINS","MITI","ADMR","BIPI"], "Energi")
_tag(["ANTM","INCO","MDKA","TINS","PSAB","BRMS","ARCI","ZINC","NCKL","HRTA",
      "MBMA","IFSH","CITA","DKFT","SMRU","TRAM","CUAN","BREN","AMMN","NIKL",
      "KRAS","GDST","ISSP"], "Logam & Mineral")
_tag(["SMGR","INTP","SMCB","WTON","WSBP","BRPT","TPIA","ESSA","AGII","INKP",
      "TKIM","FASW","SPMA","ALDO","ARNA","TOTO","KIAS","MLIA","CAKK","IKAI"],
     "Industri Dasar")
_tag(["CPIN","JPFA","MAIN","SIPD","AALI","LSIP","SIMP","SSMS","DSNG","TAPG",
      "BWPT","ANJT","SGRO","PALM","TBLA","SMAR","CEKA","MGRO","STAA"],
     "Agri & Pangan")
_tag(["PWON","BSDE","CTRA","SMRA","ASRI","LPKR","DMAS","MTLA","APLN","JRPT",
      "GMTD","DILD","BEST","SSIA","RDTX","PPRO","KIJA","MDLN","WIKA","WSKT",
      "PTPP","ADHI","TOTL","NRCA","ACST","IDPR","JSMR","META","CMNP","PTPS"],
     "Properti & Konstruksi")
_tag(["ASII","UNTR","AUTO","GJTL","IMAS","MASA","SMSM","BRAM","INDS","SELL",
      "LPIN","TRIS","SRIL","PBRX","MYTX","ERTX","STAR","BELL","UCID","CINT"],
     "Otomotif & Aneka Industri")
_tag(["GIAA","GMFI","CASS","SMDR","TMAS","IPCM","IPCC","PTIS","BIRD","ASSA",
      "TAXI","SAFE","NELY","HITS","BULL","PSSI","LEAD","SOCI","PJAA","PANR",
      "PGJO","HOTL","SHID","INPP","JIHD","BAYU","FAST","PZZA","ENAK","MAPB",
      "CSMI"], "Transport & Pariwisata")
_tag(["POWR","KEEN","ARKO","TGRA","MPOW","KOPI","SURE","BLES","MSTI","AXIO",
      "TECH","LUCK","IPTV"], "Utilitas & Lainnya")


def yahoo_symbol(ticker: str) -> str:
    """IDX ticker -> simbol Yahoo Finance.

    Hanya kode IDX polos (huruf/angka saja) yang diberi akhiran `.JK`. Simbol
    non-IDX seperti indeks (^JKSE), futures (CL=F), valas (IDR=X), atau bursa
    lain (000001.SS) dibiarkan apa adanya — menambahkan `.JK` ke simbol itu
    menghasilkan permintaan yang selalu gagal secara diam-diam.
    """
    t = ticker.strip()
    if not t or not t.isalnum():
        return t
    return f"{t}.JK"


def sector_of(ticker: str) -> str:
    return SECTOR.get(ticker, "Lainnya")
