from typing_extensions import TypedDict
from langgraph.graph import START, END, StateGraph, MessagesState
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, convert_to_openai_messages
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
import os
import sys
import json
import math
import re
from pathlib import Path
from dotenv import load_dotenv

import requests

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


SYSTEM_PROMPT = """You answer questions about a user's personal financial \
statements using ONLY the context provided in the user message.

RULES
1. Use only the numbered context blocks. Never use outside knowledge about \
markets, funds, or companies, and never infer a figure that is not written \
in the context.
2. Quote every figure exactly as it appears, including commas and decimal \
places. Do not round, reformat, or convert.
3. Cite the chunk_id in square brackets immediately after each figure you \
report, e.g. "12,345.67 [JUL2025_..._6_12]".
4. If you perform arithmetic, show the operands and the result, and cite the \
chunk_id for each operand.
5. If the context does not contain what is needed, reply exactly:
   "Not answerable from the retrieved context."
   Then state in one sentence what information was missing. Never guess, and \
never fill a gap with a plausible value.
6. If the context contains conflicting values for the same thing, report both \
with their chunk_ids instead of choosing one.

Be brief. Answer the question asked and nothing more."""


def cosine(a, b):
   dot = 0
   magA = 0
   magB = 0

   lena=len(a)

   for i in range (lena):
    dot  += a[i] * b[i]
    magA += a[i] * a[i]
    magB += b[i] * b[i]

   return dot / (math.sqrt(magA) * math.sqrt(magB))


EMBEDDINGS_FILE = ROOT / "embeddings" / "character" / "embeddings_character.json"
QUESTIONS_FILE  = ROOT / "eval" / "questions.md"
RUNS_DIR        = ROOT / "eval" / "runs"
MODEL           = "text-embedding-3-small"
TOP_K           = 5

# question keyword -> the exact field label used inside the chunks.
# Dict order = check order: the first keyword found in the question wins.
mapping ={
    # mf_units fields
    'invested':"Cumulative Amount Invested",
    'put':"Cumulative Amount Invested",
    'profit/loss':"Profit/Loss",
    'profit': "Profit/Loss",
    'loss' :"Profit/Loss",
    'nav' : "NAV",
    # the summary chunk's own label is this exact longer phrase — checked
    # BEFORE bare 'value' below, or "total portfolio value" would resolve
    # to the generic "Value" field and match every holdings row too
    'portfolio value': "Total Portfolio Value",
    # holdings fields — checked before the bare 'value'/'balance' below,
    # since dict order = check order and the more specific phrase should win
    'market value': "Value",
    'current market': "Value",
    'free bal': "Free Bal",
    'value': "Value",
    # transactions fields
    'credit':"Credit",
    'debit':"Debit",
    'closing balance':"Cl Bal",
    'balance':"Cl Bal",
}

# scheme/security name is a SECOND, separate filter from the field mapping
# above — "how much did I invest" (field) and "in Aurora ELSS" (scheme) are
# two independent questions the aggregation has to answer, not one. This
# covers mf_units schemes AND holdings/transactions securities.
# Keys are matched as substrings of the lower-cased question; values as
# case-insensitive substrings of the chunk text.
SCHEME_KEYWORDS = {
    'aurora elss': 'ELSS', 'elss': 'ELSS', 'tax saver': 'ELSS',
    'aurora small cap': 'Small Cap', 'small cap': 'Small Cap',
    'harbor bank': 'HARBOR BANK', 'harbor': 'HARBOR BANK',
    'granite bank': 'GRANITE BANK', 'granite': 'GRANITE BANK',
    'bluefin gold': 'BLUEFIN GOLD ETF',
    'bluefin silver': 'BLUEFIN SILVER ETF',
    'meridian gold': 'MERIDIAN GOLD ETF',
    'meridian silver': 'MERIDIAN SILVER ETF',
    'meridian flexi': 'MERIDIAN FLEXI CAP',
    'arcadia': 'ARCADIA',
    'kestrel': 'KESTREL',
    'lotus foods': 'LOTUS FOODS', 'lotus': 'LOTUS FOODS',
    'brightline': 'BRIGHTLINE',
    'ionic power': 'IONIC POWER',
}


