"""registry_sync.py -- Auto-trader -> Biotech Landscape registry write-back (the superset bridge).

Concordance rule (Elisa 2026-07-12): the Biotech & Tech-Bio Companies registry must be a SUPERSET
of every biotech the trader tracks. Whenever a public biotech is added to WATCHLIST_BIOTECH (or
WATCHLIST_MANUAL_ONLY), it must exist as a registry row so the two projects never diverge. The
trader only INVESTS in a filtered subset of the registry, but the registry must contain them all.

Dedup: matches an existing non-archived row by PUBLIC TICKER first (immune to name-normalization
drift), then falls back to the token-based normalized-name key shared with the Gemini gatekeeper.
Red-flag scoring stays governed by ~/Dropbox/claude/biotech-landscape/RED-FLAGS.md (shared list); a
flagged name caps at 20.

Usage:
  python registry_sync.py --backfill-basket            # upsert the WATCHLIST_BIOTECH basket
  python registry_sync.py --backfill-basket --dry-run  # preview, no writes
  python registry_sync.py --check-superset             # assert every watchlist biotech is a registry row (fail loud)
  python registry_sync.py --company "X" --ticker X --stage Public --inv-score 70 --category "Emerging biotech"
"""
import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DB_ID = "96f3780d-10cb-4d77-8d6f-c85fa8c9b4b3"          # REST database_id (NOT the data_source_id)
PROJECT_ID = "358f3cdd-67a4-81dd-ad08-f834fe3ab5a8"     # Master Project "Biotech Landscape"

_STOP = {"inc", "ltd", "llc", "co", "corp", "therapeutics",
         "bio", "biosciences", "sciences"}


def normalize(name):
    """Dedup key identical to the Gemini gatekeeper: lowercase, strip punctuation + corp suffixes."""
    n = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return " ".join(t for t in n.split() if t and t not in _STOP).strip()


def ticker_of(props):
    raw = "".join(t.get("plain_text", "") for t in props.get("Public ticker / CIK", {}).get("rich_text", []))
    m = re.match(r"^([A-Z]{1,6})\b", raw.strip())
    return m.group(1) if m else None


def _token():
    env = Path(__file__).with_name(".env")
    for line in env.read_text().splitlines():
        if line.startswith("NOTION_TOKEN"):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("FATAL: NOTION_TOKEN not found in .env")


def _api(url, headers, method="GET", body=None):
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body else None, headers=headers)
    try:
        return json.load(urllib.request.urlopen(req)), None
    except urllib.error.HTTPError as e:
        return None, f"{e.code} - {e.read().decode()[:300]}"


def _all_rows(headers):
    rows, cur = [], None
    while True:
        body = {"page_size": 100}
        if cur:
            body["start_cursor"] = cur
        d, err = _api(f"https://api.notion.com/v1/databases/{DB_ID}/query", headers, "POST", body)
        if err:
            raise SystemExit(f"FATAL: registry query failed ({err})")
        rows += d["results"]
        if not d.get("has_more"):
            return rows
        cur = d["next_cursor"]


def _find_existing(headers, company, ticker):
    """Match a non-archived row by ticker first (drift-proof), then by normalized name."""
    target = normalize(company)
    tkr = (ticker or "").upper().strip() or None
    for r in _all_rows(headers):
        p = r["properties"]
        arch = p.get("Archive Status", {}).get("select")
        if arch and arch["name"] == "Archived":
            continue
        if tkr and ticker_of(p) == tkr:
            return r["id"], p
        nm = "".join(t.get("plain_text", "") for t in p.get("Company", {}).get("title", []))
        if nm and normalize(nm) == target:
            return r["id"], p
    return None


