import json
import time
import random
from pathlib import Path
from urllib.parse import urlparse

import requests
from tqdm import tqdm

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
}

def guess_ext(url: str, content_type: str | None) -> str:
    path = urlparse(url).path.lower()
    if path.endswith(".webp"):
        return ".webp"
    if path.endswith(".png"):
        return ".png"
    if path.endswith(".jpg") or path.endswith(".jpeg"):
        return ".jpg"
    if content_type:
        ct = content_type.lower()
        if "webp" in ct: return ".webp"
        if "png" in ct: return ".png"
        if "jpeg" in ct or "jpg" in ct: return ".jpg"
    return ".jpg"

def main(raw_dir="data/raw_ads", img_root="data/images", max_images=10,
         sleep_min=0.2, sleep_max=0.6):
    Path(img_root).mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    raw_files = sorted(Path(raw_dir).glob("*.json"))
    for fp in tqdm(raw_files, desc="Download images"):
        rec = json.loads(fp.read_text(encoding="utf-8"))
        ad_id = rec["ad_id"]
        urls = rec.get("image_urls") or []
        if not urls:
            continue

        out_dir = Path(img_root) / ad_id
        out_dir.mkdir(parents=True, exist_ok=True)

        for i, url in enumerate(urls[:max_images], start=1):
            try:
                r = session.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 200 and r.content:
                    ext = guess_ext(url, r.headers.get("Content-Type"))
                    out_path = out_dir / f"{i:02d}{ext}"
                    if not out_path.exists():
                        out_path.write_bytes(r.content)
            except Exception:
                pass
            time.sleep(random.uniform(sleep_min, sleep_max))

if __name__ == "__main__":
    main()
