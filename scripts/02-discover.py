#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
API_BASE = "https://api.figma.com/v1"
PAGES_PATH = Path(__file__).resolve().parent / "pages.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "components-raw.json"
SUBCATEGORY_PREFIX = "    ↳"
SKIP_PAGE_NAMES = {
    "Welcome",
    "Changelog",
    "---",
    "WORKSPACE",
    "MARKETING COMPONENTS",
    "ECOMMERCE COMPONENTS",
    "APPLICATION COMPONENTS",
    "PAGE TEMPLATES",
}
BATCH_SIZE = 10
SLEEP_SECONDS = 1


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


def is_separator(name: str) -> bool:
    stripped = name.strip()
    if not stripped:
        return False
    return all(ch in {"-", "–", "—"} for ch in stripped)


def should_skip_page(name: str) -> bool:
    normalized = " ".join(name.strip().split())
    if not normalized:
        return True

    if is_separator(normalized):
        return True

    for skip_name in SKIP_PAGE_NAMES:
        if normalized == skip_name or normalized.startswith(f"{skip_name} "):
            return True

    return False


def load_pages(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise RuntimeError("Ongeldig pages.json formaat: 'pages' moet een lijst zijn")
    return pages


def filter_pages(pages: list[dict]) -> list[dict]:
    filtered = []
    for page in pages:
        name = page.get("name", "")
        page_id = page.get("id")
        if not isinstance(name, str) or not isinstance(page_id, str):
            continue
        if should_skip_page(name):
            continue
        if not name.startswith(SUBCATEGORY_PREFIX):
            continue
        filtered.append({"id": page_id, "name": name})
    return filtered


def fetch_nodes(page_ids: list[str]) -> dict:
    token = os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("FIGMA_PERSONAL_ACCESS_TOKEN ontbreekt in omgeving/.env")

    ids_param = quote(",".join(page_ids), safe=",:")
    url = f"{API_BASE}/files/{FILE_KEY}/nodes?ids={ids_param}"
    request = Request(
        url,
        headers={
            "X-Figma-Token": token,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_components(pages: list[dict]) -> list[dict]:
    components = []
    total_batches = (len(pages) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_index, start in enumerate(range(0, len(pages), BATCH_SIZE), start=1):
        batch = pages[start : start + BATCH_SIZE]
        batch_ids = [page["id"] for page in batch]
        payload = fetch_nodes(batch_ids)
        nodes = payload.get("nodes", {})

        for page in batch:
            page_id = page["id"]
            page_name = page["name"]
            page_document = (nodes.get(page_id) or {}).get("document") or {}
            for child in page_document.get("children", []):
                child_id = child.get("id")
                child_name = child.get("name")
                if isinstance(child_id, str) and isinstance(child_name, str):
                    components.append(
                        {
                            "id": child_id,
                            "name": child_name,
                            "page_name": page_name,
                            "page_id": page_id,
                        }
                    )

        print(f"Batch {batch_index}/{total_batches} verwerkt ({len(batch_ids)} pagina's)")
        if batch_index < total_batches:
            time.sleep(SLEEP_SECONDS)

    return components


def main() -> int:
    load_env(Path.cwd() / ".env")

    if not PAGES_PATH.exists():
        print(f"Bestand niet gevonden: {PAGES_PATH}", file=sys.stderr)
        return 1

    try:
        pages = load_pages(PAGES_PATH)
        filtered_pages = filter_pages(pages)
        components = discover_components(filtered_pages)
    except HTTPError as exc:
        print(f"HTTP fout: {exc.code} {exc.reason}", file=sys.stderr)
        try:
            body = exc.read().decode("utf-8")
            if body:
                print(body, file=sys.stderr)
        except Exception:
            pass
        return 1
    except URLError as exc:
        print(f"Netwerkfout: {exc.reason}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Onverwachte fout: {exc}", file=sys.stderr)
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "file_key": FILE_KEY,
                "filtered_page_count": len(filtered_pages),
                "component_count": len(components),
                "components": components,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Geselecteerde pagina's: {len(filtered_pages)}")
    print(f"Gevonden componenten: {len(components)}")
    print(f"Opgeslagen naar: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
