#!/usr/bin/env python3
import json
import math
import os
import random
import subprocess
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageOps

ROOT = Path('/home/sisu/.openclaw/workspace/local/projects/straffesites/relume')
MANIFEST = ROOT / 'visual-qc-manifest.json'
STATUS = ROOT / 'visual-qc-status.json'
SHOT_DIR = Path('/home/sisu/.openclaw/workspace/local/screenshots/relume-visual-qc')
BATCH_ID = 'vqc-077'
FIGMA_FILE = 'csPgPVhduXpcjSAKHqsygR'
SERVER = 'http://127.0.0.1:7842'


def sh(cmd):
    return subprocess.run(cmd, shell=True, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def ensure_server():
    p = subprocess.run("lsof -i :7842 -P -n", shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0 or 'LISTEN' not in p.stdout:
        subprocess.Popen(
            ['python3', '-m', 'http.server', '7842'],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)


def safe_name(path):
    return path.replace('/', '__').replace('.html', '')


def backoff_sleep(attempt):
    time.sleep(random.randint(30, 60) + attempt)


def fetch_figma_urls(node_ids, token):
    out = {}
    chunk_size = 10
    for i in range(0, len(node_ids), chunk_size):
        chunk = node_ids[i:i + chunk_size]
        params = urlencode({'ids': ','.join(chunk), 'format': 'png', 'scale': '2'})
        req = Request(f'https://api.figma.com/v1/images/{FIGMA_FILE}?{params}', headers={'X-Figma-Token': token})
        for attempt in range(6):
            try:
                with urlopen(req) as resp:
                    payload = json.loads(resp.read().decode('utf-8'))
                if payload.get('err'):
                    raise RuntimeError(payload['err'])
                out.update(payload.get('images', {}))
                break
            except HTTPError as e:
                if e.code == 429 and attempt < 5:
                    backoff_sleep(attempt)
                    continue
                raise
            except Exception:
                if attempt == 5:
                    raise
                backoff_sleep(attempt)
    return out


def download(url, dest):
    for attempt in range(6):
        try:
            req = Request(url)
            with urlopen(req) as resp:
                data = resp.read()
            dest.write_bytes(data)
            return
        except HTTPError as e:
            if e.code == 429 and attempt < 5:
                backoff_sleep(attempt)
                continue
            raise
        except Exception:
            if attempt == 5:
                raise
            backoff_sleep(attempt)


def capture(url, out_path, viewport):
    session = f"vqc077-{int(time.time()*1000)}"
    sh(f"agent-browser --session {session} open '{url}' --viewport {viewport}")
    sh(f"agent-browser --session {session} screenshot '{out_path}' --full")
    try:
        sh(f"agent-browser --session {session} close")
    except Exception:
        pass


def metrics(a_path, b_path):
    a = Image.open(a_path).convert('RGB')
    b = Image.open(b_path).convert('RGB')
    a2 = ImageOps.fit(a, b.size, method=Image.Resampling.LANCZOS)
    pa = a2.load()
    pb = b.load()
    w, h = b.size
    n = w * h * 3
    abs_sum = 0.0
    sq_sum = 0.0
    for y in range(h):
        for x in range(w):
            r1, g1, b1 = pa[x, y]
            r2, g2, b2 = pb[x, y]
            for d in (r1 - r2, g1 - g2, b1 - b2):
                ad = abs(d)
                abs_sum += ad
                sq_sum += d * d
    mae = abs_sum / (n * 255.0)
    rms = math.sqrt(sq_sum / n) / 255.0
    return mae, rms


def grade(mae, rms):
    if mae <= 0.030 and rms <= 0.100:
        return 'ok'
    if mae <= 0.080 and rms <= 0.220:
        return 'warn'
    return 'fail'


def worst(a, b):
    order = {'ok': 0, 'warn': 1, 'fail': 2}
    return a if order[a] >= order[b] else b


def atomic_write(path, data):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def main():
    token = os.environ.get('FIGMA_PERSONAL_ACCESS_TOKEN', '').strip()
    if not token:
        raise RuntimeError('Missing FIGMA_PERSONAL_ACCESS_TOKEN')

    ensure_server()
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    batch = next(b for b in manifest['batches'] if b['id'] == BATCH_ID)
    components = batch['components']

    node_ids = [c['nodeId'] for c in components]
    figma_urls = fetch_figma_urls(node_ids, token)

    status = json.loads(STATUS.read_text(encoding='utf-8'))

    counts = {'ok': 0, 'warn': 0, 'fail': 0}
    warn_list = []
    fail_list = []

    for comp in components:
        path = comp['path']
        node = comp['nodeId']
        base = safe_name(path)

        figma_path = SHOT_DIR / f"{base}-figma.png"
        local_d = SHOT_DIR / f"{base}-local-desktop.png"
        local_m = SHOT_DIR / f"{base}-local-mobile.png"

        url = figma_urls.get(node)
        if not url:
            raise RuntimeError(f'No Figma image URL for {node}')
        download(url, figma_path)

        local_url = f"{SERVER}/{path}"
        capture(local_url, local_d, '1440x2200')
        capture(local_url, local_m, '390x844')

        d_mae, d_rms = metrics(figma_path, local_d)
        m_mae, m_rms = metrics(figma_path, local_m)
        d_status = grade(d_mae, d_rms)
        m_status = grade(m_mae, m_rms)
        overall = worst(d_status, m_status)

        issues = []
        if d_status != 'ok':
            issues.append(f"desktop diff high (mae={d_mae:.4f}, rms={d_rms:.4f})")
        if m_status != 'ok':
            issues.append(f"mobile diff high (mae={m_mae:.4f}, rms={m_rms:.4f})")

        rel_figma = f"relume-visual-qc/{figma_path.name}"
        rel_d = f"relume-visual-qc/{local_d.name}"
        rel_m = f"relume-visual-qc/{local_m.name}"

        status[path] = {
            'status': overall,
            'checkedAt': str(date.today()),
            'desktopStatus': d_status,
            'mobileStatus': m_status,
            'issues': issues,
            'notes': f"{BATCH_ID} auto-compare desktop mae={d_mae:.4f} rms={d_rms:.4f}; mobile mae={m_mae:.4f} rms={m_rms:.4f}",
            'figmaScreenshot': rel_figma,
            'localScreenshot': rel_d,
            'localMobileScreenshot': rel_m,
            'paths': {
                'figmaDesktop': rel_figma,
                'localDesktop': rel_d,
                'localMobile': rel_m,
            },
        }

        counts[overall] += 1
        if overall == 'warn':
            warn_list.append(path)
        if overall == 'fail':
            fail_list.append(path)

    atomic_write(STATUS, status)

    print(json.dumps({'counts': counts, 'warn': warn_list, 'fail': fail_list}, indent=2))


if __name__ == '__main__':
    main()
