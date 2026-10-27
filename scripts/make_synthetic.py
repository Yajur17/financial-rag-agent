"""
Synthetic CDSL-style consolidated account statements (CAS).

Writes data_parsed/all_statements_clean.json in exactly the shape the PDF
parser (scripts/parser.js) produces after PII redaction: one object per page,
with source_file / statement_month / page_number / section_type /
section_types / text. The row chunker (scripts/chunk.py) is a line-oriented
state machine, so the page text below deliberately reproduces the quirks of a
real parsed statement:

  * ISIN-anchored records (INE... equities, INF... funds/ETFs) whose security
    name wraps over several lines before the numeric tail;
  * `--` placeholders in the balance columns (the holdings row terminator);
  * date-prefixed transaction lines (the transaction row terminator);
  * chrome lines from the bilingual PDF, where the non-Latin script did not
    survive text extraction and shows up as U+FFFD (the chunkers skip these);
  * mixed pages (transactions + holdings on one page);
  * one short security that fits on a single line (a known chunker blind spot);
  * redaction placeholders ([PAN], [FOLIO], [BOID], ...) where the parser would
    have removed personal data.

Everything here is fictional: holder, broker, AMCs, securities, ISINs, codes
and every figure. Figures are generated from a fixed seed and are internally
consistent:

  holdings value       = units x market price
  folio valuation      = units x NAV, P/L = valuation - invested
  equity / MF-in-demat = sum of the holdings rows of that kind
  total portfolio      = equity + MF-in-demat + MF folios (percentages agree)
  transaction balances = previous month's closing balance -> this month's

Run:  python3 scripts/make_synthetic.py
"""

import json
import os
import random
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data_parsed" / "all_statements_clean.json"

# Fixed seed -> identical output every run. 28 was picked because none of its
# generated figures coincides with a figure in the private source statements
# (verified with scripts/privacy_scan.py against the local denylist).
SEED = int(os.environ.get("SYNTH_SEED", 28))
HOLDER = "SAMPLE INVESTOR"          # chunk.py skips this exact line
BROKER = "NORTHSTAR BROKING LIMITED"
AMC = "Aurora Mutual Fund"
CIN = "L00000XX0000PLC000000"
CAS_TAG = "DEMO0001"

# (label, month number, last day). Output page order is newest first, like
# the original corpus (JUL, JUN, MAY) -- the chunkers carry buffer state
# across pages, so order is part of the format.
MONTHS = [("MAY 2025", 5, 31), ("JUN 2025", 6, 30), ("JUL 2025", 7, 31)]
MON_ABBR = {5: "May", 6: "Jun", 7: "Jul"}

FFFD = "�"                     # the replacement character, as extracted


# ----------------------------------------------------------------- formatting
def inr(x):
    """Indian digit grouping, 2 decimals: 312345.6 -> '3,12,345.60'."""
    neg = x < 0
    s = f"{abs(x):.2f}"
    whole, frac = s.split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + "." + frac


def inr_short(x):
    """The statement prints some totals without a trailing zero (e.g. 1.8)."""
    s = inr(x)
    return s[:-1] if s.endswith("0") else s


def q3(x):
    return f"{x:.3f}"


# --------------------------------------------------------------- the universe
# kind: EQ = equity (INE), ETF = exchange-traded fund (INF, name has "ETF"),
#       MFD = non-ETF mutual fund held in demat (INF, filtered out of the
#       holdings chunks by design), FOLIO = mutual-fund folio (mf_units table)
PERSISTENT_EQ = [
    # key,        name,                                                                          qty range, price range, trend
    ("arcadia",   "ARCADIA PHARMA LIMITED#NEW EQUITY SHARES WITH FACE VALUE RS. 2/- AFTER SUB DIVISION", (3, 4), (780, 1050), None),
    ("brightline", "BRIGHTLINE TELECOM LIMITED - EQUITY SHARES OF RE 5/- AFTER SUB-DIVISION",        (2, 3), (1580, 1980), None),
    ("coolwave",  "COOLWAVE APPLIANCES LIMITED # NEW EQUITY SHARES OF RS. 2/- AFTER SPLIT",           (1, 2), (1380, 1690), "up"),
    ("delta",     "DELTA AGRO CHEMICALS LIMITED EQUITY SHARES",                                       (5, 8), (440, 610), None),
    ("evergreen", "EVERGREEN SERVICES LIMITED - EQUITY SHARES",                                       (8, 12), (290, 410), None),
    ("falcon",    "FALCON CHEM LTD-EQUITY SHARES",                                                    (4, 6), (540, 700), None),
    ("granite",   "GRANITE BANK LIMITED#NEW EQUITY SHARES WITH FACE VALUE RE. 1/- AFTER SUBDIVISION", (5, 6), (1680, 1990), None),
    ("harbor",    "HARBOR BANK LIMITED # NEW EQ SH WITH FV RS.2/- AFTER SUB-DIVISION",                (6, 8), (1280, 1490), None),
    ("ionic",     "IONIC POWER EXCHANGE LIMITED#NEW EQUITY SHARES FACE VALUE RE. 1/- AFTER SUB DIVISION", (18, 24), (175, 225), "down"),
    ("jasmine",   "JASMINE HOTELS COMPANY LIMITED - NEW EQUITY SHARES OF RE. 1/- AFTER SPLIT",        (2, 3), (690, 810), None),
    ("kestrel",   "KESTREL ENGINEERING LIMITED- EQUITY SHARES OF RS.2/- EACH",                        (9, 10), (3300, 3700), None),
    ("lotus",     "LOTUS FOODS LIMITED#EQUITY SHARES WITH FACE VALUE RE. 1/- AFTER SUB DIVISION",     (7, 9), (395, 480), None),
    ("sunrise",   "SUNRISE PIGMENTS INDUSTRIES LIMITED#NEW EQUITY SHARE WITH FV RS.2/- AFTER SUB-DIVISION", (2, 3), (1085, 1285), "up"),
]

