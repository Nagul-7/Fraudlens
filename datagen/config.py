"""
All knobs for the synthetic fraud world live in this one file.

Every parameter has a comment saying what real-world behaviour it models.
Change a number here, re-run `python -m datagen.generate`, and the whole
world is rebuilt. Because there is ONE seed, the same config always
produces the exact same database.
"""

# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------
SEED = 20260904  # the only random seed in the project (numpy Generator)

# ---------------------------------------------------------------------------
# World size
# ---------------------------------------------------------------------------
START_DATE = "2025-01-01"  # simulated day 0
N_DAYS = 365               # 12 months of history
COMPLAINTS_PER_DAY = 300   # mean complaints per day. Real India is ~8000/day;
                           # we scale down so everything runs on a laptop.

# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
# Public India districts GeoJSON (Census-2011 codes, includes later district
# splits). Curated by udit-001/india-maps-data from public sources.
GEOJSON_URL = ("https://cdn.jsdelivr.net/gh/udit-001/india-maps-data@2884453"
               "/geojson/india.geojson")
GEOJSON_RAW_PATH = "data/india_districts_raw.geojson"  # as downloaded
GEOJSON_PATH = "data/india_districts.geojson"          # cleaned + district_id
DB_PATH = "data/fraudlens.db"

# ---------------------------------------------------------------------------
# Initial hotspots: ~25 districts in known mule-corridor regions.
# (state, district) must match names in the GeoJSON exactly.
# These are the "known-style" corridors at day 0; they DRIFT later (see below).
# ---------------------------------------------------------------------------
INITIAL_HOTSPOTS = [
    # Jharkhand - the classic "Jamtara belt"
    ("Jharkhand", "Jamtara"), ("Jharkhand", "Deoghar"), ("Jharkhand", "Giridih"),
    ("Jharkhand", "Dhanbad"), ("Jharkhand", "Dumka"), ("Jharkhand", "Bokaro"),
    # Haryana / Delhi NCR - Mewat belt + metro cash-out
    ("Haryana", "Nuh"), ("Haryana", "Gurugram"), ("Haryana", "Faridabad"),
    ("Haryana", "Palwal"), ("Delhi", "Delhi"),
    ("Uttar Pradesh", "Gautam Buddha Nagar"), ("Uttar Pradesh", "Ghaziabad"),
    # Rajasthan - Bharatpur / Alwar corridor
    ("Rajasthan", "Bharatpur"), ("Rajasthan", "Alwar"), ("Rajasthan", "Dholpur"),
    ("Rajasthan", "Jaipur"),
    # West Bengal - Kolkata metro + border districts
    ("West Bengal", "Kolkata"), ("West Bengal", "North 24 Parganas"),
    ("West Bengal", "Howrah"), ("West Bengal", "Murshidabad"),
    # Assam - Guwahati + lower Assam
    ("Assam", "Kamrup Metropolitan"), ("Assam", "Barpeta"), ("Assam", "Nagaon"),
    ("Assam", "Dhubri"),
]

# ---------------------------------------------------------------------------
# Districts, ATMs, accounts (static world)
# ---------------------------------------------------------------------------
# Population comes from the real Census 2011, joined by district name in
# datagen/population.py. `population_weight` is that population normalised to
# mean 1.0 across districts, and it drives victims, mules, ATMs and the
# background (non-corridor) cash-out rate.
# (Until Phase 4 this was a random log-normal proxy, which occasionally made a
# remote district like Kargil look bigger than a metro and let it be drawn as a
# hotspot. Real population removes that whole class of nonsense.)
HOTSPOT_POP_EXPONENT = 2.0   # when a burned hotspot is replaced by a random
                             # district, draw with probability ~ population^this.
                             # Squaring keeps new corridors in populous districts:
                             # mule recruitment needs people and bank branches.

N_NEIGHBORS = 5          # a district's "neighbours" = 5 nearest centroids
                         # (simple stand-in for true shared borders)

ATMS_PER_DISTRICT = 6    # mean ATMs per district = this * population_weight
ATMS_MIN = 2             # every district has at least this many ATMs
ATM_JITTER_DEG = 0.12    # ATMs scattered +/- this many degrees (~13 km)
                         # around the district centroid
BANKS = {                # bank name -> share of ATMs
    "SBI": 0.25, "PNB": 0.10, "Bank of Baroda": 0.08, "Canara": 0.07,
    "Union Bank": 0.06, "HDFC": 0.12, "ICICI": 0.11, "Axis": 0.09,
    "Kotak": 0.05, "IndusInd": 0.04, "IDFC First": 0.03,
}

N_VICTIM_ACCOUNTS = 40_000   # pool of potential victims (population weighted)
N_CLEAN_ACCOUNTS = 20_000    # ordinary accounts that never touch fraud money
MULES_PER_DISTRICT_MIN = 4   # every district has at least a few mule accounts
MULES_PER_HOTSPOT_EXTRA = 120  # hotspot districts have deep mule pools
MULES_EXTRA_BY_POPULATION = 6_000  # more mules spread by population weight
MULE_KYC_PROBS = {"rented": 0.55, "forged": 0.30, "real": 0.15}
                             # mule accounts are mostly rented/forged KYC
MULE_ACCOUNT_AGE_DAYS = 400  # mule accounts are young (opened < ~13 months
                             # before day 0); victim/clean accounts are older
OTHER_ACCOUNT_AGE_DAYS = 3000

