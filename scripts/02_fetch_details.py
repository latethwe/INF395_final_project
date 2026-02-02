import json
import re
import time
import random
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

SHOW_URL = "https://krisha.kz/a/show/{ad_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

TARGET_OK = 2000
MIN_IMAGES = 3

# ---------- helpers ----------
def clean_text(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()

def parse_price_digits(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    val = int(digits)
    return val if val >= 1_000_000 else None

def parse_area_from_text(text: str) -> float | None:
    t = clean_text(text)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*м²", t)
    if not m:
        return None
    return float(m.group(1).replace(",", "."))

def extract_price(soup: BeautifulSoup) -> int | None:
    price_el = soup.select_one(".offer__price")
    if not price_el:
        return None
    txt = clean_text(price_el.get_text(" ", strip=True))
    low = txt.lower()
    if re.search(r"(^|\s)от(\s|$)", low):  # skip "от"
        return None
    if "~" in txt or "≈" in txt:
        return None
    return parse_price_digits(txt)

def extract_area(soup: BeautifulSoup) -> float | None:
    h1 = soup.find("h1")
    if h1:
        a = parse_area_from_text(h1.get_text(" ", strip=True))
        if a:
            return a
    short = soup.select_one(".offer__short-description")
    if short:
        a = parse_area_from_text(short.get_text(" ", strip=True))
        if a:
            return a
    for tag in soup.find_all(["div", "span", "li"]):
        txt = tag.get_text(" ", strip=True)
        if "м²" in txt:
            a = parse_area_from_text(txt)
            if a and a > 10:
                return a
    return None

def extract_rooms_from_title(soup: BeautifulSoup) -> int | None:
    h1 = soup.find("h1")
    if not h1:
        return None
    t = clean_text(h1.get_text(" ", strip=True)).lower()
    m = re.search(r"(\d+)\s*[- ]?\s*комнат", t)
    if not m:
        return None
    v = int(m.group(1))
    return v if 0 < v < 20 else None

def find_info_value(soup: BeautifulSoup, data_name: str) -> str | None:
    item = soup.select_one(f'.offer__info-item[data-name="{data_name}"] .offer__advert-short-info')
    if not item:
        return None
    return clean_text(item.get_text(" ", strip=True))

def extract_city_district(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    span = soup.select_one(".offer__location span")
    if not span:
        return None, None
    txt = clean_text(span.get_text(" ", strip=True))
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    city = parts[0] if parts else None
    district = parts[1] if len(parts) >= 2 else None
    return city, district

def extract_floor_pair(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    val = find_info_value(soup, "flat.floor")
    if not val:
        return None, None
    m = re.search(r"(\d+)\s*из\s*(\d+)", val.lower())
    if not m:
        return None, None
    floor = int(m.group(1))
    total = int(m.group(2))
    if floor <= 0 or total <= 0:
        return None, None
    return floor, total

def extract_year_built(soup: BeautifulSoup) -> int | None:
    val = find_info_value(soup, "house.year")
    if not val:
        return None
    m = re.search(r"\d{4}", val)
    if not m:
        return None
    y = int(m.group(0))
    return y if 1800 <= y <= 2100 else None

def extract_building_type(soup: BeautifulSoup) -> str | None:
    v = find_info_value(soup, "flat.building")
    return v or None

def extract_images(soup: BeautifulSoup) -> list[str]:
    urls = []
    seen = set()

    for el in soup.select(".gallery__small-item[data-photo-url]"):
        u = clean_text(el.get("data-photo-url") or "")
        if not u or "empty-photo" in u:
            continue
        if "750x470" in u and u not in seen:
            seen.add(u)
            urls.append(u)

    if not urls:
        for el in soup.select(".gallery__small-item[data-photo-url]"):
            u = clean_text(el.get("data-photo-url") or "")
            if u and "empty-photo" not in u and u not in seen:
                seen.add(u)
                urls.append(u)

    return urls

def is_valid(rec: dict) -> bool:
    required = [
        rec.get("price"),
        rec.get("area"),
        rec.get("rooms"),
        rec.get("city"),
        rec.get("district"),
        rec.get("building_type"),
        rec.get("year_built"),
        rec.get("floor"),
        rec.get("floors_total"),
    ]
    if any(x is None for x in required):
        return False
    if not rec.get("image_urls") or len(rec["image_urls"]) < MIN_IMAGES:
        return False
    return True

def count_valid(out_dir: str) -> int:
    n = 0
    for fp in Path(out_dir).glob("*.json"):
        try:
            rec = json.loads(fp.read_text(encoding="utf-8"))
            if is_valid(rec):
                n += 1
        except Exception:
            continue
    return n

# ---------- main ----------
def main(
    ids_path="data/index/ad_ids.txt",
    out_dir="data/raw_ads",
    sleep_min=1.0,
    sleep_max=2.0,
    limit=None,
):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    session = requests.Session()

    # already have
    ok = count_valid(out_dir)
    print(f"Already valid: {ok}/{TARGET_OK}")

    ad_ids = [x.strip() for x in Path(ids_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if limit:
        ad_ids = ad_ids[:limit]

    for ad_id in tqdm(ad_ids, desc="Ads"):
        if ok >= TARGET_OK:
            print(f"Reached TARGET_OK={TARGET_OK}. Stop.")
            break

        out_path = Path(out_dir) / f"{ad_id}.json"
        if out_path.exists():
            # может уже скачано; пересчитывать не будем
            continue

        url = SHOW_URL.format(ad_id=ad_id)
        try:
            r = session.get(url, headers=HEADERS, timeout=30)
        except Exception:
            continue
        if r.status_code != 200:
            continue

        soup = BeautifulSoup(r.text, "lxml")

        price = extract_price(soup)
        if price is None:
            continue

        area = extract_area(soup)
        rooms = extract_rooms_from_title(soup)
        city, district = extract_city_district(soup)
        building_type = extract_building_type(soup)
        year_built = extract_year_built(soup)
        floor, floors_total = extract_floor_pair(soup)
        images = extract_images(soup)

        rec = {
            "ad_id": ad_id,
            "url": url,
            "price": price,
            "area": area,
            "price_per_m2": (price / area) if price and area else None,
            "rooms": rooms,
            "city": city,
            "district": district,
            "building_type": building_type,
            "year_built": year_built,
            "floor": floor,
            "floors_total": floors_total,
            "image_urls": images,
        }

        if not is_valid(rec):
            continue

        out_path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        ok += 1

        time.sleep(random.uniform(sleep_min, sleep_max))

    print(f"Done. Valid saved: {ok}/{TARGET_OK}")

if __name__ == "__main__":
    main()
