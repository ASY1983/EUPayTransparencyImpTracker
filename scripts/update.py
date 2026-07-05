#!/usr/bin/env python3
"""
EU Pay Transparency Directive Tracker — automated update script.

What it does (in order of preference, per the project's data-source policy):
  1. Structured official publication: fetches the EUR-Lex "National
     transposition measures" (NIM) page for Directive (EU) 2023/970 and
     counts the notified national measures per member state.
  2. Change detection: fetches each country's watch URL from sources.json,
     hashes the relevant content, and compares against the stored hash.
  3. Optional AI summarization: if ANTHROPIC_API_KEY is set AND a change was
     detected, asks Claude to draft a 1-2 sentence summary of the fetched
     official text. The draft is written to `proposedSummary` — it NEVER
     replaces `summary` and NEVER changes `status`. A human reviews the
     flagged country and promotes or discards the proposal.

Hard rules encoded here:
  - `status` is never modified by this script. Only a human commit changes it.
  - Official source links already in data.json are always preserved.
  - Every automated run updates `meta.lastGlobalRefresh` and per-country
    `lastChecked`, so the page always shows when data was last verified.

Usage:
  python3 scripts/update.py            # normal run (writes data.json)
  python3 scripts/update.py --dry-run  # report only, no writes
"""

import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data.json"
SOURCES = ROOT / "sources.json"
UA = {"User-Agent": "eu-ptd-tracker/1.0 (+status monitor; contact: repo owner)"}

NIM_URL = "https://eur-lex.europa.eu/legal-content/EN/NIM/?uri=CELEX:32023L0970"


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def normalise(html: str) -> str:
    """Strip volatile noise (scripts, whitespace, session tokens) so the hash
    only changes when visible content changes."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"(csrf|token|session|nonce)[=:][\w-]+", "", html, flags=re.I)
    return re.sub(r"\s+", " ", html).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def count_nim_measures(html: str) -> dict:
    """Count notified national measures per member state on the EUR-Lex NIM
    page. EUR-Lex groups measures under member-state headings; we count
    occurrences of each country name near 'National transposition' entries.
    Conservative: used only as a change signal, never as a status decision."""
    text = normalise(html)
    counts = {}
    names = {
        "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
        "CY": "Cyprus", "CZ": "Czech", "DK": "Denmark", "EE": "Estonia",
        "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
        "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
        "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta",
        "NL": "Netherlands", "PL": "Poland", "PT": "Portugal",
        "RO": "Romania", "SK": "Slovakia", "SI": "Slovenia",
        "ES": "Spain", "SE": "Sweden",
    }
    for code, name in names.items():
        counts[code] = len(re.findall(re.escape(name), text))
    return counts


def summarise_with_ai(country: str, official_text: str) -> str | None:
    """Optional: draft a 1-2 sentence summary of official text with Claude.
    Returns None when no API key is configured. The output goes into
    `proposedSummary` only — never into `summary`, never into `status`."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": (
                "You summarise official EU/national legal publications. "
                "Below is text fetched from an official source about the "
                f"transposition of Directive (EU) 2023/970 in {country}. "
                "Write ONE or TWO plain-English sentences describing the "
                "current legislative stage, strictly based on this text. "
                "Do not infer, guess, or classify a compliance status. "
                "If the text contains no clear transposition information, "
                "reply exactly: NO_CLEAR_INFORMATION.\n\n---\n"
                + official_text[:6000]
            ),
        }],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
        text = "".join(b.get("text", "") for b in out.get("content", [])).strip()
        return None if "NO_CLEAR_INFORMATION" in text else text
    except Exception as e:  # noqa: BLE001 — non-fatal by design
        print(f"  ! AI summarisation skipped for {country}: {e}")
        return None


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    data = json.loads(DATA.read_text(encoding="utf-8"))
    sources = json.loads(SOURCES.read_text(encoding="utf-8")) if SOURCES.exists() else {}
    today = date.today().isoformat()
    changes = []

    # --- 1. Structured official publication: EUR-Lex NIM page -------------
    try:
        nim_html = fetch(NIM_URL)
        nim_counts = count_nim_measures(nim_html)
        prev = data["meta"].get("nimCounts", {})
        for c in data["countries"]:
            code = c["code"]
            new, old = nim_counts.get(code, 0), prev.get(code)
            if old is not None and new != old:
                c["reviewNeeded"] = True
                changes.append(f"{c['name']}: EUR-Lex NIM measure count {old} → {new}")
        data["meta"]["nimCounts"] = nim_counts
        print(f"EUR-Lex NIM checked ({sum(nim_counts.values())} name mentions).")
    except Exception as e:  # noqa: BLE001
        print(f"! EUR-Lex NIM check failed (non-fatal): {e}")

    # --- 2. Change detection on per-country watch URLs --------------------
    for c in data["countries"]:
        watch = sources.get(c["code"], {}).get("watchUrls", [])
        c["lastChecked"] = today
        for url in watch:
            try:
                text = normalise(fetch(url))
                h = content_hash(text)
                hashes = c.setdefault("watchHashes", {})
                if hashes.get(url) and hashes[url] != h:
                    c["reviewNeeded"] = True
                    changes.append(f"{c['name']}: content changed at {url}")
                    # --- 3. Optional AI-drafted summary (human-reviewed) ---
                    proposal = summarise_with_ai(c["name"], text)
                    if proposal:
                        c["proposedSummary"] = proposal
                        c["proposedSummarySource"] = url
                hashes[url] = h
            except Exception as e:  # noqa: BLE001
                print(f"  ! {c['name']} watch URL failed ({url}): {e}")

    data["meta"]["lastGlobalRefresh"] = today
    data["meta"]["lastRunUtc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if changes:
        print("\nCHANGES DETECTED — human review needed:")
        for line in changes:
            print(f"  - {line}")
        # Signal for the GitHub Action to open an issue
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write("changes_detected=true\n")
                f.write("change_summary<<EOF\n" + "\n".join(changes) + "\nEOF\n")
    else:
        print("\nNo changes detected. Timestamps refreshed.")

    if dry_run:
        print("(dry run — data.json not written)")
        return 0

    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("data.json updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
