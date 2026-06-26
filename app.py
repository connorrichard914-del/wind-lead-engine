import streamlit as st
import subprocess
import pandas as pd
import os
import json
import plotly.express as px
import pydeck as pdk

st.set_page_config(page_title="Wind Lead Engine", layout="wide")

st.title("🌬️ Wind Turbine Lead Intelligence CRM")
st.markdown("Pipeline + Favorites + Analytics + Geo Intelligence")

# ─────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────
FAV_FILE = "output/favorites.json"
PIPELINE_FILE = "output/pipeline.json"


def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


favorites = set(load_json(FAV_FILE).get("favorites", []))
pipeline = load_json(PIPELINE_FILE)

PIPELINE_STAGES = ["New", "Contacted", "Qualified", "Closed"]

if "favorites" not in st.session_state:
    st.session_state.favorites = favorites

if "pipeline" not in st.session_state:
    st.session_state.pipeline = pipeline


# ─────────────────────────────────────────────
# RUN PIPELINE
# ─────────────────────────────────────────────
if st.button("Run Lead Discovery Pipeline"):
    with st.spinner("Running pipeline..."):
        subprocess.run(["python", "main.py"])
    st.success("Pipeline complete!")


# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
file_path = "output/leads.csv"

if not os.path.exists(file_path):
    st.info("No data found. Run pipeline first.")
    st.stop()

df = pd.read_csv(file_path)


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────
st.sidebar.header("Filters")

min_score = st.sidebar.slider("Min Score", 0, 100, 70)
hot_only = st.sidebar.toggle("🔥 Hot Only")
favorites_only = st.sidebar.toggle("⭐ Favorites Only")
search = st.sidebar.text_input("Search Company")

product_filter = st.sidebar.multiselect(
    "Product",
    sorted(df["recommended_product"].dropna().unique())
) if "recommended_product" in df.columns else []

region_filter = st.sidebar.multiselect(
    "Region",
    sorted(df["region"].dropna().unique())
) if "region" in df.columns else []

category_filter = st.sidebar.multiselect(
    "Category",
    sorted(df["category"].dropna().unique())
) if "category" in df.columns else []


# ─────────────────────────────────────────────
# FILTER LOGIC
# ─────────────────────────────────────────────
filtered_df = df.copy()

filtered_df = filtered_df[filtered_df["lead_score"] >= min_score]

if hot_only:
    filtered_df = filtered_df[filtered_df["lead_score"] >= 85]

if search:
    filtered_df = filtered_df[
        filtered_df["company_name"].astype(str).str.contains(search, case=False, na=False)
    ]

if product_filter:
    filtered_df = filtered_df[filtered_df["recommended_product"].isin(product_filter)]

if region_filter:
    filtered_df = filtered_df[filtered_df["region"].isin(region_filter)]

if category_filter:
    filtered_df = filtered_df[filtered_df["category"].isin(category_filter)]

if favorites_only:
    filtered_df = filtered_df[
        filtered_df["company_name"].isin(st.session_state.favorites)
    ]


# ─────────────────────────────────────────────
# OVERVIEW
# ─────────────────────────────────────────────
st.subheader("📊 Overview")

col1, col2, col3 = st.columns(3)

col1.metric("Total Leads", len(filtered_df))
col2.metric("Avg Score", round(filtered_df["lead_score"].mean(), 1))
col3.metric("Hot Leads", len(filtered_df[filtered_df["lead_score"] >= 85]))

st.divider()


# ─────────────────────────────────────────────
# LEAD CARDS
# ─────────────────────────────────────────────
st.subheader("📋 Lead Cards")

filtered_df = filtered_df.sort_values("lead_score", ascending=False)

