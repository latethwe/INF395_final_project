import json
import math
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Krisha Price Estimator (Demo)", layout="wide")

st.title("Krisha Price Estimator — Demo")
st.caption("Оценка цены + объяснение (почему так) + ориентир по ремонту по фото")

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

def call_predict(files=None, no_photos=False):
    data = {k: str(v) for k, v in payload.items()}
    multipart = []

    if not no_photos:
        for f in (files or [])[:7]:
            multipart.append(("images", (f.name, f.getvalue(), f.type or "application/octet-stream")))

    r = requests.post(f"{API_BASE}/predict", data=data, files=multipart, timeout=180)
    r.raise_for_status()
    return r.json()


def call_explain(files=None, no_photos=False):
    data = {k: str(v) for k, v in payload.items()}
    multipart = []

    if not no_photos:
        for f in (files or [])[:7]:
            multipart.append(("images", (f.name, f.getvalue(), f.type or "application/octet-stream")))

    r = requests.post(f"{API_BASE}/explain", data=data, files=multipart, timeout=180)
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
    # красиво для float
    if isinstance(v, float):
        # если это почти целое (типа 0.2222), оставим 4 знака
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


# -----------------------
# UI
# -----------------------
st.divider()

# Top actions
c1, c2, c3 = st.columns([1, 1, 2])

with c1:
    run_predict = st.button("Оценить (быстро)", use_container_width=True)
with c2:
    run_explain = st.button("Оценить + объяснить", use_container_width=True)
with c3:
    st.caption("Совет: для объяснения лучше 3–7 фото (кухня, санузел, общая, спальня).")

# Results placeholders
pred_out = None
exp_out = None

if run_predict:
    pred_out = call_predict(
        uploaded_files,
        no_photos=st.session_state.get("no_photos_mode", False)
    )

if run_explain:
    exp_out = call_explain(
        uploaded_files,
        no_photos=st.session_state.get("no_photos_mode", False)
    )


# Render prediction (from explain if available; otherwise from predict)
out = exp_out or pred_out
if out:
    # Support both old predict format and new explain format
    price = safe_get(out, "prediction", "price", default=out.get("price"))
    ppm2 = safe_get(out, "prediction", "price_per_m2", default=out.get("price_per_m2"))
    area_val = safe_get(out, "prediction", "area", default=payload["area"])

    colA, colB, colC = st.columns(3)
    colA.metric("Цена", fmt_money(price))
    colB.metric("Цена за м²", fmt_ppm2(ppm2))
    colC.metric("Площадь", f"{area_val:.1f} м²")

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
        st.caption(f"Оценочно влияние фото на общую цену: {fmt_money(photos_kzt)} (это интерпретация, не точная сумма факторов).")

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
        # Show as bullets
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
        st.info("Рекомендаций нет (часто значит, что модель не уверена по фото или явных сигналов не нашлось).")

    st.divider()
    with st.expander("Показать сырой JSON ответа /explain"):
        st.code(json.dumps(exp_out, ensure_ascii=False, indent=2))

else:
    st.info("Нажмите **Оценить + объяснить**, чтобы увидеть разбор факторов и оценку по фото.")

# Show uploaded images
if uploaded_files:
    st.subheader("Загруженные фото")
    imgs = uploaded_files[:7]
    cols = st.columns(min(4, len(imgs)))
    for i, f in enumerate(imgs):
        cols[i % len(cols)].image(f.getvalue(), caption=f.name, width="stretch")