# fully sold in May (debited to zero, then gone from later statements)
SOLD_EQ = [
    ("alpine",   "ALPINE TYRES LIMITED - NEW EQUITY SHARES OF RE. 1/- AFTER SPLIT"),
    ("beacon",   "BEACON MINING LIMITED - EQUITY SHARES"),
    ("cascade",  "CASCADE ENERGY & MOBILITY LIMITED # NEW EQUITY SHARES OF RS. 1/- AFTER SUB DIVISION"),
    ("coral",    "CORAL FEEDS LIMITED#NEW EQUITY SHARES FACE VALUE RE. 1/- AFTER SUB DIVISION"),
    ("dune",     "DUNE MOTORS LTD - NEW EQUITY SHARES OF RS. 2/- AFTER SUB-DIVISION"),
    ("ember",    "EMBER CIVIL ENGINEERING LIMITED # EQUITY SHARES"),
    ("fjord",    "FJORD STEEL PIPES LIMITED#NEW EQUITY SHARES WITH FACE VALUE RE.1/- AFTER SUBDIVISION"),
    ("glacier",  "GLACIER TYRE & RUBBER LIMITED # NEW EQ SH WITH FV RS.2/- AFTER SUB-DIVISION"),
    ("halcyon",  "HALCYON MEDIA LIMITED - NEW EQUITY SHARES OF RS. 5/- AFTER SPLIT"),
    ("ironclad", "IRONCLAD MINERALS LIMITED - EQUITY SHARES OF RE. 1/- AFTER SPLIT"),
    ("juniper",  "JUNIPER BUILDCON PROJECTS LIMITED # NEW EQ SH WITH FV RS.5/- AFTER SUB DIVISION"),
    ("nimbus",   "NIMBUS ASSET MANAGEMENT COMPANY LIMITED - EQUITY SHARES"),
    ("orbit",    "ORBIT RUBBER LIMITED - NEW EQUITY SHARES OF RS. 10/- AFTER CAPITAL REDUCTION"),
    ("polaris",  "POLARIS PLASTICS LIMITED-NEW EQUITY SHARES OF RS. 1/- AFTER SPLIT"),
]

ETFS = [
    # key,        name,                                                   opening May, price range
    ("mer_gold",   "MERIDIAN AMC LTD#MERIDIAN MF-MERIDIAN GOLD ETF",       (60, 90),   (74, 86)),
    ("mer_silver", "MERIDIAN AMC LTD#MERIDIAN MF-MERIDIAN SILVER ETF",     (60, 90),   (89, 101)),
    ("blu_gold",   "BLUEFIN AM PVT LTD#BLUEFIN MF-BLUEFIN GOLD ETF",       (250, 330), (13.5, 16.5)),
    ("blu_silver", "BLUEFIN AM PVT LTD#BLUEFIN MF-BLUEFIN SILVER ETF",     (0, 0),     (9.2, 11.4)),
]

MFD = [
    ("mer_flexi", "MERIDIAN AMC LTD#MERIDIAN MF-MERIDIAN FLEXI CAP FUND DIRECT PL GR PL GR OPT"),
    ("aur_small", "AURORA MONEY MANAGERS LTD#AURORA MF-AURORA SMALL CAP FUND-DIRECT-GROWTH"),
    ("aur_tax",   "AURORA MONEY MANAGERS LTD#AURORA MF-AURORA TAX SAVER-DIRECT-GROWTH"),
]

ELSS_CODE, SMALL_CODE = "AETS", "ASCG"
ELSS_SCHEME = "aurora ELSS Tax Saver Fund - Direct Plan"
SMALL_SCHEME = "aurora Small Cap Fund - Direct Plan Growth"


# ------------------------------------------------------------------- the model
def make_isin(rng, prefix, used):
    alnum = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
    while True:
        if prefix == "INE":
            s = ("INE" + "".join(rng.choice("0123456789") for _ in range(3))
                 + rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") + "01"
                 + "".join(rng.choice("0123456789") for _ in range(2))
                 + rng.choice("0123456789"))
        else:
            s = ("INF" + "".join(rng.choice("0123456789") for _ in range(3))
                 + rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
                 + "".join(rng.choice(alnum) for _ in range(2))
                 + "".join(rng.choice("0123456789") for _ in range(2))
                 + rng.choice("0123456789"))
        assert len(s) == 12, s
        if s not in used:
            used.add(s)
            return s


