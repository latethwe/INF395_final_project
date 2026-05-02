import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

SHOW_URL = "https://krisha.kz/a/show/{ad_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

TARGET_OK = 25_000
MIN_IMAGES = 4
MAX_IMAGE_URLS = 10

CONDITION_SYNONYMS = {
    "fresh": [
        "свежий ремонт",
        "евроремонт",
        "новый ремонт",
        "после ремонта",
        "дизайнерский ремонт",
        "хорошее состояние",
    ],
    "average": [
        "косметический ремонт",
        "среднее состояние",
        "нормальное состояние",
        "требуется косметический",
    ],
    "needs": [
        "требует ремонта",
        "без ремонта",
        "черновая",
        "черновая отделка",
        "под ремонт",
        "незавершенный ремонт",
    ],
}

OBJECT_HINTS = {
    "flat": ["квартира", "квартиры", "/kvartiry/"],
    "house": ["дом", "дома", "/doma/"],
    "dacha": ["дача", "дачи", "/dachi/"],
    "commercial": ["коммерчес", "/kommercheskaya/"],
}


# ---------- helpers ----------
def clean_text(s: str) -> str:
    return (s or "").replace("\xa0", " ").strip()


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", clean_text(s))


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
    if re.search(r"(^|\s)от(\s|$)", low):
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


def find_info_value_by_label(soup: BeautifulSoup, label: str) -> str | None:
    label_norm = clean_text(label).lower()
    for item in soup.select(".offer__info-item"):
        title = item.select_one(".offer__info-title")
        value = item.select_one(".offer__advert-short-info")
        if not title or not value:
            continue
        t = clean_text(title.get_text(" ", strip=True)).lower()
        if t == label_norm:
            v = clean_text(value.get_text(" ", strip=True))
            return v or None
    return None


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


def extract_residential_complex(soup: BeautifulSoup) -> str | None:
    for data_name in ("map.complex", "flat.complex", "house.complex", "residential.complex"):
        v = find_info_value(soup, data_name)
        if v:
            return v

    for label in ("Жилой комплекс", "ЖК"):
        v = find_info_value_by_label(soup, label)
        if v:
            return v

    return None


