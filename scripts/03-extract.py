#!/usr/bin/env python3
import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
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

# Breakpoint detection
DESKTOP_MIN_WIDTH = 1200
DESKTOP_MAX_WIDTH = 1700
MOBILE_MAX_WIDTH = 600


def normalized_name(node: dict) -> str:
    raw = (node.get("name") or "")
    return raw.lower().replace(" ", "").replace("_", "").replace("-", "")


def get_visible_children(node: dict) -> list[dict]:
    return [c for c in node.get("children", []) or [] if c.get("visible", True)]


def get_desktop_child(node: dict) -> dict | None:
    """
    For a COMPONENT_SET (or any node with desktop+mobile variants),
    return the desktop breakpoint child.
    """
    if not node:
        return None
    children = get_visible_children(node)
    if not children:
        return None

    for child in children:
        if "desktop" in normalized_name(child):
            return child

    for child in children:
        box = child.get("absoluteBoundingBox") or {}
        w = float(box.get("width") or 0)
        if DESKTOP_MIN_WIDTH <= w <= DESKTOP_MAX_WIDTH:
            return child

    return max(children, key=lambda c: float((c.get("absoluteBoundingBox") or {}).get("width") or 0), default=None)


def get_mobile_child(node: dict) -> dict | None:
    if not node:
        return None
    children = get_visible_children(node)
    if not children:
        return None

    for child in children:
        norm = normalized_name(child)
        if "mobile" in norm or "phone" in norm:
            return child

    for child in children:
        variants = child.get("variantProperties") or {}
        if any("mobile" in str(v).lower() for v in variants.values()):
            return child

    for child in children:
        box = child.get("absoluteBoundingBox") or {}
        w = float(box.get("width") or 0)
        if 0 < w <= MOBILE_MAX_WIDTH:
            return child

    return min(children, key=lambda c: float((c.get("absoluteBoundingBox") or {}).get("width") or 10**9), default=None)


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
        return "rgba(0,0,0,0)"
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
    rounded = int(round(v))
    if rounded <= 0:
        return None
    return f"{rounded}px"


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


def node_box(node: dict) -> dict:
    return node.get("absoluteBoundingBox") or {}


def node_width(node: dict) -> float:
    return float(node_box(node).get("width") or 0)


def node_height(node: dict) -> float:
    return float(node_box(node).get("height") or 0)


def infer_layout_mode(node: dict) -> str | None:
    layout_mode = node.get("layoutMode")
    if layout_mode in {"HORIZONTAL", "VERTICAL"}:
        return layout_mode

    children = get_visible_children(node)
    if len(children) < 2:
        return None

    xs = [float(node_box(c).get("x") or 0) for c in children]
    ys = [float(node_box(c).get("y") or 0) for c in children]
    if (max(xs) - min(xs)) > 12 and (max(ys) - min(ys)) < 24:
        return "HORIZONTAL"
    if (max(ys) - min(ys)) > 12:
        return "VERTICAL"
    return None


def is_row_layout(node: dict) -> bool:
    return infer_layout_mode(node) == "HORIZONTAL"


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


def map_layout_classes(node: dict, responsive: bool = False) -> list[str]:
    classes = []
    layout_mode = infer_layout_mode(node)
    if layout_mode == "HORIZONTAL":
        if responsive:
            classes.extend(["flex", "flex-col", "md:flex-row"])
        else:
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