def walk(rng, start, trend=None):
    """Three month-end prices (May, Jun, Jul)."""
    lo, hi = {"up": (1.03, 1.09), "down": (0.82, 0.93)}.get(trend, (0.95, 1.07))
    p1 = start
    p2 = p1 * rng.uniform(lo, hi)
    p3 = p2 * rng.uniform(lo, hi)
    return [round(p1, 3), round(p2, 3), round(p3, 3)]


def build_model(seed=SEED):
    """Every figure in the synthetic statements, as plain Python data.

    make_ground_truth.py imports this so the eval answers are computed from
    the same source of truth that the statement text is rendered from.
    """
    rng = random.Random(seed)
    used = set()
    sec = {}           # key -> security record
    txns = {m: [] for m, _, _ in MONTHS}

    def add(key, name, kind, prices, closing):
        sec[key] = {"key": key, "name": name, "kind": kind,
                    "isin": make_isin(rng, "INE" if kind == "EQ" else "INF", used),
                    "price": prices, "close": closing}

    # transaction dates (month, role) -> date string
    d_may_sell = f"{rng.choice([12, 14, 15, 16]):02d}-05-2025"
    d_may_etf = f"{rng.choice([2, 5, 8, 9]):02d}-05-2025"
    d_may_buy = f"{rng.choice([19, 20, 22, 23]):02d}-05-2025"
    d_jun_etf = f"{rng.choice([10, 11, 12]):02d}-06-2025"
    d_jun_buy = f"{rng.choice([20, 23, 25, 26]):02d}-06-2025"
    d_jul_etf = f"{rng.choice([7, 9, 10, 11]):02d}-07-2025"
    d_jul_buy = f"{rng.choice([17, 22, 23, 24]):02d}-07-2025"
    d_jul_buy2 = f"{rng.choice([25, 28, 30]):02d}-07-2025"

    def txn(month, key, date, op, credit, debit, style):
        txns[month].append({"key": key, "date": date, "op": op, "credit": credit,
                            "debit": debit, "cl": round(op + credit - debit, 3),
                            "style": style})

    # ---- persistent equities
    for key, name, (qlo, qhi), (plo, phi), trend in PERSISTENT_EQ:
        prices = walk(rng, rng.uniform(plo, phi), trend)
        base = rng.randint(qlo, qhi)
        if key == "brightline":        # bought in May, topped up in July
            close = [base, base, base + 1]
            txn("MAY 2025", key, d_may_buy, 0, base, 0, "payout")
            txn("JUL 2025", key, d_jul_buy2, base, 1, 0, "payout")
        elif key == "granite":         # July top-up via inter-depository credit
            close = [base, base, base + 2]
            txn("JUL 2025", key, d_jul_buy, base, 2, 0, "intdep")
        elif key == "harbor":
            close = [base, base, base + 2]
            txn("JUL 2025", key, d_jul_buy, base, 2, 0, "payout")
        elif key == "kestrel":
            close = [base, base + 1, base + 1]
            txn("JUN 2025", key, d_jun_buy, base, 1, 0, "payout")
        elif key == "lotus":           # partly sold in May, bought back in June
            sold = rng.randint(5, 9)
            close = [base, base + 5, base + 5]
            txn("MAY 2025", key, d_may_sell, base + sold, 0, sold, "epdr")
            txn("JUN 2025", key, d_jun_buy, base, 5, 0, "payout")
        else:
            close = [base, base, base]
        add(key, name, "EQ", prices, close)

    # ---- equities sold out in May
    for key, name in SOLD_EQ:
        prices = walk(rng, rng.uniform(60, 3800))
        qty = rng.randint(2, 40)
        add(key, name, "EQ", prices, [0, 0, 0])
        sec[key]["sold_qty"] = qty
        txn("MAY 2025", key, d_may_sell, qty, 0, qty, "epdr")

    # ---- ETFs: a monthly buy every month
    etf_buys = {
        "mer_gold":   [rng.choice([8, 10, 12])] * 3,
        "mer_silver": [rng.choice([10, 12]), rng.choice([10, 12]), rng.choice([6, 8])],
        "blu_gold":   [rng.choice([40, 60])] * 3,
        "blu_silver": [rng.choice([30, 40]), rng.choice([30, 40]), rng.choice([60, 70, 80])],
    }
    for key, name, (olo, ohi), (plo, phi) in ETFS:
        prices = walk(rng, rng.uniform(plo, phi))
        bal = rng.randint(olo, ohi) if ohi else 0
        close = []
        for i, (m, _, _) in enumerate(MONTHS):
            buy = etf_buys[key][i]
            d = [d_may_etf, d_jun_etf, d_jul_etf][i]
            txn(m, key, d, bal, buy, 0, "payout")
            bal += buy
            close.append(bal)
        add(key, name, "ETF", prices, close)

    # ---- mutual-fund folios (mf_units table) + their demat twins
    elss_nav = rng.uniform(310, 440)
    small_nav = rng.uniform(190, 290)
    def nav_path(start):
        jun = start * rng.uniform(1.035, 1.065)     # June is the strong month
        jul = jun * rng.uniform(0.972, 0.99)       # July gives some back
        return [round(start, 4), round(jun, 4), round(jul, 4)]
    elss_navs, small_navs = nav_path(elss_nav), nav_path(small_nav)

    # (scheme, invested, May P/L ratio) -- the 2nd ELSS folio is a recent,
    # barely-in-profit one; the small-cap folio is the big winner.
    folio_specs = [
        ("ELSS", round(rng.uniform(52000, 68000), 2), rng.uniform(0.08, 0.14)),
        ("ELSS", float(rng.choice([15000, 18000, 25000])), rng.uniform(0.012, 0.03)),
        ("SMALL", round(rng.uniform(36000, 47000), 2), rng.uniform(0.45, 0.6)),
        ("ELSS", round(rng.uniform(21000, 31000), 2), rng.uniform(0.24, 0.33)),
    ]
    folios = []
    for scheme, invested, ratio in folio_specs:
        navs = elss_navs if scheme == "ELSS" else small_navs
        units = round(invested * (1 + ratio) / navs[0], 3)
        rows = []
        for nav in navs:
            val = round(units * nav, 2)
            pl = round(val - invested, 2)
            rows.append({"nav": nav, "valuation": val, "pl": pl,
                         "pct": round(pl / invested * 100, 2)})
            assert pl > 0, "every folio must stay in profit (chunk.py splits on digit-space-digit)"
        folios.append({"scheme": scheme, "isin": None, "units": units,
                       "invested": invested, "months": rows})

    # demat MFs
    flexi_nav = walk(rng, rng.uniform(1850, 2350))
    bal, close = 0.0, []
    for i, (m, _, _) in enumerate(MONTHS):
        buy = round(rng.uniform(0.41, 0.58), 3)
        txn(m, "mer_flexi", [d_may_etf, d_jun_etf, d_jul_etf][i], bal, buy, 0, "bsemf")
        bal = round(bal + buy, 3)
        close.append(bal)
    add("mer_flexi", MFD[0][1], "MFD", flexi_nav, close)

    bal, close = round(rng.uniform(30, 45), 3), []
    for i, (m, _, _) in enumerate(MONTHS):
        buy = round(rng.uniform(15, 20), 3)
        txn(m, "aur_small", [d_may_etf, d_jun_etf, d_jul_etf][i], bal, buy, 0, "bsemf")
        bal = round(bal + buy, 3)
        close.append(bal)
    add("aur_small", MFD[1][1], "MFD", [round(n, 3) for n in small_navs], close)

    locked = round(rng.uniform(15, 25), 3)
    add("aur_tax", MFD[2][1], "MFD", [round(n, 3) for n in elss_navs], [locked] * 3)
    sec["aur_tax"]["locked"] = True
    sec["aur_tax"]["lockin_until"] = f"{rng.randint(10, 27):02d}-0{rng.randint(1, 9)}-2028"
    sec["aur_tax"]["lockin_tag"] = f"ELSS{rng.randint(2101, 2399)}"

    for f in folios:
        f["isin"] = sec["aur_tax"]["isin"] if f["scheme"] == "ELSS" else sec["aur_small"]["isin"]

    # ---- per-month valuation summary
    summary = []
    for i, (m, _, _) in enumerate(MONTHS):
        eq = round(sum(round(s["close"][i] * s["price"][i], 2)
                       for s in sec.values() if s["kind"] == "EQ"), 2)
        mfd = round(sum(round(s["close"][i] * s["price"][i], 2)
                        for s in sec.values() if s["kind"] in ("ETF", "MFD")), 2)
        mff = round(sum(f["months"][i]["valuation"] for f in folios), 2)
        total = round(eq + mfd + mff, 2)
        pct = {k: round(v / total * 100, 2) for k, v in
               (("Equity", eq), ("Mutual Fund Folios", mff), ("Mutual Funds Held in Demat Form", mfd))}
        drift = round(100 - sum(pct.values()), 2)
        pct["Mutual Fund Folios"] = round(pct["Mutual Fund Folios"] + drift, 2)
        summary.append({"month": m, "equity": eq, "mf_demat": mfd, "mf_folios": mff,
                        "cdsl": round(eq + mfd, 2), "total": total, "pct": pct,
                        "n_isins": sum(1 for s in sec.values()
                                       if i == 0 or s["close"][i] > 0)})

    # ---- 14 months of valuation history (Jun 2024 .. Jul 2025)
    hist = [summary[0]["total"]]
    for _ in range(11):                       # walk backwards from May 2025
        hist.insert(0, round(hist[0] / rng.uniform(0.94, 1.07), 2))
    hist += [summary[1]["total"], summary[2]["total"]]
    labels = [f"{mo} {yr}" for mo, yr in
              [("Jun", 2024), ("Jul", 2024), ("Aug", 2024), ("Sep", 2024), ("Oct", 2024),
               ("Nov", 2024), ("Dec", 2024), ("Jan", 2025), ("Feb", 2025), ("Mar", 2025),
               ("Apr", 2025), ("May", 2025), ("Jun", 2025), ("Jul", 2025)]]

    # ---- particulars codes (settlement ids etc.) -- random, fictional
    codes = {
        "cm_id": f"M{rng.randint(30000, 99999)}",
        "tm_cp": f"{rng.randint(10000, 99999)}",
        "bse_id": f"IN{rng.randint(100000, 999999)}",
        "sett_prefix": f"{rng.randint(130000, 199999)}2025",
        "mf_sett_prefix": f"{rng.randint(120000, 199999)}25",
    }
    for m in txns:
        for t in txns[m]:
            if t["style"] == "epdr":
                t["txn_no"] = str(rng.randint(41000000, 49999999))
            t["sett_no"] = f"{rng.randint(100, 199)}"
            t["mf_sett_no"] = f"{rng.randint(26000, 26999)}"

    return {"securities": sec, "transactions": txns, "folios": folios,
            "summary": summary, "history": list(zip(labels, hist)), "codes": codes}