def upsert(headers, c, dry_run=False):
    """Create or merge one company row. c is a dict; see BASKET for the field set."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    match = _find_existing(headers, c["company"], c.get("ticker"))

    # Factual + time fields (refreshed on both create and merge -- fresher data wins).
    props = {
        "Stage": {"select": {"name": c.get("stage", "Public")}},
        "Public ticker / CIK": {"rich_text": [{"text": {"content": c["ticker"]}}]},
        "Neuro flag": {"checkbox": c.get("neuro", False)},
        "Last reviewed": {"date": {"start": today}},
        "Last checked": {"date": {"start": today}},
    }
    if c.get("inv_score") is not None:
        props["Investment Score"] = {"number": c["inv_score"]}
    if c.get("modality"):
        props["Modality"] = {"select": {"name": c["modality"]}}
    if c.get("indication"):
        props["Indication"] = {"multi_select": [{"name": x.strip()} for x in c["indication"].split(",")]}
    if c.get("next_catalyst"):
        props["Next catalyst"] = {"date": {"start": c["next_catalyst"]}}
    if c.get("catalyst_event"):
        props["Catalyst event"] = {"rich_text": [{"text": {"content": c["catalyst_event"]}}]}
    if c.get("lead_asset"):
        props["Lead Asset"] = {"rich_text": [{"text": {"content": c["lead_asset"]}}]}
    if c.get("thesis"):
        props["Investment angle"] = {"checkbox": True}
        props["Investment thesis"] = {"rich_text": [{"text": {"content": c["thesis"][:1990]}}]}
    if c.get("risk_flags"):
        props["Risk flags"] = {"rich_text": [{"text": {"content": c["risk_flags"]}}]}

    cats = [x.strip() for x in c["category"].split(",")]

    if match:
        page_id, existing = match
        # Anti-clobber: UNION multi-selects with what is already there (Category, Contributor).
        ex_cat = [x["name"] for x in existing.get("Category", {}).get("multi_select", [])]
        props["Category"] = {"multi_select": [{"name": x} for x in dict.fromkeys(ex_cat + cats)]}
        ex_contrib = [x["name"] for x in existing.get("Contributor", {}).get("multi_select", [])]
        props["Contributor"] = {"multi_select": [{"name": x} for x in dict.fromkeys(ex_contrib + ["auto-trader"])]}
        if dry_run:
            return f"[dry-run] MERGE {c['company']} ({c['ticker']}) -> existing row {page_id}"
        _, err = _api(f"https://api.notion.com/v1/pages/{page_id}", headers, "PATCH", {"properties": props})
        return f"MERGED {c['company']} ({c['ticker']})" if not err else f"ERROR {c['company']}: {err}"

    props["Category"] = {"multi_select": [{"name": x} for x in cats]}
    props.update({
        "Company": {"title": [{"text": {"content": c["company"]}}]},
        "Contributor": {"multi_select": [{"name": "auto-trader"}]},
        "Archive Status": {"select": {"name": "Active"}},
        "Outcome": {"select": {"name": "Too early"}},
        "Linked Project": {"relation": [{"id": PROJECT_ID}]},
    })
    if dry_run:
        return f"[dry-run] CREATE {c['company']} ({c['ticker']}) inv={c.get('inv_score')}"
    _, err = _api("https://api.notion.com/v1/pages", headers, "POST",
                  {"parent": {"database_id": DB_ID}, "properties": props})
    return f"CREATED {c['company']} ({c['ticker']})" if not err else f"ERROR {c['company']}: {err}"


# Tickers parked in WATCHLIST_MANUAL_ONLY that are NOT biotech (so the biotech-superset rule
# does not apply to them). PLTR = Palantir (enterprise AI, parked for valuation-overlay reasons).
NON_BIOTECH = {"PLTR"}


def check_superset(headers):
    """Fail loud if any biotech ticker the trader tracks is missing from the registry."""
    sys.path.insert(0, str(Path(__file__).parent))  # import watchlist regardless of cwd
    import watchlist
    tracked = sorted((set(watchlist.WATCHLIST_BIOTECH) | set(watchlist.WATCHLIST_MANUAL_ONLY)) - NON_BIOTECH)
    reg = {ticker_of(r["properties"]) for r in _all_rows(headers)}
    reg.discard(None)
    missing = [t for t in tracked if t not in reg]
    if missing:
        print(f"SUPERSET VIOLATION: {len(missing)} tracked biotech ticker(s) NOT in the registry: {missing}")
        print("Fix: run registry_sync.py --company/--ticker for each, or --backfill-basket.")
        sys.exit(1)
    print(f"SUPERSET OK: all {len(tracked)} tracked biotech tickers are registry rows.")


# Current WATCHLIST_BIOTECH basket (built 2026-07-12, catalyst dates PDUFA-verified per Session 19
# / Recommendation Gate). Investment Scores are PROVISIONAL Claude estimates via the registry
# 6-component rubric (catalyst 0-30 / clinical 0-20 / financial 0-20 / stage 0-10 / moat 0-10 /
# neuro 0-10), NOT independently sourced numbers -- each thesis stores the component breakdown so a
# future /portfolio-review can audit it. None carry a RED-FLAGS.md trigger, so none are capped.
BASKET = [
    {"company": "Cogent Biosciences", "ticker": "COGT", "stage": "Public", "modality": "Small molecule",
     "indication": "GIST, Systemic mastocytosis", "lead_asset": "bezuclastinib (KIT inhibitor)",
     "category": "Emerging biotech", "inv_score": 74, "neuro": False,
     "next_catalyst": "2026-11-30", "catalyst_event": "GIST PDUFA Nov 30 2026 + mastocytosis PDUFA Dec 30 2026 (dual approval)",
     "thesis": "PROVISIONAL score (Claude rubric estimate, not independently sourced): catalyst 28 / clinical 16 / financial 12 / stage 10 / moat 8 / neuro 0 = 74. Two near-term PDUFAs on bezuclastinib; approval-risk (positive pivotal in hand). Auto-trader half-size.",
     "risk_flags": "Binary PDUFA catalyst -- half-size only."},
    {"company": "Protagonist Therapeutics", "ticker": "PTGX", "stage": "Public", "modality": "Protein",
     "indication": "Polycythemia vera", "lead_asset": "rusfertide (hepcidin mimetic peptide)",
     "category": "Emerging biotech", "inv_score": 72, "neuro": False,
     "next_catalyst": "2026-09-30", "catalyst_event": "rusfertide PDUFA Q3 2026 (polycythemia vera); Takeda partnership",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 26 / clinical 15 / financial 14 / stage 10 / moat 7 / neuro 0 = 72. Rusfertide PDUFA Q3 2026; Takeda strategic partnership de-risks financing. Half-size.",
     "risk_flags": "Binary PDUFA catalyst -- half-size only."},
    {"company": "BridgeBio Pharma", "ticker": "BBIO", "stage": "Public", "modality": "Small molecule",
     "indication": "LGMD2I", "lead_asset": "BBP-418 (ribitol)",
     "category": "Emerging biotech", "inv_score": 73, "neuro": False,
     "next_catalyst": "2026-11-27", "catalyst_event": "BBP-418 PDUFA Nov 27 2026 (LGMD2I)",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 25 / clinical 16 / financial 15 / stage 10 / moat 7 / neuro 0 = 73. BBP-418 PDUFA Nov 2026; revenue-backed by acoramidis (Attruby) commercial ramp. Half-size.",
     "risk_flags": "Binary PDUFA catalyst -- half-size only."},
    {"company": "Scholar Rock Holding", "ticker": "SRRK", "stage": "Public", "modality": "mAb",
     "indication": "Spinal muscular atrophy", "lead_asset": "apitegromab (anti-myostatin mAb)",
     "category": "Emerging biotech", "inv_score": 83, "neuro": True,
     "next_catalyst": "2026-09-30", "catalyst_event": "apitegromab PDUFA Sep 30 2026 (SMA)",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 26 / clinical 16 / financial 13 / stage 10 / moat 8 / neuro 10 = 83. First myostatin inhibitor for SMA, positive TOPAZ Ph3. NEURO by disease-area (SMA = motor-neuron disease); note apitegromab acts PERIPHERALLY on muscle myostatin, does not cross the BBB -- borderline vs a CNS-targeted therapy. Half-size.",
     "risk_flags": "Binary PDUFA catalyst -- half-size only. Neuro flag is disease-area, not central mechanism."},
    {"company": "Ultragenyx Pharmaceutical", "ticker": "RARE", "stage": "Public", "modality": "Gene therapy",
     "indication": "Sanfilippo syndrome (MPS IIIA)", "lead_asset": "UX111 (AAV gene therapy)",
     "category": "Emerging biotech", "inv_score": 80, "neuro": True,
     "next_catalyst": "2026-09-19", "catalyst_event": "UX111 PDUFA Sep 19 2026 (Sanfilippo gene therapy)",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 25 / clinical 15 / financial 12 / stage 10 / moat 8 / neuro 10 = 80. UX111 CNS-targeted AAV gene therapy for neurodegenerative Sanfilippo (true CNS neuro). Multi-asset company. Half-size.",
     "risk_flags": "Binary PDUFA catalyst -- half-size only."},
    {"company": "Vaxcyte", "ticker": "PCVX", "stage": "Public", "modality": "Protein",
     "indication": "Pneumococcal disease", "lead_asset": "VAX-31 (31-valent conjugate vaccine)",
     "category": "Emerging biotech", "inv_score": 70, "neuro": False,
     "next_catalyst": "2026-12-15", "catalyst_event": "VAX-31 topline Q4 2026 (immunobridging endpoint)",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 22 / clinical 14 / financial 16 / stage 10 / moat 8 / neuro 0 = 70. VAX-31 broad pneumococcal vaccine, strong balance sheet. Data readout (not PDUFA) -- higher variance. Half-size.",
     "risk_flags": "Data readout, not approval -- higher variance; half-size only."},
    {"company": "Cullinan Therapeutics", "ticker": "CGEM", "stage": "Public", "modality": "Small molecule",
     "indication": "EGFR exon20 NSCLC", "lead_asset": "zipalertinib",
     "category": "Emerging biotech", "inv_score": 66, "neuro": False,
     "next_catalyst": "2027-02-27", "catalyst_event": "zipalertinib PDUFA Feb 27 2027 (EGFR ex20 NSCLC)",
     "thesis": "PROVISIONAL score (Claude rubric estimate): catalyst 20 / clinical 15 / financial 14 / stage 10 / moat 7 / neuro 0 = 66. Zipalertinib PDUFA Feb 2027 (~7mo out), Taiho partnership. Half-size.",
     "risk_flags": "Binary PDUFA catalyst (further out) -- half-size only."},
]


# WATCHLIST_MANUAL_ONLY biotech names (tracked but never auto-traded -- pure data-readout, red-flag,
# or out-of-window). Part of the superset. Scores are PROVISIONAL rubric estimates with breakdowns;
# CAPR is RED-FLAG capped at 20 (post-CRL resubmission = unresolved CRL per RED-FLAGS.md). LRMR is
# already a registry row (capped 20), so it is not repeated here. PLTR is excluded (not biotech).
BASKET_MANUAL = [
    {"company": "Celldex Therapeutics", "ticker": "CLDX", "stage": "Public", "modality": "mAb",
     "indication": "Chronic spontaneous urticaria", "lead_asset": "barzolvolimab (anti-KIT mAb)",
     "category": "Emerging biotech", "inv_score": 60, "neuro": False,
     "next_catalyst": "2026-12-15", "catalyst_event": "barzolvolimab Phase 3 CSU readout Q4 2026",
     "thesis": "PROVISIONAL (Claude rubric): catalyst 24 / clinical 12 / financial 12 / stage 10 / moat 6 / neuro 0 = 60. MANUAL-ONLY: pure Phase 3 data-readout (not approval), high gap variance.",
     "risk_flags": "MANUAL-ONLY: binary data-readout, high variance. Not auto-traded."},
    {"company": "Summit Therapeutics", "ticker": "SMMT", "stage": "Public", "modality": "mAb",
     "indication": "NSCLC", "lead_asset": "ivonescimab (PD-1/VEGF bispecific)",
     "category": "Emerging biotech", "inv_score": 50, "neuro": False,
     "thesis": "PROVISIONAL (Claude rubric): catalyst 16 / clinical 12 / financial 10 / stage 10 / moat 2 / neuro 0 = 50. MANUAL-ONLY: mixed OS / squamous data + funding overhang.",
     "risk_flags": "MANUAL-ONLY: mixed pivotal data + funding overhang. Not auto-traded."},
    {"company": "Savara", "ticker": "SVRA", "stage": "Public", "modality": "Protein",
     "indication": "Autoimmune pulmonary alveolar proteinosis", "lead_asset": "molgramostim (inhaled GM-CSF)",
     "category": "Emerging biotech", "inv_score": 55, "neuro": False,
     "thesis": "PROVISIONAL (Claude rubric): catalyst 22 / clinical 13 / financial 8 / stage 10 / moat 2 / neuro 0 = 55. MANUAL-ONLY: single-product aPAP PDUFA, high single-name variance.",
     "risk_flags": "MANUAL-ONLY: single-product concentration risk. Not auto-traded."},
    {"company": "Capricor Therapeutics", "ticker": "CAPR", "stage": "Public", "modality": "Cell therapy",
     "indication": "Duchenne muscular dystrophy cardiomyopathy", "lead_asset": "deramiocel (CAP-1002)",
     "category": "Emerging biotech", "inv_score": 20, "neuro": False,
     "thesis": "PROVISIONAL, RED-FLAG CAPPED at 20 per RED-FLAGS.md: prior FDA CRL on deramiocel (post-CRL resubmission = unresolved). MANUAL-ONLY / auto-fail.",
     "risk_flags": "RED-FLAG: prior CRL (unresolved, resubmission pending). Auto-fail. Not auto-traded."},
    {"company": "Viking Therapeutics", "ticker": "VKTX", "stage": "Public", "modality": "Small molecule",
     "indication": "Obesity", "lead_asset": "VK2735 (dual GLP-1/GIP)",
     "category": "Emerging biotech", "inv_score": 50, "neuro": False,
     "next_catalyst": "2027-06-30", "catalyst_event": "VK2735 obesity Phase 3 readout 2027 (out of near-term window)",
     "thesis": "PROVISIONAL (Claude rubric): catalyst 14 / clinical 14 / financial 14 / stage 10 / moat 6 / neuro 0 = 58, docked to 50 for a make-or-break single catalyst not until 2027 (out of window). MANUAL-ONLY.",
     "risk_flags": "MANUAL-ONLY: pivotal catalyst 2027, out of near-term window. Not auto-traded."},
    {"company": "CRISPR Therapeutics", "ticker": "CRSP", "stage": "Public", "modality": "Gene therapy",
     "indication": "Sickle cell / beta-thalassemia, oncology", "lead_asset": "Casgevy (exa-cel)",
     "category": "Emerging biotech", "inv_score": 58, "neuro": False,
     "thesis": "PROVISIONAL (Claude rubric): catalyst 14 / clinical 16 / financial 14 / stage 10 / moat 4 / neuro 0 = 58. MANUAL-ONLY: small-cap gene-therapy, binary commercial ramp / pipeline.",
     "risk_flags": "MANUAL-ONLY: binary gene-therapy commercialization. Not auto-traded."},
    {"company": "Schrodinger", "ticker": "SDGR", "stage": "Public", "modality": "Other",
     "indication": "Computational drug discovery platform + proprietary pipeline", "lead_asset": "SGR-1505 (MALT1), platform",
     "category": "AI drug discovery", "inv_score": 55, "neuro": False,
     "thesis": "PROVISIONAL (Claude rubric): catalyst 12 / clinical 12 / financial 15 / stage 10 / moat 6 / neuro 0 = 55. MANUAL-ONLY: AI-drug-discovery small-cap, software + early pipeline.",
     "risk_flags": "MANUAL-ONLY: platform + early pipeline, revenue lumpy. Not auto-traded."},
]


def main():
    ap = argparse.ArgumentParser(description="Auto-trader -> Biotech registry write-back")
    ap.add_argument("--backfill-basket", action="store_true", help="Upsert the WATCHLIST_BIOTECH basket")
    ap.add_argument("--backfill-manual", action="store_true", help="Upsert the WATCHLIST_MANUAL_ONLY biotech names")
    ap.add_argument("--check-superset", action="store_true", help="Assert every tracked biotech is a registry row")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--company"); ap.add_argument("--ticker"); ap.add_argument("--stage", default="Public")
    ap.add_argument("--inv-score", type=int); ap.add_argument("--category", default="Emerging biotech")
    ap.add_argument("--modality"); ap.add_argument("--indication"); ap.add_argument("--lead-asset")
    ap.add_argument("--next-catalyst"); ap.add_argument("--catalyst-event"); ap.add_argument("--thesis")
    ap.add_argument("--risk-flags"); ap.add_argument("--neuro", action="store_true")
    args = ap.parse_args()

    headers = {"Authorization": f"Bearer {_token()}",
               "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

    if args.check_superset:
        check_superset(headers)
        return
    if args.backfill_basket:
        for c in BASKET:
            print(upsert(headers, c, dry_run=args.dry_run))
        return
    if args.backfill_manual:
        for c in BASKET_MANUAL:
            print(upsert(headers, c, dry_run=args.dry_run))
        return
    if args.company and args.ticker:
        c = {"company": args.company, "ticker": args.ticker, "stage": args.stage,
             "inv_score": args.inv_score, "category": args.category, "modality": args.modality,
             "indication": args.indication, "lead_asset": args.lead_asset,
             "next_catalyst": args.next_catalyst, "catalyst_event": args.catalyst_event,
             "thesis": args.thesis, "risk_flags": args.risk_flags, "neuro": args.neuro}
        print(upsert(headers, c, dry_run=args.dry_run))
        return
    ap.error("Pass --backfill-basket, --check-superset, or --company + --ticker")


if __name__ == "__main__":
    main()
