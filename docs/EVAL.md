# The Chunking Fix — A RAG Case Study

**Project:** a retrieval system over monthly brokerage statements (mutual fund holdings, equity holdings, transactions) — a stand-in for "search a company's internal documents," built to learn the real mechanics of RAG rather than just call an API.

> **About the figures.** The work below was done and measured on the author's private statements. Figures and names quoted here are the equivalents from the synthetic dataset in this repo, so every example is reproducible; the metrics are from the original runs.

This is the story of one bug, why it mattered, how I found it, and what actually fixed it — written so I can explain it cold in an interview, not just point at a repo.

---

## 1. The setup

A RAG pipeline is four steps: **parse → chunk → embed → retrieve**. I had all four working end to end — PDF statements parsed into clean JSON, chunked, embedded with `text-embedding-3-small`, and a cosine-similarity retriever I hand-wrote in Python (no LangChain, so I actually understand what's happening at each step).

To know if it worked, I didn't eyeball it — I built a 20-question eval set with hand-written ground truth (exact figures taken from the statements), and scored **Top-1** (is the right chunk rank #1?) and **Top-3** (is it in the top 3?).

**Baseline: Top-1 25%, Top-3 ~40%.** Not great. Time to find out why.

---

## 2. The diagnosis

The original chunker was the naive, textbook default: slice every page into fixed 400-character windows with 50 characters of overlap. It doesn't know or care what's *in* the text — it just counts characters.

The bank statements are full of tables: ISIN code, security name, NAV, units held, value — one row per holding. A 400-character window has no concept of "row." It would routinely cut a table in half, so the row's **number** (say, a NAV of `287.8626`) landed in one chunk while the **scheme name and ISIN that gave that number meaning** landed in a different chunk, or worse, on a page of column headers.

I could see this concretely in one failing question: *"What is the NAV of Aurora Small Cap Fund in July 2025?"* — the retriever kept returning a chunk full of column headers (`NAV`, `Closing Balance`, `Cumulative Amount Invested`...) instead of the actual row with the number in it. The retriever wasn't broken. **The chunks it had to choose from were broken.**

That reframed the whole problem: this wasn't a "better embedding model" problem or a "bigger top-k" problem. It was a **structure problem**, upstream of the model entirely. No amount of throwing a smarter model at bad chunks fixes bad chunks.

---

## 3. The fix: row-aware chunking

The fix, in one sentence: **one chunk = one table row, never a character count.**

Instead of slicing by length, I wrote a chunker that reads the raw text line-by-line and only closes a chunk when it recognizes a *complete logical record* — using the ISIN code (`INE...`/`INF...`) as the anchor that marks where a record starts. Everything between one ISIN and the next (or the row's numeric tail) belongs to the same chunk.

Two design details that turned out to matter a lot:

- **No size cap, no overlap.** Character chunking needs overlap because its boundaries are arbitrary and might slice a fact in half — the overlap is a patch for that. Row chunking's boundaries are *semantic* (start of a record, end of a record), so there's nothing to patch. If your chunk boundary is already correct, overlap is dead weight.
- **Label the numbers.** A bare `389.1062` embeds almost meaninglessly. `|NAV: 389.1062 |Cumulative Amount Invested: 25,000.00 |Profit/Loss: 1,222.26` gives the embedding model actual semantic anchors to match a question against. This was a second, separate fix layered on top of the row-chunking — row-chunking got the *right facts* into one place; labeling made those facts *findable*.

I built this three times over, for three different table shapes in the statements (mutual fund units, equity/ETF holdings, transaction records), plus a fourth pass that pulled out a portfolio-summary line I found sitting unused in the raw text. **116 chunks total**, replacing the old blind 400-character windows entirely.

---

## 4. What actually went wrong along the way (the real interview material)

The fix wasn't "write it once, done." Building the holdings chunker specifically surfaced five distinct bugs, each teaching a different lesson:

1. **A one-cycle lag in my own buffering logic** — I was printing a variable's *old* value before updating it, so every record printed one cycle late and the last two records on every page silently vanished. Lesson: when a loop "remembers the previous thing," check exactly *when* you read vs. write that memory.

2. **Records split across a PDF page boundary got dropped.** My buffer reset every time I moved to a new page — but a table row doesn't know or care about page breaks. Moved the buffer state so it survives across pages. Lesson: real documents don't respect your code's mental model of "one page = one unit."

3. **The data had a field I wasn't using.** I was checking a single-label field (`section_type`) to decide which table a line of text belonged to — but some pages genuinely mix two tables, and the data already had a *second*, richer field (`section_types`, a list) recording that. Switching to the richer field was the actual fix. Lesson: check what your own pipeline already computed before reaching for a patch.

4. **A "smart" proxy turned out to be wrong.** I was using the ISIN prefix (`INF` vs `INE`) to decide "mutual fund" vs "equity" — until I found ETFs, which legitimately use the `INF` prefix but belong in the holdings table, not the mutual-fund table. The prefix was never the real signal; the row's actual shape (and whether the name contains "ETF") was. Lesson: a proxy that's *usually* right will eventually meet the case where it's wrong — better to key off the real thing when you can.

5. **A transaction line masqueraded as the end of a holdings record**, because both happened to contain the same placeholder token (`--`). Fixed by checking whether the line *starts with a date* — transaction lines do, holdings-summary lines never do. Lesson: when a single-token heuristic breaks, look for a more specific signature rather than patching with more exceptions.

None of these were found by reading the code and spotting the bug. **Every one was found by re-running the eval and noticing the output was wrong** — a habit, not a one-off.

---

## 5. The result

| | Before | After |
|---|---|---|
| Top-1 | 25% | **35%** |
| Top-3 | ~40% | **70%** |

The original target question (the NAV lookup that started this) now retrieves correctly. Beyond that single fix, two entire categories of question went from *impossible* to *answerable*, because the data for them simply didn't exist in the old corpus:

- **Transactions** (dates, debits/credits) had no chunker at all before this — a whole section of the source document was invisible to retrieval.
- **Portfolio summary** (total value, asset-class percentages) was sitting in the raw text the whole time, unused, until I found it while debugging something else.

---

## 6. What's still failing, and why that's not a bug

Not every remaining failure is a problem to fix — some are the honest edge of what pure retrieval can do:

- **Aggregate/superlative questions** ("which holding is highest," "what's my total invested across all folios") — no single chunk states a computed answer like this. This is the real boundary between *retrieval* and *reasoning*; the next phase of this project (an LLM that computes over retrieved facts) is what closes this gap, not a better chunker.
- **One real regression I found and kept, rather than quietly patching:** adding the new summary chunks caused one previously-passing question to start failing, because the new chunks were topically similar enough to out-rank the correct answer. **Lesson: adding chunks to a corpus adds retrieval *competition*, not just coverage.** A chunk that used to weakly win can get crowded out by new, similar-sounding chunks. The production fix for this is query routing or metadata filtering — not deleting the new data.

---

## The one-paragraph version, for when you only get 60 seconds

*"I had a RAG system with 25% Top-1 accuracy. Instead of assuming the embedding model was the problem, I diagnosed it directly — the chunker was slicing tables at arbitrary character counts, so a number would land in one chunk and the label that gave it meaning would land in another. I rebuilt the chunker to respect the actual row structure of the data instead, which took Top-1 to 35% and Top-3 to 70%. Along the way I found and fixed five separate bugs — a buffering lag, a page-boundary data loss, a wrong classification proxy — and I found one real regression that a naive fix would have hidden: adding new chunk types can crowd out a previously-correct answer, because more chunks means more retrieval competition, not just more coverage. That's the boundary I'm at now — pure retrieval can't do aggregation or superlatives, which is exactly why the next phase of this project is teaching an LLM to reason over what gets retrieved, not just fetch it."*
