# From Retrieval to an Agent — Building the LangGraph Layer

> **About the figures in this document.** The system was built and measured on the author's private brokerage statements. Every figure, security name and chunk id quoted below has been replaced with its equivalent from the synthetic dataset shipped in this repo (`scripts/make_synthetic.py`), so you can reproduce each example. The bugs, design decisions and metrics are from the original runs.

**Companion to [EVAL.md](EVAL.md).** That document is the story of fixing *retrieval*. This one is the story of what happens when retrieval isn't enough, and you have to teach the system to decide.

---

## 1. Where this picks up

By the end of the chunking work, the system could reliably fetch a fact. Ask it *"what's the NAV of Aurora Small Cap in July"* and the right chunk comes back.

But an eval set of 20 questions had a stubborn floor: **7 of them returned nothing at all.** Not wrong answers — *no* answer. Questions like *"how much did the portfolio grow from May to July"* or *"what percentage was in mutual fund folios."*

The reason is structural, and it's the most important idea in this whole project:

> **No single chunk contains a computed answer.** Retrieval can find a fact. It cannot combine two facts. "Growth from May to July" isn't written anywhere in the document — it's a subtraction someone has to perform.

That's the boundary between *retrieval* and *reasoning*, and it's where this phase starts.

---

## 2. The aggregation path — and why it abandons similarity search

The first fix was a function that answers "sum a field" questions by filtering the corpus directly on metadata:

```python
for c in corpus:                                   # all 116 chunks
    if c["statement_month"] not in month: continue
    if scheme and not any(s in c["text"] for s in scheme): continue
    total += extract_number(c["text"], field)
```

**Why not just use the existing similarity search with a bigger `k`?** Because a top-k search answers *"which chunks look most like this question?"* — and for a sum, that's the wrong question. It returns a ranked guess. If the 6th-most-similar chunk happened to be one of the records you needed, your total is quietly wrong, and nothing raises an error.

Metadata filtering returns *everything matching the rules*. Completeness by construction, not by hoping `k` was big enough.

The trade is that it only works when the question can be reduced to structured filters. Which is exactly what the router in section 4 is for.

**The interview line:** *"Top-k is for 'find me something relevant.' It's the wrong tool for 'count all of these.' I route aggregation questions to exhaustive metadata-filtered retrieval instead, so completeness is guaranteed rather than probable."*

---

## 3. The bug that threw no error

While generalising the filters to handle several months at once, this got written:

```python
for m in month:
    if c["statement_month"] != m:
        continue
```

It looks fine. It does nothing.

`continue` advances the loop it sits in — the loop over *months*. It spins through the list, finds nothing to do, and execution falls through to the summing code below **on every chunk, unconditionally**. The month filter was inert.

The symptom: a question asking for July returned all three months added together. `15,244.24` came out as `41,978.30`.

**No exception. No warning. A plausible-looking number.**

The only thing that caught it was having written down the expected answer beforehand and comparing.

> **Lesson worth stating out loud in an interview:** the dangerous bugs in a data pipeline aren't the ones that crash. They're the ones that return a confident, well-formatted, wrong number. Ground-truth test cases aren't bureaucracy — they're the only detector you have.

The fix was one line: `if c["statement_month"] not in month: continue`.

---

## 4. Wrapping it in LangGraph

With both paths working as plain functions, the next step was making the *choice between them* explicit.

### The four pieces

**State** — a `TypedDict` with `question` and `answer`. One object that travels through the system, arriving with the question filled in and the answer blank. Think of a patient file at a hospital: every department reads what previous departments wrote and adds its own notes. Nobody passes information by shouting down the corridor.

**Nodes** — plain functions, `(state) -> dict of updates`. `aggregate_node` and `retrieve_node` are thin wrappers around logic that already worked. **A node returns only the fields it changed**, not the whole state — LangGraph merges the update in. That merge semantic is the single most common thing to get wrong.

**Edges** — control flow between node *names*. Nodes are registered under a string label; edges refer to that label, never to the function object. That indirection is what makes routing possible: a router returns a name.

**Compile** — turns the description into a runnable, and validates it. Name a node in an edge that doesn't exist and it fails at startup, not halfway through question 14.

### The mental shift from a chain

A LangChain chain is a **recipe** — do A, then B, then C, same order every time. A graph is a **map**. Nothing executes until `.invoke()`; until then you're describing a shape. That's why the order of your `add_node`/`add_edge` calls doesn't matter.

---

