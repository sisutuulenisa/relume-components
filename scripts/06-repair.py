#!/usr/bin/env python3
"""
06-repair.py — Repareert lege component HTML files door Figma node data opnieuw op te halen.

Aanpak:
1. Scan alle component HTML files op lege inhoud
2. Groepeer lege componenten en haal node data op via Figma API (met throttling)
3. Her-render naar HTML
4. Update source_node_id in index.json (voor Figma PNG export)

Runs zijn hervatbaar via repair-state.json.
"""

import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
INDEX_FILE = ROOT_DIR / "index.json"
STATE_FILE = ROOT_DIR / "repair-state.json"

FIGMA_TOKEN = os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN", "")
FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
API_BASE = "https://api.figma.com/v1"

BATCH_SIZE = 10          # Smaller batches to avoid 429
THROTTLE = 2.0           # Seconds between successful API calls
RETRY_WAIT = 15.0        # Seconds to wait on 429
MAX_RETRIES = 4          # Max retries per batch

EMPTY_MARKER = '<section class="w-full mx-auto max-w-[1440px]"></section>'


# ── Load extract module ───────────────────────────────────────────────────────
def load_extract_module():
    spec = importlib.util.spec_from_file_location("extract", SCRIPT_DIR / "03-extract.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"repaired": [], "failed": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Figma API with retry ──────────────────────────────────────────────────────
def api_fetch_nodes(component_ids: list[str]) -> dict:
    """Fetch node documents for given IDs. Returns {id: document_dict}."""
    query = urlencode({"ids": ",".join(component_ids)})
    url = f"{API_BASE}/files/{FILE_KEY}/nodes?{query}"

    for attempt in range(MAX_RETRIES):
        req = Request(url, headers={"X-Figma-Token": FIGMA_TOKEN, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read())
                nodes = data.get("nodes", {})
                result = {}
                for cid in component_ids:
                    doc = (nodes.get(cid) or {}).get("document")
                    if doc:
                        result[cid] = doc
                return result
        except HTTPError as e:
            if e.code == 429:
                wait = RETRY_WAIT * (2 ** attempt)
                print(f"    429 rate limit — waiting {wait:.0f}s (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                print(f"    HTTP {e.code} — {e.reason}")
                return {}
        except (URLError, OSError) as e:
            print(f"    Network error: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(THROTTLE)
            return {}

    print("    ⚠️  Max retries exceeded, skipping batch")
    return {}


# ── Find empty components ─────────────────────────────────────────────────────
def find_empty_components(components: list[dict]) -> list[dict]:
    empty = []
    for c in components:
        p = ROOT_DIR / c["path"]
        if not p.exists():
            empty.append(c)
            continue
        content = p.read_text(encoding="utf-8")
        if EMPTY_MARKER in content or len(content) < 600:
            empty.append(c)
    return empty


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("🔧 Relume Component Repair Script")
    print(f"   Figma file: {FILE_KEY}")
    print(f"   Throttle: {THROTTLE}s between batches, {RETRY_WAIT}s on 429\n")

    # Load extract module (for render_node, get_desktop_child, build_html_document, etc.)
    extract = load_extract_module()

    # Load index
    with open(INDEX_FILE) as f:
        index_data = json.load(f)
    components = index_data["components"]

    # Find empty components
    empty = find_empty_components(components)
    print(f"📋 Found {len(empty)} empty/broken components (of {len(components)} total)")

    if not empty:
        print("✅ Nothing to repair!")
        return 0

    # Load repair state (for resuming)
    state = load_state()
    repaired_set = set(state["repaired"])
    failed_set = set(state["failed"])

    # Filter: skip already repaired or permanently failed
    to_repair = [c for c in empty if c["id"] not in repaired_set and c["id"] not in failed_set]
    print(f"   Already repaired: {len(repaired_set)}, failed: {len(failed_set)}, remaining: {len(to_repair)}\n")

    if not to_repair:
        print("✅ All components already processed.")
        # Still regenerate index if needed
    else:
        # Batch fetch and re-render
        total = len(to_repair)
        batches = [to_repair[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

        print(f"🔄 Processing {total} components in {len(batches)} batches of {BATCH_SIZE}...")

        for batch_idx, batch in enumerate(batches):
            batch_ids = [c["id"] for c in batch]
            print(f"\n  Batch {batch_idx+1}/{len(batches)}: {batch_ids[0]}..{batch_ids[-1]}")

            # Fetch from Figma
            nodes = api_fetch_nodes(batch_ids)
            print(f"    Fetched: {len(nodes)}/{len(batch)} nodes")

            # Render each component
            for comp in batch:
                comp_id = comp["id"]
                node = nodes.get(comp_id, {})

                # Determine effective node (desktop child)
                figma_export_id = comp_id
                if node.get("type") == "COMPONENT_SET":
                    desktop_child = extract.get_desktop_child(node)
                    if desktop_child and desktop_child.get("id"):
                        figma_export_id = desktop_child["id"]

                # Render
                category_name = comp.get("category", "uncategorized")
                markup = extract.render_node(node, category=category_name, is_root=True, indent=4)

                if not markup or markup.strip() == "":
                    markup = (
                        "    <section class=\"w-full mx-auto max-w-[1440px] p-[24px]\">"
                        "<p class=\"text-[16px] text-gray-700\">Placeholder</p></section>"
                    )
                    print(f"    ⚠️  {comp['name']}: no node data, using placeholder")
                    failed_set.add(comp_id)
                else:
                    comp_name = comp.get("name") or "Component"
                    html_doc = extract.build_html_document(comp_name, markup)
                    out_path = ROOT_DIR / comp["path"]
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(html_doc, encoding="utf-8")
                    repaired_set.add(comp_id)

                    # Update source_node_id in components list
                    for c in components:
                        if c["id"] == comp_id:
                            c["source_node_id"] = figma_export_id
                            break

                    print(f"    ✅ {comp['category']}/{comp['name']} -> {out_path.name}")

            # Save state after each batch
            state["repaired"] = list(repaired_set)
            state["failed"] = list(failed_set)
            save_state(state)

            # Throttle between batches
            if batch_idx < len(batches) - 1:
                print(f"    ⏳ Throttling {THROTTLE}s...")
                time.sleep(THROTTLE)

    # Update index.json
    index_data["components"] = components
    index_data["generated_at"] = datetime.now(timezone.utc).isoformat()
    INDEX_FILE.write_text(json.dumps(index_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n✅ index.json updated")

    # Final count
    remaining_empty = find_empty_components(components)
    print(f"\n📊 Summary:")
    print(f"   Total components: {len(components)}")
    print(f"   Repaired this run: {len(repaired_set)}")
    print(f"   Failed (no data): {len(failed_set)}")
    print(f"   Still empty: {len(remaining_empty)}")
    print(f"\n🎉 Done! Dev server: http://100.76.31.10:7842/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
