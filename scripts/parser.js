/**
 * CDSL CAS PDF Parser (ES Module)
 *
 * Turns monthly CDSL Consolidated Account Statement PDFs (data_raw/*.pdf)
 * into page-level JSON with section labels, then writes a PII-redacted
 * copy (data_parsed/all_statements_clean.json) -- the file chunk.py reads.
 *
 * The public repo ships synthetic statements in that clean format instead of
 * real PDFs (scripts/make_synthetic.py), so you only need this to run the
 * pipeline on your own statements.
 *
 * Run:  node scripts/parser.js
 * Deps: npm install pdfjs-dist
 * Optional: REDACT_LOCALITIES="CITY,DISTRICT,STATE" to redact address
 *           lines that are only a locality name.
 */

import fs   from "fs";
import path from "path";
import { fileURLToPath } from "url";
import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// ─── Configuration ────────────────────────────────────────────────────────────
const DATA_RAW_DIR      = path.join(ROOT, "data_raw");
const DATA_PARSED_DIR   = path.join(ROOT, "data_parsed");
const OUTPUT_RAW_JSON   = path.join(DATA_PARSED_DIR, "all_statements_raw.json");
const OUTPUT_CLEAN_JSON = path.join(DATA_PARSED_DIR, "all_statements_clean.json");
const PER_STMT_DIR      = path.join(DATA_PARSED_DIR, "per_statement");
// ──────────────────────────────────────────────────────────────────────────────


// ─── Language filter ──────────────────────────────────────────────────────────

function stripHindi(text) {
  return text
    .replace(/[\u0900-\u097F]+/g, " ")
    .replace(/ {2,}/g, " ")
    .trim();
}


// ─── Section rules ────────────────────────────────────────────────────────────
// Used for BOTH primary classification and multi-label detection.
// Each pattern must be strong enough to fire only on its intended section type.
// "Account Details Account Details" removed — it appears in nav chrome on every page.

const SECTION_RULES = [
  {
    type: "holdings",
    patterns: [
      /HOLDING STATEMENT\s+AS ON/i,
      /Current\s+Bal\s+Frozen\s+Bal/i,
      /Market\s+Price\s*\/\s*Face\s+Value/i,
    ],
  },
  {
    type: "transactions",
    patterns: [
      /STATEMENT OF TRANSACTIONS\s+FOR THE PERIOD/i,
      /Op\.\s*Bal\s+Credit\s+Debit\s+Cl\.\s*Bal/i,
      /EP-DR\s+Txn:/i,
      /PAYOUT-CR\s+CM/i,
      /BSECH-CR\s+IN/i,
    ],
  },
  {
    type: "mf_units",
    patterns: [
      /MUTUAL FUND UNITS HELD\s+(WITH|AS ON)/i,
      /Closing\s+Bal\s*\(Units\)/i,
      /Unrealised\s+Profit[\s/]Loss/i,
      /Annualised\s+Return/i,
    ],
  },
  {
    type: "summary",
    // Only patterns that are unique to summary/account-detail pages and cannot
    // appear in nav chrome or financial data tables.
    patterns: [
      /Summary of Investments/i,
      /Consolidated Portfolio Valuation for Year/i,
      /YOUR CONSOLIDATED\s+PORTFOLIO VALUE/i,
      /Account Type\s+Account Details\s+No\. of ISINs/i,   // table header row, summary only
      /CDSL Demat Account\s+[A-Z]{3,}/,                     // followed by the DP name
      /CAS ID:/i,
      /DP Name\s*:\s*[A-Z]{3,}/,                           // p4 account detail block
      /BO Sub Status\s*:/i,
      /BO Status\s*:\s*INDIVIDUAL/i,
      /Scheme Code\s*:\s*[A-Z0-9]{3,6}\b/,
    ],
  },
];

// Notes override — checked against full text before any other rule.
// Signals that ONLY appear on Notes/About pages, never on financial data pages.
const NOTES_OVERRIDE_PATTERNS = [
  /NOTES TO CAS/i,
  /If you approach your DP\/MF for your statement/i,
  /Your depository,\s*CDSL,\s*was set up with the objective/i,
  /ISO22301:2012 certification for its Business Continuity/i,
  /Easi \(Electronic access to securities information\)/i,
  /E Locker Facility.*CDSL has introduced/i,
];

/**
 * Returns primary section_type for a page.
 * Pass 0: notes override on full text (prevents nav-strip false positives)
 * Pass 1: priority rules on first 35 lines
 * Pass 2: priority rules on full text
 */
