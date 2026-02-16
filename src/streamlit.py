import json
from pathlib import Path
import csv

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    import folium
    from streamlit_folium import st_folium
    HAS_MAP_PICKER = True
except Exception:
    HAS_MAP_PICKER = False

st.set_page_config(page_title="Krisha Price Estimator (Demo)", layout="wide")

st.title("Krisha Price Estimator — Demo")
st.caption("Оценка цены + объяснение + ориентир по ремонту + 2–3 похожих объявления")


def load_rc_options() -> list[str]:
    names = set()

    # Single source of truth: curated list from dropdown export
    csv_path = PROJECT_ROOT / "data" / "rc_names" / "almaty_rc_names.csv"
    if csv_path.exists():
        try:
            with csv_path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    v = str((row or {}).get("name") or "").strip()
                    if v:
                        names.add(v)
        except Exception:
            pass

    # Fallback source: raw ads
    raw_dir = PROJECT_ROOT / "data" / "raw_ads"
    if raw_dir.exists():
        for fp in raw_dir.glob("*.json"):
            try:
                rec = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            v = str(rec.get("residential_complex") or "").strip()
            if v:
                names.add(v)

    options = sorted(names, key=lambda x: x.lower())
    return ["Не выбрано"] + options

# -----------------------
# Sidebar inputs
# -----------------------
with st.sidebar:
    st.header("Параметры квартиры")

    area = st.number_input("Площадь, м²", min_value=5.0, max_value=500.0, value=48.0, step=0.1)
    rooms = st.number_input("Комнат", min_value=1, max_value=10, value=2, step=1)
    floor = st.number_input("Этаж", min_value=1, max_value=200, value=2, step=1)
    floors_total = st.number_input("Этажей в доме", min_value=1, max_value=200, value=9, step=1)
    year_built = st.number_input("Год постройки", min_value=1900, max_value=2026, value=2025, step=1)

    district = st.selectbox(
        "Район",
        [
            "Алмалинский р-н",
            "Ауэзовский р-н",
            "Бостандыкский р-н",
            "Жетысуский р-н",
            "Медеуский р-н",
            "Наурызбайский р-н",
            "Турксибский р-н",
            "Алатауский р-н",
        ],
        index=0,
    )

    building_type = st.selectbox(
        "Тип дома",
        ["монолитный", "кирпичный", "панельный", "иной"],
        index=0,
    )

    rc_options = load_rc_options()
    st.caption(f"ЖК в базе: {max(0, len(rc_options) - 1)}")
    if len(rc_options) <= 1:
        st.warning(f"Список ЖК пуст. Проверь файл: {PROJECT_ROOT / 'data' / 'rc_names' / 'almaty_rc_names.csv'}")
    rc_query = st.text_input(
        "ЖК",
        value="",
        placeholder="Начни вводить название ЖК...",
        help="Фильтрация работает по подстроке: остаются только подходящие варианты.",
    )
    q = rc_query.strip().lower()
    if q:
        filtered_rc = [rc_options[0]] + [x for x in rc_options[1:] if q in x.lower()]
    else:
        filtered_rc = rc_options

    if len(filtered_rc) == 1:
        st.caption("По вашему запросу ЖК не найдено в списке.")

    selected_rc = st.selectbox(
        "Выберите ЖК из списка",
        filtered_rc,
        index=0,
        help="Список уже отфильтрован по полю выше.",
    )

    st.divider()
    st.header("Локация")

    if "latitude" not in st.session_state:
        st.session_state["latitude"] = 43.238949
    if "longitude" not in st.session_state:
        st.session_state["longitude"] = 76.889709
    if "map_picked" not in st.session_state:
        st.session_state["map_picked"] = False

    if HAS_MAP_PICKER:
        st.caption("Кликни по карте, чтобы поставить метку и заполнить latitude/longitude")
        fmap = folium.Map(
            location=[st.session_state["latitude"], st.session_state["longitude"]],
            zoom_start=12,
            control_scale=True,
        )
        if st.session_state.get("map_picked", False):
            folium.Marker(
                [st.session_state["latitude"], st.session_state["longitude"]],
                tooltip="Выбранная точка",
            ).add_to(fmap)
        folium.LatLngPopup().add_to(fmap)
        map_state = st_folium(fmap, height=280, use_container_width=True, key="pick_map")
        clicked = (map_state or {}).get("last_clicked")
        if clicked:
            new_lat = round(float(clicked["lat"]), 6)
            new_lon = round(float(clicked["lng"]), 6)
            old_lat = float(st.session_state["latitude"])
            old_lon = float(st.session_state["longitude"])
            if abs(new_lat - old_lat) > 1e-7 or abs(new_lon - old_lon) > 1e-7:
                st.session_state["latitude"] = new_lat
                st.session_state["longitude"] = new_lon
                st.session_state["map_picked"] = True
                st.rerun()
    else:
        st.info("Для выбора точки с карты: pip install folium streamlit-folium")

    latitude = st.number_input(
        "Latitude",
        min_value=-90.0,
        max_value=90.0,
        value=float(st.session_state["latitude"]),
        step=0.000001,
        format="%.6f",
    )
    longitude = st.number_input(
        "Longitude",
        min_value=-180.0,
        max_value=180.0,
        value=float(st.session_state["longitude"]),
        step=0.000001,
        format="%.6f",
    )

    st.session_state["latitude"] = float(latitude)
    st.session_state["longitude"] = float(longitude)

    use_location = st.checkbox(
        "Использовать координаты в оценке",
        value=True,
        help="Если выключить, latitude/longitude не отправляются в API.",
    )

    st.divider()
    st.header("Фото")
    uploaded_files = st.file_uploader(
        "Загрузите 1–7 фото (jpg/jpeg/png/webp)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
    )

    st.divider()
    st.checkbox(
        "Оценка без фото (игнорировать ремонт)",
        key="no_photos_mode",
        help="Используется как базовая оценка без учёта визуального состояния",
    )
    if uploaded_files and len(uploaded_files) > 7:
        st.warning("Будет использовано только первые 7 фото.")

