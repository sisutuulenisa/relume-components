#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
API_BASE = "https://api.figma.com/v1"
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = ROOT_DIR / ".env"
DEFAULT_COMPONENTS_RAW = SCRIPT_DIR / "components-raw.json"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "components"
DEFAULT_INDEX_PATH = ROOT_DIR / "index.json"

IMAGE_LIKE_TYPES = {"RECTANGLE", "ELLIPSE", "VECTOR", "STAR", "POLYGON"}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def slugify(text: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or fallback


def clean_page_name(name: str) -> str:
    cleaned = re.sub(r"^[\s↳]+", "", name or "").strip()
    return re.sub(r"\s+", " ", cleaned)


def rgba(fill_color: dict | None, opacity: float | None = None) -> str:
    if not fill_color:
        return "rgba(0,0,0,1)"
    r = int(round(float(fill_color.get("r", 0)) * 255))
    g = int(round(float(fill_color.get("g", 0)) * 255))
    b = int(round(float(fill_color.get("b", 0)) * 255))
    a = float(fill_color.get("a", 1))
    if opacity is not None:
        a *= float(opacity)
    a = max(0.0, min(1.0, a))
    return f"rgba({r},{g},{b},{a:.3f})"


def fmt_px(value) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return f"{int(round(v))}px"


def class_px(prefix: str, value) -> str | None:
    px = fmt_px(value)
    if not px:
        return None
    return f"{prefix}-[{px}]"


def dedupe_classes(classes: list[str]) -> list[str]:
    seen = set()
    result = []
    for cls in classes:
        if not cls or cls in seen:
            continue
        seen.add(cls)
        result.append(cls)
    return result


def first_visible_fill(node: dict) -> dict | None:
    for fill in node.get("fills", []) or []:
        if fill.get("visible", True):
            return fill
    return None


def first_visible_stroke(node: dict) -> dict | None:
    for stroke in node.get("strokes", []) or []:
        if stroke.get("visible", True):
            return stroke
    return None


def padding_classes(node: dict) -> list[str]:
    pt = node.get("paddingTop")
    pr = node.get("paddingRight")
    pb = node.get("paddingBottom")
    pl = node.get("paddingLeft")
    if any(v is None for v in (pt, pr, pb, pl)):
        return []

    classes = []
    if pt == pr == pb == pl:
        c = class_px("p", pt)
        if c:
            classes.append(c)
        return classes

    if pl == pr:
        c = class_px("px", pl)
        if c:
            classes.append(c)
    else:
        for prefix, value in (("pl", pl), ("pr", pr)):
            c = class_px(prefix, value)
            if c:
                classes.append(c)

    if pt == pb:
        c = class_px("py", pt)
        if c:
            classes.append(c)
    else:
        for prefix, value in (("pt", pt), ("pb", pb)):
            c = class_px(prefix, value)
            if c:
                classes.append(c)

    return classes


def border_radius_classes(node: dict) -> list[str]:
    classes = []
    corner_radius = node.get("cornerRadius")
    if corner_radius is not None:
        c = class_px("rounded", corner_radius)
        if c:
            classes.append(c)
        return classes

    radii = node.get("rectangleCornerRadii")
    if isinstance(radii, list) and len(radii) == 4:
        if radii[0] == radii[1] == radii[2] == radii[3]:
            c = class_px("rounded", radii[0])
            if c:
                classes.append(c)
        else:
            mapping = [
                ("rounded-tl", radii[0]),
                ("rounded-tr", radii[1]),
                ("rounded-br", radii[2]),
                ("rounded-bl", radii[3]),
            ]
            for prefix, value in mapping:
                c = class_px(prefix, value)
                if c:
                    classes.append(c)
    return classes


def map_layout_classes(node: dict) -> list[str]:
    classes = []
    layout_mode = node.get("layoutMode")
    if layout_mode == "HORIZONTAL":
        classes.extend(["flex", "flex-row"])
    elif layout_mode == "VERTICAL":
        classes.extend(["flex", "flex-col"])

    if node.get("layoutWrap") == "WRAP":
        classes.append("flex-wrap")

    align_primary = node.get("primaryAxisAlignItems")
    if align_primary == "MIN":
        classes.append("justify-start")
    elif align_primary == "CENTER":
        classes.append("justify-center")
    elif align_primary == "MAX":
        classes.append("justify-end")
    elif align_primary == "SPACE_BETWEEN":
        classes.append("justify-between")

    align_cross = node.get("counterAxisAlignItems")
    if align_cross == "MIN":
        classes.append("items-start")
    elif align_cross == "CENTER":
        classes.append("items-center")
    elif align_cross == "MAX":
        classes.append("items-end")
    elif align_cross == "BASELINE":
        classes.append("items-baseline")

    gap = class_px("gap", node.get("itemSpacing"))
    if gap:
        classes.append(gap)
    return classes


def map_size_classes(node: dict, is_root: bool = False) -> list[str]:
    if is_root:
        return ["w-full"]

    box = node.get("absoluteBoundingBox") or {}
    classes = []
    w = class_px("w", box.get("width"))
    h = class_px("h", box.get("height"))
    if w:
        classes.append(w)
    if h:
        classes.append(h)
    return classes


def map_fill_stroke_classes(node: dict) -> list[str]:
    classes = []
    fill = first_visible_fill(node)
    if fill and fill.get("type") == "SOLID":
        classes.append(f"bg-[{rgba(fill.get('color'), fill.get('opacity'))}]")

    stroke = first_visible_stroke(node)
    if stroke and stroke.get("type") == "SOLID":
        classes.append("border")
        classes.append(f"border-[{rgba(stroke.get('color'), stroke.get('opacity'))}]")
    return classes


def map_effect_classes(node: dict) -> list[str]:
    for effect in node.get("effects", []) or []:
        if effect.get("visible", True) and effect.get("type") == "DROP_SHADOW":
            return ["shadow-md"]
    return []


def map_text_classes(node: dict) -> list[str]:
    classes = []
    style = node.get("style", {}) or {}

    font_size = style.get("fontSize")
    if font_size:
        classes.append(f"text-[{int(round(float(font_size)))}px]")

    font_weight = style.get("fontWeight")
    if font_weight:
        classes.append(f"font-[{int(round(float(font_weight)))}]")

    line_height = style.get("lineHeightPx")
    if line_height:
        classes.append(f"leading-[{int(round(float(line_height)))}px]")

    letter_spacing = style.get("letterSpacing")
    if letter_spacing and float(letter_spacing) != 0:
        classes.append(f"tracking-[{float(letter_spacing):g}px]")

    fill = first_visible_fill(node)
    if fill and fill.get("type") == "SOLID":
        classes.append(f"text-[{rgba(fill.get('color'), fill.get('opacity'))}]")
    else:
        classes.append("text-gray-900")

    text_align = style.get("textAlignHorizontal")
    if text_align == "LEFT":
        classes.append("text-left")
    elif text_align == "CENTER":
        classes.append("text-center")
    elif text_align == "RIGHT":
        classes.append("text-right")
    elif text_align == "JUSTIFIED":
        classes.append("text-justify")

    text_case = style.get("textCase")
    if text_case == "UPPER":
        classes.append("uppercase")
    elif text_case == "LOWER":
        classes.append("lowercase")

    decoration = style.get("textDecoration")
    if decoration == "UNDERLINE":
        classes.append("underline")
    elif decoration == "STRIKETHROUGH":
        classes.append("line-through")

    return classes


def is_image_placeholder(node: dict) -> bool:
    node_type = node.get("type")
    node_name = (node.get("name") or "").lower()
    fill = first_visible_fill(node)
    if fill and fill.get("type") == "IMAGE":
        return True
    if node_type in IMAGE_LIKE_TYPES and any(word in node_name for word in ("image", "img", "photo", "picture")):
        return True
    return False


def semantic_root_tag(category: str) -> str:
    c = (category or "").lower()
    if "nav" in c or "menu" in c:
        return "nav"
    if "hero" in c or "header" in c:
        return "header"
    if "blog" in c or "article" in c or "post" in c:
        return "article"
    return "section"


def semantic_text_tag(node: dict) -> str:
    style = node.get("style", {}) or {}
    size = float(style.get("fontSize") or 0)
    if size >= 36:
        return "h1"
    if size >= 30:
        return "h2"
    if size >= 24:
        return "h3"
    if size >= 20:
        return "h4"
    return "p"


def build_layout_classes(node: dict, is_root: bool = False) -> list[str]:
    classes = []
    classes.extend(map_size_classes(node, is_root=is_root))
    classes.extend(map_layout_classes(node))
    classes.extend(padding_classes(node))
    classes.extend(border_radius_classes(node))
    classes.extend(map_fill_stroke_classes(node))
    classes.extend(map_effect_classes(node))
    if node.get("clipsContent"):
        classes.append("overflow-hidden")
    return dedupe_classes(classes)


def render_node(node: dict, category: str, is_root: bool = False, indent: int = 2) -> str:
    if node.get("visible") is False:
        return ""

    node_type = node.get("type")
    pad = " " * indent

    if node_type == "TEXT":
        tag = semantic_text_tag(node)
        text = (node.get("characters") or "").strip() or node.get("name") or "Placeholder text"
        classes = dedupe_classes(map_text_classes(node))
        return f'{pad}<{tag} class="{" ".join(classes)}">{html.escape(text)}</{tag}>'

    if is_image_placeholder(node):
        classes = build_layout_classes(node, is_root=False)
        classes.append("bg-gray-200")
        if not any(c.startswith("h-[") for c in classes):
            classes.append("h-[240px]")
        if not any(c.startswith("w-[") for c in classes):
            classes.append("w-full")
        return f'{pad}<div class="{" ".join(dedupe_classes(classes))}" role="img" aria-label="Image placeholder"></div>'

    children = [c for c in node.get("children", []) or [] if c.get("visible", True)]
    if is_root:
        tag = semantic_root_tag(category)
    elif node_type == "INSTANCE" and "button" in (node.get("name") or "").lower():
        tag = "button"
    else:
        tag = "div"

    classes = build_layout_classes(node, is_root=is_root)
    if is_root:
        classes.extend(["mx-auto", "max-w-[1440px]"])

    opening = f'{pad}<{tag} class="{" ".join(dedupe_classes(classes))}">'
    closing = f"{pad}</{tag}>"

    if not children:
        if tag == "button":
            label = node.get("name") or "Button"
            base = dedupe_classes(classes + ["px-[16px]", "py-[10px]", "rounded-[8px]", "bg-gray-900", "text-white"])
            return f'{pad}<button class="{" ".join(base)}">{html.escape(label)}</button>'
        return f"{opening}{closing[len(pad):]}"

    rendered_children = []
    for child in children:
        chunk = render_node(child, category=category, is_root=False, indent=indent + 2)
        if chunk:
            rendered_children.append(chunk)

    if not rendered_children:
        return f"{opening}{closing[len(pad):]}"

    return "\n".join([opening, *rendered_children, closing])


def api_get(path: str) -> dict:
    token = os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("FIGMA_PERSONAL_ACCESS_TOKEN ontbreekt in omgeving/.env")

    request = Request(
        f"{API_BASE}{path}",
        headers={
            "X-Figma-Token": token,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def chunked(items: list[str], size: int) -> list[list[str]]:
    out = []
    for i in range(0, len(items), size):
        out.append(items[i : i + size])
    return out


def fetch_nodes_with_fallback(components: list[dict], fetch_batch_size: int) -> tuple[dict, bool]:
    by_id = {c["id"]: c.get("node") for c in components if c.get("id")}
    component_ids = [c["id"] for c in components if c.get("id")]
    if not component_ids:
        return by_id, False

    used_api = False
    for id_batch in chunked(component_ids, fetch_batch_size):
        query = urlencode({"ids": ",".join(id_batch)})
        path = f"/files/{FILE_KEY}/nodes?{query}"
        try:
            payload = api_get(path)
        except (HTTPError, URLError, RuntimeError) as exc:
            print(f"[WARN] Kon component-batch niet ophalen via API ({id_batch[0]}..): {exc}", file=sys.stderr)
            continue
        except Exception as exc:
            print(f"[WARN] Onverwachte fout bij API-fetch ({id_batch[0]}..): {exc}", file=sys.stderr)
            continue

        used_api = True
        nodes = payload.get("nodes", {})
        for cid in id_batch:
            doc = nodes.get(cid, {}).get("document")
            if doc:
                by_id[cid] = doc
    return by_id, used_api


def read_components(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    components: list[dict] = []

    if isinstance(data.get("kept_pages"), list):
        for page in data.get("kept_pages", []):
            category = clean_page_name(page.get("name") or "uncategorized")
            for comp in page.get("components", []):
                components.append(
                    {
                        "id": comp.get("id"),
                        "name": comp.get("name") or "component",
                        "type": comp.get("type"),
                        "page_id": page.get("id"),
                        "page_name": category,
                        "node": comp.get("node"),
                    }
                )
        return components

    if isinstance(data.get("components"), list):
        for comp in data.get("components", []):
            components.append(
                {
                    "id": comp.get("id"),
                    "name": comp.get("name") or "component",
                    "type": comp.get("type"),
                    "page_id": comp.get("page_id"),
                    "page_name": clean_page_name(comp.get("page_name") or "uncategorized"),
                    "node": comp.get("node"),
                }
            )
        return components

    return components


def build_html_document(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>{safe_title}</title>
    <script src=\"https://cdn.tailwindcss.com\"></script>
  </head>
  <body class=\"bg-white text-gray-900 antialiased\">
{body}
  </body>
</html>
"""


def run_git_commit(message: str, push: bool) -> None:
    subprocess.run(["git", "add", "-A"], cwd=ROOT_DIR, check=True)
    commit = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
    )
    if commit.returncode != 0:
        text = (commit.stdout or "") + "\n" + (commit.stderr or "")
        if "nothing to commit" in text.lower():
            return
        raise RuntimeError(text.strip())
    if push:
        subprocess.run(["git", "push"], cwd=ROOT_DIR, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Relume components to HTML + Tailwind")
    parser.add_argument("--components-raw", type=Path, default=DEFAULT_COMPONENTS_RAW)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("--fetch-batch-size", type=int, default=20)
    parser.add_argument("--git-batch-size", type=int, default=0, help="Commit iedere N componenten (0 = uit)")
    parser.add_argument("--push", action="store_true", help="Push na iedere batch commit")
    args = parser.parse_args()

    load_env(ENV_PATH)

    if not args.components_raw.exists():
        print(f"components-raw niet gevonden: {args.components_raw}", file=sys.stderr)
        return 1

    components = read_components(args.components_raw)
    if not components:
        print("Geen componenten gevonden in components-raw.json", file=sys.stderr)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    nodes_by_id, used_api = fetch_nodes_with_fallback(components, max(1, args.fetch_batch_size))

    manifest = []
    per_category_counter = {}
    pending_commit_count = 0
    pending_categories = set()
    total = len(components)

    for idx, component in enumerate(components, start=1):
        category_name = component.get("page_name") or "uncategorized"
        category_slug = slugify(category_name, fallback="uncategorized")
        category_dir = args.output_dir / category_slug
        category_dir.mkdir(parents=True, exist_ok=True)

        name_slug = slugify(component.get("name") or "component", fallback="component")
        count = per_category_counter.get((category_slug, name_slug), 0) + 1
        per_category_counter[(category_slug, name_slug)] = count
        filename = f"{name_slug}.html" if count == 1 else f"{name_slug}-{count}.html"

        node = nodes_by_id.get(component["id"]) or component.get("node") or {}
        component_markup = render_node(node, category=category_name, is_root=True, indent=4)
        if not component_markup:
            component_markup = (
                "    <section class=\"w-full mx-auto max-w-[1440px] p-[24px]\">"
                "<p class=\"text-[16px] text-gray-700\">Placeholder</p></section>"
            )

        html_doc = build_html_document(component.get("name") or "Component", component_markup)
        out_path = category_dir / filename
        out_path.write_text(html_doc, encoding="utf-8")

        rel_path = out_path.relative_to(ROOT_DIR).as_posix()
        manifest.append(
            {
                "id": component.get("id"),
                "name": component.get("name"),
                "category": category_name,
                "category_slug": category_slug,
                "type": component.get("type"),
                "path": rel_path,
                "source_page_id": component.get("page_id"),
                "source_node_id": component.get("id"),
            }
        )

        pending_commit_count += 1
        pending_categories.add(category_slug)
        print(f"[{idx}/{total}] {rel_path}")

        if args.git_batch_size > 0 and pending_commit_count >= args.git_batch_size:
            category_label = next(iter(pending_categories)) if len(pending_categories) == 1 else "mixed"
            message = f"feat: add {category_label} components"
            run_git_commit(message, push=args.push)
            pending_commit_count = 0
            pending_categories = set()
            print(f"[git] {message}")

    if args.git_batch_size > 0 and pending_commit_count > 0:
        category_label = next(iter(pending_categories)) if len(pending_categories) == 1 else "mixed"
        message = f"feat: add {category_label} components"
        run_git_commit(message, push=args.push)
        print(f"[git] {message}")

    args.index_path.write_text(
        json.dumps(
            {
                "file_key": FILE_KEY,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "component_count": len(manifest),
                "used_api_for_component_css": used_api,
                "components": manifest,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Totaal componenten: {len(manifest)}")
    print(f"Manifest: {args.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