def loadQuestionsFromMarkdown(filepath):
    if filepath == None:
        raise ValueError ('Questions file not found, using fallback:',filepath)

    file=open(filepath, encoding="utf-8")
    text=file.read()
    lines=re.split(r"\r?\n", text)

    questions=[]
    currentSection = "general"
    pending=None

    for rawLine in lines:
        line=rawLine.strip()
        sectionMatch = re.search(r"^\*\*\s*Section:\s*([^*]+)\*\*$", line)

        if sectionMatch:
           currentSection = re.sub(r"\(\d+\)", "", sectionMatch.group(1)).strip().lower()
           continue

        qMatch=re.search(r"^\*\*\s*(Q\d+)\s*\*\*\s*[—-]\s+(.+)$",line)
        if qMatch:
            pending = {"id":qMatch[1],"section":currentSection,"question":qMatch[2].strip(),"groundTruth":None}
            questions.append(pending)
            continue
        if pending and line.lower().startswith("ground truth:"):
            pending["groundTruth"]=re.sub(r"^Ground truth:\s*","",line,flags=re.I).strip()
            continue
        if not line  and pending:
            pending=None
    questionreturn=questions
    return questionreturn


# statement_month values only ever look like this in this corpus — hardcoding
# their chronological order lets us pick "the latest one" without needing a
# real date parser for a 3-month dataset.
MONTH_ORDER = ["MAY 2025", "JUN 2025", "JUL 2025"]
MONTH_KEYWORDS = {
    'may': "MAY 2025",
    'jun': "JUN 2025", 'june': "JUN 2025",
    'jul': "JUL 2025", 'july': "JUL 2025",
}


def get_scheme(question):
    q = question.lower()
    schemes=[]
    for keyword, scheme in SCHEME_KEYWORDS.items():
        if keyword in q and scheme not in schemes:
            schemes.append(scheme)
    return schemes if schemes else None   # no scheme named in the question -> don't filter by scheme


def get_month(question):
    q = question.lower()
    months=[]
    for keyword, month in MONTH_KEYWORDS.items():
        if keyword in q:
            months.append(month)
    return months if months else [MONTH_ORDER[-1]]   # no month named -> assume "current" = latest available


def embedQuery(text):

    url="https://api.openai.com/v1/embeddings"

    apiKey=os.environ['OPENAI_API_KEY']
    token='Bearer '+ apiKey

    header = {
         "Content-Type":  "application/json",
         "Authorization": token
    }

    body= {
        "model":MODEL,
        "input": text,
        "encoding_format": "float"
    }

    response = requests.post(url, headers=header,json=body)
    jsonResponse=response.json()
    return(jsonResponse["data"][0]["embedding"])


if not EMBEDDINGS_FILE.exists():
    sys.exit(f"Embeddings not found at {EMBEDDINGS_FILE.relative_to(ROOT)} — "
             "run `python3 scripts/embed.py` first (see README quickstart).")

with open(EMBEDDINGS_FILE, encoding="utf-8") as f:
        corpus = json.load(f)

def retrieve(question):
    if question:
         qVec = embedQuery(question)
         scored_corpus = [{**c, 'score': cosine(qVec, c["embedding"])} for c in corpus]
         scored = sorted(scored_corpus, key=lambda x: x["score"], reverse=True)[:TOP_K]

         topResults = []
         for i, r in enumerate(scored):
            print(f"{i+1}, [{r['score']:.3f}] {r['statement_month']} | {r['section_type']} | p{r['page_number']}")

            topResults.append({
                "rank": i + 1,
                "score": r["score"],
                "chunk_id": r["chunk_id"],
                "statement_month": r["statement_month"],
                "section_type": r["section_type"],
                "page_number": r["page_number"],
                # the FULL row. An earlier version truncated this to 220
                # characters and the model started inventing the missing half.
                "text_preview": r["text"].replace("\n", " ")})

         runOutput = [{"question": question, "top_k": topResults}]   # built ONCE, after the loop, from the finished list
         return runOutput

    else:
        raise ValueError("No Question were provided")


def get_field(line):
   for field, value in mapping.items():
    if field in line.lower():
        return value

   return None   # only after checking every field, not just the first one


class AgentState(TypedDict):
    question:str
    answer: object
    context:  list
    grounding: dict