payload = {
    "area": float(area),
    "rooms": int(rooms),
    "floor": int(floor),
    "floors_total": int(floors_total),
    "year_built": int(year_built),
    "district": str(district),
    "building_type": str(building_type),
    "residential_complex": (None if selected_rc == "Не выбрано" else selected_rc),
    "latitude": float(st.session_state["latitude"]) if use_location else None,
    "longitude": float(st.session_state["longitude"]) if use_location else None,
}


# -----------------------
# Helpers
# -----------------------
def fmt_money(x: float) -> str:
    if x is None:
        return "—"
    return f"{x:,.0f} ₸".replace(",", " ")


def fmt_ppm2(x: float) -> str:
    if x is None:
        return "—"
    return f"{x:,.0f} ₸/м²".replace(",", " ")


def fmt_pct(x: float) -> str:
    if x is None:
        return "—"
    sign = "+" if x >= 0 else ""
    return f"{sign}{x:.1f}%"


def build_form_data(data: dict) -> dict:
    out = {}
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        out[k] = str(v)
    return out


def call_predict(files=None, no_photos=False):
    data = build_form_data(payload)
    multipart = []

    if not no_photos:
        for f in (files or [])[:7]:
            multipart.append(("images", (f.name, f.getvalue(), f.type or "application/octet-stream")))

    r = requests.post(f"{API_BASE}/predict", data=data, files=multipart, timeout=180)
    r.raise_for_status()
    return r.json()


def call_explain(files=None, no_photos=False):
    data = build_form_data(payload)
    multipart = []

    if not no_photos:
        for f in (files or [])[:7]:
            multipart.append(("images", (f.name, f.getvalue(), f.type or "application/octet-stream")))

    r = requests.post(f"{API_BASE}/explain", data=data, files=multipart, timeout=180)
    r.raise_for_status()
    return r.json()


def call_predict_by_url(ad_url: str):
    data = {"url": (ad_url or "").strip()}
    r = requests.post(f"{API_BASE}/predict_by_url", data=data, timeout=180)
    r.raise_for_status()
    return r.json()