# ------------------------------------------------------------------ rendering
def wrap(text, width):
    lines = textwrap.wrap(text, width=width, break_on_hyphens=True)
    for ln in lines:
        # a wrapped line that starts like an ISIN would open a bogus record
        assert not ln.startswith(("INE", "INF")), ln
        assert "--" not in ln, ln
    return lines


def chrome_header(first_page=False):
    lines = [
        f"{FFFD}{FFFD} {FFFD} {FFFD} {FFFD} {FFFD} ( {FFFD} ) {FFFD} {FFFD}",
        f"A {FFFD} , 25 , {FFFD} {FFFD} , {FFFD} {FFFD} {FFFD} , {FFFD},",
        f"( {FFFD}), - [PINCODE] | ( CIN : {CIN})",
        f"{FFFD} {FFFD} {FFFD}{FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} NPS {FFFD} {FFFD} {FFFD}",
        f"{FFFD} {FFFD} (CAS)",
    ]
    if not first_page:
        lines += [
            "Investments",
            f"{FFFD} {FFFD} {FFFD} Account Details Account Details",
            "Account Details",
            f"MF Details MF {FFFD} Notes {FFFD} {FFFD} {FFFD} About CDSL CDSL {FFFD}",
            HOLDER,
        ]
    return lines


TXN_HEADER = ["ISIN Security", "Transaction", "Particulars",
              "Date Op. Bal Credit Debit Cl. Bal", "Stamp", "Duty", "(`)"]