def aggregate_node(state):
    # The aggregate path runs the LangGraph ReAct agent (run_agent ->
    # react_agent). It returns (answer, rows), so verify_node can still ground
    # the figures against the rows the tools actually read.
    answer, rows = run_agent(state["question"])
    context = [{"text_preview": r["text"]} for r in rows]
    return {"answer": answer, "context": context}

def generate_node(state):
    q       = state["question"]        # state KEY, from AgentState
    context = state["context"]         # state KEY, from AgentState
    apiResponse = generate(q, context)
    return {"answer": apiResponse}     # dict of updates, not a bare value

def retrieve_node(state):
    q      = state["question"]
    result = retrieve(q)
    retreiveChunks = result[0]["top_k"]
    return {"context": retreiveChunks}   # writes the key generate_node reads


# ---------------------------------------------------------------- grounding
# The prompt ASKS the model not to invent figures. This VERIFIES it did not.
# Deliberately plain code and not a second LLM call: a second model can agree
# with the first one's invention, and "does this number appear in the source?"
# is a string comparison, not a judgement call.

NUMBER   = re.compile(r"\d[\d,]*\.?\d*")
CITATION = re.compile(r"\[[^\]]*\]")


def extract_numbers(text):
    """Every numeric token in text, as (raw_string, float) pairs.

    Citations are stripped FIRST. A chunk_id like
    [JUL2025_DEMO0001_TXN.pdf_JUL 2025_6_13] is full of digits that are not
    figures, and counting them would flood the ungrounded list with noise.
    """
    cleaned = CITATION.sub(" ", text)
    found = []
    for m in NUMBER.finditer(cleaned):
        raw = m.group(0).rstrip(".")
        # a bare 4-digit year (e.g. "July 2025") is a date, not a figure. Money
        # in this corpus always carries a comma or decimal (3,38,508.33), so a
        # plain 19xx/20xx token is safe to skip and stops false "ungrounded" flags.
        if re.fullmatch(r"(?:19|20)\d{2}", raw):
            continue
        try:
            found.append((raw, float(raw.replace(",", ""))))
        except ValueError:
            continue
    return found


def context_values(chunks):
    """Every number present in the retrieved chunks, as a set of floats.

    Compares VALUES, not strings, so 3,38,508.33 and 338508.33 are the same
    thing. Prompt rule 2 asks the model to preserve formatting; the checker
    shouldn't depend on it having obeyed.
    """
    values = set()
    for c in chunks:
        for _, v in extract_numbers(c["text_preview"]):
            values.add(round(v, 4))
    return values


def is_derived(value, grounded_values, tol=0.01):
    """Is this the result of arithmetic on figures that ARE grounded?

    A growth question's correct answer is a subtraction of two portfolio
    totals — right, and nowhere in the source. Without this check the best
    answer in the eval set gets flagged as a hallucination.
    """
    vs = list(grounded_values)
    for i, a in enumerate(vs):
        for b in vs[i:]:
            if abs(value - (a + b)) < tol or abs(value - abs(a - b)) < tol:
                return True
    return abs(value - sum(vs)) < tol      # running total, e.g. Q15


def check_grounding(answer, chunks):
    ctx   = context_values(chunks)
    found = extract_numbers(answer)

    grounded, unmatched = [], []
    for raw, val in found:
        (grounded if round(val, 4) in ctx else unmatched).append((raw, val))

    # DEDUPE before the arithmetic check. Prompt rule 4 makes the model print
    # its operands twice — once listing them, once in the sum — so a naive
    # list doubles every value and sum() comes out at 2x the real total.
    grounded_values = sorted({round(v, 4) for _, v in grounded})

    derived, ungrounded = [], []
    for raw, val in unmatched:
        (derived if is_derived(val, grounded_values) else ungrounded).append(raw)

    checked = len(found)
    return {
        "figures":     checked,
        "grounded":    [r for r, _ in grounded],
        "derived":     derived,
        "ungrounded":  ungrounded,
        "is_grounded": not ungrounded,
        # what fraction of figures we can account for — the reportable metric
        "rate": (len(grounded) + len(derived)) / checked if checked else 1.0,
    }