def safe_get(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def _as_text(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def impacts_to_rows(items):
    rows = []
    for it in items or []:
        rows.append(
            {
                "Фактор": _as_text(it.get("feature_label") or it.get("feature")),
                "Значение": _as_text(it.get("value")),
                "Влияние, % к ₸/м²": float(it.get("impact_pct_ppm2") or 0.0),
                "Влияние, ₸/м²": float(it.get("impact_kzt_ppm2") or 0.0),
                "Влияние, ₸ (всего)": float(it.get("impact_kzt_total") or 0.0),
                "Причина": _as_text(it.get("reason") or ""),
            }
        )
    return rows


def render_comparables(items):
    st.subheader("Похожие объявления")
    if not items:
        st.info("Похожие объявления пока не найдены в локальном датасете.")
        return

    cols = st.columns(min(3, len(items)))
    for i, it in enumerate(items[:3]):
        col = cols[i % len(cols)]
        with col:
            img = it.get("image")
            if isinstance(img, str) and img:
                p = Path(img)
                p_abs = p if p.is_absolute() else (PROJECT_ROOT / p)
                if p_abs.exists():
                    col.image(str(p_abs), caption=f"ad_id: {it.get('ad_id')}", width="stretch")
                elif img.startswith("http://") or img.startswith("https://"):
                    col.image(img, caption=f"ad_id: {it.get('ad_id')}", width="stretch")

            col.markdown(f"**Цена:** {fmt_money(it.get('price'))}")
            col.markdown(f"**₸/м²:** {fmt_ppm2(it.get('price_per_m2'))}")
            col.markdown(f"**Площадь:** {_as_text(it.get('area'))} м²")
            col.markdown(f"**Комнат:** {_as_text(it.get('rooms'))}")
            col.markdown(f"**Район:** {_as_text(it.get('district'))}")
            if it.get("residential_complex"):
                col.markdown(f"**ЖК:** {_as_text(it.get('residential_complex'))}")
            if it.get("distance_km") is not None:
                col.markdown(f"**Дистанция:** {float(it['distance_km']):.2f} км")

            if it.get("url"):
                col.markdown(f"[Открыть объявление]({it['url']})")


# -----------------------
# UI
# -----------------------
st.divider()

c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    run_predict = st.button("Оценить (быстро)", use_container_width=True)
with c2:
    run_explain = st.button("Оценить + объяснить", use_container_width=True)
with c3:
    st.caption("Для объяснения лучше 3–7 фото (кухня, санузел, общая, спальня).")

st.divider()
st.subheader("Оценка по ссылке объявления")
ad_url_input = st.text_input(
    "Ссылка Krisha (или ad_id)",
    value="",
    placeholder="https://krisha.kz/a/show/123456789",
)
run_predict_by_url = st.button("Оценить по ссылке", use_container_width=True)

pred_out = None
exp_out = None
url_out = None

if run_predict:
    try:
        pred_out = call_predict(
            uploaded_files,
            no_photos=st.session_state.get("no_photos_mode", False),
        )
    except requests.HTTPError as e:
        body = ""
        if e.response is not None:
            body = e.response.text[:800]
        st.error(f"Ошибка API /predict: {e}\n\n{body}")
    except Exception as e:
        st.error(f"Ошибка запроса /predict: {e}")

if run_explain:
    try:
        exp_out = call_explain(
            uploaded_files,
            no_photos=st.session_state.get("no_photos_mode", False),
        )
    except requests.HTTPError as e:
        body = ""
        if e.response is not None:
            body = e.response.text[:800]
        st.error(f"Ошибка API /explain: {e}\n\n{body}")
    except Exception as e:
        st.error(f"Ошибка запроса /explain: {e}")

if run_predict_by_url:
    if not ad_url_input.strip():
        st.warning("Введите ссылку на объявление или ad_id.")
    else:
        try:
            url_out = call_predict_by_url(ad_url_input.strip())
        except requests.HTTPError as e:
            body = ""
            if e.response is not None:
                body = e.response.text[:800]
            st.error(f"Ошибка API /predict_by_url: {e}\n\n{body}")
        except Exception as e:
            st.error(f"Ошибка запроса /predict_by_url: {e}")

out = exp_out or pred_out
if out:
    price = safe_get(out, "prediction", "price", default=out.get("price"))
    ppm2 = safe_get(out, "prediction", "price_per_m2", default=out.get("price_per_m2"))
    area_val = safe_get(out, "prediction", "area", default=payload["area"])

    colA, colB, colC = st.columns(3)
    colA.metric("Цена", fmt_money(price))
    colB.metric("Цена за м²", fmt_ppm2(ppm2))
    colC.metric("Площадь", f"{area_val:.1f} м²")

    st.divider()
    comps = out.get("comparables", [])
    render_comparables(comps)

st.divider()

if exp_out:
    st.subheader("Почему такая цена")

    top_pos = safe_get(exp_out, "why_this_price", "top_positive", default=[])
    top_neg = safe_get(exp_out, "why_this_price", "top_negative", default=[])
    summary = safe_get(exp_out, "why_this_price", "summary", default={})

    left, right = st.columns(2)

    with left:
        st.markdown("### Плюсы (поднимают цену)")
        rows = impacts_to_rows(top_pos)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("Плюсы не выделены.")

    with right:
        st.markdown("### Минусы (снижают цену)")
        rows = impacts_to_rows(top_neg)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.info("Минусы не выделены.")

    no_photos_mode = st.session_state.get("no_photos_mode", False)
    photos_used = (not no_photos_mode) and bool(uploaded_files)

    st.markdown("### Сводка")
    big_plus = summary.get("biggest_plus")
    big_minus = summary.get("biggest_minus")
    photos_pct = summary.get("photos_effect_pct_ppm2")
    photos_kzt = summary.get("photos_effect_kzt_total")

    s1, s2, s3 = st.columns(3)
    s1.metric("Главный плюс", big_plus or "—")
    s2.metric("Главный минус", big_minus or "—")
    if not photos_used:
        s3.metric("Фото", "не использовались")
    else:
        s3.metric("Влияние фото", fmt_pct(photos_pct) if photos_pct is not None else "—")

    if photos_kzt is not None:
        st.caption(
            f"Оценочно влияние фото на общую цену: {fmt_money(photos_kzt)} (интерпретация, не точная сумма факторов)."
        )

    st.divider()

    st.subheader("Ремонт/состояние по фото (ориентир)")
    ren = exp_out.get("renovation", {})

    r1, r2, r3 = st.columns(3)
    r1.metric("Оценка", ren.get("condition_label", "—"))
    r2.metric("Уверенность", f"{float(ren.get('confidence', 0.0)):.2f}")
    r3.metric("Комментарий", ren.get("confidence_note", "—"))

    signals = ren.get("signals", [])
    if signals:
        st.markdown("**Сигналы (по фото):**")
        for s in signals:
            tag = s.get("label") or s.get("tag")
            conf = s.get("confidence", None)
            low = s.get("low_confidence", False)
            tail = []
            if conf is not None:
                tail.append(f"{float(conf):.2f}")
            if low:
                tail.append("низкая уверенность")
            suffix = f" ({', '.join(tail)})" if tail else ""
            st.write(f"- {tag}{suffix}")
    else:
        st.info("Сигналы не выделены (часто так бывает, если фото мало или они не про интерьер).")

    notes = ren.get("notes", [])
    for n in notes:
        st.caption(n)

    st.divider()

    st.subheader("Рекомендации")
    recs = exp_out.get("recommendations", [])
    if recs:
        for r in recs:
            title = r.get("title", "Рекомендация")
            why = r.get("why", "")
            uplift = r.get("expected_uplift_pct")
            pr = r.get("priority", "")
            uplift_txt = ""
            if isinstance(uplift, (list, tuple)) and len(uplift) == 2:
                uplift_txt = f"Ожидаемый эффект: ~{uplift[0]}–{uplift[1]}%"
            meta = " • ".join([x for x in [pr, uplift_txt] if x])
            st.markdown(f"**{title}**")
            if meta:
                st.caption(meta)
            if why:
                st.write(why)
            st.write("---")
    else:
        st.info("Рекомендаций нет (модель не уверена по фото или явных сигналов не нашлось).")

    st.divider()
    with st.expander("Показать сырой JSON ответа /explain"):
        st.code(json.dumps(exp_out, ensure_ascii=False, indent=2))

else:
    st.info("Нажмите **Оценить + объяснить**, чтобы увидеть разбор факторов и оценку по фото.")

if url_out:
    st.divider()
    st.subheader("Результат по ссылке")
    listing = url_out.get("listing", {})
    prediction = url_out.get("prediction", {})
    diff = url_out.get("difference", {})
    price_diff = (diff or {}).get("price", {}) or {}
    ppm2_diff = (diff or {}).get("price_per_m2", {}) or {}

    c_url1, c_url2, c_url3 = st.columns(3)
    c_url1.metric("Цена в объявлении", fmt_money((listing or {}).get("price")))
    c_url2.metric("Оценка модели", fmt_money((prediction or {}).get("price")))
    c_url3.metric(
        "Разница",
        fmt_money(price_diff.get("diff")),
        delta=(f"{float(price_diff.get('diff_pct')):+.1f}%" if price_diff.get("diff_pct") is not None else None),
    )

    c_url4, c_url5, c_url6 = st.columns(3)
    c_url4.metric("₸/м² в объявлении", fmt_ppm2((listing or {}).get("price_per_m2")))
    c_url5.metric("₸/м² модель", fmt_ppm2((prediction or {}).get("price_per_m2")))
    c_url6.metric(
        "Разница по ₸/м²",
        fmt_ppm2(ppm2_diff.get("diff")),
        delta=(f"{float(ppm2_diff.get('diff_pct')):+.1f}%" if ppm2_diff.get("diff_pct") is not None else None),
    )

    st.caption(
        f"Фото: найдено {int((listing or {}).get('image_urls_count') or 0)}, "
        f"скачано для модели {int((listing or {}).get('images_downloaded_count') or 0)}."
    )
    if listing.get("url"):
        st.markdown(f"[Открыть объявление]({listing['url']})")

    render_comparables((prediction or {}).get("comparables", []))

if uploaded_files:
    st.subheader("Загруженные фото")
    imgs = uploaded_files[:7]
    cols = st.columns(min(4, len(imgs)))
    for i, f in enumerate(imgs):
        cols[i % len(cols)].image(f.getvalue(), caption=f.name, width="stretch")
