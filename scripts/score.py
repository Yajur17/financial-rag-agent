"""
Route-aware evaluation over eval/questions.md (Q01-Q20).

Each question is routed exactly as the graph would route it:
  retrieve path  -> ranking metrics: hit@1, hit@3, precision@k, recall@k, AP -> MAP
  aggregate path -> exact-match accuracy of the ReAct agent's answer

Calls the OpenAI API (one embedding per retrieve question, 2+ chat calls per
aggregate question). Run: python3 scripts/score.py
"""
import re
from lang import (retrieve, corpus, loadQuestionsFromMarkdown, QUESTIONS_FILE,
                  TOP_K, route_question, run_agent)


def evidence_tokens(ground_truth):          # pulls `backticked` markers out of the GT line
    return re.findall(r"`([^`]+)`", ground_truth or "")


def is_relevant(chunk_text, tokens):
    """Relevant = chunk text contains ANY evidence token (case-insensitive)."""
    low = chunk_text.lower()
    return any(t.lower() in low for t in tokens)


def relevant_total(tokens):
    """R = how many chunks in the WHOLE corpus are relevant. (corpus key = 'text')"""
    return sum(1 for c in corpus if is_relevant(c["text"], tokens))


# --- RETRIEVE path: ranking metrics (retrieved chunk key = 'text_preview') ---
def precision_at_k(retrieved, tokens, k):
    rel = sum(1 for c in retrieved[:k] if is_relevant(c["text_preview"], tokens))
    return rel / k


def recall_at_k(retrieved, tokens, k, R):
    if R == 0:
        return 0.0
    rel = sum(1 for c in retrieved[:k] if is_relevant(c["text_preview"], tokens))
    return rel / R


def hit_at_k(retrieved, tokens, k):
    return any(is_relevant(c["text_preview"], tokens) for c in retrieved[:k])


def average_precision(retrieved, tokens, R):
    hits = 0
    precisions = []
    for i, chunk in enumerate(retrieved):          # i is 0-based -> rank = i+1
        if is_relevant(chunk["text_preview"], tokens):
            hits += 1
            precisions.append(hits / (i + 1))
    return sum(precisions) / R if R else 0.0


# --- AGGREGATE path: exact-match accuracy -----------------------------------
# Simple + approximate (like Option A): a question is CORRECT if every NAME token
# appears in the answer AND at least one NUMBER token appears. Names are
# AND-required identifiers ("HARBOR BANK"); figures usually come in OR-groups
# ("any of 8,982 or 11,723"), so one hit is enough.
def _name_in(token, answer):
    """A name token matches if each of its words is the PREFIX of some answer word.
    So GT 'JUL 2025' matches an answer that says 'July 2025' (jul -> july)."""
    awords = re.findall(r"[a-z0-9]+", answer.lower())
    twords = re.findall(r"[a-z0-9]+", token.lower())
    return all(any(aw.startswith(tw) for aw in awords) for tw in twords)


def answer_correct(answer, tokens):
    names = [t for t in tokens if re.search(r"[a-z]", t.lower())]
    nums  = [t for t in tokens if t not in names]
    names_ok = all(_name_in(n, answer) for n in names)
    nums_ok  = (not nums) or any(n.replace(",", "") in answer.replace(",", "") for n in nums)
    return names_ok and nums_ok


def score():
    questions = loadQuestionsFromMarkdown(QUESTIONS_FILE)
    k = TOP_K

    retr = [q for q in questions if route_question({"question": q["question"]}) == "retrieve"]
    aggr = [q for q in questions if q not in retr]

    # ---------- RETRIEVE path ----------
    print(f"\n=== RETRIEVE path ({len(retr)} questions) — ranking metrics ===")
    print(f"{'Q':<5}{'R':>3}{'hit@1':>7}{'hit@3':>7}{'P@'+str(k):>7}{'R@'+str(k):>7}{'AP':>7}")
    aps = []
    for q in retr:
        tokens    = evidence_tokens(q["groundTruth"])
        retrieved = retrieve(q["question"])[0]["top_k"]
        R         = relevant_total(tokens)
        ap        = average_precision(retrieved, tokens, R)
        aps.append(ap)
        print(f"{q['id']:<5}{R:>3}"
              f"{('Y' if hit_at_k(retrieved, tokens, 1) else '.'): >7}"
              f"{('Y' if hit_at_k(retrieved, tokens, 3) else '.'): >7}"
              f"{precision_at_k(retrieved, tokens, k):>7.2f}"
              f"{recall_at_k(retrieved, tokens, k, R):>7.2f}"
              f"{ap:>7.2f}")
    print(f"MAP: {sum(aps) / len(aps):.3f}" if aps else "MAP: n/a")

    # ---------- AGGREGATE path ----------
    print(f"\n=== AGGREGATE path ({len(aggr)} questions) — exact-match accuracy ===")
    correct = 0
    for q in aggr:
        tokens      = evidence_tokens(q["groundTruth"])
        answer, _   = run_agent(q["question"])   # v2: LangGraph ReAct agent
        ok          = answer_correct(answer, tokens)
        correct    += ok
        print(f"{q['id']:<5}{'Y' if ok else '.'}   {answer[:75]}")
    if aggr:
        print(f"Accuracy: {correct}/{len(aggr)} = {100 * correct / len(aggr):.0f}%")


if __name__ == "__main__":
    score()