def verify_node(state):
    answer = state["answer"]

    # defensive: a non-string answer has no figures to check
    if not isinstance(answer, str):
        return {"grounding": {"figures": 0, "grounded": [], "derived": [],
                              "ungrounded": [], "is_grounded": True,
                              "rate": 1.0}}

    report = check_grounding(answer, state["context"])
    flag   = "OK" if report["is_grounded"] else "UNGROUNDED"
    print(f"[grounding {flag}] {len(report['grounded'])} grounded, "
          f"{len(report['derived'])} derived, "
          f"{len(report['ungrounded'])} ungrounded"
          + (f" -> {report['ungrounded']}" if report["ungrounded"] else ""))

    # annotate, never block: a flagged answer still reaches the caller, marked.
    return {"grounding": report}


def route_question(state):
    if get_field(state["question"]) is None:
        return "retrieve"         # a node NAME, as a string
    return "aggregate"


def generate(question,context):
    url='https://api.openai.com/v1/chat/completions'

    apiKey=os.environ['OPENAI_API_KEY']
    token='Bearer '+ apiKey

    header = {
            "Content-Type":  "application/json",
            "Authorization": token
    }

    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},   # the rules
            {"role": "user", "content": f"Question: {question}\n\nContext:\n\n{format_context(context)}"}
        ],
        "temperature": 0,
    }

    response = requests.post(url, headers=header, json=body)
    jsonresponse=response.json()
    return jsonresponse["choices"][0]["message"]["content"]


def format_context(chunks):
    blocks = []
    for c in chunks:
        blocks.append(
            f"[{c['chunk_id']}]\n"
            f"month: {c['statement_month']} | section: {c['section_type']} | page: {c['page_number']}\n"
            f"{c['text_preview']}"
        )
    return "\n\n---\n\n".join(blocks)


# ================================================================ tool calling
# The aggregate path used to know ONE verb: sum. That's why "which holding is
# highest?" returned a total, and "which securities were debited?" returned a
# number. Here it gets three verbs and the MODEL picks which one the question
# wants. The figures themselves never touch the model: it only chooses the
# verb, the deterministic code reads the numbers. Grounded by construction.

def name_of(text):
    """A row's name = everything before the first '|', minus the leading ISIN
    token (e.g. 'INE123A01011 KESTREL ENGINEERING ...' -> 'KESTREL ENGINEERING ...')."""
    head = text.split("|")[0]
    head = re.sub(r"^\s*[A-Z0-9]{12}\s+", "", head)   # strip the 12-char ISIN
    return head.strip()


def fetch_rows(field, scheme, month):
    """The 'one fetch' all three verbs read from. Every row matching the
    month (+scheme) that carries `field`, as {name, value, chunk_id, text}.
    Doesn't sum, doesn't pick — just collects the rows.

    This replaced an earlier function that filtered AND summed in one loop —
    which is exactly why it could only ever add."""
    rows = []
    for c in corpus:
        if c["statement_month"] not in month:
            continue
        if scheme is not None and not any(s.lower() in c["text"].lower() for s in scheme):
            continue
        # anchor the field to a row boundary (start, or after a '|') so a
        # field name can't match as a SUBSTRING of a longer one — e.g. 'Value'
        # must not hit 'Total Portfolio Value:' in the summary chunk.
        m = re.search(rf"(?:^|\|)\s*{re.escape(field)}:\s*([\d,]+\.?\d*)", c["text"])
        if not m:
            continue
        rows.append({
            "name":     name_of(c["text"]),
            "value":    float(m.group(1).replace(",", "")),
            "chunk_id": c["chunk_id"],
            "text":     c["text"],
        })
    return rows


# --- the three verbs: same rows in, different shape out ----------------------
def sum_field(rows):
    return round(sum(r["value"] for r in rows), 2)

def max_field(rows):
    if not rows:
        return None
    top = max(rows, key=lambda r: r["value"])
    return {"name": top["name"], "value": top["value"]}

def list_field(rows):
    return [{"name": r["name"], "value": r["value"]} for r in rows]


# ================================================================ ReAct agent
# bind_tools tells the model the tools exist, ToolNode runs whichever it picks,
# and a conditional edge loops llm <-> tools until the model stops calling a
# tool and just answers. That llm->tool->llm loop IS ReAct.
# (v1 was a hand-rolled single round over raw chat/completions: pick a verb ->
# run it -> phrase the answer. This replaced it with the framework version.)