def map_size_classes(node: dict, is_root: bool = False, parent: dict | None = None) -> list[str]:
    if is_root:
        return ["w-full"]

    box = node_box(node)
    classes = []

    w_val = float(box.get("width") or 0)
    h_val = float(box.get("height") or 0)
    parent_w = node_width(parent) if parent else 0

    if parent_w > 0 and 0 < w_val < parent_w:
        width_pct = int(round((w_val / parent_w) * 100))
        if 0 < width_pct < 100:
            classes.append(f"w-[{width_pct}%]")
        else:
            w = class_px("w", w_val)
            if w:
                classes.append(w)
    else:
        w = class_px("w", w_val)
        if w:
            classes.append(w)

    has_children = bool(get_visible_children(node))
    keep_height = not has_children or node.get("type") in IMAGE_LIKE_TYPES
    if keep_height:
        h = class_px("h", h_val)
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
        fw = int(round(float(font_weight)))
        weight_map = {
            100: "font-thin",
            200: "font-extralight",
            300: "font-light",
            400: "font-normal",
            500: "font-medium",
            600: "font-semibold",
            700: "font-bold",
            800: "font-extrabold",
            900: "font-black",
        }
        closest = min(weight_map.keys(), key=lambda k: abs(k - fw))
        classes.append(weight_map[closest])
        if closest != fw:
            classes.append(f"font-[{fw}]")

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


def is_small_icon(node: dict) -> bool:
    if node.get("type") not in IMAGE_LIKE_TYPES:
        return False
    fill = first_visible_fill(node)
    if fill and fill.get("type") == "IMAGE":
        return False
    box = node.get("absoluteBoundingBox") or {}
    w = float(box.get("width") or 0)
    h = float(box.get("height") or 0)
    return w < 64 and h < 64


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


def extract_text(node: dict) -> str:
    if node.get("type") == "TEXT":
        return (node.get("characters") or "").strip()
    for child in get_visible_children(node):
        value = extract_text(child)
        if value:
            return value
    return ""


def has_icon_descendant(node: dict) -> bool:
    name = (node.get("name") or "").lower()
    if "icon" in name or "arrow" in name or "chevron" in name:
        return True
    return any(has_icon_descendant(child) for child in get_visible_children(node))


def is_tab_container(node: dict) -> bool:
    children = get_visible_children(node)
    if len(children) < 3 or not is_row_layout(node):
        return False
    labels = [extract_text(child) for child in children]
    return sum(1 for l in labels if l) >= 3


def is_button_node(node: dict) -> bool:
    return node.get("type") == "INSTANCE" and "button" in (node.get("name") or "").lower()


def is_button_group(node: dict) -> bool:
    children = get_visible_children(node)
    if len(children) < 2 or not is_row_layout(node):
        return False
    return sum(1 for c in children if is_button_node(c)) >= 2


def dedupe_tab_panels(children: list[dict]) -> list[dict]:
    if len(children) < 3:
        return children
    first = children[0]
    if not get_visible_children(first):
        return children
    first_inner = get_visible_children(first)[0]
    if not is_tab_container(first_inner):
        return children

    kept = [first]
    panel_name = (children[1].get("name") or "").strip().lower() if len(children) > 1 else ""
    for idx, child in enumerate(children[1:], start=1):
        name = (child.get("name") or "").strip().lower()
        if idx == 1:
            kept.append(child)
            continue
        if panel_name and name == panel_name:
            continue
        kept.append(child)
    return kept


def build_layout_classes(node: dict, is_root: bool = False, parent: dict | None = None, responsive: bool = False) -> list[str]:
    classes = []
    classes.extend(map_size_classes(node, is_root=is_root, parent=parent))
    classes.extend(map_layout_classes(node, responsive=responsive))
    classes.extend(padding_classes(node))
    classes.extend(border_radius_classes(node))
    classes.extend(map_fill_stroke_classes(node))
    classes.extend(map_effect_classes(node))
    if node.get("clipsContent"):
        classes.append("overflow-hidden")
    return dedupe_classes(classes)


