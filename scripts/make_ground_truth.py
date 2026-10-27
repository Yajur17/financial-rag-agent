"""
Writes eval/questions.md (Q01-Q20) and eval/questions2.md (Q21-Q50) with every
ground-truth figure COMPUTED from the synthetic data model -- nothing is typed
by hand, so the answers can't drift from the statements.

Format (parsed by lang.loadQuestionsFromMarkdown / score.py):

    **Section: name (count)**
    **Q01** — question text
    Ground truth: `token` and `token`

Backticked tokens are the evidence markers score.py uses: a retrieved chunk is
relevant if it contains ANY of them; an aggregate answer is correct if it
contains every NAME token and at least one NUMBER token.

Figures are often truncated to the rupee (e.g. `2,94,664` for 2,94,664.88) so
the token still matches the chunk text as a substring however the model
formats the decimals.

Run after make_synthetic.py (and chunk.py, so the relevance sanity check can
see the corpus):  python3 scripts/make_ground_truth.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_synthetic import build_model, inr, q3, MONTHS   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
Q1_FILE = ROOT / "eval" / "questions.md"
Q2_FILE = ROOT / "eval" / "questions2.md"
CHUNKS = ROOT / "chunks" / "character" / "chunks_character.json"

M = build_model()
SEC, TXN, FOL, SM = M["securities"], M["transactions"], M["folios"], M["summary"]
MAY, JUN, JUL = 0, 1, 2
LBL = [m for m, _, _ in MONTHS]


def tr(x):
    """Truncate to the rupee, keeping Indian grouping: 2,94,664.88 -> 2,94,664."""
    return inr(x).split(".")[0]


def short(key):
    s = SEC[key]
    if s["kind"] in ("ETF", "MFD"):
        return s["name"].split("MF-")[-1]
    return re.split(r"\s*(?:LIMITED|LTD|#| - )", s["name"])[0].strip()


def val(key, i):
    s = SEC[key]
    return round(s["close"][i] * s["price"][i], 2)


def visible(i):
    """Holdings rows that actually become chunks in month i (equities + ETFs,
    minus the single-line row the chunker drops; May keeps zero-balance rows)."""
    return [k for k, s in SEC.items()
            if s["kind"] in ("EQ", "ETF") and k != "falcon" and (i == 0 or s["close"][i] > 0)]


def txns_for(key):
    return [(m, t) for m in LBL for t in TXN[m] if t["key"] == key]


def pct(a, b):
    return (b - a) / a * 100


def fol_name(f):
    return "aurora ELSS Tax Saver" if f["scheme"] == "ELSS" else "aurora Small Cap"


def sign(x):
    return f"+{inr(x)}" if x >= 0 else inr(x)


# ======================================================================= Q01-20
def part1():
    out = []
    add = lambda qid, q, gt: out.append((qid, q, gt))

    t = [s["total"] for s in SM]
    top = max(range(3), key=lambda i: t[i])
    add("Q01", "What was the total portfolio value in May 2025?", f"`{tr(t[MAY])}`")
    add("Q02", "What was the total portfolio value in July 2025?", f"`{tr(t[JUL])}`")
    add("Q03", "Which month had the highest portfolio value across all three statements?",
        f"`{tr(t[top])}` and `{LBL[top]}`")
    add("Q04", "How much did the portfolio grow from May 2025 to July 2025?",
        f"both `{tr(t[MAY])}` and `{tr(t[JUL])}` must appear across top-3")
    add("Q05", "What percentage of the portfolio was in mutual fund folios in June 2025?",
        f"`{SM[JUN]['pct']['Mutual Fund Folios']:.2f}`")

    hv = [tr(val("harbor", i)) for i in range(3)]
    add("Q06", "What is the current market value of Harbor Bank shares?",
        f"`HARBOR BANK` and any of `{hv[0]}` or `{hv[1]}` or `{hv[2]}`")
    gv = [tr(val("blu_gold", i)) for i in range(3)]
    add("Q07", "How many units of Bluefin Gold ETF do I hold and what is their value?",
        f"`BLUEFIN GOLD ETF` and any of `{gv[0]}` or `{gv[1]}` or `{gv[2]}`")
    add("Q08", "What is the combined market value of my Harbor Bank and Granite Bank holdings in July 2025?",
        f"both `{tr(val('harbor', JUL))}` and `{tr(val('granite', JUL))}` must appear across top-3")

    eq_rows = [k for k in visible(JUL)]
    leader = max(eq_rows, key=lambda k: val(k, JUL))
    assert leader == "kestrel", leader
    kv = [tr(val("kestrel", i)) for i in range(3)]
    add("Q09", "Which equity holding has the highest single-position value?",
        f"`KESTREL` and any of `{kv[0]}` or `{kv[1]}` or `{kv[2]}`")
    av = [tr(val("arcadia", i)) for i in range(3)]
    add("Q10", "I held Arcadia Pharma in all three months. Did its value go up or down?",
        f"`ARCADIA` and at least two of `{av[0]}` or `{av[1]}` or `{av[2]}`")

    sell_date = next(t["date"] for t in TXN["MAY 2025"] if t["style"] == "epdr")
    dd = int(sell_date[:2])
    add("Q11", f"What transactions happened on {dd} May 2025?",
        f"`{sell_date}` and `EP-DR Txn`")
    bs = next(t for t in TXN["MAY 2025"] if t["key"] == "blu_silver")
    assert bs["op"] == 0
    add("Q12", "When did I receive Bluefin Silver ETF units and how many?",
        f"`BLUEFIN SILVER ETF` and `{q3(bs['credit'])}`")
    lj = next(t for t in TXN["JUN 2025"] if t["key"] == "lotus")
    add("Q13", "Did I buy or sell Lotus Foods shares in June 2025?",
        f"`LOTUS FOODS` and `{lj['date']}`")
    add("Q14", "Which securities were debited from my account in May 2025?",
        f"`EP-DR` and `{sell_date}` and `Debit`")
    ms = [t["date"] for _, t in txns_for("mer_silver")]
    add("Q15", "How many Meridian Silver ETF units did I receive across all months?",
        f"`MERIDIAN SILVER ETF` and at least two of `{ms[0]}` or `{ms[1]}` or `{ms[2]}`")

    small = next(f for f in FOL if f["scheme"] == "SMALL")
    add("Q16", "What is the NAV of Aurora Small Cap Fund in July 2025?",
        f"`{small['months'][JUL]['nav']:.4f}` and `{small['isin']}`")
    add("Q17", "What is the combined market value of my Meridian Gold ETF and Bluefin Gold ETF holdings in July 2025?",
        f"both `{tr(val('mer_gold', JUL))}` and `{tr(val('blu_gold', JUL))}` must appear across top-3")
    inv_total = round(sum(f["invested"] for f in FOL), 2)
    add("Q18", "How much total have I invested in mutual funds across all folios?", f"`{tr(inv_total)}`")
    add("Q19", "The Aurora Small Cap Fund has grown a lot. What was the unrealised profit in May versus July 2025?",
        f"`{tr(small['months'][MAY]['pl'])}` (May) and `{tr(small['months'][JUL]['pl'])}` (July) — both must appear across top-3")
    low = min(FOL, key=lambda f: f["months"][MAY]["pct"])
    add("Q20", "Which folio had the lowest annualised return in May 2025?",
        f"`{low['months'][MAY]['pct']:.2f}` and `{q3(low['units'])}`")
    return out


def write_part1(rows):
    sections = [("summary", rows[0:5]), ("holdings", rows[5:10]),
                ("transactions", rows[10:15]), ("mf_units", rows[15:20])]
    lines = []
    for n, (name, qs) in enumerate(sections):
        lines.append(f"**Section: {name} ({len(qs)})**")
        lines.append("")
        for qid, q, gt in qs:
            lines += [f"**{qid}** — {q}", f"Ground truth: {gt}", ""]
        if n < len(sections) - 1:
            lines += ["---", ""]
    lines += [
        "---", "",
        "Notes",
        "",
        "- Ground truth is generated by `scripts/make_ground_truth.py` from the synthetic data model.",
        "- Cross-chunk questions (Q03, Q04, Q08, Q10, Q15, Q17, Q19) need evidence from several chunks "
        "(different months or different securities); for retrieval scoring, a chunk is relevant if it "
        "contains ANY backticked token.",
        "- Q16 and Q20 are precision questions: one specific figure in exactly one chunk.",
        "- Q20 says \"annualised\" because that is the column header in May/June; the figure is the "
        "unrealised profit % (the corpus has no XIRR column).",
        "",
    ]
    Q1_FILE.write_text("\n".join(lines), encoding="utf-8")


# ======================================================================= Q21-50
def part2():
    t = [s["total"] for s in SM]
    small = next(f for f in FOL if f["scheme"] == "SMALL")
    elss = [f for f in FOL if f["scheme"] == "ELSS"]
    na = "(not answerable from corpus — transactions record unit quantities only, no rupee cash-flow amounts"
    S = {}

    # --- growth & allocation
    S["Q21"] = ("How much did my portfolio value increase in 2025, and how much of that increase came from additional investments versus investment gains?",
                f"`{tr(t[MAY])}` and `{tr(t[JUL])}` and `{inr(t[JUL] - t[MAY])}` (May→Jul growth); the capital-vs-gains split is `{na}, so new capital deployed in ₹ cannot be separated from market appreciation)`")

    d1, d2 = t[JUN] - t[MAY], t[JUL] - t[JUN]
    big = JUN if d1 >= d2 else JUL
    a, b = big - 1, big
    classes = [("Equity", "equity"), ("Mutual Fund Folios", "mf_folios"),
               ("Mutual Funds Held in Demat Form", "mf_demat")]
    deltas = sorted(((SM[b][k] - SM[a][k], lab, k) for lab, k in classes), reverse=True)
    top = deltas[0]
    others = "; ".join(f"{lab} (`{inr(SM[a][k])}`→`{inr(SM[b][k])}`)" for _, lab, k in deltas[1:])
    S["Q22"] = ("Which month recorded the largest increase in my portfolio value, and what were the main contributors to that change?",
                f"`{LBL[big]}` and `{inr(max(d1, d2))}` ({LBL[a].split()[0].title()}→{LBL[b].split()[0].title()} rise `{tr(t[a])}`→`{tr(t[b])}`, larger than the other month's `{inr(min(d1, d2))}`); "
                f"top asset-class contributor `{top[1]}` (`{inr(SM[a][top[2]])}`→`{inr(SM[b][top[2]])}`, {sign(top[0])}); other classes: {others}")

    F = [s["mf_folios"] for s in SM]
    S["Q23"] = ("If I exclude all new investments and withdrawals, how much did my existing portfolio appreciate between May and July 2025?",
                f"`(not answerable from corpus for the full portfolio — equity/ETF positions added units with no recorded rupee purchase price, so appreciation cannot be isolated)`; "
                f"the MF folios alone (units unchanged May→Jul, so pure appreciation) moved `{inr(F[MAY])}`→`{inr(F[JUL])}`, i.e. `{inr(F[JUL] - F[MAY])}`")

    both = [k for k in visible(MAY) if SEC[k]["close"][MAY] > 0 and SEC[k]["close"][JUL] > 0]
    gains = sorted(both, key=lambda k: val(k, JUL) - val(k, MAY), reverse=True)[:3]
    parts = [f"`{short(k)}` (`{inr(val(k, MAY))}`→`{inr(val(k, JUL))}`, {sign(val(k, JUL) - val(k, MAY))})" for k in gains]
    added = [f"{short(k)} {SEC[k]['close'][MAY]:g}→{SEC[k]['close'][JUL]:g}" for k in gains
             if SEC[k]["close"][JUL] != SEC[k]["close"][MAY]]
    caveat = (f" — judgement call: raw value deltas include added units ({', '.join(added)}), not pure appreciation, since no equity cost basis exists in the corpus"
              if added else " — all with unchanged unit counts, so these are price moves")
    S["Q24"] = ("Which investments contributed the most to my portfolio's overall growth between May and July 2025?",
                "largest absolute value gains among demat holdings are " + ", ".join(parts) + caveat)

    sh = {lab: (SM[MAY]["pct"][lab], SM[JUL]["pct"][lab]) for lab, _ in classes}
    winner = max(sh, key=lambda l: sh[l][1] - sh[l][0])
    rest = "; ".join(f"{l} `{sh[l][0]:.2f}`→`{sh[l][1]:.2f}`" for l in sh if l != winner)
    S["Q25"] = ("How did my portfolio allocation change between May and July 2025, and which asset category gained the largest share?",
                f"`{winner}` gained the largest share, `{sh[winner][0]:.2f}`→`{sh[winner][1]:.2f}` ({sh[winner][1] - sh[winner][0]:+.2f}pts); {rest}")

    # --- unrealised profit & no-purchase moves
    by_pl = max(FOL, key=lambda f: f["months"][JUL]["pl"])
    by_pct = max(FOL, key=lambda f: f["months"][JUL]["pct"])
    if by_pl is by_pct:
        lead = (f"`{fol_name(by_pl)}` / `{by_pl['isin']}` leads on both in July — absolute profit "
                f"`{inr(by_pl['months'][JUL]['pl'])}` and return `{by_pl['months'][JUL]['pct']:.2f}`%")
    else:
        lead = (f"absolute: `{fol_name(by_pl)}` `{inr(by_pl['months'][JUL]['pl'])}`; percentage: "
                f"`{fol_name(by_pct)}` `{by_pct['months'][JUL]['pct']:.2f}`%")
    S["Q26"] = ("Which investments generated the highest unrealised profit in absolute terms, and which delivered the highest return as a percentage of invested capital?",
                lead + "; (scope limited to the 4 MF folios — equity/ETF holdings carry no cost basis, so no unrealised profit figure exists for them)")

    pl_moves = "; ".join(f"`{inr(f['months'][MAY]['pl'])}`→`{inr(f['months'][JUL]['pl'])}`" for f in FOL)
    declined = [f for f in FOL if f["months"][JUL]["pl"] < f["months"][MAY]["pl"]]
    fell_jun_jul = all(f["months"][JUL]["pl"] < f["months"][JUN]["pl"] for f in FOL)
    if not declined:
        txt = (f"`(not answerable as asked — none declined)`; all four MF folios' unrealised profit rose May→Jul ({pl_moves}), "
               "and equity/ETF holdings have no unrealised-profit field."
               + (" (They did fall Jun→Jul, but the question specifies May→Jul.)" if fell_jun_jul else ""))
    else:
        worst = min(declined, key=lambda f: f["months"][JUL]["pl"] - f["months"][MAY]["pl"])
        txt = f"`{fol_name(worst)}` folio fell most ({pl_moves})"
    S["Q27"] = ("Which holdings experienced the largest decline in unrealised profit between May and July 2025, and by how much?", txt)

    no_txn_up = [k for k in both if not txns_for(k) and val(k, JUL) > val(k, MAY)]
    items = ", ".join(f"`{short(k)}` (`{inr(val(k, MAY))}`→`{inr(val(k, JUL))}`, qty {SEC[k]['close'][MAY]:g} constant)"
                      for k in sorted(no_txn_up, key=lambda k: short(k)))
    S["Q28"] = ("Which investments increased in market value despite having no recorded purchases during the available period?",
                f"{items} — all rose with no transaction in any month; also the aurora MF folios (invested amount constant, e.g. `{inr(small['invested'])}`) rose on pure appreciation")

    # --- capital deployed
    jun = sorted(TXN["JUN 2025"], key=lambda x: SEC[x["key"]]["name"])
    debits = [x for x in jun if x["debit"]]
    eq_jun = [x for x in jun if SEC[x["key"]]["kind"] == "EQ"]
    other_jun = [x for x in jun if SEC[x["key"]]["kind"] != "EQ"]
    S["Q29"] = ("Which securities did I buy or sell in June 2025, and what was the net amount invested after accounting for both purchases and sales?",
                ("all June movements are credits (buys/payins), no debits (no sales) — " if not debits else "")
                + ", ".join(f"`{short(x['key'])}` (`{x['date']}`, +{x['credit']:g})" for x in eq_jun)
                + f", plus `{other_jun[0]['date']}` credits to "
                + ", ".join(short(x["key"]) for x in other_jun)
                + "; net rupee amount is `(not answerable from corpus — transaction Credit/Debit columns are unit quantities, not rupee values)`")
    S["Q30"] = ("How much fresh capital did I deploy into investments across May, June, and July 2025, excluding transfers and non-investment transactions?",
                f"`{na}, so ₹ capital deployed cannot be computed; MF-folio invested amounts are unchanged across the window, so no fresh folio capital)`")

    received = {}
    for m in LBL:
        for x in TXN[m]:
            if x["credit"]:
                received.setdefault(x["key"], []).append(x)
    tot = sorted(received, key=lambda k: sum(x["credit"] for x in received[k]), reverse=True)[:3]
    parts = []
    for k in tot:
        xs = received[k]
        parts.append(f"`{short(k)}` (+{sum(x['credit'] for x in xs):g}, {xs[0]['op']:g}→{xs[-1]['cl']:g})")
    S["Q31"] = ("Which investments received the most additional capital during these three months, and how much did I invest in each?",
                "`(not answerable in ₹ — no rupee transaction amounts in corpus)`; by units received, the largest additions are " + ", ".join(parts))

    # --- concentration & rankings
    pct_moves = ", ".join(f"`{f['months'][MAY]['pct']:.2f}`→`{f['months'][JUL]['pct']:.2f}`" for f in FOL)
    contra = [f for f in FOL if f["months"][JUL]["valuation"] > f["months"][MAY]["valuation"]
              and f["months"][JUL]["pct"] < f["months"][MAY]["pct"]]
    S["Q32"] = ("Are there any holdings whose market value increased while their unrealised return percentage decreased between May and July 2025?",
                ("`(none)` — for the four MF folios (the only holdings with a return %), both value and return rose May→Jul ("
                 + pct_moves + "); equity/ETF holdings have no return-% field") if not contra else
                ", ".join(fol_name(f) for f in contra))

    eq_vis_jul = [k for k in visible(JUL) if SEC[k]["kind"] == "EQ"]
    eq_vis_sum = round(sum(val(k, JUL) for k in eq_vis_jul), 2)
    kj = val("kestrel", JUL)
    S["Q33"] = ("Which of my individual equity holdings accounted for the largest percentage of my total equity portfolio in July 2025?",
                f"`KESTREL` at `{inr(kj)}`, about `{kj / SM[JUL]['equity'] * 100:.2f}`% of the July Equity total `{inr(SM[JUL]['equity'])}` "
                f"(≈{kj / eq_vis_sum * 100:.1f}% if measured against the summed visible equity rows `{inr(eq_vis_sum)}`)")

    def top5(i):
        ks = sorted([k for k in visible(i) if SEC[k]["close"][i] > 0], key=lambda k: val(k, i), reverse=True)[:5]
        return ks, round(sum(val(k, i) for k in ks), 2)
    k5j, s5j = top5(JUL)
    k5m, s5m = top5(MAY)
    S["Q34"] = ("What percentage of my portfolio was concentrated in my five largest holdings in July 2025, and how did that compare with May?",
                "judgement call (universe = demat holdings, base = total portfolio). July top-5 "
                + " + ".join(f"`{short(k)}` `{inr(val(k, JUL))}`" for k in k5j)
                + f" = `{inr(s5j)}` = `{s5j / t[JUL] * 100:.2f}`% of `{inr(t[JUL])}`; May top-5 = `{inr(s5m)}` = `{s5m / t[MAY] * 100:.2f}`% of `{inr(t[MAY])}`")

    def ranks(i):
        ks = sorted(both, key=lambda k: val(k, i), reverse=True)
        return {k: r + 1 for r, k in enumerate(ks)}
    rm, rj = ranks(MAY), ranks(JUL)
    move = {k: rm[k] - rj[k] for k in both}
    fall = min(both, key=lambda k: move[k])
    rises = sorted(both, key=lambda k: move[k], reverse=True)[:3]
    S["Q35"] = ("Which holdings moved up or down the most in the portfolio rankings between May and July 2025?",
                f"biggest fall `{short(fall)}` (rank {rm[fall]}→{rj[fall]}, {move[fall]:+d}); biggest rises "
                + ", ".join(f"`{short(k)}` ({rm[k]}→{rj[k]}, {move[k]:+d})" for k in rises)
                + " — ranked by value among demat holdings held in both months")

    # --- mutual-fund performance
    inv = round(sum(f["invested"] for f in FOL), 2)
    pl_jul = round(sum(f["months"][JUL]["pl"] for f in FOL), 2)
    S["Q36"] = ("How much of my total mutual fund investment was in profit, and what percentage return did that represent in July 2025?",
                f"all four folios in profit — invested `{tr(inv)}` → July value `{tr(F[JUL])}`, total unrealised profit `{inr(pl_jul)}`, return `{pl_jul / inv * 100:.2f}`%")

    e_inv = round(sum(f["invested"] for f in elss), 2)
    e_val = round(sum(f["months"][JUL]["valuation"] for f in elss), 2)
    S["Q37"] = ("Do I hold the same mutual fund through multiple folios, and what are my combined invested amount, market value, and unrealised profit for each scheme?",
                f"yes — `aurora ELSS Tax Saver` / `{elss[0]['isin']}` held in three folios (invested "
                + ", ".join(f"`{inr(f['invested'])}`" for f in elss)
                + f"; combined `{inr(e_inv)}`, July value `{inr(e_val)}`, profit `{inr(e_val - e_inv)}`); "
                f"`aurora Small Cap` / `{small['isin']}` in one folio (`{inr(small['invested'])}` / `{inr(small['months'][JUL]['valuation'])}` / `{inr(small['months'][JUL]['pl'])}`)")

    en = [elss[0]["months"][i]["nav"] for i in range(3)]
    sn = [small["months"][i]["nav"] for i in range(3)]
    abs_lead = "ELSS" if en[JUL] - en[MAY] > sn[JUL] - sn[MAY] else "Small Cap"
    pct_lead = "ELSS" if pct(en[MAY], en[JUL]) > pct(sn[MAY], sn[JUL]) else "Small Cap"
    S["Q38"] = ("Which mutual fund had the largest increase in NAV between May and July 2025, in both absolute and percentage terms?",
                f"only two schemes exist — ELSS `{en[MAY]:.4f}`→`{en[JUL]:.4f}` (+{en[JUL] - en[MAY]:.4f}, +{pct(en[MAY], en[JUL]):.2f}%) vs "
                f"Small Cap `{sn[MAY]:.4f}`→`{sn[JUL]:.4f}` (+{sn[JUL] - sn[MAY]:.4f}, +{pct(sn[MAY], sn[JUL]):.2f}%); "
                + (f"`aurora {abs_lead}` leads on both" if abs_lead == pct_lead else
                 f"`aurora {abs_lead}` leads on absolute, `aurora {pct_lead}` on percentage"))

    assert all(m["pct"] > 0 for f in FOL for m in f["months"])
    low = min(FOL, key=lambda f: f["months"][MAY]["pct"])
    S["Q39"] = ("Which mutual fund folios had negative unrealised returns in any of the three months, and did their performance improve or deteriorate by July?",
                f"`(none)` — every folio had a positive return in all three months; the lowest was the folio with `{low['months'][MAY]['pct']:.2f}`% in May "
                f"(`{low['isin']}`, {q3(low['units'])} units), which {'rose' if low['months'][JUL]['pct'] > low['months'][MAY]['pct'] else 'fell'} to `{low['months'][JUL]['pct']:.2f}`% by July")

    ranked = sorted(FOL, key=lambda f: f["months"][JUL]["pct"], reverse=True)
    S["Q40"] = ("Rank my mutual fund folios by annualised return in July 2025, and show their invested amounts and unrealised profits alongside the returns.",
                "ranked by Profit/Loss% (corpus has no true *annualised* return column — same convention as Q20): "
                + " > ".join(f"`{f['months'][JUL]['pct']:.2f}`% {fol_name(f)} (invested `{inr(f['invested'])}`, profit `{inr(f['months'][JUL]['pl'])}`)" for f in ranked))

    S["Q41"] = ("Which of my investments had the highest annualised return but contributed relatively little to my total portfolio profit?",
                (f"`(no investment fits this pattern)` — the highest-return holding (`{fol_name(by_pct)}`, `{by_pct['months'][JUL]['pct']:.2f}`%) is also the single largest profit contributor (`{inr(by_pct['months'][JUL]['pl'])}`); equity holdings have no return/profit data to rank")
                if by_pct is by_pl else f"`{fol_name(by_pct)}`")

    # --- reconciliation & cash flow
    quiet = sorted({short(k) for k in visible(JUL) if not txns_for(k)})
    S["Q42"] = ("Which securities appeared in my holdings statements but had no corresponding transactions in the available transaction records?",
                ", ".join(f"`{n}`" for n in quiet)
                + f" (held but never transacted); also the aurora `ELSS` folios (`{elss[0]['isin']}`) appear in mf_units but in no transaction (transactions only show aurora `{small['isin']}`)")

    expl = []
    for k in both:
        for m, x in txns_for(k):
            if SEC[k]["kind"] == "EQ":
                expl.append(f"`{short(k)}` {x['op']:g}→{x['cl']:g} by `{x['date']}` {'+' + format(x['credit'], 'g') if x['credit'] else '-' + format(x['debit'], 'g')}")
    S["Q43"] = ("Are there any transactions that could explain sudden changes in the quantity or market value of my holdings between consecutive statements?",
                "yes — " + "; ".join(expl))

    multi = [k for k in received if len({x["date"][3:5] for x in received[k]}) >= 2]
    multi = sorted(multi, key=lambda k: sum(x["credit"] for x in received[k]), reverse=True)
    S["Q44"] = ("Which securities did I receive additional units of across multiple months, and what was the total quantity received for each security?",
                ", ".join(f"`{short(k)}` {sum(x['credit'] for x in received[k]):g} ("
                          + " / ".join(f"`{x['date']}` {x['credit']:g}" for x in received[k]) + ")" for k in multi))

    vis_sum = round(sum(val(k, JUL) for k in visible(JUL)), 2)
    hidden_mf = round(sum(val(k, JUL) for k, s in SEC.items() if s["kind"] == "MFD"), 2)
    hidden_eq = val("falcon", JUL)
    gap = round(t[JUL] - vis_sum - F[JUL], 2)
    S["Q45"] = ("Can you reconcile my total portfolio value in July 2025 with the sum of my individual holdings and identify any unexplained differences?",
                f"summary is internally consistent — Equity `{inr(SM[JUL]['equity'])}` + `Mutual Funds Held in Demat Form` `{inr(SM[JUL]['mf_demat'])}` + MF Folios `{inr(F[JUL])}` = `{inr(t[JUL])}`; "
                f"but the visible holding rows sum to only `{inr(vis_sum)}` and folios `{inr(F[JUL])}`, leaving `{inr(gap)}` unexplained — the corpus chunks omit `{inr(hidden_mf)}` of non-ETF demat MFs and `{inr(hidden_eq)}` of equity (a single-line row the chunker drops)")

    S["Q46"] = ("Which investments had positive unrealised profits in May but lower or negative unrealised profits in July 2025?",
                (f"`(none)` — all four folios' unrealised profit was higher in July than May ({pl_moves}); equities have no profit field")
                if not declined else ", ".join(fol_name(f) for f in declined))

    better = "June" if small["months"][JUN]["pct"] > small["months"][JUL]["pct"] else "July"
    S["Q47"] = ("Did my portfolio perform better in June or July 2025 after accounting for the additional capital invested during those months?",
                f"full capital-adjusted comparison is `(not answerable — no rupee cash-flow amounts in corpus)`; on constant-capital MF folios, {better} was the stronger month "
                f"(e.g. Small Cap `{small['months'][JUN]['pct']:.2f}`% / value `{inr(small['months'][JUN]['valuation'])}` in June vs `{small['months'][JUL]['pct']:.2f}`% / `{inr(small['months'][JUL]['valuation'])}` in July)")

    rest = sorted((f for f in FOL if f is not by_pl), key=lambda f: f["months"][JUL]["pl"], reverse=True)
    S["Q48"] = ("Which investments made the most money for me in absolute terms, rather than simply having the highest percentage return?",
                f"`{fol_name(by_pl)}` / `{by_pl['isin']}`, `{inr(by_pl['months'][JUL]['pl'])}` (July), above the next folios ("
                + ", ".join(f"`{inr(f['months'][JUL]['pl'])}`" for f in rest)
                + "); scope limited to MF folios — equities have no cost basis, so their absolute gain is not in the corpus")
    S["Q49"] = ("If I had sold my investments at their July 2025 market values, what would my total unrealised profit have been, and which holdings would have contributed the most to it?",
                f"total MF-folio unrealised profit `{inr(pl_jul)}`, largest contributor `{fol_name(by_pl)}` `{inr(by_pl['months'][JUL]['pl'])}`; note the true whole-portfolio figure is `(not fully answerable — equity/ETF holdings have no cost basis in the corpus)`")
    S["Q50"] = ("Based on my May, June, and July 2025 statements and transaction records, explain what changed in my portfolio, how much additional capital I invested, and how much of the change came from investment performance rather than cash flows.",
                f"portfolio rose `{tr(t[MAY])}`→`{tr(t[JUL])}` (+`{inr(t[JUL] - t[MAY])}`); the capital-vs-performance split is `(not answerable from corpus — transactions give unit quantities only, no rupee cash flows)`; "
                f"the measurable pure-performance piece is the MF folios' appreciation `{inr(F[MAY])}`→`{inr(F[JUL])}` (+`{inr(F[JUL] - F[MAY])}`), units unchanged")
    return S


def write_part2(S):
    sections = [("growth & allocation", ["Q21", "Q22", "Q23", "Q24", "Q25"]),
                ("unrealised profit & no-purchase moves", ["Q26", "Q27", "Q28"]),
                ("capital deployed", ["Q29", "Q30", "Q31"]),
                ("concentration & rankings", ["Q32", "Q33", "Q34", "Q35"]),
                ("mutual-fund performance", ["Q36", "Q37", "Q38", "Q39", "Q40", "Q41"]),
                ("reconciliation & cash flow", ["Q42", "Q43", "Q44", "Q45", "Q46", "Q47", "Q48", "Q49", "Q50"])]
    lines = []
    for n, (name, ids) in enumerate(sections):
        lines += [f"**Section: {name} ({len(ids)})**", ""]
        for qid in ids:
            q, gt = S[qid]
            lines += [f"**{qid}** — {q}", f"Ground truth: {gt}", ""]
        if n < len(sections) - 1:
            lines += ["---", ""]
    Q2_FILE.write_text("\n".join(lines), encoding="utf-8")


def sanity_check(rows):
    """Every Q01-Q20 evidence token must exist somewhere in the chunk corpus,
    or retrieval scoring would have R = 0 for that question."""
    if not CHUNKS.exists():
        print("(chunks not found -- run scripts/chunk.py to enable the relevance check)")
        return
    corpus = [c["text"].lower() for c in json.loads(CHUNKS.read_text(encoding="utf-8"))]
    bad = 0
    for qid, _, gt in rows:
        for tok in re.findall(r"`([^`]+)`", gt):
            n = sum(1 for c in corpus if tok.lower() in c)
            if n == 0:
                bad += 1
                print(f"  {qid}: token `{tok}` is not in any chunk")
    if bad:
        print("  (expected only for aggregate-path questions such as Q03/Q18, which are scored on the\n"
              "   answer text -- a month label or a computed total -- not on retrieved chunks)")
    else:
        print("relevance check: every Q01-Q20 token is present in the corpus")


def main():
    rows = part1()
    write_part1(rows)
    write_part2(part2())
    print(f"wrote {Q1_FILE.relative_to(ROOT)} and {Q2_FILE.relative_to(ROOT)}")
    sanity_check(rows)


if __name__ == "__main__":
    main()