function detectSectionType(fullText) {
  if (NOTES_OVERRIDE_PATTERNS.some((re) => re.test(fullText))) return "notes";

  const topLines = fullText.split("\n").slice(0, 35).join("\n");

  for (const rule of SECTION_RULES) {
    if (rule.patterns.some((re) => re.test(topLines))) return rule.type;
  }
  for (const rule of SECTION_RULES) {
    if (rule.patterns.some((re) => re.test(fullText))) return rule.type;
  }

  return "unknown";
}

/**
 * Returns ALL section types present anywhere on the page (for mixed-content pages).
 * E.g. a page with both STATEMENT OF TRANSACTIONS and HOLDING STATEMENT returns
 * ["transactions", "holdings"].
 * Notes pages always return ["notes"] only.
 */
function detectAllSectionTypes(fullText) {
  if (NOTES_OVERRIDE_PATTERNS.some((re) => re.test(fullText))) return ["notes"];

  const matched = [];
  for (const rule of SECTION_RULES) {
    if (rule.patterns.some((re) => re.test(fullText))) matched.push(rule.type);
  }
  return matched.length > 0 ? matched : ["unknown"];
}


// ─── Boilerplate line filter ──────────────────────────────────────────────────

const DROP_LINE_PATTERNS = [
  /^\s*Page\s+\d+\s+of\s+\d+\s*$/i,
  /^Central Depository Services \(India\) Limited\s*$/i,
  /^A Wing,?\s*25th Floor/i,
  /^Lower Parel/i,
  /^CONSOLIDATED ACCOUNT STATEMENT \(CAS\) FOR SECURITIES HELD/i,
  /^FORM AND INVESTMENTS IN MUTUAL FUNDS\s*$/i,
  /^Summary of\s*$/i,
  /^Investments\s+Account Details\s+CDSL Demat/i,
  /^CDSL DEMAT\s*$/i,
  /^MF Details\s+MF\s*$/i,
  /^Notes\s+CDSL\s*$/i,
  /^About CDSL\s*$/i,
  /^\s*[-–—|]{3,}\s*$/,
  /^\s*\*{3,}\s*$/,
  /^\s*$/,
];

function isDroppedLine(line) {
  return DROP_LINE_PATTERNS.some((re) => re.test(line));
}

function cleanLines(rawText) {
  return rawText
    .split("\n")
    .map(stripHindi)
    .filter((line) => line.length > 2 && !isDroppedLine(line))
    .join("\n");
}


// ─── PII redaction ────────────────────────────────────────────────────────────
// Rules:
//   - Holder name redacted ONLY in explicit personal-name contexts (not standalone tokens)
//   - Email rejoined across lines before matching
//   - Nominee, CAS ID, BO ID, DP/Client IDs, mobile, folio, address, PIN all redacted



const LOCALITY_RE = (process.env.REDACT_LOCALITIES || "")
  .split(",").map((s) => s.trim()).filter(Boolean)
  .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
  .join("|");