## 5. The router — where it stops being decoration

```python
def route_question(state):
    if get_field(state["question"]) is None:
        return "retrieve"
    return "aggregate"
```

In English: *if I can't work out which field this question is asking about, I can't compute an answer — so search instead of failing.*

This is what made the graph earn its place. Wrapping one function in a one-node graph is ceremony. Adding a decision point is architecture.

**Result: 20 questions, 0 failures.** 13 computed, 7 fall back to retrieval.

And the fallback isn't a consolation prize. Asked *"what percentage was in mutual fund folios in June?"*, retrieval returns the June summary chunk — which literally reads `Mutual Fund Folios: 1,82,494.73 (56.12%)`. The system didn't compute the answer. It put the answer in front of the user anyway.

| | Before | After |
|---|---|---|
| Questions returning nothing | 7 / 20 | **0 / 20** |
| Computed answers | 13 | 13 |
| Retrieval fallback | — | 7 |

---

## 6. "Why LangGraph? An if-statement would do."

It would. Today's graph has two paths and no loops — plain Python handles that.

The honest answer is that the graph buys things needed *next*, not now:

- **Cycles.** An if-statement runs once. A graph can loop: try, inspect the result, route differently, try again. This is the thing neither plain sequential code nor a LangChain chain expresses cleanly, and it's what "agent" actually means in practice.
- **Accumulating state.** Every node reads what earlier nodes wrote without threading arguments through signatures.
- **Checkpointing.** A run can be frozen mid-flight and resumed — which is the mechanism for human-in-the-loop approval steps.
- **Shared vocabulary.** Nodes, edges, conditional routing, state — this is how these systems are discussed in the industry.

Saying *"an if-statement would have covered today; I used a graph because the next three things I want need cycles and shared state"* is a stronger answer than pretending it was strictly necessary.

---

## 7. Known limits, stated honestly

Not everything is fixed, and knowing precisely what isn't is worth more than pretending otherwise.

- **Superlatives and lists.** *"Which holding is highest?"* and *"which securities were debited?"* both route to aggregation, which only knows how to **sum**. They return a confident, wrong number. These need a MAX path and a list-returning path — different functions, not a tweak.
- **Vague time ranges.** `get_month` matches the literal keywords `may`/`jun`/`july`. A phrase like *"all three months"* matches none of them and silently falls back to the latest month only.
- **Requesting a field that doesn't exist in that section.** `Cumulative Amount Invested` exists only on mutual fund chunks — an equity holdings statement never records what you paid. Ask for an equity holding's invested amount and every chunk fails the regex, and the function returns a clean `0`.

  **That last one is the most dangerous failure mode in the system**, because `0` and "I have no data for that" are indistinguishable to the caller. Any production version needs those to be different outcomes.

- **Retrieval competition.** Documented in [EVAL.md](EVAL.md) and still true: adding chunk types adds retrieval *competition*, not just coverage. One previously-passing question regressed when summary chunks were introduced.

---

---

## 8. The deeper design flaw — one verb

The limits in section 7 look like three separate missing features. They're one.

Take a real question: *"By how much did my Bluefin Gold ETF holding increase from May to July?"*

Trace it through the extractors:

```
get_scheme -> ['BLUEFIN GOLD ETF']    ✓
get_month  -> ['MAY 2025', 'JUL 2025'] ✓
get_field  -> None                     ✗
```

Two of three slots parse correctly. And the data is sitting right there — May `4,957.56`, July `5,958.70`, so the answer is **+1,001.14**. The system still can't produce it.

The missing thing isn't a keyword. **It's a verb.** This system knows exactly one operation: *sum*. Every question, whatever it asks, ends at `total_value += value`.

That's because the filtering and the arithmetic are fused in the same loop:

```python
for c in corpus:
    ...filters...
    total_value += value      # find AND reduce, welded together
```

Split them, and the missing features stop being features:

```python
def fetch_values(field, scheme, months) -> list[record]:
    """Find matching records. Return them. Don't reduce."""
```

| Question type | Reduction | Fixes |
|---|---|---|
| "total" | `sum(v)` | today's behaviour |
| "increase from X to Y" | `last − first`, ordered | delta questions |
| "highest" | `max(...)`, return the name | superlatives |
| "which securities" | return names, not a number | list questions |
| "what percentage" | `part / whole` | ratio questions |

One fetch, five endings. Add an `operation` slot alongside field/scheme/month, and one `compute_node` that dispatches on it.