# ---------------------------------------------------------------------------
# Complaints (physics rule 1: ~300/day, log-normal amounts)
# ---------------------------------------------------------------------------
FRAUD_CATEGORIES = {     # category -> share of complaints
    "UPI": 0.40, "investment": 0.22, "card": 0.16,
    "loan_app": 0.12, "digital_arrest": 0.10,
}
AMOUNT_MEDIAN = {        # median rupees lost per category (log-normal)
    "UPI": 15_000, "card": 30_000, "loan_app": 20_000,
    "investment": 250_000, "digital_arrest": 600_000,
}
AMOUNT_SIGMA = 0.9       # log-normal spread (0.9 -> heavy right tail)
AMOUNT_MIN = 1_000

# Complaint weekday pattern: Mon..Sun. Fewer frauds/reports on weekends.
COMPLAINT_WEEKDAY_FACTOR = [1.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.70]
# Hour-of-day weights (index = hour 0..23) for WHEN the fraud happens:
# scam calls / UPI tricks peak in working hours and the evening.
COMPLAINT_HOUR_WEIGHTS = [
    0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.7, 1.0, 1.3, 1.5, 1.6,
    1.5, 1.4, 1.5, 1.5, 1.5, 1.4, 1.3, 1.2, 1.0, 0.7, 0.5, 0.3,
]
# Victims take time to notice and report: log-normal delay in hours.
REPORT_DELAY_MEDIAN_H = 3.0
REPORT_DELAY_SIGMA = 1.0

# ---------------------------------------------------------------------------
# Mule chain (physics rule 2: 3-7 hops, fan-out, minutes-hours delays)
# ---------------------------------------------------------------------------
HOPS_MIN, HOPS_MAX = 3, 7   # chain depth (number of transfers after victim)
SPLIT_PROB = 0.30           # chance an account fans out to several accounts
FANOUT_MIN, FANOUT_MAX = 2, 4
MAX_ACCOUNTS_PER_HOP = 6    # cap so a chain never explodes
FIRST_HOP_DELAY_MIN = (1, 30)   # minutes: money leaves the victim fast
HOP_DELAY_MEDIAN_MIN = 25       # log-normal hop delay, median 25 minutes ...
HOP_DELAY_SIGMA = 1.0           # ... spread gives a few minutes to hours
MULE_HOTSPOT_PULL = 0.50    # share of intermediate mules picked from hotspots
                            # (mule pools are dense in the corridors)

# ---------------------------------------------------------------------------
# Cash-out (physics rule 3: 70% cash out, 2-48h later, structured <= 50k)
# ---------------------------------------------------------------------------
CASHOUT_PROB = 0.70             # chains that end in ATM withdrawals
                                # (the rest leak to crypto / wallets / goods)
CASHOUT_DELAY_MEDIAN_H = 10.0   # log-normal hours after the fraud ...
CASHOUT_DELAY_SIGMA = 0.7
CASHOUT_DELAY_RANGE_H = (2, 48) # ... clipped to this range
CASHOUT_FRACTION = (0.70, 0.95) # share of the stolen amount that reaches ATMs
WITHDRAWAL_MAX = 50_000         # structuring: never above this per withdrawal
WITHDRAWAL_MIN = 10_000
WITHDRAWAL_ROUND = 500          # ATMs dispense round amounts
MAX_WITHDRAWALS_PER_CHAIN = 15  # very large frauds are cashed out elsewhere too
WITHDRAWAL_GAP_MIN = (5, 40)    # minutes between successive withdrawals
                                # (mule hopping between nearby ATMs)

# ---------------------------------------------------------------------------
# Weekly / diurnal patterns (physics rule 6)
# ---------------------------------------------------------------------------
# Hour-of-day weights for withdrawals: early morning and late evening peaks
# (few people around, CCTV review is slow, banks are closed).
WITHDRAWAL_HOUR_WEIGHTS = [
    0.6, 0.4, 0.3, 0.3, 0.6, 1.2, 1.8, 2.0, 1.8, 1.2, 0.8, 0.6,
    0.5, 0.5, 0.5, 0.6, 0.7, 0.9, 1.4, 1.9, 2.0, 1.8, 1.3, 0.9,
]
N_RANDOM_HOLIDAYS = 15   # bank-holiday-style days sprinkled through the year
HOLIDAY_KEEP_PROB = 0.50 # a cash-out that lands on a Sunday/holiday happens
                         # with this prob; otherwise it slips to the next day
                         # (ATMs run dry / gangs wait for refills)

# ---------------------------------------------------------------------------
# Geography (physics rule 4: ~65% in hotspots, hotspots drift, noise everywhere)
# ---------------------------------------------------------------------------
HOTSPOT_SHARE = 0.65        # share of cash-out chains that go to an ACTIVE hotspot;
                            # the rest land anywhere, weighted by population
DRIFT_EVERY_DAYS = 30       # hotspot set is reconsidered once a month
HOTSPOT_RETIRE_PROB = 0.12  # chance each hotspot gets "burned" at a drift step
                            # (police crackdown) and is replaced by a new one
NEW_HOTSPOT_NEAR_PROB = 0.60  # replacement is a neighbour of an existing
                              # hotspot (corridor spreads) vs random district

# ---------------------------------------------------------------------------
# Self-excitation (physics rule 5: a cash-out makes nearby cash-outs likelier)
# ---------------------------------------------------------------------------
EXCITE_STRENGTH = 1.5         # each cash-out chain adds this to the district's
                              # weight multiplier (1 + boost) for the next days
EXCITE_NEIGHBOR_FACTOR = 0.5  # neighbours get this fraction of the boost
EXCITE_DAYS = (3, 7)          # how long the boost lasts (gang works the
                              # corridor until it is burned), then it cools
EXCITE_CAP = 6.0              # boost can never exceed this (no runaway)