# The model picks the VERB and a rough field word; scheme/month we still derive
# deterministically from the question (we never let the model guess a month).
# _CTX carries the question into the tools and collects the rows they read, so
# verify_node can still ground the figures afterwards.
_CTX = {"question": None, "rows": []}

def _rows_for(field_hint):
    q     = _CTX["question"]
    # field comes from the QUESTION first (reliable keyword->label mapping), the
    # model's hint only as fallback. The model is good at picking the VERB, not
    # at naming the exact corpus label — e.g. it passes "value" for a "portfolio
    # value" question, which wrongly maps to holdings' generic "Value" field.
    field = get_field(q) or get_field(field_hint)
    rows  = fetch_rows(field, get_scheme(q), get_month(q))
    _CTX["rows"].extend(rows)                        # remember for grounding
    return rows

def _payload(rows, result):
    # the result PLUS the per-row operands, so a derived total can be grounded
    # against its source rows (not flagged as a bare, unsourced number).
    return json.dumps({"result": result,
                       "source_rows": [{"name": r["name"], "value": r["value"]} for r in rows]})

# With bind_tools, the DOCSTRING becomes the tool description the model reads and
# the type hints become the arg schema.
@tool
def sum_field_tool(field: str) -> str:
    """Add a numeric field across every matching row. Use for 'how much total',
    'combined', 'across all folios/months'. field e.g. invested, value, debit."""
    rows = _rows_for(field)
    return _payload(rows, sum_field(rows))

@tool
def max_field_tool(field: str) -> str:
    """Return the single highest row by value (name + value). Use for 'which is
    highest/largest/most'. field e.g. value, nav, profit."""
    rows = _rows_for(field)
    return _payload(rows, max_field(rows))

@tool
def list_field_tool(field: str) -> str:
    """Return ALL matching rows by name. Use for 'which securities', 'list all',
    'what was debited/credited'. field e.g. debit, credit, value."""
    rows = _rows_for(field)
    return _payload(rows, list_field(rows))

AGENT_TOOLS = [sum_field_tool, max_field_tool, list_field_tool]

AGENT_SYS = ("You answer questions about the user's financial statements by calling "
             "ONE of the provided tools, then summarising its result. Pick the tool "
             "that matches the question: a total -> sum_field_tool, the highest one -> "
             "max_field_tool, a list of which ones -> list_field_tool. After the tool "
             "returns, answer in one or two short sentences, quoting every figure "
             "exactly. When the result is a total, also state the per-row figures from "
             "source_rows. Never invent a number that isn't in the tool result.")

# the model, with the three tools attached. bind_tools = "here are your tools";
# it does NOT run them, it just lets the model emit a tool_call.
llm            = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_with_tools = llm.bind_tools(AGENT_TOOLS)

def llm_node(state):
    # one model turn: returns either tool_calls OR a final answer.
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

def should_continue(state):
    # the conditional loop edge, written explicitly: did the model ask for a tool?
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END   # tool_calls -> run them; else stop

# MessagesState = a prebuilt State whose `messages` key already carries the
# add_messages reducer — so every node APPENDS to history instead of
# overwriting, which is what keeps the llm<->tool conversation intact.
react = StateGraph(MessagesState)
react.add_node("llm", llm_node)
react.add_node("tools", ToolNode(AGENT_TOOLS))   # runs whichever tool the model named
react.add_edge(START, "llm")
react.add_conditional_edges("llm", should_continue, {"tools": "tools", END: END})
react.add_edge("tools", "llm")                   # <-- the loop back: tool result -> model again
react_agent = react.compile()

# The entire block above is what create_agent(llm, AGENT_TOOLS) builds in ONE line.
# It is wired by hand so every piece is explainable. The shortcut:
#     from langchain.agents import create_agent
#     react_agent = create_agent(llm, AGENT_TOOLS, prompt=AGENT_SYS)

