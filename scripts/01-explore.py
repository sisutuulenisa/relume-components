#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


FILE_KEY = "csPgPVhduXpcjSAKHqsygR"
API_BASE = "https://api.figma.com/v1"
OUTPUT_PATH = Path(__file__).resolve().parent / "pages.json"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


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


def fetch_file(depth: int = 1) -> dict:
    token = os.environ.get("FIGMA_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("FIGMA_PERSONAL_ACCESS_TOKEN ontbreekt in omgeving/.env")

    url = f"{API_BASE}/files/{FILE_KEY}?depth={depth}"
    request = Request(
        url,
        headers={
            "X-Figma-Token": token,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    load_env(ENV_PATH)
    try:
        payload = fetch_file(depth=1)
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

    pages = []
    document = payload.get("document", {})
    for child in document.get("children", []):
        if child.get("type") == "CANVAS":
            pages.append(
                {
                    "id": child.get("id"),
                    "name": child.get("name"),
                    "type": child.get("type"),
                }
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "file_key": FILE_KEY,
                "api_base": API_BASE,
                "page_count": len(pages),
                "pages": pages,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Gevonden pagina's ({len(pages)}):")
    for page in pages:
        print(f"- {page['name']} ({page['id']})")
    print(f"\nOpgeslagen naar: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