function redact(text) {
  let t = text;

  // Step 1: collapse line-broken email addresses before any other replacement
  //   "SOMEONE123@EXAMPLE.\nCOM" → "SOMEONE123@EXAMPLE.COM"
  t = t.replace(/([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+)\.\n([a-zA-Z]{2,})/g, "$1.$2");

  // PAN: 5 alpha + 4 digit + 1 alpha
  t = t.replace(/\b[A-Z]{5}[0-9]{4}[A-Z]\b/g, "[PAN]");

  // Email (catches the rejoined version above too)
  t = t.replace(/[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/gi, "[EMAIL]");

  // 16-digit BO ID
  t = t.replace(/\b\d{16}\b/g, "[BOID]");

  // DP ID and Client ID numbers
  t = t.replace(/(DP\s*I[Dd]\s*[:\s]+)\d+/gi,    "$1[DPID]");
  t = t.replace(/(CLIENT\s*I[Dd]\s*[:\s]+)\d+/gi, "$1[CLIENTID]");

  // Mobile: masked XXXXXX1234 form or raw 10-digit mobile
  t = t.replace(/\bXXXXXX\d{4}\b/g, "[MOBILE]");
  t = t.replace(/\b[6-9]\d{9}\b/g,  "[MOBILE]");

  // Folio numbers (10+ digit / digit pattern)
  t = t.replace(/\b\d{10,}\/\d\b/g, "[FOLIO]");

  // Address lines
  t = t.replace(/FLAT NO[^\n]*/gi,  "[ADDRESS]");
  t = t.replace(/PINCODE:\s*\d+/gi, "[PINCODE]");
  t = t.replace(/\b\d{6}\b/g,       "[PINCODE]");

  // CAS ID (e.g. "CAS ID: AB12345678")
  t = t.replace(/(CAS ID:\s*)[A-Z0-9]+/gi, "$1[CASID]");

  // Nominee name (follows "Nominee :" label)
  t = t.replace(/(Nominee\s*:\s*)[A-Z][a-zA-Z ]{2,30}/g, "$1[NOMINEE]");

  // Holder name — ONLY in known personal-name contexts, never standalone tokens.
  // Context 1: "In the single name of NAME ( PAN"
  t = t.replace(/(In the single name of\s+)[A-Z][A-Z ]{2,40}(\s*\(?\s*PAN)/g,  "$1[HOLDER-NAME]$2");
  // Context 2: standalone "NAME ( PAN :" line
  t = t.replace(/(^\s*)[A-Z][A-Z ]{2,40}(\s*\(\s*PAN\s*:)/gm,                "$1[HOLDER-NAME]$2");
  // Context 3: "Name/Joint Name(s)  NAME" table cell
  t = t.replace(/(Name\/Joint Name\s*\(s\)\s+)[A-Z][A-Z ]{2,40}/gi,           "$1[HOLDER-NAME]");
  // Context 4: name line directly before address block ("FIRSTNAME LASTNAME\nFLAT NO")
  t = t.replace(/^([A-Z][A-Z ]{2,40})(?=\n\[ADDRESS\])/gm,                    "[HOLDER-NAME]");

  // Locality-only address lines (city / district / state), from REDACT_LOCALITIES
  if (LOCALITY_RE) {
    t = t.replace(new RegExp(`^(${LOCALITY_RE})\\s*$`, "gim"), "[LOCATION]");
    // locality fragment lines left after address redaction
    t = t.replace(new RegExp(`^[A-Z ,]*(${LOCALITY_RE})[A-Z ,]*\\s*$`, "gim"), "[LOCATION]");
  }

  return t;
}


// ─── statement_month parser ───────────────────────────────────────────────────

function parseStatementMonth(filename) {
  const upper = filename.toUpperCase();
  const named = upper.match(/([A-Z]{3})(\d{4})/);
  if (named) return `${named[1]} ${named[2]}`;
  const numeric = upper.match(/(\d{4})[-_](\d{2})/);
  if (numeric) {
    const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
    const m = parseInt(numeric[2], 10);
    return `${months[m - 1] || numeric[2]} ${numeric[1]}`;
  }
  return "unknown";
}


// ─── Core page extractor ──────────────────────────────────────────────────────

async function extractPages(pdfPath) {
  const dataBuffer = new Uint8Array(fs.readFileSync(pdfPath));
  const pdf = await pdfjsLib.getDocument({ data: dataBuffer }).promise;

  const filename       = path.basename(pdfPath);
  const statementMonth = parseStatementMonth(filename);
  const pages          = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page    = await pdf.getPage(i);
    const content = await page.getTextContent();

    let lastY   = null;
    let rawText = "";
    for (const item of content.items) {
      const y = item.transform?.[5] ?? 0;
      if (lastY !== null && Math.abs(y - lastY) > 4) rawText += "\n";
      rawText += item.str + " ";
      lastY = y;
    }

    const cleanedText = cleanLines(rawText);
    if (!cleanedText || cleanedText.length < 30) continue;

    const sectionType  = detectSectionType(cleanedText);
    const sectionTypes = detectAllSectionTypes(cleanedText);

    pages.push({
      source_file:     filename,
      statement_month: statementMonth,
      page_number:     i,
      section_type:    sectionType,    // primary label (first strong signal, top-window)
      section_types:   sectionTypes,   // all matched labels (for mixed-content pages)
      text:            cleanedText,
    });
  }

  return pages;
}


// ─── QA guardrail ─────────────────────────────────────────────────────────────

function runQA(pages, filename) {
  const counts = {};
  for (const p of pages) counts[p.section_type] = (counts[p.section_type] || 0) + 1;

  const total      = pages.length;
  const unknown    = counts["unknown"] || 0;
  const unknownPct = total > 0 ? (unknown / total) * 100 : 0;

  const required = ["transactions", "holdings"];
  const missing  = required.filter((s) => !counts[s]);

  // Also check via section_types array (catches mixed pages)
  const allTypes = new Set(pages.flatMap((p) => p.section_types));
  const missingFromAny = required.filter((s) => !allTypes.has(s));

  console.log(`  Sections (primary): ${Object.entries(counts).map(([k,v]) => `${k}=${v}`).join(", ")}`);
  console.log(`  All types seen:     ${[...allTypes].join(", ")}`);

  let ok = true;
  if (missingFromAny.length > 0) {
    console.error(`  QA FAIL [${filename}]: sections missing even in section_types: ${missingFromAny.join(", ")}`);
    ok = false;
  }
  if (unknownPct > 10) {
    console.error(`  QA FAIL [${filename}]: unknown = ${unknown}/${total} (${unknownPct.toFixed(1)}%) exceeds 10%`);
    ok = false;
  }
  if (ok) console.log("  QA passed");
  return ok;
}


// ─── Batch runner ─────────────────────────────────────────────────────────────

async function run() {
  const pdfFiles = fs
    .readdirSync(DATA_RAW_DIR)
    .filter((f) => f.toLowerCase().endsWith(".pdf"))
    .map((f) => path.join(DATA_RAW_DIR, f));

  if (pdfFiles.length === 0) {
    console.error(`No PDFs found in ${DATA_RAW_DIR}`);
    process.exit(1);
  }

  console.log(`Found ${pdfFiles.length} PDF(s)...\n`);
  fs.mkdirSync(PER_STMT_DIR, { recursive: true });

  const RETRIEVAL_SECTIONS = new Set(["summary", "transactions", "holdings", "mf_units"]);
  let qaFailed = false;
  const allPagesRaw = [];

  for (const pdfPath of pdfFiles) {
    const filename = path.basename(pdfPath);
    console.log(`Processing: ${filename}`);

    try {
      const pages = await extractPages(pdfPath);
      console.log(`  → ${pages.length} pages extracted`);

      const qaOk = runQA(pages, filename);
      if (!qaOk) qaFailed = true;

      // Per-statement raw
      const perRaw = path.join(PER_STMT_DIR, filename.replace(".pdf", "_raw.json"));
      fs.writeFileSync(perRaw, JSON.stringify(pages, null, 2), "utf8");

      // Per-statement clean: drop notes/unknown, redact PII
      const cleanPages = pages
        .filter((p) => RETRIEVAL_SECTIONS.has(p.section_type))
        .map((p) => ({ ...p, text: redact(p.text) }));
      const perClean = path.join(PER_STMT_DIR, filename.replace(".pdf", "_clean.json"));
      fs.writeFileSync(perClean, JSON.stringify(cleanPages, null, 2), "utf8");

      console.log(`  → _raw.json (${pages.length}p)  _clean.json (${cleanPages.length}p)`);
      allPagesRaw.push(...pages);

    } catch (err) {
      console.error(`  ✗ Failed: ${err.message}`);
    }
  }

  // Write combined outputs (no append/dedupe — always fresh from this run)
  fs.writeFileSync(OUTPUT_RAW_JSON,   JSON.stringify(allPagesRaw, null, 2), "utf8");
  console.log(`\nRaw:   ${allPagesRaw.length} pages → all_statements_raw.json`);

  const allClean = allPagesRaw
    .filter((p) => RETRIEVAL_SECTIONS.has(p.section_type))
    .map((p) => ({ ...p, text: redact(p.text) }));
  fs.writeFileSync(OUTPUT_CLEAN_JSON, JSON.stringify(allClean, null, 2), "utf8");
  console.log(`Clean: ${allClean.length} pages (notes/unknown dropped, PII redacted) → all_statements_clean.json`);

  // Global section breakdown
  const breakdown = {};
  for (const p of allPagesRaw) breakdown[p.section_type] = (breakdown[p.section_type] || 0) + 1;
  console.log(`\nGlobal section breakdown:`);
  for (const [k, v] of Object.entries(breakdown)) console.log(`  ${k.padEnd(14)}: ${v}`);

  if (qaFailed) {
    console.error(`\nQA FAILED. Review section counts above.`);
    process.exit(1);
  } else {
    console.log(`\nAll QA checks passed.`);
  }
}

run().catch((err) => {
  console.error("Fatal error:", err.message);
  process.exit(1);
});