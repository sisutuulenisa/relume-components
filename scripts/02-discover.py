#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
API_BASE = "https://api.figma.com/v1"
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
ENV_PATH = ROOT_DIR / ".env"
PAGES_PATH = SCRIPT_DIR / "pages.json"
OUTPUT_PATH = SCRIPT_DIR / "components-raw.json"

ALLOWED_COMPONENT_TYPES = {"FRAME", "COMPONENT", "COMPONENT_SET", "INSTANCE"}


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


def clean_page_name(name: str) -> str:
    cleaned = re.sub(r"^[\s↳]+", "", name or "").strip()
    return re.sub(r"\s+", " ", cleaned)


def is_overlay_page(name: str) -> bool:
    normalized = clean_page_name(name).lower()
    if not normalized:
        return True
    if all(ch in {"-", "–", "—"} for ch in normalized):
        return True

    if normalized.startswith("welcome"):
        return True
    if normalized.startswith("changelog"):
        return True
    if normalized.startswith("workspace"):
        return True

    if normalized in {"sitemap", "wireframe", "style guide", "design"}:
        return True

    if normalized.endswith("components"):
        return True

    if "deprecated" in normalized and "components" in normalized:
        return True

    return False


def build_component_meta(node: dict, page_id: str, page_name: str, path: list[str], top_level: bool) -> dict:
    return {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
        "page_id": page_id,
        "page_name": page_name,
        "top_level": top_level,
        "path": " / ".join(path + [node.get("name", "")]).strip(" /"),
        "node": node,
    }


def walk_components(node: dict, page_id: str, page_name: str, path: list[str], results: list[dict], top_level: bool) -> None:
    node_type = node.get("type")
    current_path = path + [node.get("name", "")]

    if node_type in ALLOWED_COMPONENT_TYPES:
        results.append(build_component_meta(node, page_id, page_name, path, top_level))

    for child in node.get("children", []) or []:
        walk_components(
            child,
            page_id=page_id,
            page_name=page_name,
            path=current_path,
            results=results,
            top_level=False,
        )


def load_pages() -> list[dict]:
    if not PAGES_PATH.exists():
        raise RuntimeError("scripts/pages.json niet gevonden. Run eerst scripts/01-explore.py")
    data = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
    return data.get("pages", [])


def main() -> int:
    load_env(ENV_PATH)

    try:
        pages = load_pages()
    except Exception as exc:
        print(f"Fout bij laden van pages.json: {exc}", file=sys.stderr)
        return 1

    kept_pages = []
    skipped_pages = []
    total_components = 0

    for page in pages:
        page_id = page.get("id")
        page_name_raw = page.get("name", "")
        page_name = clean_page_name(page_name_raw)
        if not page_id:
            continue

        if is_overlay_page(page_name_raw):
            skipped_pages.append(
                {
                    "id": page_id,
                    "name": page_name_raw,
                    "reason": "overlay/workspace/separator",
                }
            )
            continue

        path = f"/files/{FILE_KEY}/nodes?ids={quote(page_id, safe='')}"
        try:
            node_payload = api_get(path)
        except HTTPError as exc:
            print(f"HTTP fout voor pagina {page_name} ({page_id}): {exc.code} {exc.reason}", file=sys.stderr)
            try:
                body = exc.read().decode("utf-8")
                if body:
                    print(body, file=sys.stderr)
            except Exception:
                pass
            return 1
        except URLError as exc:
            print(f"Netwerkfout voor pagina {page_name} ({page_id}): {exc.reason}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"Onverwachte fout voor pagina {page_name} ({page_id}): {exc}", file=sys.stderr)
            return 1

        page_document = node_payload.get("nodes", {}).get(page_id, {}).get("document")
        if not page_document:
            print(f"Waarschuwing: geen document voor pagina {page_name} ({page_id})", file=sys.stderr)
            continue

        top_level_components = []
        recursive_components = []
        for child in page_document.get("children", []) or []:
            if child.get("type") in ALLOWED_COMPONENT_TYPES:
                top_level_components.append(build_component_meta(child, page_id, page_name, [page_name], top_level=True))
            walk_components(
                child,
                page_id=page_id,
                page_name=page_name,
                path=[page_name],
                results=recursive_components,
                top_level=False,
            )

        kept_pages.append(
            {
                "id": page_id,
                "name": page_name,
                "raw_name": page_name_raw,
                "top_level_component_count": len(top_level_components),
                "recursive_component_count": len(recursive_components),
                "components": top_level_components,
                "recursive_components": recursive_components,
            }
        )
        total_components += len(top_level_components)
        print(
            f"[OK] {page_name}: top-level={len(top_level_components)}, recursive={len(recursive_components)}"
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "file_key": FILE_KEY,
                "api_base": API_BASE,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "kept_page_count": len(kept_pages),
                "skipped_page_count": len(skipped_pages),
                "total_top_level_components": total_components,
                "kept_pages": kept_pages,
                "skipped_pages": skipped_pages,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\nBewaarde pagina's: {len(kept_pages)}")
    print(f"Overgeslagen pagina's: {len(skipped_pages)}")
    print(f"Totaal top-level componenten: {total_components}")
    print(f"Opgeslagen naar: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
