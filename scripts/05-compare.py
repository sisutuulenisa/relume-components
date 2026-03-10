#!/usr/bin/env python3
"""
05-compare.py - Vergelijkt Relume HTML components met Figma designs
Genereert een visueel rapport: compare/index.html
"""

import json
import os
import sys
import time
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
INDEX_FILE = BASE_DIR / "index.json"
COMPARE_DIR = BASE_DIR / "compare"
FIGMA_DIR = COMPARE_DIR / "figma"
HTML_DIR = COMPARE_DIR / "html"
STATE_FILE = COMPARE_DIR / "state.json"

FIGMA_TOKEN = os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN", "")
FIGMA_FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
DEV_SERVER = "http://100.76.31.10:7842"
FIGMA_API = "https://api.figma.com/v1"
BATCH_SIZE = 100
THROTTLE = 0.5


# ── State management ─────────────────────────────────────────────────────────
def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "figma_urls": {},           # node_id -> url
        "figma_done": [],           # node_ids where PNG is downloaded
        "html_done": [],            # slugs where screenshot is done
        "report_done": False,
    }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Figma helpers ─────────────────────────────────────────────────────────────
def figma_get_image_urls(node_ids: list[str]) -> dict:
    """Haal image URLs op van Figma API voor een batch node IDs."""
    ids_str = ",".join(node_ids)
    url = f"{FIGMA_API}/images/{FIGMA_FILE_KEY}?ids={ids_str}&format=png&scale=1"
    req = urllib.request.Request(url, headers={"X-Figma-Token": FIGMA_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data.get("images", {})
    except Exception as e:
        print(f"  ⚠️  Figma API error: {e}", file=sys.stderr)
        return {}


def download_file(url: str, dest: Path) -> bool:
    """Download een bestand naar dest. Returns True bij succes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "relume-compare/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"  ⚠️  Download failed {url}: {e}", file=sys.stderr)
        return False


# ── Browser screenshot ────────────────────────────────────────────────────────
def screenshot_component(url: str, dest: Path) -> bool:
    """Maak een screenshot via agent-browser CLI."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Open de pagina
        result = subprocess.run(
            ["agent-browser", "open", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  ⚠️  agent-browser open failed: {result.stderr[:100]}", file=sys.stderr)
            return False

        # Screenshot maken
        result = subprocess.run(
            ["agent-browser", "screenshot", str(dest), "--full"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  ⚠️  agent-browser screenshot failed: {result.stderr[:100]}", file=sys.stderr)
            return False

        return dest.exists()
    except subprocess.TimeoutExpired:
        print(f"  ⚠️  Timeout for {url}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"  ⚠️  Screenshot error: {e}", file=sys.stderr)
        return False


# ── Rapport genereren ─────────────────────────────────────────────────────────
def generate_report(components: list[dict]):
    """Genereer compare/index.html."""
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)

    categories = sorted(set(c["category"] for c in components))

    # Bouw component cards HTML
    cards_html = []
    for comp in components:
        cat = comp["category"]
        cat_slug = comp["category_slug"]
        name = comp["name"]
        slug = Path(comp["path"]).stem

        figma_path = FIGMA_DIR / cat_slug / f"{slug}.png"
        html_path = HTML_DIR / cat_slug / f"{slug}.png"

        # Relatieve paden voor HTML
        figma_rel = f"figma/{cat_slug}/{slug}.png"
        html_rel = f"html/{cat_slug}/{slug}.png"

        figma_exists = figma_path.exists()
        html_exists = html_path.exists()

        figma_img = f'<img src="{figma_rel}" alt="Figma" loading="lazy">' if figma_exists else '<div class="missing">⚠️ Figma ontbreekt</div>'
        html_img = f'<img src="{html_rel}" alt="HTML" loading="lazy">' if html_exists else '<div class="missing">⚠️ HTML ontbreekt</div>'

        warning = "" if (figma_exists and html_exists) else ' data-incomplete="true"'

        cards_html.append(f"""
  <div class="card" data-category="{cat}"{warning}>
    <div class="card-header">
      <span class="cat-badge">{cat}</span>
      <span class="comp-name">{name}</span>
      {"<span class='warn-badge'>⚠️</span>" if not (figma_exists and html_exists) else ""}
    </div>
    <div class="card-body">
      <div class="col">
        <div class="col-label">Figma</div>
        {figma_img}
      </div>
      <div class="col">
        <div class="col-label">HTML</div>
        {html_img}
      </div>
    </div>
  </div>""")

    # Category opties
    cat_options = '\n'.join(f'<option value="{c}">{c}</option>' for c in categories)
    total = len(components)
    figma_count = sum(1 for c in components if (FIGMA_DIR / c["category_slug"] / f"{Path(c['path']).stem}.png").exists())
    html_count = sum(1 for c in components if (HTML_DIR / c["category_slug"] / f"{Path(c['path']).stem}.png").exists())

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Relume Compare — HTML vs Figma</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: #0a0a0a;
      color: #e0e0e0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size: 14px;
    }}
    header {{
      position: sticky;
      top: 0;
      background: #111;
      border-bottom: 1px solid #222;
      padding: 12px 20px;
      display: flex;
      align-items: center;
      gap: 16px;
      z-index: 100;
    }}
    header h1 {{
      font-size: 16px;
      font-weight: 600;
      color: #fff;
      flex-shrink: 0;
    }}
    .stats {{
      font-size: 12px;
      color: #666;
      flex-shrink: 0;
    }}
    .stats span {{ color: #aaa; }}
    select, input[type=text] {{
      background: #1a1a1a;
      border: 1px solid #333;
      color: #e0e0e0;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 13px;
    }}
    select:focus, input:focus {{
      outline: none;
      border-color: #555;
    }}
    label {{ font-size: 12px; color: #888; }}
    .filter-group {{ display: flex; align-items: center; gap: 8px; }}
    .spacer {{ flex: 1; }}
    #search {{
      width: 220px;
    }}
    main {{
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .card {{
      background: #111;
      border: 1px solid #222;
      border-radius: 10px;
      overflow: hidden;
    }}
    .card[data-incomplete="true"] {{
      border-color: #4a3800;
    }}
    .card-header {{
      padding: 10px 14px;
      background: #161616;
      border-bottom: 1px solid #222;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .cat-badge {{
      background: #1e2a1e;
      color: #6aad6a;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 500;
      flex-shrink: 0;
    }}
    .comp-name {{
      font-weight: 500;
      color: #ddd;
    }}
    .warn-badge {{
      margin-left: auto;
      color: #f0a500;
      font-size: 13px;
    }}
    .card-body {{
      display: grid;
      grid-template-columns: 1fr 1fr;
    }}
    .col {{
      padding: 10px;
      border-right: 1px solid #1a1a1a;
    }}
    .col:last-child {{ border-right: none; }}
    .col-label {{
      font-size: 11px;
      color: #555;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
      font-weight: 600;
    }}
    .col img {{
      width: 100%;
      height: auto;
      display: block;
      border-radius: 4px;
      background: #0d0d0d;
    }}
    .missing {{
      background: #1a1200;
      color: #f0a500;
      border-radius: 4px;
      padding: 20px;
      text-align: center;
      font-size: 13px;
    }}
    .hidden {{ display: none; }}
    .count-indicator {{
      font-size: 12px;
      color: #555;
      padding: 8px 20px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>🔍 Relume Compare</h1>
    <div class="stats">
      <span>{figma_count}</span>/{total} Figma &nbsp;|&nbsp; <span>{html_count}</span>/{total} HTML
    </div>
    <div class="spacer"></div>
    <div class="filter-group">
      <label>Categorie</label>
      <select id="cat-filter" onchange="filterCards()">
        <option value="">Alle categorieën</option>
        {cat_options}
      </select>
    </div>
    <div class="filter-group">
      <label>Toon</label>
      <select id="status-filter" onchange="filterCards()">
        <option value="">Alle</option>
        <option value="incomplete">Alleen onvolledig ⚠️</option>
        <option value="complete">Alleen volledig</option>
      </select>
    </div>
    <input type="text" id="search" placeholder="Zoek component..." oninput="filterCards()">
  </header>
  <div class="count-indicator" id="count-indicator">{total} componenten</div>
  <main id="cards">
{''.join(cards_html)}
  </main>
  <script>
    function filterCards() {{
      const cat = document.getElementById('cat-filter').value;
      const status = document.getElementById('status-filter').value;
      const search = document.getElementById('search').value.toLowerCase();
      const cards = document.querySelectorAll('.card');
      let visible = 0;
      cards.forEach(card => {{
        const cardCat = card.dataset.category || '';
        const incomplete = card.dataset.incomplete === 'true';
        const text = card.innerText.toLowerCase();

        const catMatch = !cat || cardCat === cat;
        const statusMatch =
          status === '' ? true :
          status === 'incomplete' ? incomplete :
          status === 'complete' ? !incomplete : true;
        const searchMatch = !search || text.includes(search);

        const show = catMatch && statusMatch && searchMatch;
        card.classList.toggle('hidden', !show);
        if (show) visible++;
      }});
      document.getElementById('count-indicator').textContent = visible + ' componenten';
    }}
  </script>
</body>
</html>"""

    report_path = COMPARE_DIR / "index.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"✅ Rapport geschreven: {report_path}")


# ── Hoofdprogramma ────────────────────────────────────────────────────────────
def main():
    # Directories aanmaken
    COMPARE_DIR.mkdir(parents=True, exist_ok=True)
    FIGMA_DIR.mkdir(parents=True, exist_ok=True)
    HTML_DIR.mkdir(parents=True, exist_ok=True)

    # Index laden
    with open(INDEX_FILE) as f:
        data = json.load(f)
    components = data["components"]
    total = len(components)
    print(f"📋 {total} componenten geladen")

    # State laden (voor hervatten)
    state = load_state()
    figma_urls: dict = state.get("figma_urls", {})
    figma_done: set = set(state.get("figma_done", []))
    html_done: set = set(state.get("html_done", []))

    # ── Stap 1: Figma image URLs ophalen ──────────────────────────────────────
    print("\n🎨 Stap 1: Figma image URLs ophalen...")

    all_node_ids = [c["source_node_id"] for c in components]
    missing_ids = [nid for nid in all_node_ids if nid not in figma_urls]

    if missing_ids:
        print(f"  {len(missing_ids)} nog op te halen ({len(figma_urls)} al gecached)")
        batches = [missing_ids[i:i+BATCH_SIZE] for i in range(0, len(missing_ids), BATCH_SIZE)]
        for batch_idx, batch in enumerate(batches):
            print(f"  Batch {batch_idx+1}/{len(batches)} ({len(batch)} IDs)...")
            urls = figma_get_image_urls(batch)
            figma_urls.update(urls)
            state["figma_urls"] = figma_urls
            save_state(state)
            time.sleep(THROTTLE)
        print(f"  ✅ {len(figma_urls)} URLs opgehaald")
    else:
        print(f"  ✅ Alle {len(figma_urls)} URLs al gecached")

    # ── Stap 1b: Figma PNGs downloaden ────────────────────────────────────────
    print("\n⬇️  Figma PNGs downloaden...")
    for i, comp in enumerate(components):
        node_id = comp["source_node_id"]
        cat_slug = comp["category_slug"]
        slug = Path(comp["path"]).stem
        key = f"{cat_slug}/{slug}"

        if key in figma_done:
            continue

        url = figma_urls.get(node_id)
        if not url:
            print(f"  [{i+1}/{total}] ⚠️  Geen URL voor {cat_slug}/{comp['name']}")
            figma_done.add(key)  # Skip, markeer als 'gedaan' (ook al ontbreekt het)
            continue

        print(f"  [{i+1}/{total}] {cat_slug}/{comp['name']}")
        dest = FIGMA_DIR / cat_slug / f"{slug}.png"

        if not dest.exists():
            success = download_file(url, dest)
            if success:
                figma_done.add(key)
            time.sleep(0.1)
        else:
            figma_done.add(key)

        # State opslaan elke 50 downloads
        if (i + 1) % 50 == 0:
            state["figma_done"] = list(figma_done)
            save_state(state)

    state["figma_done"] = list(figma_done)
    save_state(state)
    print(f"  ✅ Figma PNGs klaar")

    # ── Stap 2: HTML screenshots ───────────────────────────────────────────────
    print("\n📸 Stap 2: HTML screenshots maken...")
    for i, comp in enumerate(components):
        cat_slug = comp["category_slug"]
        slug = Path(comp["path"]).stem
        key = f"{cat_slug}/{slug}"

        if key in html_done:
            continue

        dest = HTML_DIR / cat_slug / f"{slug}.png"
        if dest.exists():
            html_done.add(key)
            continue

        # URL bouwen: gebruik het 'path' veld relatief aan de server root
        # path = "components/style-guide/icons.html"
        component_url = f"{DEV_SERVER}/{comp['path']}"
        print(f"  [{i+1}/{total}] {cat_slug}/{comp['name']}")

        success = screenshot_component(component_url, dest)
        if success:
            html_done.add(key)
        else:
            print(f"    ⚠️  Screenshot mislukt, ga verder")

        # State opslaan elke 25 screenshots
        if (i + 1) % 25 == 0:
            state["html_done"] = list(html_done)
            save_state(state)

    state["html_done"] = list(html_done)
    save_state(state)
    print(f"  ✅ HTML screenshots klaar")

    # ── Stap 3: Rapport genereren ──────────────────────────────────────────────
    print("\n📄 Stap 3: Rapport genereren...")
    generate_report(components)

    state["report_done"] = True
    save_state(state)

    print(f"\n🎉 Klaar! Rapport beschikbaar op: {DEV_SERVER}/compare/index.html")
    print(f"   Figma: {len(figma_done)} / {total}")
    print(f"   HTML:  {len(html_done)} / {total}")


if __name__ == "__main__":
    main()