**The graph, the router, and the state schema are all untouched** — which is precisely the payoff for having built the routing layer. New capability slots in; it doesn't require a rewrite.

> **The generalisable lesson:** when several features all feel missing at once, check whether they're really one abstraction that was never separated. Fusing "find the data" with "do the arithmetic" wasn't a shortcut — it was the thing preventing four different question types from ever working.

---

## 9. Would this scale? — measured, not guessed

Worth benchmarking rather than hand-waving, because the result is counterintuitive.

**The scan is not the bottleneck:**

```
      116 chunks (actual) ->    0.5 ms
   ~104,000 chunks        ->   13.5 ms
 ~1,044,000 chunks        ->  134.9 ms
```

A million chunks filters in 135ms — because the cheap metadata comparison eliminates most rows before anything expensive runs. *Cheap filters first* is carrying real weight.

**Memory is the bottleneck:**

```
embeddings file: 4.5 MB for 116 chunks
 100k chunks ->  4.1 GB loaded by json.load()
   1M chunks -> 40.7 GB
```

Every chunk carries a 1536-dimension embedding. And the aggregation path **never uses those embeddings** — it's loading gigabytes of vectors to run a string comparison.

**What production changes, in priority order:**

1. **Push the filter into the storage layer.** Vector DB with indexed metadata filtering; vectors stay server-side and never enter the application process.
2. **Store numbers as numbers.** The bigger design flaw: chunks hold `"Value: 11,723.44"` as *text*, re-parsed by regex on every query. Extract typed fields once at ingestion.
3. **Aggregations shouldn't touch the vector store.** Once fields are typed, a sum is SQL. Postgres does that over 100M rows in milliseconds. A vector database is the wrong tool for arithmetic.
4. **Async.** The real per-query bottleneck is a ~200ms blocking embedding call, not compute.
5. **Tenancy — the one that matters most here.** With many users on a shared index, the `user_id` filter must be applied *inside* the search, never after retrieval. If another user's chunk enters the candidate set at all, it has already leaked into a ranking, a log, or a model's context window.

**On generating the SQL:** the model should emit validated *parameters* — field, entities, date range, operation — as JSON checked against an allowlist, with the query built in code using bound parameters. The model never sees SQL, so injection is structurally impossible and the tenancy filter can't be influenced by a prompt. Text-to-SQL earns its place only when the question space is genuinely non-enumerable; a bounded domain makes it a less testable version of a classification problem.

Note that `get_field` / `get_scheme` / `get_month` **already are** this pattern — with keyword rules as the extractor instead of a model. The upgrade swaps three functions; nothing downstream changes.

---

## 10. Teaching it to talk — the generation node

Until this point the system had never called a chat model. It retrieved and it
computed. Ask it about your portfolio and it answered `300208.31`.

That's a search engine with a calculator bolted on. The missing piece was the
one the whole project is named after.

### The first decision: where generation does *not* go

```
START → route → aggregate ───────────────────→ END
              → retrieve → generate → verify → END
```

Only the retrieval path generates. The aggregation path already has an exact,
verified number — passing `15,244.24` through a language model adds
hallucination risk and buys nothing.

> **Knowing when *not* to use a model is a better answer than using one
> everywhere.** Thirteen of the twenty questions cost zero LLM tokens, because
> the cheapest way to answer a question is not to ask a model.

### The prompt is the engineering, not the plumbing

The HTTP call took twenty minutes. The system prompt is where the work is:

1. Answer **only** from the provided context — no outside knowledge
2. Quote figures **exactly**, commas and decimals intact
3. Cite the `chunk_id` after every figure
4. If you do arithmetic, **show the operands**, each cited
5. If the context lacks the answer, reply with a **fixed string**:
   `Not answerable from the retrieved context.`
6. On conflicting values, report both with their chunk_ids

Each rule is a decision, and three are worth defending out loud:

- **Rule 5 is an exact sentence, not "say you don't know."** A constant string
  is *countable* — `answer.startswith("Not answerable")` gives you a refusal
  rate. "I'm not sure" phrased forty ways is unmeasurable.
- **Rule 2 exists to make automated verification possible.** Section 11's
  checker matches numbers from the answer against the source. Let the model
  round and the check breaks.
- **Rule 6 is corpus-specific.** These statements restate the same holding
  across three months, so retrieval routinely returns May and July versions of
  one row. Without the rule, the model silently picks one.

### The first hallucination, caught red-handed

Before the prompt existed, asked when Bluefin Silver ETF units were received:

