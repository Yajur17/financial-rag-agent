"""
Retrieval-only baseline runner (the pre-LangGraph eval harness).

Embeds every question in eval/questions.md, ranks all chunks by cosine
similarity, and writes the top-k per question to eval/runs/<timestamp>.json
for Top-1 / Top-3 inspection. No generation, no routing.

Kept for history: this is the harness that measured the chunking fix
(Top-1 25% -> 35%, Top-3 ~40% -> 70%). It deliberately keeps its original
220-character text_preview -- the truncation that later turned out to make the
generator improvise (see docs/AGENT.md section 10). lang.py passes full rows.

Run: python3 scripts/fetch.py   (calls the OpenAI embeddings API)
"""

import json
import re
import os
import math
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


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

FALLBACK_QUESTIONS = [
  { "id": "F01", "section": "general", "question": "What is the total portfolio value in May 2025?", "groundTruth": "" },
  { "id": "F02", "section": "general", "question": "How many units of Aurora Small Cap Fund do I hold?", "groundTruth": "" },
  { "id": "F03", "section": "general", "question": "What transactions happened in July 2025?", "groundTruth": "" },
  { "id": "F04", "section": "general", "question": "What is the NAV of Aurora ELSS Tax Saver Fund?", "groundTruth": "" },
  { "id": "F05", "section": "general", "question": "What is the market value of Harbor Bank shares?", "groundTruth": "" },
]


def loadQuestionsFromMarkdown(filepath):
    if filepath == None:
        print('Questions file not found, using fallback:',filepath)
        return FALLBACK_QUESTIONS

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


def embedQuery(text):
    import requests

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

def run():
    if os.environ.get('OPENAI_API_KEY') is None:   # .get() not ['..'] — bracket raises KeyError if missing, defeating the check
        raise ValueError("OPENAI_API_KEY is missing (set it in .env or the shell)")

    print('Found OpenAI API key, Loading Embeddings')

    with open(EMBEDDINGS_FILE, encoding="utf-8") as f:
        corpus = json.load(f)
        print(len(corpus))

    questions = loadQuestionsFromMarkdown(QUESTIONS_FILE)

    if QUESTIONS_FILE and len(questions) == 0:
        raise ValueError('No questions parsed from ', QUESTIONS_FILE, '. Check markdown format.')

    if not QUESTIONS_FILE and len(questions) == 0:
        raise ValueError('No fallback questions available.')

    print('Questions loaded: ', len(questions), ' from ', QUESTIONS_FILE)

    runstamp = re.sub(r'[:.]', '-', datetime.now().isoformat())
    os.makedirs(RUNS_DIR, exist_ok=True)
    runOutputPath = os.path.join(RUNS_DIR, f"first_test_{runstamp}.json")
    runOutput = []

    for q in questions:
        print(f"{q['id']} {q['section']} {q['question']}")
        qVec = embedQuery(q["question"])
        scored_corpus = [{**c, 'score': cosine(qVec, c["embedding"])} for c in corpus]
        scored = sorted(scored_corpus, key=lambda x: x["score"], reverse=True)[:TOP_K]   # THE sort: by score, highest first, take 5

        topResults = []
        for i, r in enumerate(scored):
            print(f"{i+1}, [{r['score']:.3f}] {r['statement_month']} | {r['section_type']} | p{r['page_number']}")
            text_chunk = r["text"][0:150].replace("\n", " ")
            print(text_chunk)

            topResults.append({
                "rank": i + 1,
                "score": r["score"],
                "chunk_id": r["chunk_id"],
                "statement_month": r["statement_month"],
                "section_type": r["section_type"],
                "page_number": r["page_number"],
                "text_preview": r["text"][0:220].replace("\n", " ")})

        runOutput.append({          # once per question, not once per chunk
            "id": q["id"],
            "section": q["section"],
            "question": q["question"],
            "ground_truth": q["groundTruth"],
            "top_k": topResults})

    with open(runOutputPath, "w", encoding="utf-8") as f:   # write once, after all questions
        f.write(json.dumps(runOutput, indent=2))
    print(f"Run output saved: {runOutputPath}")


if __name__ == "__main__":
    run()