def build_image_placeholder_classes(node: dict, parent: dict | None = None, responsive: bool = False) -> list[str]:
    classes = []
    classes.extend(map_size_classes(node, is_root=False, parent=parent))

    parent_w = node_width(parent) if parent else 0
    node_w = node_width(node)
    if parent_w > 0 and node_w > 0:
        width_pct = int(round((node_w / parent_w) * 100))
        width_pct = max(1, min(100, width_pct))
        if responsive and width_pct <= 60:
            classes.append("w-full")
            classes.append(f"md:w-[{width_pct}%]")
        elif width_pct < 100:
            classes.append(f"w-[{width_pct}%]")
    elif is_row_layout(parent or {}):
        classes.append("max-w-[50%]")

    if responsive and is_row_layout(parent or {}):
        classes.append("w-full")
        if not any(c.startswith("md:w-") for c in classes):
            classes.append("md:w-1/2")

    classes.extend(map_layout_classes(node, responsive=False))
    classes.extend(padding_classes(node))
    classes.extend(border_radius_classes(node))
    if node.get("clipsContent"):
        classes.append("overflow-hidden")

    classes.extend(["bg-gray-100", "rounded-lg", "flex", "items-center", "justify-center"])
    if not any(c.startswith("h-[") for c in classes):
        classes.append("h-[240px]")
    if not any(c.startswith("w-[") for c in classes) and not any(c == "w-full" for c in classes):
        classes.append("w-full")
    return dedupe_classes(classes)


def render_node(
    node: dict,
    category: str,
    is_root: bool = False,
    indent: int = 2,
    parent: dict | None = None,
    responsive: bool = False,
) -> str:
    if node.get("visible") is False:
        return ""

    if is_root and node.get("type") == "COMPONENT_SET":
        desktop = get_desktop_child(node)
        mobile = get_mobile_child(node)
        node = desktop or mobile or node
        responsive = bool(desktop and mobile)

    if not is_root and node.get("type") == "COMPONENT_SET":
        desktop = get_desktop_child(node)
        if desktop:
            node = desktop

    node_type = node.get("type")
    pad = " " * indent

    if node_type == "TEXT":
        tag = semantic_text_tag(node)
        text = (node.get("characters") or "").strip() or node.get("name") or "Placeholder text"
        classes = dedupe_classes(map_text_classes(node))
        return f'{pad}<{tag} class="{" ".join(classes)}">{html.escape(text)}</{tag}>'

    if is_small_icon(node):
        w_val = int(round(node_width(node) or 24))
        h_val = int(round(node_height(node) or 24))
        return f'{pad}<div class="w-[{w_val}px] h-[{h_val}px] bg-gray-400 rounded-sm flex-shrink-0" role="img" aria-label="Icon placeholder"></div>'

    if node_type in IMAGE_LIKE_TYPES or is_image_placeholder(node):
        classes = build_image_placeholder_classes(node, parent=parent, responsive=responsive)
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" class="w-12 h-12 text-gray-400" fill="none" '
            'viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">'
            '<rect x="3" y="3" width="18" height="18" rx="2" ry="2" stroke="currentColor" fill="none"/>'
            '<circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>'
            '<polyline points="21 15 16 10 5 21" stroke="currentColor" fill="none"/>'
            "</svg>"
        )
        return f'{pad}<div class="{" ".join(classes)}" role="img" aria-label="Image placeholder">{svg}</div>'

    children = get_visible_children(node)
    if is_root:
        children = dedupe_tab_panels(children)

    if is_tab_container(node):
        tab_classes = ["hidden", "md:flex", "flex-row", "border-b", "border-gray-200"]
        rows = [f'{pad}<div class="{" ".join(tab_classes)}">']
        for idx, child in enumerate(children):
            label = extract_text(child) or f"Tab {idx + 1}"
            cls = "border border-gray-900 px-4 py-2 text-sm" if idx == 0 else "px-4 py-2 text-sm text-gray-500"
            rows.append(f'{pad}  <button class="{cls}">{html.escape(label)}</button>')
        rows.append(f"{pad}</div>")
        return "\n".join(rows)

    if is_button_group(node):
        group_rows = [f'{pad}<div class="flex flex-row items-center gap-[24px]">']
        button_nodes = [c for c in children if is_button_node(c)]
        for idx, btn in enumerate(button_nodes[:2]):
            label = extract_text(btn) or "Button"
            if idx == 0:
                cls = "bg-gray-900 text-white px-4 py-2.5 rounded"
            else:
                cls = "border border-gray-900 text-gray-900 px-4 py-2.5 rounded bg-transparent"
                if has_icon_descendant(btn):
                    label = f"{label} →"
            group_rows.append(f'{pad}  <button class="{cls}">{html.escape(label)}</button>')
        group_rows.append(f"{pad}</div>")
        return "\n".join(group_rows)

    if is_root:
        tag = semantic_root_tag(category)
    elif is_button_node(node):
        tag = "button"
    else:
        tag = "div"

    classes = build_layout_classes(node, is_root=is_root, parent=parent, responsive=responsive)

    if responsive and parent and is_row_layout(parent):
        classes.append("w-full")
        if not any(c.startswith("md:w-") for c in classes):
            classes.append("md:w-1/2")

    if tag == "button":
        if not any(c.startswith("bg-") for c in classes):
            classes.extend(["bg-gray-900", "text-white", "px-[16px]", "py-[10px]", "rounded-[8px]"])
        classes.append("cursor-pointer")

    if is_root:
        classes.extend(["mx-auto", "max-w-[1440px]", "px-[20px]", "md:px-[80px]"])

    opening = f'{pad}<{tag} class="{" ".join(dedupe_classes(classes))}">'
    closing = f"{pad}</{tag}>"

    if not children:
        if tag == "button":
            label = extract_text(node) or node.get("name") or "Button"
            base = dedupe_classes(classes + ["px-[16px]", "py-[10px]", "rounded-[8px]", "bg-gray-900", "text-white"])
            return f'{pad}<button class="{" ".join(base)}">{html.escape(label)}</button>'
        return f"{opening}{closing[len(pad):]}"

    rendered_children = []
    for child in children:
        chunk = render_node(
            child,
            category=category,
            is_root=False,
            indent=indent + 2,
            parent=node,
            responsive=responsive,
        )
        if chunk:
            rendered_children.append(chunk)

    if not rendered_children:
        return f"{opening}{closing[len(pad):]}"

    return "\n".join([opening, *rendered_children, closing])