for i, row in filtered_df.iterrows():

    company = row.get("company_name", f"Lead {i}")
    score = row.get("lead_score", "N/A")

    region = row.get("region", "Unknown")
    category = row.get("category", "Unknown")
    product = row.get("recommended_product", "N/A")

    signals = row.get("signals_detected", "Not available")
    reasoning = row.get("recommended_reasoning", None)

    email = row.get("email", None)
    phone = row.get("phone", None)

    is_fav = company in st.session_state.favorites

    label = (
        "🔥 HOT" if isinstance(score, (int, float)) and score >= 85 else
        "⚡ WARM" if isinstance(score, (int, float)) and score >= 75 else
        "🟡 NORMAL"
    )

    star = "⭐" if is_fav else ""

    with st.expander(f"{star} {label} {company} — {score}"):

        colA, colB = st.columns(2)

        with colA:
            st.write("Region:", region)
            st.write("Category:", category)
            st.write("Product:", product)
            st.write("Signals:", signals)

        with colB:
            st.write("Score:", score)
            st.write("Email:", email if email else "Not found")
            st.write("Phone:", phone if phone else "Not found")

        st.markdown("### 🔥 Why this lead matters")

        if reasoning:
            st.write(reasoning)
        else:
            if isinstance(score, (int, float)) and score >= 85:
                st.success("High energy + infrastructure scale + grid exposure.")
            elif isinstance(score, (int, float)) and score >= 75:
                st.info("Moderate industrial energy demand.")
            else:
                st.write("Lower priority opportunity.")

        c1, c2 = st.columns(2)

        with c1:
            if st.button("⭐ Toggle Favorite", key=f"fav_{company}"):
                if is_fav:
                    st.session_state.favorites.remove(company)
                else:
                    st.session_state.favorites.add(company)

        with c2:
            stage = st.selectbox(
                "Pipeline Stage",
                PIPELINE_STAGES,
                index=PIPELINE_STAGES.index(
                    st.session_state.pipeline.get(company, "New")
                ),
                key=f"stage_{company}"
            )
            st.session_state.pipeline[company] = stage


# ─────────────────────────────────────────────
# SAVE STATE
# ─────────────────────────────────────────────
save_json(FAV_FILE, {"favorites": list(st.session_state.favorites)})
save_json(PIPELINE_FILE, st.session_state.pipeline)


# ─────────────────────────────────────────────
# ANALYTICS
# ─────────────────────────────────────────────
st.divider()
st.subheader("📈 Analytics Dashboard")

st.plotly_chart(
    px.histogram(df, x="lead_score", nbins=20, title="Lead Score Distribution"),
    use_container_width=True
)

region_counts = df["region"].value_counts().reset_index()
region_counts.columns = ["region", "count"]

st.plotly_chart(
    px.bar(region_counts, x="region", y="count", title="Leads by Region"),
    use_container_width=True
)

cat_counts = df["category"].value_counts().reset_index()
cat_counts.columns = ["category", "count"]

st.plotly_chart(
    px.bar(cat_counts, x="category", y="count", title="Leads by Category"),
    use_container_width=True
)

if "recommended_product" in df.columns:
    prod_counts = df["recommended_product"].value_counts().reset_index()
    prod_counts.columns = ["product", "count"]

    st.plotly_chart(
        px.pie(prod_counts, names="product", values="count", title="KW20 vs KW30 Split"),
        use_container_width=True
    )


# ─────────────────────────────────────────────
# 🌍 GEO HEAT MAP
# ─────────────────────────────────────────────
st.divider()
st.subheader("🌍 Global Lead Heat Map")

region_coords = {
    "North America": {"lat": 39.5, "lon": -98.35},
    "South America": {"lat": -15.6, "lon": -56.1},
    "Africa": {"lat": 1.3, "lon": 17.8},
}

map_df = df.copy()

map_df["lat"] = map_df["region"].map(lambda r: region_coords.get(r, {}).get("lat"))
map_df["lon"] = map_df["region"].map(lambda r: region_coords.get(r, {}).get("lon"))

map_df = map_df.dropna(subset=["lat", "lon"])

agg = map_df.groupby(["region", "lat", "lon"]).agg(
    lead_count=("company_name", "count"),
    avg_score=("lead_score", "mean")
).reset_index()

layer = pdk.Layer(
    "ScatterplotLayer",
    data=agg,
    get_position=["lon", "lat"],
    get_radius="lead_count * 200000",
    get_fill_color="[255, 140, 0, 180]",
    pickable=True,
)

view_state = pdk.ViewState(
    latitude=20,
    longitude=0,
    zoom=1.2,
)

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={
            "text": "{region}\nLeads: {lead_count}\nAvg Score: {avg_score}"
        }
    )
)


# ─────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────
csv = filtered_df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="⬇️ Export Filtered Leads",
    data=csv,
    file_name="filtered_leads.csv",
    mime="text/csv"
)