def extract_condition_raw(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    for label in ("Состояние квартиры", "Состояние дома"):
        v = find_info_value_by_label(soup, label)
        if v:
            return v, "listing_tag"

    for data_name in ("flat.renovation", "house.condition", "condition"):
        v = find_info_value(soup, data_name)
        if v:
            return v, "listing_tag"

    return None, None


def normalize_condition(value: str | None) -> str:
    txt = normalize_whitespace(value or "").lower()
    if not txt:
        return "unknown"

    for norm, patterns in CONDITION_SYNONYMS.items():
        for p in patterns:
            if p in txt:
                return norm

    if "ремонт" in txt and "треб" in txt:
        return "needs"
    if "ремонт" in txt and ("евро" in txt or "дизайн" in txt or "свеж" in txt):
        return "fresh"
    if "ремонт" in txt:
        return "average"
    return "unknown"


def condition_from_description(description: str | None) -> tuple[str, str | None]:
    if not description:
        return "unknown", None
    norm = normalize_condition(description)
    if norm == "unknown":
        return norm, None
    return norm, "description"


def extract_description(soup: BeautifulSoup) -> str | None:
    selectors = [
        "div.offer__description",
        "section.offer__description",
        "[data-name='text'] .text",
        "[itemprop='description']",
        ".a-options-text",
    ]
    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            txt = normalize_whitespace(node.get_text(" ", strip=True))
            if txt:
                return txt

    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or ""
        if '"description"' not in raw:
            continue
        m = re.search(r'"description"\s*:\s*"(.*?)"\s*(,|})', raw, flags=re.DOTALL)
        if not m:
            continue
        txt = m.group(1)
        txt = txt.encode("utf-8", errors="ignore").decode("unicode_escape", errors="ignore")
        txt = normalize_whitespace(txt)
        if txt:
            return txt

    return None


def infer_object_type(url: str, soup: BeautifulSoup) -> str:
    haystacks = [url.lower()]
    h1 = soup.find("h1")
    if h1:
        haystacks.append(clean_text(h1.get_text(" ", strip=True)).lower())

    merged = " ".join(haystacks)
    for object_type, hints in OBJECT_HINTS.items():
        if any(h in merged for h in hints):
            return object_type
    return "unknown"


def _parse_coord_value(x: str | float | int | None) -> float | None:
    if x is None:
        return None
    s = str(x).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _valid_lat_lon(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def extract_coordinates(html: str, soup: BeautifulSoup) -> tuple[float | None, float | None]:
    attr_pairs = [
        ("data-lat", "data-lon"),
        ("data-latitude", "data-longitude"),
        ("data-geo-lat", "data-geo-lon"),
        ("data-map-lat", "data-map-lon"),
    ]
    for lat_attr, lon_attr in attr_pairs:
        for el in soup.select(f"[{lat_attr}][{lon_attr}]"):
            lat = _parse_coord_value(el.get(lat_attr))
            lon = _parse_coord_value(el.get(lon_attr))
            if _valid_lat_lon(lat, lon):
                return lat, lon

    patterns = [
        r'"lat(?:itude)?"\s*:\s*([+-]?\d+(?:[.,]\d+)?)\s*,\s*"(?:lon|lng|longitude)"\s*:\s*([+-]?\d+(?:[.,]\d+)?)',
        r'"(?:lon|lng|longitude)"\s*:\s*([+-]?\d+(?:[.,]\d+)?)\s*,\s*"lat(?:itude)?"\s*:\s*([+-]?\d+(?:[.,]\d+)?)',
        r'lat(?:itude)?\s*[:=]\s*([+-]?\d+(?:[.,]\d+)?)\s*[,;]\s*(?:lon|lng|longitude)\s*[:=]\s*([+-]?\d+(?:[.,]\d+)?)',
    ]

    for i, p in enumerate(patterns):
        m = re.search(p, html, flags=re.IGNORECASE)
        if not m:
            continue

        if i == 1:
            lon = _parse_coord_value(m.group(1))
            lat = _parse_coord_value(m.group(2))
        else:
            lat = _parse_coord_value(m.group(1))
            lon = _parse_coord_value(m.group(2))

        if _valid_lat_lon(lat, lon):
            return lat, lon

    return None, None


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


def has_new_schema(rec: dict) -> bool:
    required_keys = [
        "description",
        "object_type",
        "condition_raw",
        "condition_norm",
        "condition_source",
        "condition_confidence",
        "collected_at",
    ]
    return all(k in rec for k in required_keys)


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
    refresh_existing_missing_fields=True,
):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    session = requests.Session()

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
            if not refresh_existing_missing_fields:
                continue
            try:
                existing = json.loads(out_path.read_text(encoding="utf-8"))
                if is_valid(existing) and has_new_schema(existing):
                    continue
            except Exception:
                pass

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
        residential_complex = extract_residential_complex(soup)
        year_built = extract_year_built(soup)
        floor, floors_total = extract_floor_pair(soup)
        images = extract_images(soup)
        latitude, longitude = extract_coordinates(r.text, soup)
        description = extract_description(soup)
        object_type = infer_object_type(url, soup)

        condition_raw, condition_source = extract_condition_raw(soup)
        condition_norm = normalize_condition(condition_raw)
        condition_confidence = 0.9 if condition_norm != "unknown" else 0.0

        if condition_norm == "unknown":
            cond_from_text, cond_source_text = condition_from_description(description)
            if cond_from_text != "unknown":
                condition_norm = cond_from_text
                condition_source = cond_source_text
                condition_confidence = 0.55

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
            "residential_complex": residential_complex,
            "year_built": year_built,
            "floor": floor,
            "floors_total": floors_total,
            "latitude": latitude,
            "longitude": longitude,
            "image_urls": images[:MAX_IMAGE_URLS],
            "description": description,
            "object_type": object_type,
            "condition_raw": condition_raw,
            "condition_norm": condition_norm,
            "condition_source": condition_source,
            "condition_confidence": condition_confidence,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        }

        if not is_valid(rec):
            continue

        out_path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        ok += 1

        time.sleep(random.uniform(sleep_min, sleep_max))

    print(f"Done. Valid saved: {ok}/{TARGET_OK}")


if __name__ == "__main__":
    main()