TXN_FOOTER = [f"ISIN ISIN Security {FFFD}{FFFD} {FFFD}", "Transaction", "Particulars",
              f"{FFFD} Date {FFFD} Op. Bal", "Credit Cr. Debit Dr. Cl. Bal Cl.",
              "Stamp", f"Duty ( ₹ )", f"{FFFD} {FFFD}", f"{FFFD} ( ₹ )"]
HLD_HEADER = ["ISIN Security", "Current", "Bal", "Frozen", "Bal", "Pledge", "Bal",
              "Pledge", "Setup", "Bal", "Free Bal", "Market", "Price /", "Face",
              "Value", "Value (`)"]
HLD_FOOTER = [f"ISIN {FFFD}{FFFD} {FFFD} {FFFD}", f"{FFFD} /", f"{FFFD} {FFFD}",
              f"₹ {FFFD} {FFFD}"]


def particulars(t, model, month_num):
    c = model["codes"]
    if t["style"] == "epdr":
        return [f"EP-DR Txn:{t['txn_no']}", "CtBo:[BOID]", f"{c['sett_prefix']}{t['sett_no']}"]
    if t["style"] in ("payout", "intdep"):
        head = "PAYOUT-CR CM" if t["style"] == "payout" else "INTDEP-CR CM"
        return [head, f"{c['cm_id']} TM/CP", f"{c['tm_cp']} SETT",
                f"{c['sett_prefix']}{t['sett_no']}"]
    # BSE StAR MF credit
    dd, mm, yyyy = t["date"].split("-")
    return [f"BSECH-CR {c['bse_id']}", f"11 {dd}{mm}{yyyy}C00{1 + int(dd) % 5}",
            f"SETT {c['mf_sett_prefix']}{t['mf_sett_no']}"]


def txn_rows(model, month, month_num):
    sec = model["securities"]
    out = []
    for t in sorted(model["transactions"][month], key=lambda t: sec[t["key"]]["name"]):
        s = sec[t["key"]]
        lines = [s["isin"]] + wrap(s["name"], 24) + particulars(t, model, month_num)
        credit = q3(t["credit"]) if t["credit"] else "--"
        debit = q3(t["debit"]) if t["debit"] else "--"
        lines.append(f"{t['date']} {q3(t['op'])} {credit} {debit} {q3(t['cl'])} 0")
        out.append(lines)
    return out


def hld_rows(model, i):
    sec = model["securities"]
    rows = [s for s in sec.values() if i == 0 or s["close"][i] > 0]
    out = []
    for s in sorted(rows, key=lambda s: s["name"]):
        qty, price = s["close"][i], s["price"][i]
        value = round(qty * price, 2)
        if qty:
            free = "--" if s.get("locked") else q3(qty)
            tail = f"{q3(qty)} -- -- -- {free} {price:.3f} {inr(value)}"
        else:
            tail = f"-- -- -- -- -- {price:.3f} 0.00"
        if s["key"] == "falcon":                      # short name -> single line
            out.append([f"{s['isin']} {s['name']} {tail}"])
        else:
            out.append([s["isin"]] + wrap(s["name"], 29) + [tail])
    return out


