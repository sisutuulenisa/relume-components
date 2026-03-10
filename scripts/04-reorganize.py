#!/usr/bin/env python3
"""
04-reorganize.py — Herstructureer components/ naar Pages / Ecommerce / Application / Templates
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_COMP = ROOT / "components"
NEW_COMP = ROOT / "components"  # zelfde root, nieuwe substructuur
INDEX = ROOT / "index.json"

# Groepsmapping: category-slug → group
GROUP_MAP = {
    # ── PAGES ──────────────────────────────────────────────────────────────
    "careers":                      "pages",
    "gallery":                      "pages",
    "contact":                      "pages",
    "faq":                          "pages",
    "pricing":                      "pages",
    "logos":                        "pages",
    "team":                         "pages",
    "timelines":                    "pages",
    "cta-new":                      "pages",
    "cta":                          "pages",
    "cookie-consent":               "pages",
    "blog-headers":                 "pages",
    "blog-sections":                "pages",
    "blog-post-headers":            "pages",
    "blog-post-pages":              "pages",
    "blog-pages":                   "pages",
    "banners":                      "pages",
    "contact-modals":               "pages",
    "comparisons":                  "pages",
    "portfolio-sections":           "pages",
    "portfolio-headers":            "pages",
    "portfolio-pages":              "pages",
    "event-sections":               "pages",
    "event-headers":                "pages",
    "event-item-headers":           "pages",
    "stats-sections":               "pages",
    "stat-cards":                   "pages",
    "multi-step-forms":             "pages",
    "long-form-content-sections":   "pages",
    "loaders":                      "pages",
    "links-pages":                  "pages",
    "features":                     "pages",
    "headers":                      "pages",
    "hero-headers-new":             "pages",
    "navbars":                      "pages",
    "footers":                      "pages",
    # ── ECOMMERCE ──────────────────────────────────────────────────────────
    "product-headers":              "ecommerce",
    "product-list-sections":        "ecommerce",
    "category-filters":             "ecommerce",
    # ── APPLICATION ────────────────────────────────────────────────────────
    "application-shells":           "application",
    "sidebars":                     "application",
    "topbars":                      "application",
    "page-headers":                 "application",
    "section-headers":              "application",
    "card-headers":                 "application",
    "sign-up-and-log-in-pages":     "application",
    "sign-up-and-log-in-modals":    "application",
    "onboarding-forms":             "application",
    "tables":                       "application",
    "stacked-lists":                "application",
    "grid-lists":                   "application",
    "forms":                        "application",
    "description-lists":            "application",
    # ── PAGE TEMPLATES ─────────────────────────────────────────────────────
    "home-pages":                   "templates",
    "pricing-pages":                "templates",
    "about-pages":                  "templates",
    "legal-pages":                  "templates",
    "contact-pages":                "templates",
    # ── STYLE GUIDE ────────────────────────────────────────────────────────
    "style-guide":                  "style-guide",
}

def main():
    idx = json.loads(INDEX.read_text())

    moved = 0
    skipped = 0

    new_idx = []
    for entry in idx:
        cat = entry["category"]
        group = GROUP_MAP.get(cat, "pages")  # fallback → pages

        old_rel = entry["file"]                    # bijv. "components/navbars/navbar-1.html"
        old_path = ROOT / old_rel

        # Nieuw pad: components/<group>/<category>/<file>
        new_rel = f"components/{group}/{cat}/{old_path.name}"
        new_path = ROOT / new_rel

        if old_rel == new_rel:
            # al goed
            entry["group"] = group
            new_idx.append(entry)
            continue

        if old_path.exists():
            new_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_path), str(new_path))
            moved += 1
        else:
            # Al verplaatst of ontbreekt
            skipped += 1

        entry["file"] = new_rel
        entry["group"] = group
        new_idx.append(entry)

    # Opruimen lege mappen
    for d in sorted(OLD_COMP.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()

    INDEX.write_text(json.dumps(new_idx, indent=2, ensure_ascii=False) + "\n")
    print(f"✅ Verplaatst: {moved}, overgeslagen: {skipped}")
    print(f"📋 index.json bijgewerkt met group-veld")

    # Controleer nieuwe structuur
    groups = {}
    for e in new_idx:
        g = e.get("group","?")
        groups[g] = groups.get(g,0)+1
    print("\n📁 Nieuwe structuur:")
    for g, cnt in sorted(groups.items()):
        print(f"  components/{g}/  — {cnt} componenten")


if __name__ == "__main__":
    main()