def api_get(path: str, max_retries: int = 6, base_delay: float = 2.0) -> dict:
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

    for attempt in range(max_retries):
        try:
            with urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", base_delay * (2 ** attempt)))
                print(
                    f"[RATE LIMIT] 429 — wacht {retry_after}s (poging {attempt + 1}/{max_retries})",
                    file=sys.stderr,
                )
                time.sleep(retry_after)
            else:
                raise

    raise RuntimeError(f"API call mislukt na {max_retries} pogingen: {path}")


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
            used_api = True
            nodes = payload.get("nodes", {})
            for cid in id_batch:
                doc = nodes.get(cid, {}).get("document")
                if doc:
                    by_id[cid] = doc
        except (HTTPError, URLError, RuntimeError) as exc:
            print(f"[WARN] Kon component-batch niet ophalen via API ({id_batch[0]}..): {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[WARN] Onverwachte fout bij API-fetch ({id_batch[0]}..): {exc}", file=sys.stderr)
        finally:
            time.sleep(1.5)  # 1.5s tussen batches
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
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>{safe_title}</title>
    <script src=\"https://cdn.tailwindcss.com\"></script>
    <style>
      html, body {{ margin: 0; padding: 0; }}
    </style>
  </head>
  <body class=\"bg-white text-gray-900 antialiased font-sans\">
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

        # Resolve the desktop breakpoint — used both for rendering and Figma PNG export
        figma_export_node_id = component.get("id")
        if node.get("type") == "COMPONENT_SET":
            desktop_child = get_desktop_child(node)
            if desktop_child and desktop_child.get("id"):
                figma_export_node_id = desktop_child["id"]

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
                "source_node_id": figma_export_node_id,
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
