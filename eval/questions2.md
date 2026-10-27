**Section: growth & allocation (5)**

**Q21** — How much did my portfolio value increase in 2025, and how much of that increase came from additional investments versus investment gains?
Ground truth: `3,00,208` and `3,38,508` and `38,300.02` (May→Jul growth); the capital-vs-gains split is `(not answerable from corpus — transactions record unit quantities only, no rupee cash-flow amounts, so new capital deployed in ₹ cannot be separated from market appreciation)`

**Q22** — Which month recorded the largest increase in my portfolio value, and what were the main contributors to that change?
Ground truth: `JUN 2025` and `24,949.60` (May→Jun rise `3,00,208`→`3,25,157`, larger than the other month's `13,350.42`); top asset-class contributor `Mutual Funds Held in Demat Form` (`43,897.11`→`53,960.36`, +10,063.25); other classes: Mutual Fund Folios (`1,75,004.21`→`1,82,494.73`); Equity (`81,306.99`→`88,702.82`)

**Q23** — If I exclude all new investments and withdrawals, how much did my existing portfolio appreciate between May and July 2025?
Ground truth: `(not answerable from corpus for the full portfolio — equity/ETF positions added units with no recorded rupee purchase price, so appreciation cannot be isolated)`; the MF folios alone (units unchanged May→Jul, so pure appreciation) moved `1,75,004.21`→`1,80,001.86`, i.e. `4,997.65`

**Q24** — Which investments contributed the most to my portfolio's overall growth between May and July 2025?
Ground truth: largest absolute value gains among demat holdings are `KESTREL ENGINEERING` (`32,454.00`→`36,341.46`, +3,887.46), `GRANITE BANK` (`11,093.07`→`14,864.38`, +3,771.31), `HARBOR BANK` (`8,982.21`→`11,723.44`, +2,741.23) — judgement call: raw value deltas include added units (KESTREL ENGINEERING 9→10, GRANITE BANK 6→8, HARBOR BANK 7→9), not pure appreciation, since no equity cost basis exists in the corpus

**Q25** — How did my portfolio allocation change between May and July 2025, and which asset category gained the largest share?
Ground truth: `Mutual Funds Held in Demat Form` gained the largest share, `14.62`→`18.57` (+3.95pts); Equity `27.08`→`28.25`; Mutual Fund Folios `58.30`→`53.18`

---

**Section: unrealised profit & no-purchase moves (3)**

**Q26** — Which investments generated the highest unrealised profit in absolute terms, and which delivered the highest return as a percentage of invested capital?
Ground truth: `aurora Small Cap` / `INF915ESK346` leads on both in July — absolute profit `20,706.82` and return `55.61`%; (scope limited to the 4 MF folios — equity/ETF holdings carry no cost basis, so no unrealised profit figure exists for them)

**Q27** — Which holdings experienced the largest decline in unrealised profit between May and July 2025, and by how much?
Ground truth: `(not answerable as asked — none declined)`; all four MF folios' unrealised profit rose May→Jul (`6,564.54`→`8,280.04`; `543.95`→`1,222.26`; `18,866.63`→`20,706.82`; `6,680.24`→`7,443.89`), and equity/ETF holdings have no unrealised-profit field. (They did fall Jun→Jul, but the question specifies May→Jul.)

**Q28** — Which investments increased in market value despite having no recorded purchases during the available period?
Ground truth: `ARCADIA PHARMA` (`2,512.80`→`2,633.21`, qty 3 constant), `COOLWAVE APPLIANCES` (`3,328.89`→`3,666.21`, qty 2 constant), `JASMINE HOTELS COMPANY` (`1,416.70`→`1,432.23`, qty 2 constant), `SUNRISE PIGMENTS INDUSTRIES` (`2,531.45`→`2,782.35`, qty 2 constant) — all rose with no transaction in any month; also the aurora MF folios (invested amount constant, e.g. `37,233.59`) rose on pure appreciation

---

**Section: capital deployed (3)**

**Q29** — Which securities did I buy or sell in June 2025, and what was the net amount invested after accounting for both purchases and sales?
Ground truth: all June movements are credits (buys/payins), no debits (no sales) — `KESTREL ENGINEERING` (`23-06-2025`, +1), `LOTUS FOODS` (`23-06-2025`, +5), plus `10-06-2025` credits to AURORA SMALL CAP FUND-DIRECT-GROWTH, BLUEFIN GOLD ETF, BLUEFIN SILVER ETF, MERIDIAN FLEXI CAP FUND DIRECT PL GR PL GR OPT, MERIDIAN GOLD ETF, MERIDIAN SILVER ETF; net rupee amount is `(not answerable from corpus — transaction Credit/Debit columns are unit quantities, not rupee values)`

**Q30** — How much fresh capital did I deploy into investments across May, June, and July 2025, excluding transfers and non-investment transactions?
Ground truth: `(not answerable from corpus — transactions record unit quantities only, no rupee cash-flow amounts, so ₹ capital deployed cannot be computed; MF-folio invested amounts are unchanged across the window, so no fresh folio capital)`

**Q31** — Which investments received the most additional capital during these three months, and how much did I invest in each?
Ground truth: `(not answerable in ₹ — no rupee transaction amounts in corpus)`; by units received, the largest additions are `BLUEFIN SILVER ETF` (+140, 0→140), `BLUEFIN GOLD ETF` (+120, 294→414), `AURORA SMALL CAP FUND-DIRECT-GROWTH` (+54.373, 40.09→94.463)

---

**Section: concentration & rankings (4)**

**Q32** — Are there any holdings whose market value increased while their unrealised return percentage decreased between May and July 2025?
Ground truth: `(none)` — for the four MF folios (the only holdings with a return %), both value and return rose May→Jul (`11.31`→`14.27`, `2.18`→`4.89`, `50.67`→`55.61`, `30.26`→`33.72`); equity/ETF holdings have no return-% field

**Q33** — Which of my individual equity holdings accounted for the largest percentage of my total equity portfolio in July 2025?
Ground truth: `KESTREL` at `36,341.46`, about `38.00`% of the July Equity total `95,631.37` (≈39.2% if measured against the summed visible equity rows `92,695.86`)

**Q34** — What percentage of my portfolio was concentrated in my five largest holdings in July 2025, and how did that compare with May?
Ground truth: judgement call (universe = demat holdings, base = total portfolio). July top-5 `KESTREL ENGINEERING` `36,341.46` + `GRANITE BANK` `14,864.38` + `HARBOR BANK` `11,723.44` + `MERIDIAN GOLD ETF` `9,285.54` + `MERIDIAN SILVER ETF` `8,441.86` = `80,656.68` = `23.83`% of `3,38,508.33`; May top-5 = `67,464.63` = `22.47`% of `3,00,208.31`

**Q35** — Which holdings moved up or down the most in the portfolio rankings between May and July 2025?
Ground truth: biggest fall `IONIC POWER EXCHANGE` (rank 7→11, -4); biggest rises `BRIGHTLINE TELECOM` (10→7, +3), `LOTUS FOODS` (11→8, +3), `ARCADIA PHARMA` (14→13, +1) — ranked by value among demat holdings held in both months

---

**Section: mutual-fund performance (6)**

**Q36** — How much of my total mutual fund investment was in profit, and what percentage return did that represent in July 2025?
Ground truth: all four folios in profit — invested `1,42,348` → July value `1,80,001`, total unrealised profit `37,653.01`, return `26.45`%

**Q37** — Do I hold the same mutual fund through multiple folios, and what are my combined invested amount, market value, and unrealised profit for each scheme?
Ground truth: yes — `aurora ELSS Tax Saver` / `INF034DXT044` held in three folios (invested `58,038.05`, `25,000.00`, `22,077.21`; combined `1,05,115.26`, July value `1,22,061.45`, profit `16,946.19`); `aurora Small Cap` / `INF915ESK346` in one folio (`37,233.59` / `57,940.41` / `20,706.82`)

**Q38** — Which mutual fund had the largest increase in NAV between May and July 2025, in both absolute and percentage terms?
Ground truth: only two schemes exist — ELSS `379.0409`→`389.1062` (+10.0653, +2.66%) vs Small Cap `278.7201`→`287.8626` (+9.1425, +3.28%); `aurora ELSS` leads on absolute, `aurora Small Cap` on percentage

**Q39** — Which mutual fund folios had negative unrealised returns in any of the three months, and did their performance improve or deteriorate by July?
Ground truth: `(none)` — every folio had a positive return in all three months; the lowest was the folio with `2.18`% in May (`INF034DXT044`, 67.391 units), which rose to `4.89`% by July

**Q40** — Rank my mutual fund folios by annualised return in July 2025, and show their invested amounts and unrealised profits alongside the returns.
Ground truth: ranked by Profit/Loss% (corpus has no true *annualised* return column — same convention as Q20): `55.61`% aurora Small Cap (invested `37,233.59`, profit `20,706.82`) > `33.72`% aurora ELSS Tax Saver (invested `22,077.21`, profit `7,443.89`) > `14.27`% aurora ELSS Tax Saver (invested `58,038.05`, profit `8,280.04`) > `4.89`% aurora ELSS Tax Saver (invested `25,000.00`, profit `1,222.26`)

**Q41** — Which of my investments had the highest annualised return but contributed relatively little to my total portfolio profit?
Ground truth: `(no investment fits this pattern)` — the highest-return holding (`aurora Small Cap`, `55.61`%) is also the single largest profit contributor (`20,706.82`); equity holdings have no return/profit data to rank

---

**Section: reconciliation & cash flow (9)**

**Q42** — Which securities appeared in my holdings statements but had no corresponding transactions in the available transaction records?
Ground truth: `ARCADIA PHARMA`, `COOLWAVE APPLIANCES`, `DELTA AGRO CHEMICALS`, `EVERGREEN SERVICES`, `IONIC POWER EXCHANGE`, `JASMINE HOTELS COMPANY`, `SUNRISE PIGMENTS INDUSTRIES` (held but never transacted); also the aurora `ELSS` folios (`INF034DXT044`) appear in mf_units but in no transaction (transactions only show aurora `INF915ESK346`)

**Q43** — Are there any transactions that could explain sudden changes in the quantity or market value of my holdings between consecutive statements?
Ground truth: yes — `BRIGHTLINE TELECOM` 0→2 by `20-05-2025` +2; `BRIGHTLINE TELECOM` 2→3 by `25-07-2025` +1; `GRANITE BANK` 6→8 by `24-07-2025` +2; `HARBOR BANK` 7→9 by `24-07-2025` +2; `KESTREL ENGINEERING` 9→10 by `23-06-2025` +1; `LOTUS FOODS` 15→7 by `12-05-2025` -8; `LOTUS FOODS` 7→12 by `23-06-2025` +5

**Q44** — Which securities did I receive additional units of across multiple months, and what was the total quantity received for each security?
Ground truth: `BLUEFIN SILVER ETF` 140 (`05-05-2025` 40 / `10-06-2025` 40 / `11-07-2025` 60), `BLUEFIN GOLD ETF` 120 (`05-05-2025` 40 / `10-06-2025` 40 / `11-07-2025` 40), `AURORA SMALL CAP FUND-DIRECT-GROWTH` 54.373 (`05-05-2025` 17.487 / `10-06-2025` 17.119 / `11-07-2025` 19.767), `MERIDIAN GOLD ETF` 36 (`05-05-2025` 12 / `10-06-2025` 12 / `11-07-2025` 12), `MERIDIAN SILVER ETF` 26 (`05-05-2025` 10 / `10-06-2025` 10 / `11-07-2025` 6), `BRIGHTLINE TELECOM` 3 (`20-05-2025` 2 / `25-07-2025` 1), `MERIDIAN FLEXI CAP FUND DIRECT PL GR PL GR OPT` 1.643 (`05-05-2025` 0.563 / `10-06-2025` 0.549 / `11-07-2025` 0.531)

**Q45** — Can you reconcile my total portfolio value in July 2025 with the sum of my individual holdings and identify any unexplained differences?
Ground truth: summary is internally consistent — Equity `95,631.37` + `Mutual Funds Held in Demat Form` `62,875.10` + MF Folios `1,80,001.86` = `3,38,508.33`; but the visible holding rows sum to only `1,18,002.32` and folios `1,80,001.86`, leaving `40,504.15` unexplained — the corpus chunks omit `37,568.64` of non-ETF demat MFs and `2,935.51` of equity (a single-line row the chunker drops)

**Q46** — Which investments had positive unrealised profits in May but lower or negative unrealised profits in July 2025?
Ground truth: `(none)` — all four folios' unrealised profit was higher in July than May (`6,564.54`→`8,280.04`; `543.95`→`1,222.26`; `18,866.63`→`20,706.82`; `6,680.24`→`7,443.89`); equities have no profit field

**Q47** — Did my portfolio perform better in June or July 2025 after accounting for the additional capital invested during those months?
Ground truth: full capital-adjusted comparison is `(not answerable — no rupee cash-flow amounts in corpus)`; on constant-capital MF folios, June was the stronger month (e.g. Small Cap `58.80`% / value `59,127.65` in June vs `55.61`% / `57,940.41` in July)

**Q48** — Which investments made the most money for me in absolute terms, rather than simply having the highest percentage return?
Ground truth: `aurora Small Cap` / `INF915ESK346`, `20,706.82` (July), above the next folios (`8,280.04`, `7,443.89`, `1,222.26`); scope limited to MF folios — equities have no cost basis, so their absolute gain is not in the corpus

**Q49** — If I had sold my investments at their July 2025 market values, what would my total unrealised profit have been, and which holdings would have contributed the most to it?
Ground truth: total MF-folio unrealised profit `37,653.01`, largest contributor `aurora Small Cap` `20,706.82`; note the true whole-portfolio figure is `(not fully answerable — equity/ETF holdings have no cost basis in the corpus)`

**Q50** — Based on my May, June, and July 2025 statements and transaction records, explain what changed in my portfolio, how much additional capital I invested, and how much of the change came from investment performance rather than cash flows.
Ground truth: portfolio rose `3,00,208`→`3,38,508` (+`38,300.02`); the capital-vs-performance split is `(not answerable from corpus — transactions give unit quantities only, no rupee cash flows)`; the measurable pure-performance piece is the MF folios' appreciation `1,75,004.21`→`1,80,001.86` (+`4,997.65`), units unchanged