> *"40 units on 10 June, and an additional 60 units on 11 July, bringing your
> total to 140 units."*

Ground truth was `40.000` (received in May). The July figure wasn't in the
context the model had been given — it was invented. And **40 + 60 = 100**, not 140
— it couldn't even add its own fabrication. Written in exactly the same
confident register as every correct answer.

The cause was upstream: `text_preview` was truncated to **220 characters**.
The model got half a row, recognised the shape, and filled the gap.

> **Truncated context doesn't make a model say "I don't know." It makes it
> improvise.**

### What the prompt fixed — and what it didn't

After the rules went in, every figure carried a citation, the invented `60`
and `140` disappeared, and Q20 refused in the exact specified string.

But Q15 stayed wrong. It answered:

```
78.000 [MAY_8_..] + 10.000 [JUN_5_..] + 6.000 [JUL_6_..] + 88.000 [JUN_7_..] = 182.000
```

The arithmetic is right. The answer is wrong — two of those chunk_ids are
*holdings* pages. It added balances to receipts.

Here's the part worth saying in an interview:

> **The prompt didn't make the system more accurate. It made it auditable.**
> Before, it said "94 units" and there was no way to know why. After, you can
> see in three seconds that two of its four sources were the wrong kind of
> document.

And the failure isn't a generation failure at all. Retrieval handed it the
wrong documents. **A bad answer wearing a generation costume is usually a
retrieval problem** — and rule 3's citations are what made that diagnosable.

### Why generation became its own node

It started life as a function call inside `retrieve_node`. That works, and it
throws away four things:

- **Retry.** A rate-limited model call re-runs the whole box, including a
  fresh embedding call and search you already paid for.
- **Tracing.** One box taking 3.4 seconds tells you nothing about whether
  retrieval or the model was slow.
- **Routing.** No gap to insert a reranker, a grounding check, or a
  try-again loop into.
- **State.** The chunks died as a local variable — and section 11's checker
  needs the chunks *and* the answer together.

That last one forced the change. **A node is the unit of retry, of tracing,
and of routing.** Anything you might want to retry, time, or route around has
to be one.

---

## 11. Verifying it — the grounding check

The prompt *asks* the model not to invent figures. Section 11 *verifies* it
didn't.

```
generate → verify → END
```

### Why code, and not a second model

LLM-as-judge is the common answer, and it's right for *"is this answer
relevant, well-reasoned, complete?"* — subjective things code can't assess.

For *"does 38,300.02 appear in the source?"* it's strictly worse: slower,
costlier, non-deterministic, and it shares the first model's blind spots.

> **Never verify a model with the same model.** A second call can confidently
> agree with the first one's invention. Anything checkable, check with code.

### Three buckets, not two

Run a naive checker on Q04 and it flags `38,300.02` as a hallucination — which
is the *correct answer*, a subtraction that appears nowhere in the source.

| Bucket | Meaning |
|---|---|
| **Grounded** | The value appears in the retrieved context |
| **Derived** | Not in context, but arithmetic on grounded values |
| **Ungrounded** | Neither. The real flag |

**Prompt rule 4 is what makes "derived" mechanically checkable.** Forcing the
model to print its operands turns "trust me, I computed it" into something a
program can confirm. The rules and the verifier were designed together.

### Two implementation details that matter

**Citations are stripped first.** A chunk_id like
`[JUL2025_DEMO0001_TXN.pdf_JUL 2025_6_13]` is full of digits that aren't
figures. Skip that and the ungrounded list is pure noise.

**Values are compared, not strings.** `3,38,508.33` and `338508.33` are the
same number. Rule 2 asks the model to preserve format; the checker shouldn't
*depend* on it having obeyed.

### The bug: the prompt broke its own verifier

First run flagged Q15's `182.000` as ungrounded — wrongly, since
78 + 10 + 6 + 88 = 182 and all four are grounded.

Cause: **rule 4 makes the model print its operands twice**, once listing them
and once in the arithmetic line. The grounded list held eight values instead of
four, and `sum()` came out at 364. One `set()` fixed it.

> A verifier has to account for the format the prompt enforces. The two are
> coupled whether you designed them that way or not.

### Reading the result honestly

**7 of 7 generated answers fully grounded — 100%.**

That does **not** mean the system is correct. Q15 is still wrong. What it means
is narrower and exactly right: **no figure was invented.** Every number traces
to a chunk, or to arithmetic on numbers that do.

