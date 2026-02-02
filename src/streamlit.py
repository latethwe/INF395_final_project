import json
import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(page_title="Krisha Price Estimator (Demo)", layout="wide")

st.title("Krisha Price Estimator — Demo")
st.caption("Сравнение: tabular-only vs tabular + фото (ремонт/состояние)")

# ---- Sidebar inputs ----
with st.sidebar:
    st.header("Параметры квартиры")

    area = st.number_input("Площадь, м²", min_value=5.0, max_value=500.0, value=75.1, step=0.1)
    rooms = st.number_input("Комнат", min_value=1, max_value=10, value=3, step=1)
    floor = st.number_input("Этаж", min_value=1, max_value=200, value=14, step=1)
    floors_total = st.number_input("Этажей в доме", min_value=1, max_value=200, value=15, step=1)
    year_built = st.number_input("Год постройки", min_value=1900, max_value=2026, value=2023, step=1)

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
    st.header("Фото (для оценки с ремонтом)")
    uploaded_files = st.file_uploader(
        "Загрузите 1–7 фото (jpg/jpeg/png/webp)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True
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

# ---- Helpers ----
def fmt_money(x: float) -> str:
    return f"{x:,.0f} ₸".replace(",", " ")

def fmt_ppm2(x: float) -> str:
    return f"{x:,.0f} ₸/м²".replace(",", " ")

def call_predict_tabular():
    data = {k: str(v) for k, v in payload.items()}
    r = requests.post(f"{API_BASE}/predict_tabular", data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def call_predict_with_photos(files):
    data = {k: str(v) for k, v in payload.items()}
    multipart = []
    for f in (files or [])[:7]:
        # streamlit UploadedFile: bytes via getvalue()
        multipart.append(("images", (f.name, f.getvalue(), f.type or "application/octet-stream")))
    r = requests.post(f"{API_BASE}/predict", data=data, files=multipart, timeout=180)
    r.raise_for_status()
    return r.json()

# ---- UI ----
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Tabular-only (без фото)")
    st.caption("Оценка по параметрам. Используйте как “базу” без учёта ремонта.")
    if st.button("Оценить без фото", width="stretch"):
        try:
            out = call_predict_tabular()
            st.success("Готово")
            st.metric("Цена", fmt_money(out["price"]))
            st.metric("Цена за м²", fmt_ppm2(out["price_per_m2"]))
            st.code(json.dumps(out, ensure_ascii=False, indent=2))
        except Exception as e:
            st.error(f"Ошибка: {e}")

with col2:
    st.subheader("С фото (ремонт/состояние)")
    st.caption("Оценка по параметрам + фото. Демонстрирует влияние ремонта.")
    if st.button("Оценить с фото", width="stretch"):
        if not uploaded_files:
            st.warning("Загрузите хотя бы 1 фото.")
        else:
            try:
                out = call_predict_with_photos(uploaded_files)
                st.success("Готово")
                st.metric("Цена", fmt_money(out["price"]))
                st.metric("Цена за м²", fmt_ppm2(out["price_per_m2"]))
                st.code(json.dumps(out, ensure_ascii=False, indent=2))
            except Exception as e:
                st.error(f"Ошибка: {e}")

st.divider()
st.subheader("Демо-сценарий: доказать влияние ремонта")
st.markdown(
    """
1) Нажми **Оценить без фото** — это “средняя” оценка без состояния ремонта.  
2) Загрузите фото **евроремонт** → **Оценить с фото** (должно быть выше).  
3) Замените фото на **убитое состояние** → снова **Оценить с фото** (должно быть ниже).  
"""
)

if uploaded_files:
    st.subheader("Загруженные фото")
    imgs = uploaded_files[:7]
    cols = st.columns(min(4, len(imgs)))
    for i, f in enumerate(imgs):
        cols[i % len(cols)].image(f.getvalue(), caption=f.name, width="stretch")
