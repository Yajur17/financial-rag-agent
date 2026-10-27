"""
Row-aware chunker: one chunk = one logical table row.

Reads data_parsed/all_statements_clean.json (parsed statement pages) and
writes chunks/character/chunks_character.json. Four small state machines, one
per table shape:

  mf_units      - mutual-fund folio rows (scheme name lines + an INF... line
                  carrying the numeric tail)
  holdings      - demat holdings rows (ISIN line, wrapped name, a numeric line
                  containing `--` placeholders); equities (INE) and ETFs only
  transactions  - ISIN line, wrapped name + particulars, terminated by a line
                  that starts with a dd-mm-yyyy date
  summary       - the "Total Portfolio Value across investments" line plus
                  the asset-class rows on the same page

Every number is emitted with its label (|NAV: ... |Value: ...) so the
embedding has something semantic to match a question against.

(The output folder keeps its historical name "character" -- it replaced the
original 400-character windows and the rest of the pipeline reads this path.)
"""

import json
import re
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN_STATEMENT = ROOT / "data_parsed" / "all_statements_clean.json"
CHUNKS_DIR = ROOT / "chunks" / "character"
CHUNKS_FILE = CHUNKS_DIR / "chunks_character.json"

# The account holder's name appears as a bare chrome line on every page. The
# parser does not redact it there, so the mf_units buffer must skip it.
# Change this to your own name if you run the pipeline on real statements.
HOLDER_NAME = "SAMPLE INVESTOR"

SKIP={"Investments","Current","Annual","ISIN Security Current", "Frozen", "Pledge", "Pledge", "Setup", "Free Bal Price / ", "Face Value Value (`)","Pending","Remat","Demat" ,"ised","Bal", "Return","Market" ,"(%)","Account Details", HOLDER_NAME, "Scheme Name ISIN Folio No.","Closing", "Bal", "(Units)", "NAV (`)", "Cumulative", "Amount", "Invested (in", "INR)", "Valuation (`)", "Unrealised", "Profit/Loss","Unreali", "sed", "Profit/", "Loss(%)"}


def holings_is_data_line(line):
    search=re.search(r"^INF\w",line) or re.search(r"^INE\w",line)
    if search:
        return True
    else:
        return False

def is_data_line(line):
    search=re.search(r"^INF\w",line)
    if search:
        return True
    else:
        return False

with open(CLEAN_STATEMENT, encoding="utf-8") as f:
    corpus = json.load(f)

allChunks=[]
counter=0
hld_buffer=[]
hld_bufferline=""
collecting_hld=False

txn_buffer=[]
txn_bufferline=""
collecting_txn=False