> **Grounding catches invention. It does not catch misuse.** Q15's figures were
> all real and all cited; retrieval handed the model the wrong *kind* of
> document. No verifier reading the answer can see that.

A clean run isn't a broken checker — it's a **regression guard**, and it's
already proven it fires, because it fired on Q15 before the dedupe fix.

**The interview line:**

> *"I extract every figure from the generated answer and verify it against the
> retrieved context in code — not a second LLM, because that can agree with the
> first one's invention. Figures not in the source are then checked as
> arithmetic on figures that are, so computed answers don't false-positive. I
> report a groundedness rate rather than claiming the prompt prevents
> hallucination — currently 7 of 7."*

---

## 12. Giving it hands — tool calling

Section 8 named the deepest flaw: the aggregation path knew **one verb**. It
could only `sum`. So *"which holding is highest?"* (Q09) returned a total, and
*"which securities were debited?"* (Q14) returned a number instead of a list —
both confident, both wrong.

The fix was the capability most agent stacks are built on: **tool calling.**

### One fetch, three verbs

The old `aggregate_general` fused *find the rows* with *add them up* in one
loop — that's why it could only ever add. Split them:

```
fetch_rows(field, scheme, month)  →  the matching rows, once
   ├─ sum_field   → add the values      (Q18, Q01…)
   ├─ max_field   → the row with the biggest value, by NAME   (Q09 → KESTREL)
   └─ list_field  → every row, by name                        (Q14)
```

Same fetch, three endings. All three read the *same* rows — the verb only
changes what you do with them, which is exactly why the fetch can happen
*before* the model is even called.

### Who picks the verb? The model.

Not an `if "highest" in question` keyword router — that's brittle and teaches
nothing. I hand the model three **tool schemas** (name + description +
parameters) and it reads the question and returns a `tool_call` choosing one.
`finish_reason` comes back as `tool_calls`, not `stop` — the model is saying
*"I'm not answering, I want a tool."*

> **The design line:** *"The model classifies intent and picks the tool. The
> tool reads the figures deterministically. The model never touches a number —
> so the answer is grounded by construction."* This is the same
> deterministic-figures principle from Section 11, now with the model doing only
> the part it's actually good at: reading intent.

### The loop, closed

```
user      → the question
assistant → tool_call: max_field           ← a request, not an answer
tool      → the result, tied back by tool_call_id
assistant → the final sentence, phrased from the result
```

Two model calls, one deterministic execution in between. `aggregate_node` now
runs this loop and routes its output through the **same `verify` node** from
Section 11 (`aggregate → verify → END`, where it used to be `aggregate → END`)
— so these answers get grounded too, which they never were before.

### Three bugs, each a real tool-calling lesson

| Bug | Cause | Fix |
|---|---|---|
| **Substring collision** | field `Value` matched inside `Total Portfolio **Value**:` in the summary chunk — the biggest number, so `max` grabbed it | Anchor the field regex to a row boundary: `(?:^\|\|)\s*{field}:` |
| **Parallel tool calls** | the model emitted 2+ `tool_calls` in one message ("Harbor Bank *and* Granite Bank"); the API rejects the turn unless **every** `tool_call_id` gets a reply | `parallel_tool_calls: False` — one verb answers each question, so there's nothing to parallelise |
| **Derived figures flagged** | a *sum* isn't literally in the corpus, so grounding called it ungrounded | send the contributing `source_rows` back in the tool result, so the model cites the per-row operands and `is_derived` validates the total |

A fourth, smaller one fell out of routing aggregate through `verify`: the
grounding checker counted a bare year (`"July 2025"`) as a figure. Money in this
corpus always carries a comma or decimal, so `extract_numbers` now skips a plain
`^(19|20)\d{2}$` token.

### The result

**Q09 → KESTREL ENGINEERING, 36,341.46. Q14 → the full list of 15 debited
securities. 20 of 20 answers fully grounded** — and the aggregation path is now
verified, which it never was.

### Why this is the *tight* version, on purpose

What I built is **single-hop**: one question → one verb → one answer. Code
pre-fetches, the model picks once, done. Predictable and testable. The *fuller*
pattern — `bind_tools` / `ToolNode` / a **ReAct** loop — lets the model drive:
call a tool, see the result, decide the next tool, decide when to stop. That's
the next step; the single-hop version is the right first one because every piece
is deterministic enough to unit-test. (That next step has since shipped — see section 13.)

**The interview line:**

