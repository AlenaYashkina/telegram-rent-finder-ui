import os
import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
st.set_page_config(page_title="Telegram Rent Finder", layout="wide")
st.title("Telegram Rent Finder UI")
st.caption("Filter and export **image-only** listings collected from Telegram.")

csv_path = "matches.csv"
if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
    df = pd.read_csv(csv_path)
else:
    with open("data/sample_listings.json", "r", encoding="utf-8") as f:
        df = pd.DataFrame(json.load(f))

for col in ["channel","message_id","date_local","price_usd","score","url","text"]:
    if col not in df.columns:
        df[col] = None

st.sidebar.header("Filters")
min_price = float(os.getenv("USD_MIN", 400))
max_price = float(os.getenv("USD_MAX", 500))
pmin, pmax = st.sidebar.slider("Price $", 0.0, 2000.0, (min_price, max_price), step=10.0)
smin, smax = st.sidebar.slider("Score", 0, 10, (0, 10), step=1)
query = st.sidebar.text_input("Search text (regex ok)", "")
only_links = st.sidebar.checkbox("Only with a post URL", value=True)

mask = (df["price_usd"].fillna(0).between(pmin, pmax)) & (df["score"].fillna(0).between(smin, smax))
if only_links and "url" in df.columns:
    mask &= df["url"].astype(str).str.len() > 0
if query.strip():
    mask &= df["text"].astype(str).str.contains(query, case=False, regex=True)

view = df.loc[mask].copy()
st.subheader(f"Results: {len(view)}")
st.dataframe(view[["date_local","price_usd","score","channel","url","text"]], use_container_width=True, height=560)

st.download_button(
    "Export CSV (filtered)",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="rent_filtered.csv",
    mime="text/csv"
)
