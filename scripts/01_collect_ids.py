import os
import re
import time
import random
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

LIST_URL = "https://krisha.kz/prodazha/kvartiry/almaty/"
ID_RE = re.compile(r"/a/show/(\d+)")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

def extract_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    ids = set()
    for a in soup.select("a[href*='/a/show/']"):
        href = a.get("href", "")
        m = ID_RE.search(href)
        if m:
            ids.add(m.group(1))
    return ids

def main(out_path="data/index/ad_ids.txt", pages=250, sleep_min=1.0, sleep_max=2.0):
    os.makedirs("data/index", exist_ok=True)
    session = requests.Session()

    all_ids = set()
    for page in tqdm(range(1, pages + 1), desc="Pages"):
        params = {"page": page} if page > 1 else {}
        url = LIST_URL + ("?" + urlencode(params) if params else "")
        r = session.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        all_ids.update(extract_ids(r.text))
        time.sleep(random.uniform(sleep_min, sleep_max))

    with open(out_path, "w", encoding="utf-8") as f:
        for ad_id in sorted(all_ids):
            f.write(ad_id + "\n")

    print(f"Saved {len(all_ids)} ids -> {out_path}")

if __name__ == "__main__":
    main()