> *"I gave the aggregation path real tool calling — the model reads the question
> and picks one of three verbs, sum, max, or list, and deterministic code runs
> it over the fetched rows. The model never touches a figure, so the answer
> stays grounded by construction. The bug worth telling is parallel tool calls:
> the model can request several tools in one turn, and the API rejects the turn
> unless every tool_call_id gets a reply — I disabled parallelism because each
> question maps to exactly one verb."*

---

## 13. Letting the model drive — the ReAct loop

The single-hop version pre-fetched rows in code and let the model pick a verb
once. Version 2 hands the loop to LangGraph:

```
START → llm ──tool_calls?──→ tools ──→ llm → … → END
```

- **`bind_tools`** attaches `sum_field_tool`, `max_field_tool` and
  `list_field_tool` to the model. With `@tool`, the docstring *is* the tool
  description the model reads and the type hints *are* the argument schema —
  no hand-written JSON schemas.
- **`ToolNode`** runs whichever tool the model named and appends the result as
  a `tool` message.
- **A conditional edge** (`should_continue`) loops `llm → tools → llm` until the
  model answers without asking for a tool. That loop is ReAct.
- **`MessagesState`** carries the `add_messages` reducer, so every node appends
  to the conversation instead of overwriting it.

Two things deliberately did **not** move to the model:

- **The field.** The model is good at the verb and bad at the exact corpus label —
  it passes `"value"` for a *portfolio value* question, which maps to the
  holdings' generic `Value` field. So the field comes from the question's keyword
  mapping first and the model's hint only as a fallback.
  **The model picks the verb; code picks the field.**
- **The month.** Scheme and month are still extracted deterministically from the
  question. A model never guesses a date range.

The tools also record every row they read, so the aggregate path still flows
through the same `verify` node. A `FileLogger` callback
(`scripts/trace_agent.py`) writes each model request, response, tool call and
tool result to `eval/agent_trace.log`, which is how you see the loop run.

### Measuring it per path

One MAP number over all twenty questions turned out to be misleading: aggregate
questions never retrieve anything, so ranking metrics on them are noise.
`scripts/score.py` routes every question exactly as the graph does and scores
each path on its own terms — **precision@k / recall@k / hit@k / MAP** for the
retrieve path, **exact-match accuracy** for the aggregate path. On the private
statements that gave **retrieve-path MAP 0.530** and **aggregate exact-match
11/13 (85%)**. Splitting the metric by path is also what surfaced the month
filter that silently did nothing (section 3): an aggregate answer that is
plausible but wrong only shows up when that path has its own scorecard.

---

## The 60-second version

> *"I built a retrieval system over financial statements, then hit the limit of pure retrieval — it can fetch a fact but can't combine several. So I added an aggregation path that filters the corpus by metadata and sums matching records exactly once, rather than relying on top-k similarity, which can silently omit a record and give you a wrong total with no error.*
>
> *Then I wrapped both paths in a LangGraph state machine with a conditional router: it inspects the question, and if it can't classify which field is being asked for, it can't compute — so it falls back to semantic retrieval instead of failing. That took the eval set from 7 of 20 questions returning nothing to all 20 returning either a computed answer or the relevant source chunks.*
>
> *On the retrieval path I then added a generation node — deliberately not on the aggregation path, since that already produces an exact number and a model could only make it worse. The prompt forces context-only answering, exact figures, a citation per figure, visible arithmetic operands, and a fixed refusal string so refusals are countable. After that a verify node extracts every figure from the answer and checks it against the retrieved context in code, not with a second model, with a separate bucket for values that are arithmetic on grounded ones. Currently 7 of 7 generated answers are fully grounded.*
>
> *The bug worth mentioning is a filter that silently did nothing — a `continue` inside an inner loop, so it never excluded anything and every total was summed across three months instead of one. No exception, plausible output. Only caught it because I had ground-truth numbers to compare against. The equivalent on the generation side was a model reporting '50 units plus 75 units, total 175' — invented figure, broken arithmetic, written in exactly the same confident tone as the correct answers.*
>
> *Finally I gave the aggregation path tool calling — the model reads the question and picks one of three verbs, sum, max or list, and deterministic code runs it over the rows, so the figures never touch the model. That fixed the two questions that needed a maximum or a list rather than a sum, and took the aggregation path from unverified to fully grounded. The tool-calling gotcha worth naming is parallel tool calls: the model can request several tools in one turn and the API rejects the turn unless every tool_call_id gets a reply."*