# ---- tracing: one callback that logs every API call + tool run to a file ----
# A callback handler receives events as the graph runs. We only need four:
#   on_chat_model_start -> the REQUEST  (model, messages, tools, tool_choice)
#   on_llm_end          -> the RESPONSE (content, tool_calls, token usage)
#   on_tool_start/end   -> the tool run (name, args, result)
# They fire in execution order, so the file reads top-to-bottom as the loop ran.
# This is what a hosted tracer (e.g. LangSmith) does, written to a local file.
class FileLogger(BaseCallbackHandler):
    def __init__(self, path):
        self.path = path
        self.step = 0
        open(self.path, "w").close()        # start each run with a fresh file

    def _write(self, entry):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, indent=2, default=str) + "\n\n")

    def on_chat_model_start(self, serialized, messages, **kwargs):
        # reconstruct the EXACT request body sent over the wire: messages in
        # OpenAI format + the full tools array (name/description/parameters that
        # bind_tools generated) + tool_choice + model params.
        self.step += 1
        p = kwargs.get("invocation_params", {})
        request = {
            "model":       p.get("model"),
            "temperature": p.get("temperature"),
            "tool_choice": p.get("tool_choice"),
            "tools":       p.get("tools"),                        # full tool schemas
            "messages":    convert_to_openai_messages(messages[0]),
        }
        self._write({"step": self.step, "event": "1_MODEL_REQUEST", "request": request})

    def on_llm_end(self, response, **kwargs):
        # the raw response: content, the raw OpenAI-format tool_calls, and the
        # full response_metadata (finish_reason, model_name, token_usage, ...).
        msg = response.generations[0][0].message
        self._write({
            "step": self.step, "event": "2_MODEL_RESPONSE",
            "response": {
                "content":           msg.content,
                "tool_calls":        msg.additional_kwargs.get("tool_calls"),
                "finish_reason":     msg.response_metadata.get("finish_reason"),
                "response_metadata": msg.response_metadata,
                "usage_metadata":    getattr(msg, "usage_metadata", None),
            },
        })

    def on_tool_start(self, serialized, input_str, **kwargs):
        self._write({"step": self.step, "event": "3_TOOL_START",
                     "tool": serialized.get("name"), "args": input_str})

    def on_tool_end(self, output, **kwargs):
        self._write({"step": self.step, "event": "4_TOOL_RESULT",
                     "output": str(output)})


def run_agent(question, log_path=None):
    """Drive the ReAct agent for one question -> (answer_str, rows_used).
    Pass log_path to dump every API call + tool run to that file (via the
    FileLogger callback)."""
    _CTX["question"] = question
    _CTX["rows"]     = []
    config = {"callbacks": [FileLogger(log_path)]} if log_path else {}
    result = react_agent.invoke(
        {"messages": [SystemMessage(AGENT_SYS), HumanMessage(question)]},
        config=config,
    )
    return result["messages"][-1].content, list(_CTX["rows"])


builder = StateGraph(AgentState)
builder.add_node("aggregate", aggregate_node)
builder.add_node("retrieve", retrieve_node)
builder.add_node("generate", generate_node)
builder.add_node("verify", verify_node)

builder.add_conditional_edges(START, route_question)
builder.add_edge("aggregate", "verify")
builder.add_edge("retrieve", "generate")
builder.add_edge("generate", "verify")
builder.add_edge("verify", END)

app = builder.compile()


def ask(question):
    """One question through the full graph; prints the answer + grounding."""
    out = app.invoke({"question": question})
    print(out["answer"])
    return out


def run():
     questions = loadQuestionsFromMarkdown(QUESTIONS_FILE)

     generated = 0          # answers that went through the model
     clean     = 0          # ...of those, ones with no ungrounded figure
     flagged   = []

     for q in questions:
        print(f"\n{q['id']}: {q['question']}")
        try:
           out = app.invoke({"question": q['question']})
           print(out["answer"])

           g = out.get("grounding")
           if g and g["figures"]:
              generated += 1
              if g["is_grounded"]:
                 clean += 1
              else:
                 flagged.append((q['id'], g["ungrounded"]))
        except ValueError as e:
           print(f"SKIPPED — {e}")

     # the reportable number: not "I told it not to hallucinate" but
     # "I verified every figure and here is the rate"
     print("\n" + "=" * 46)
     if generated:
        print(f"Grounding: {clean}/{generated} generated answers fully grounded "
              f"({100 * clean / generated:.0f}%)")
     for qid, nums in flagged:
        print(f"  {qid} ungrounded: {nums}")


if __name__ == "__main__":
    # python3 scripts/lang.py                 -> all Q01-Q20 + grounding summary
    # python3 scripts/lang.py "some question" -> just that one question
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
    else:
        run()