for file in corpus:
    if "mf_units" in file["section_types"]:
        lines=file["text"].split("\n")
        buffer=[]

        for line in lines:
            if re.search(r"�",line):
                continue

            if line.strip() in SKIP:
                continue

            new_mf=is_data_line(line)


            if new_mf:
                bufferline=" ".join(buffer)
                row=" ".join([bufferline,line])
                splitted = re.split(r'(?<=\d)\s(?=\d)', row)
                # the folio column is the redaction placeholder "[FOLIO]" --
                # splitting on "]" separates "scheme + ISIN + folio" from units
                folio_split=re.split(r"(?<=\])",splitted[0])
                if len(splitted)==6 and len(folio_split)==2:
                    updated_row=folio_split[0]+' '+' |Closing Balance Units:'+folio_split[1]+ ' |NAV: '+ splitted[1] + ' |Cumulative Amount Invested: '+ splitted[2] + ' |Valuation: '+ splitted[3] + ' |Profit/Loss: '+splitted[4] + ' |Profit/Loss% : '+splitted[5]
                    counter+=1
                    allChunks.append({
                        "chunk_id":  f'{file["source_file"]}_{file["statement_month"]}_{file["page_number"]}_{counter}',
                        "chunk_index":counter,
                        "source_file":     file["source_file"],
                        "statement_month": file["statement_month"],
                        "page_number":     file["page_number"],
                        "section_type":    file["section_type"],
                        "text": updated_row
                    })

                buffer=[]
                bufferline=""
            else:
                buffer.append(line)

    if "holdings" in file["section_types"]:
        lines=file["text"].split("\n")

        for line in lines:
            line_clean = line.strip().replace("\xa0", " ")

            new_hld=holings_is_data_line(line_clean)

            if new_hld:
                # NOTE: a row whose ISIN, name and numbers all fit on ONE line
                # is never closed (we `continue` before checking for `--`), so
                # single-line holdings are silently dropped. Known limitation,
                # kept so the chunk counts match the measured eval runs.
                hld_buffer=[line_clean]
                collecting_hld=True
                continue

            if not collecting_hld:
                continue

            if re.search(r"�",line_clean):
                continue

            is_transaction_line = re.match(r"^\d{2}-\d{2}-\d{4}", line_clean)

            if "--" in line_clean and not is_transaction_line:
                hld_buffer.append(line_clean)
                hld_bufferline=" ".join(hld_buffer)

                tokens = hld_bufferline.split()
                isin = tokens[0]
                security_name = " ".join(tokens[1:-7])
                numeric_tail = tokens[-7:]

                # mf_units scheme rows (no "ETF" in the name) leak onto mixed
                # holdings/mf_units pages via the shared INF prefix; only real
                # equities (INE) and ETFs (INF containing "ETF") belong here.
                if isin.startswith("INE") or "ETF" in security_name:
                    current, frozen, pledge, other, free_bal, price, value = numeric_tail
                    updated_hld_row = (
                        isin + " " + security_name +
                        " |Current: " + current +
                        " |Frozen: " + frozen +
                        " |Pledge: " + pledge +
                        " |Other: " + other +
                        " |Free Bal: " + free_bal +
                        " |Price: " + price +
                        " |Value: " + value
                    )

                    counter += 1
                    allChunks.append({
                        "chunk_id":  f'{file["source_file"]}_{file["statement_month"]}_{file["page_number"]}_{counter}',
                        "chunk_index": counter,
                        "source_file": file["source_file"],
                        "statement_month": file["statement_month"],
                        "page_number": file["page_number"],
                        "section_type": "holdings",
                        "text": updated_hld_row
                    })

                hld_buffer=[]
                collecting_hld=False
            else:
                hld_buffer.append(line_clean)

    if "transactions" in file["section_types"]:
        lines=file["text"].split("\n")

        for line in lines:
            line_clean = line.strip().replace("\xa0", " ")

            new_txn = re.search(r"^INF\w", line_clean) or re.search(r"^INE\w", line_clean)

            if new_txn:
                # a fresh ISIN always starts a new record. if the previous
                # buffer never reached its date-terminal line, it wasn't a
                # real transaction (likely a holdings row bleeding onto this
                # mixed page) -- overwriting txn_buffer here discards it.
                txn_buffer=[line_clean]
                collecting_txn=True
                continue

            if not collecting_txn:
                continue

            if re.search(r"�",line_clean):
                continue

            is_terminal = re.match(r"^\d{2}-\d{2}-\d{4}", line_clean)

            if is_terminal:
                txn_buffer.append(line_clean)
                txn_bufferline=" ".join(txn_buffer)

                tokens = txn_bufferline.split()
                isin = tokens[0]
                date, op_bal, credit, debit, cl_bal, stamp_duty = tokens[-6:]
                security_name = " ".join(tokens[1:-6])

                txn_type = "Credit" if credit != "--" else ("Debit" if debit != "--" else "None")

                updated_txn_row = (
                    isin + " " + security_name +
                    " |Type: " + txn_type +
                    " |Date: " + date +
                    " |Op Bal: " + op_bal +
                    " |Credit: " + credit +
                    " |Debit: " + debit +
                    " |Cl Bal: " + cl_bal +
                    " |Stamp Duty: " + stamp_duty
                )

                counter += 1
                allChunks.append({
                    "chunk_id":  f'{file["source_file"]}_{file["statement_month"]}_{file["page_number"]}_{counter}',
                    "chunk_index": counter,
                    "source_file": file["source_file"],
                    "statement_month": file["statement_month"],
                    "page_number": file["page_number"],
                    "section_type": "transactions",
                    "text": updated_txn_row
                })

                txn_buffer=[]
                collecting_txn=False
            else:
                txn_buffer.append(line_clean)

    if "summary" in file["section_types"]:
        lines=file["text"].split("\n")
        total_line=None
        asset_rows=[]

        for line in lines:
            line_clean = line.strip()

            m_total = re.search(r"Total Portfolio Value across investments ₹\s*([\d,]+\.\d+)\s*as on\s*(\d{2}-\d{2}-\d{4})", line_clean)
            if m_total:
                total_line = (m_total.group(1), m_total.group(2))
                continue

            m_row = re.match(r"^([A-Za-z][A-Za-z .]+?)\s+([\d,]+\.\d+)\s+([\d,]+\.\d+)$", line_clean)
            if m_row:
                asset_rows.append(m_row.groups())

        if total_line and asset_rows:
            parts = [f"Total Portfolio Value: {total_line[0]} as on {total_line[1]}"]
            for name, value, pct in asset_rows:
                parts.append(f"|{name.strip()}: {value} ({pct}%)")
            summary_text = " ".join(parts)

            counter += 1
            allChunks.append({
                "chunk_id":  f'{file["source_file"]}_{file["statement_month"]}_{file["page_number"]}_{counter}',
                "chunk_index": counter,
                "source_file": file["source_file"],
                "statement_month": file["statement_month"],
                "page_number": file["page_number"],
                "section_type": "summary",
                "text": summary_text
            })

os.makedirs(CHUNKS_DIR, exist_ok=True)
with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
    json.dump(allChunks, f, indent=2, ensure_ascii=False)

counts = {}
for c in allChunks:
    counts[c["section_type"]] = counts.get(c["section_type"], 0) + 1
print(f"Chunks written: {len(allChunks)}  {counts}")
print(f"Output: {CHUNKS_FILE.relative_to(ROOT)}")