def flat(rows):
    return [ln for r in rows for ln in r]


def render_month(model, i):
    month, mnum, last = MONTHS[i]
    sm = model["summary"][i]
    period_from, period_to = f"01-{mnum:02d}-2025", f"{last:02d}-{mnum:02d}-2025"
    pages = []

    # ---- p1: cover
    p1 = [f"FORM AND INVESTMENTS IN MUTUAL FUNDS FOR THE PERIOD FROM {period_from}",
          f"TO {period_to}"] + chrome_header(first_page=True)[:3] + [
          f"{period_from} {period_to} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}{FFFD} {FFFD} {FFFD}",
          f"{FFFD} {FFFD} {FFFD} NPS {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} (CAS)",
          "Summary of Investments", "(On the basis of PAN of first holder)",
          f"{FFFD} {FFFD} {FFFD}", f"({FFFD} PAN )",
          "Name/Joint Name (s) [HOLDER-NAME](In `) View Statement", HOLDER,
          "CDSL Demat Accounts", "NSDL Demat Accounts *", "Mutual Fund Folios",
          inr(sm["cdsl"]), "N.A", inr(sm["mf_folios"]), "Click Here",
          f"Total Portfolio Value {inr(sm['total'])}",
          f"/ {FFFD} {FFFD} {FFFD} {FFFD} ( ₹ ) {FFFD} {FFFD}",
          "* No Demat Account for this PAN pattern"]
    pages.append((["summary"], p1))

    # ---- p2: consolidated summary
    ab = MON_ABBR[mnum]
    p2 = chrome_header(first_page=True) + [
        "CAS ID: [CASID]", "[HOLDER-NAME]", "[ADDRESS]", "[LOCATION]", "[LOCATION]",
        "[LOCATION]", "[PINCODE]",
        f"Statement for the period from 01-{ab}-2025 to {last:02d}-{ab}-2025 01- -2025 {last:02d}- -2025 {FFFD} {FFFD} {FFFD} {FFFD}",
        "YOUR CONSOLIDATED",
        f"PORTFOLIO VALUE {FFFD} {FFFD} {FFFD} {FFFD} ` {inr(sm['total'])} | Summary",
        "Your Demat Account and Mutual Fund Folios", "In the single name of",
        "[HOLDER-NAME]( PAN :[PAN] )",
        "Account Type Account Details No. of ISINs/ Schemes Value in `",
        "CDSL Demat Account", BROKER, "DP Id: [DPID] Client Id :[CLIENTID]",
        f"{sm['n_isins']} {inr(sm['cdsl'])}",
        f"Mutual Fund Folios 4 Folios 4 {inr(sm['mf_folios'])}",
        f"Total {inr_short(sm['total'])}", f"Grand Total {inr(sm['total'])}",
        f"{FFFD} {FFFD} ISIN/ {FFFD} {FFFD} ₹ {FFFD} {FFFD}"]
    pages.append((["summary"], p2))

    # ---- p3: 12-month valuation history + asset classes
    hist = model["history"][i:i + 12]
    p3 = [f"Consolidated Portfolio Valuation for Year {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}",
          "Month-Year", "Portfolio Valuation", "(In `)", "Changes in ` Changes in %"]
    for j, (label, val) in enumerate(hist):
        if j == 0:
            p3.append(f"{label} {inr(val)}")
        else:
            prev = hist[j - 1][1]
            p3.append(f"{label} {inr(val)} {inr(val - prev)} {(val - prev) / prev * 100:.2f}")
    p3 += [f"- {FFFD} {FFFD} {FFFD} {FFFD} ( ₹ ) {FFFD} {FFFD} ₹ {FFFD} {FFFD} % {FFFD}",
           f"Consolidated Portfolio for Accounts for the Month {FFFD} {FFFD} {FFFD} {FFFD}",
           "Asset Class Value Percentage",
           f"Equity {inr(sm['equity'])} {sm['pct']['Equity']:.2f}",
           f"Mutual Fund Folios {inr(sm['mf_folios'])} {sm['pct']['Mutual Fund Folios']:.2f}",
           f"Mutual Funds Held in Demat Form {inr(sm['mf_demat'])} {sm['pct']['Mutual Funds Held in Demat Form']:.2f}",
           f"Total {inr_short(sm['total'])} 100.00", f"{FFFD} {FFFD} {FFFD} {FFFD} {FFFD}{FFFD}"]
    pages.append((["summary"], p3))

    # ---- p4: account details + folio blocks
    p4 = chrome_header(first_page=True) + [
        "Account Details Account Details", f"{HOLDER} PAN: [PAN]", "CDSL Demat Accounts",
        f"DP Name : {BROKER} DP ID : [DPID] CLIENT ID : [CLIENTID]",
        "Email Id : [EMAIL]", "Mobile No : [MOBILE] BO Sub Status : Individual-Resident",
        "BSDA : YES RGESS : NO", "Account Status : Active", "BO Status : INDIVIDUAL",
        "Frozen Status : Not Frozen", "Nominee : [NOMINEE]", "MF Folios"]
    for f in model["folios"]:
        name, code = (ELSS_SCHEME, ELSS_CODE) if f["scheme"] == "ELSS" else (SMALL_SCHEME, SMALL_CODE)
        p4 += [f"AMC Name : {AMC}", f"Scheme Name : {name} Scheme Code : {code}",
               "Folio No : [FOLIO] Mode of Holding : Single Email id : [EMAIL]",
               "KYC of Investor/s : KYC OK Mobile No : [MOBILE] Nominee : [NOMINEE]",
               f"ISIN : {f['isin']} UCC : RTA : DEMO-RTA"]
    pages.append((["summary"], p4))

    # ---- transactions + holdings pages
    t_rows = txn_rows(model, month, mnum)
    h_rows = hld_rows(model, i)
    if i == 0:
        t_split, h_split = [6, 15, 1], [14, 17, 3]
    elif i == 1:
        t_split, h_split = [5, 3], [11, 9]
    else:
        t_split, h_split = [5, 4], [9, 11]
    assert sum(t_split) == len(t_rows), (month, len(t_rows))
    assert sum(h_split) == len(h_rows), (month, len(h_rows))

    def take(rows, n):
        chunk, rest = rows[:n], rows[n:]
        return chunk, rest

    # p5: address block, summary, first transactions
    sm_rows = [("Mutual Fund Folios", sm["mf_folios"]), ("Equity", sm["equity"]),
               ("Mutual Funds Held in Demat Form", sm["mf_demat"])]
    p5 = chrome_header() + [
        "[HOLDER-NAME]", "[ADDRESS]", "SECTOR 00, SAMPLE NAGAR , [PINCODE]", "EXAMPLE STATE INDIA",
        "Attention: SEBI vide its circular no. CIR/MRD/",
        "DP/31/2014 dated November 12, 2014 mandated",
        "depositories to issue a Consolidated Account",
        "Statement (CAS) to view all investments held in",
        "CDSL/NSDL/Mutual Funds. We trust this initiative",
        "by SEBI would be beneficial to you.",
        f"{FFFD} {FFFD}: SEBI {FFFD} {FFFD} . CIR/MRD/",
        f"DP/31/2014 {FFFD} 12 {FFFD} , 2014 {FFFD}",
        f"{FFFD} {FFFD} {FFFD} CDSL/NSDL/{FFFD} {FFFD}",
        f"{FFFD} {FFFD} (CAS) {FFFD} {FFFD} {FFFD}",
        f"Total Portfolio Value across investments ₹ {inr(sm['total'])} as on {period_to} {period_to} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} ₹ {inr(sm['total'])}",
        "Assets Class Value in ` %"]
    for label, v in sm_rows:
        p5.append(f"{label} {inr(v)} {sm['pct'][label]:.2f}")
    p5 += [f"Total {inr(sm['total'])} 100.00",
           f"{FFFD} {FFFD} {FFFD} ₹ {FFFD} {FFFD} %",
           f"DEMAT ACCOUNTS HELD WITH CDSL CDSL {FFFD} DEMAT",
           f"BO ID : [BOID] BO ID: [BOID] DP Name : {BROKER} DP : {BROKER}",
           f"STATEMENT OF TRANSACTIONS FOR THE PERIOD FROM {period_from} TO {period_to} {period_from} {period_to} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}"]
    chunk, t_rows = take(t_rows, t_split[0])
    p5 += TXN_HEADER + flat(chunk) + TXN_FOOTER
    pages.append((["transactions", "summary"], p5))

    hold_hdr = [f"HOLDING STATEMENT AS ON {period_to} {period_to} {FFFD} {FFFD} {FFFD}"] + HLD_HEADER

    def last_holdings_block():
        tax = model["securities"]["aur_tax"]
        return [f"HOLDING STATEMENT AS ON {period_to} (Other Details) {FFFD} {FFFD} {FFFD} {period_to} ( {FFFD} {FFFD} )",
                "ISIN Security Date Balance Description Lockin", "Pending", "Demat",
                "Pending", "Remat", tax["isin"]] + wrap(tax["name"], 29) + [
                f"{tax['lockin_until']} {tax['lockin_tag']} {q3(tax['close'][i])} 0.000 0.000",
                f"Portfolio Value ` {inr(sm['cdsl'])} as on {period_to}",
                f"ISIN {FFFD}{FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}",
                "For any queries regarding demat account statement, please contact your "
                f"respective Depository Participant. DEMAT {FFFD} {FFFD} {FFFD} ◌ {FFFD} {FFFD} {FFFD} {FFFD}{FFFD} {FFFD} {FFFD}"]

    if i == 0:
        chunk, t_rows = take(t_rows, t_split[1])
        pages.append((["transactions"], chrome_header() + TXN_HEADER + flat(chunk) + TXN_FOOTER))
        tchunk, t_rows = take(t_rows, t_split[2])
        hchunk, h_rows = take(h_rows, h_split[0])
        pages.append((["holdings", "transactions"], chrome_header() + TXN_HEADER + flat(tchunk)
                      + TXN_FOOTER + hold_hdr + flat(hchunk) + HLD_FOOTER))
        hchunk, h_rows = take(h_rows, h_split[1])
        pages.append((["holdings"], chrome_header() + HLD_HEADER + flat(hchunk) + HLD_FOOTER))
        hchunk, h_rows = take(h_rows, h_split[2])
        pages.append((["holdings"], chrome_header() + HLD_HEADER + flat(hchunk) + HLD_FOOTER
                      + last_holdings_block()))
    else:
        tchunk, t_rows = take(t_rows, t_split[1])
        hchunk, h_rows = take(h_rows, h_split[0])
        pages.append((["holdings", "transactions"], chrome_header() + TXN_HEADER + flat(tchunk)
                      + TXN_FOOTER + hold_hdr + flat(hchunk) + HLD_FOOTER))
        hchunk, h_rows = take(h_rows, h_split[1])
        pages.append((["holdings"], chrome_header() + HLD_HEADER + flat(hchunk) + HLD_FOOTER
                      + last_holdings_block()))

    # ---- mf_units page
    if i < 2:
        ret_hdr = ["Annual", "ised", "Return", "(%)"]
    else:
        ret_hdr = ["Unreali", "sed", "Profit/", "Loss(%)"]
    pm = chrome_header() + [
        f"MUTUAL FUND UNITS HELD WITH MF/RTA MF/RTA {FFFD} {FFFD} {FFFD} {FFFD}",
        f"MUTUAL FUND UNITS HELD AS ON {period_to} {period_to} {FFFD} {FFFD} {FFFD}",
        "Scheme Name ISIN Folio No.", "Closing", "Bal", "(Units)", "NAV (`)", "Cumulative",
        "Amount", "Invested (in", "INR)", "Valuation (`)", "Unrealised", "Profit/Loss"] + ret_hdr
    for f in model["folios"]:
        r = f["months"][i]
        if f["scheme"] == "ELSS":
            pm += [f"{ELSS_CODE} - aurora ELSS", "Tax Saver Fund -", "Direct Plan"]
        else:
            pm += [f"{SMALL_CODE} - aurora Small", "Cap Fund - Direct", "Plan Growth"]
        pm.append(f"{f['isin']} [FOLIO] {q3(f['units'])} {r['nav']:.4f} {inr(f['invested'])} "
                  f"{inr(r['valuation'])} {inr(r['pl'])} {r['pct']:.2f}")
    inv_total = round(sum(f["invested"] for f in model["folios"]), 2)
    pm += [f"Grand Total {inr(inv_total)} {inr(sm['mf_folios'])}",
           f"{FFFD} {FFFD} ISIN {FFFD}", f"( {FFFD} {FFFD} )", f"NAV ( ₹ )", f"{FFFD} {FFFD}",
           f"{FFFD} (INR {FFFD})", f"{FFFD} ( ₹ )", "Unrealised", "Profit/Loss",
           "Annuali", "sed", "Return", "(%)",
           "1 Annualised Return (%) indicates the return on investment in the mutual fund schemes since April 1, 2015 or the date of your investment, whichever is later.",
           "It is computed using XIRR (Extended Internal rate of Return) method and takes in to account NAV appreciation as well as dividend.",
           "2 Annualised Return (%) has not been computed where the details provided to CDSL by mutual funds are not adequate where the investment has been held",
           "for less thana month or where the holdings have become zero.",
           "3 The XIRR provided is based on the available information indicating the unrelised profit in (%) and is not an absolute indication of the XIRR.",
           "Load Structures", "IDCW - Income Distribution and Capital Withdrawal",
           f"1. {ELSS_CODE} - {ELSS_SCHEME} : Entry load - NIL, Exit load - NIL. Lock in period is 3 years from the date of subscription.The above investment",
           "in an ELSS scheme is eligible for availing tax benefits under Section 80C of Income Tax Act,1961.",
           f"2. {SMALL_CODE} - {SMALL_SCHEME} : Entry Load NIL, Exit Load - 1.00% if redeemed with in 365 days from the date of allotment.NIL if redeemed",
           "after 365 days from the date of allotment of units.",
           "Notes: All unit allotments are subject to realization of payment; The pending MF transactions as on the last date of previous month would be reflected in the next",
           f"monthly statement. {FFFD} {FFFD} {FFFD} : {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}; {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} {FFFD} MF {FFFD} {FFFD} {FFFD} {FFFD} {FFFD}"]
    pages.append((["mf_units"], pm))

    mon = month.split()[0]
    src = f"{mon}2025_{CAS_TAG}_TXN.pdf"
    out = []
    for n, (types, lines) in enumerate(pages, start=1):
        out.append({"source_file": src, "statement_month": month, "page_number": n,
                    "section_type": types[0], "section_types": types,
                    "text": "\n".join(lines)})
    return out


def main():
    model = build_model()
    corpus = []
    for i in (2, 1, 0):                        # JUL, JUN, MAY -- newest first
        corpus += render_month(model, i)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in model["summary"]:
        print(f"{s['month']}: total {inr(s['total'])}  equity {inr(s['equity'])}  "
              f"MF demat {inr(s['mf_demat'])}  MF folios {inr(s['mf_folios'])}")
    print(f"{len(corpus)} pages -> {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
