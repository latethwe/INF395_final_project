import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


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
    urls: list[str] = []
    seen: set[str] = set()

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


def _normalize_krisha_url(url: str) -> tuple[str, str | None]:
    raw = (url or "").strip()
    if not raw:
        raise ValueError("Пустая ссылка")

    m = re.search(r"(\d{6,})", raw)
    ad_id = m.group(1) if m else None

    if raw.isdigit():
        return f"https://krisha.kz/a/show/{raw}", raw

    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "https://" + raw

    parsed = urlparse(raw)
    if "krisha.kz" not in parsed.netloc.lower():
        raise ValueError("Ссылка должна быть с домена krisha.kz")

    return raw, ad_id


def fetch_listing(url: str, session: requests.Session | None = None) -> dict[str, Any]:
    s = session or requests.Session()
    norm_url, ad_id = _normalize_krisha_url(url)

    r = s.get(norm_url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise ValueError(f"Не удалось открыть объявление (HTTP {r.status_code})")

    soup = BeautifulSoup(r.text, "lxml")
    price = extract_price(soup)
    area = extract_area(soup)
    rooms = extract_rooms_from_title(soup)
    city, district = extract_city_district(soup)
    building_type = extract_building_type(soup)
    residential_complex = extract_residential_complex(soup)
    year_built = extract_year_built(soup)
    floor, floors_total = extract_floor_pair(soup)
    latitude, longitude = extract_coordinates(r.text, soup)
    image_urls = extract_images(soup)

    if ad_id is None:
        m = re.search(r"/a/show/(\d+)", r.url)
        if m:
            ad_id = m.group(1)

    rec: dict[str, Any] = {
        "ad_id": ad_id,
        "url": r.url or norm_url,
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
        "image_urls": image_urls,
    }
    return rec


def _safe_image_suffix(url: str, content_type: str) -> str:
    c = (content_type or "").lower()
    if "png" in c:
        return ".png"
    if "webp" in c:
        return ".webp"
    if "jpeg" in c or "jpg" in c:
        return ".jpg"

    path = urlparse(url).path.lower()
    if path.endswith(".png"):
        return ".png"
    if path.endswith(".webp"):
        return ".webp"
    return ".jpg"


def download_images(image_urls: list[str], out_dir: Path, max_images: int, session: requests.Session | None = None) -> list[Path]:
    s = session or requests.Session()
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    for i, u in enumerate((image_urls or [])[:max_images], start=1):
        try:
            rr = s.get(u, headers=HEADERS, timeout=30)
            if rr.status_code != 200 or not rr.content:
                continue
            ext = _safe_image_suffix(u, rr.headers.get("Content-Type", ""))
            fp = out_dir / f"{i:02d}{ext}"
            fp.write_bytes(rr.content)
            saved.append(fp)
        except Exception:
            continue
    return saved


def build_model_payload_from_listing(rec: dict[str, Any]) -> dict[str, Any]:
    required = ("area", "rooms", "floor", "floors_total", "year_built")
    missing = [k for k in required if rec.get(k) in (None, "")]
    if missing:
        raise ValueError("Не удалось извлечь обязательные поля: " + ", ".join(missing))

    district = str(rec.get("district") or "").strip() or "unknown"
    building_type = str(rec.get("building_type") or "").strip() or "unknown"
    residential_complex = rec.get("residential_complex")
    if isinstance(residential_complex, str):
        residential_complex = residential_complex.strip() or None

    return {
        "area": float(rec["area"]),
        "rooms": int(rec["rooms"]),
        "floor": int(rec["floor"]),
        "floors_total": int(rec["floors_total"]),
        "year_built": int(rec["year_built"]),
        "district": district,
        "building_type": building_type,
        "residential_complex": residential_complex,
        "latitude": rec.get("latitude"),
        "longitude": rec.get("longitude"),
    }


def make_price_diff(pred_price: Optional[float], actual_price: Optional[float]) -> dict[str, Any]:
    if pred_price is None or actual_price is None or float(actual_price) <= 0:
        return {"pred": pred_price, "actual": actual_price, "diff": None, "diff_pct": None}
    diff = float(pred_price) - float(actual_price)
    diff_pct = (diff / float(actual_price)) * 100.0
    return {"pred": float(pred_price), "actual": float(actual_price), "diff": diff, "diff_pct": diff_pct}

