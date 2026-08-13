
import os
import io
import glob
import streamlit as st
import pandas as pd
import plotly.express as px
import xml.etree.ElementTree as ET
import plotly.graph_objects as go
from datetime import datetime

def parse_xml(source) -> pd.DataFrame | None:

    try:
        if isinstance(source, (str, os.PathLike)):
            tree     = ET.parse(source)
            filename = os.path.basename(source)
        else:
            tree     = ET.parse(io.BytesIO(source.read()))
            filename = source.name

        root = tree.getroot()

        baseline_id = root.get("BaselineTestId", "")
        beadlot_id  = root.get("BeadlotDefinitionId", "")
        date_run    = root.get("DateRun", "")
        test_result      = int(root.get("TestResultPassed", 0))

        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
            try:
                date_run_parsed = datetime.strptime(date_run, fmt)
                break
            except ValueError:
                continue
        else:
            date_run_parsed = None

        rows = []

        for fr in root.findall(".//FlowRate"):
            flow_rate = fr.get("Rate")
            channels  = fr.findall(".//PerformanceTestChannel")
            if len(channels) == 0:
                continue
            for ch in channels:
                rows.append({
                    "SourceFile"     : filename,
                    "BaselineTestId" : baseline_id,
                    "BeadlotId"      : beadlot_id,
                    "DateRun"        : date_run_parsed,
                    "TestResultPassed": test_result,
                    "FlowRate"       : float(flow_rate),
                    "Channel"        : ch.get("ShortName_PnN"),
                    "RobustCV"       : float(ch.get("RobustCV", 0)),
                    "LaserDelay"     : float(ch.get("LaserDelay", 0)),
                    
                })

        if len(rows) == 0:
            return None

        return pd.DataFrame(rows)

    except Exception as e:
        st.warning(f"Could not parse {filename} — {e}")
        return None

# ── helper — apply consistent x axis formatting to any figure ─────────────────

def format_x_axis(fig, df: pd.DataFrame) -> go.Figure:
    """
    Forces monthly tick marks aligned exactly to the dates in the data.
    Applies to all x axes in the figure including facet rows.
    """

    # Get the actual date range from the data
    date_min = df["DateRun"].min()
    date_max = df["DateRun"].max()

    # Build a list of the first of every month between min and max date
    tick_dates = pd.date_range(
        start = date_min.replace(day=1),
        end   = date_max,
        freq  = "MS"                      # MS = Month Start
    )

    # Format tick labels as "Jan 2024", "Feb 2024" etc.
    tick_labels = [d.strftime("%b %Y") for d in tick_dates]

    # Apply to every x axis in the figure (facet_row creates multiple)
    fig.update_xaxes(
        tickmode     = "array",
        tickvals     = tick_dates,
        ticktext     = tick_labels,
        tickangle    = 45,
        showgrid     = True,
        gridcolor    = "lightgrey",
    )

    return fig

def load_from_uploads(uploaded_files) -> pd.DataFrame:
    """Mode 1 — file uploader in browser"""
    frames = [parse_xml(f) for f in uploaded_files]
    frames = [f for f in frames if f is not None]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["BaselineTestId"].notna() & (df["BaselineTestId"] != "")]
    return df


def load_from_api(api_endpoint: str, token: str) -> pd.DataFrame:
    """
    Mode 2 — API pull (stub — plug in when bearer token is ready)
    Only this function changes when the API is available.
    Everything else in the app stays identical.
    """
    import requests

    response = requests.get(
        api_endpoint,
        headers={"Authorization": f"Bearer {token}"}
    )
    response.raise_for_status()
    xml_files = response.json()["files"]    # adjust key to match API response

    frames = []
    for xml_content in xml_files:
        source = io.BytesIO(xml_content.encode("utf-8"))
        df     = parse_xml(source)
        if df is not None:
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    
    df = pd.concat(frames, ignore_index=True)
    df = df[df["BaselineTestId"].notna() & (df["BaselineTestId"] != "")]
    return df


@st.cache_data
def load_from_folder(folder: str) -> pd.DataFrame:
    """Mode 3 — local folder, development only"""
    files  = glob.glob(os.path.join(folder, "*000Results.xml"))
    frames = [parse_xml(f) for f in files]
    frames = [f for f in frames if f is not None]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df = df[df["BaselineTestId"].notna() & (df["BaselineTestId"] != "")]
    return df



st.set_page_config(
    page_title = "Attune CytPix Monitor",
    page_icon  = "🔬",
    layout     = "wide"
)

st.title("🔬 Attune CytPix Performance Monitor")
st.caption("Trends from performance test results")

with st.sidebar:

    st.header("Data Source")

    data_mode = st.radio(
        "Load data from",
        options = ["Upload Files", "Local Folder"],
        index   = 0
    )

    if data_mode == "Upload Files":
        uploaded_files = st.file_uploader(
            label                 = "Upload Results XML files",
            type                  = ["xml"],
            accept_multiple_files = True
        )

    elif data_mode == "Local Folder":
        folder   = st.text_input(
            label = "Folder Path",
            value = "C:/Users/yass038/OneDrive - PNNL/Documents/PerformanceTestResults"
        )
        load_btn = st.button("Load", type="primary")

    # ── Mode 2: API stub ───────────────────────────────────────────────────────
    # Uncomment when bearer token is ready:
    #
    # elif data_mode == "API":
    #     api_endpoint = st.text_input("API Endpoint")
    #     token        = st.text_input("Bearer Token", type="password")
    #     load_btn     = st.button("Fetch", type="primary")

df_all = pd.DataFrame()

if data_mode == "Upload Files":
    if uploaded_files:
        df_all = load_from_uploads(uploaded_files)

elif data_mode == "Local Folder":
    if load_btn:
        df_all = load_from_folder(folder)
        st.session_state["df_all"] = df_all
    if "df_all" in st.session_state:
        df_all = st.session_state["df_all"]

if df_all.empty:
    st.info("Upload Results XML files using the sidebar to begin.")
    st.stop()

with st.sidebar:
    st.success(f"Loaded {df_all['SourceFile'].nunique()} files")

with st.sidebar:

    st.header("Filters")

    # Baseline
    baseline_options  = sorted(df_all["BaselineTestId"].unique().tolist())
    selected_baseline = st.selectbox("Baseline Test ID", baseline_options)

    # Flow rate — multiselect, all on by default
    flow_options   = sorted(df_all["FlowRate"].unique().tolist())
    selected_flows = st.multiselect(
        label   = "Flow Rate (µL/min)",
        options = flow_options,
        default = flow_options
    )

    # Channel — single selector, one at a time for clean lines
    channel_options  = sorted(df_all["Channel"].unique().tolist())
    selected_channel = st.selectbox(
        label   = "Channel",
        options = channel_options,
        index   = 0
    )

df = df_all[
    (df_all["BaselineTestId"] == selected_baseline) &
    (df_all["FlowRate"].isin(selected_flows)) &
    (df_all["Channel"]        == selected_channel)
].copy().sort_values("DateRun")

df["FlowRate"] = pd.Categorical(
    df["FlowRate"],
    categories = sorted(selected_flows)
)

if df.empty:
    st.warning("No data matches the selected filters.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)

c1.metric("Tests in View", df["DateRun"].nunique())
c2.metric("Channel",       selected_channel)
c3.metric("Flow Rates",    df["FlowRate"].nunique())
c4.metric("Bead Lots",     df["BeadlotId"].nunique())

st.divider()

st.subheader("Pass / Fail Overview — All Channels")
st.caption("Green = passed | Red = failed — select a channel above to investigate")
df_heatmap = df_all[
    df_all["BaselineTestId"] == selected_baseline
].copy()
# One row per test date + channel (TestResultPassed is test-level, same across flow rates)
df_heatmap = (
    df_heatmap
    .groupby(["DateRun", "Channel"])["TestResultPassed"]
    .first()
    .reset_index()
)
pivot = df_heatmap.pivot(
    index   = "Channel",
    columns = "DateRun",
    values  = "TestResultPassed"
)
pivot.columns = [
    pd.Timestamp(c).strftime("%b %Y") for c in pivot.columns
]

# Pivot so rows = channels, columns = dates
pivot = df_heatmap.pivot(
    index   = "Channel",
    columns = "DateRun",
    values  = "TestResultPassed"
)
fig_heatmap = px.imshow(
    pivot,
    color_continuous_scale = [[0, "#d62728"], [1, "#2ca02c"]],   # red=fail green=pass
    zmin        = 0,
    zmax        = 1,
    aspect      = "auto",
    labels      = dict(color="Result"),
    title       = "Instrument Pass/Fail by Channel and Test Date"
)
fig_heatmap.update_coloraxes(
    colorbar = dict(
        tickvals  = [0, 1],
        ticktext  = ["Fail", "Pass"],
        thickness = 15
    )
)

fig_heatmap.update_layout(
    height = 400,
    margin = dict(l=60, r=40, t=60, b=80),
    xaxis  = dict(tickangle=45)
)

st.plotly_chart(fig_heatmap, use_container_width=True)



col_left, col_right = st.columns(2)

with col_left:

    st.subheader(f"RobustCV — {selected_channel}")

    fig_cv = px.line(
        df,
        x          = "DateRun",
        y          = "RobustCV",
        facet_row  = "FlowRate",
        markers    = True,
        hover_data = ["TestResultPassed","SourceFile"],
        labels     = {
            "RobustCV" : "Robust CV (%)",
        }
    )

    fig_cv.update_traces(
        line   = dict(width=2),
        marker = dict(size=7)
    )
    fig_cv.update_yaxes(matches=None, showticklabels=True)
    fig_cv.update_layout(
        height     = 600,
        showlegend = False,
        margin     = dict(l=60, r=40, t=60, b=80)
    )
    fig_cv.for_each_annotation(
        lambda a: a.update(text=a.text.split("=")[-1] + " µL/min")
    )

    # ── apply month tick formatting ────────────────────────────────────────────
    fig_cv = format_x_axis(fig_cv, df)

    st.plotly_chart(fig_cv, use_container_width=True)
with col_right:

    st.subheader(f"LaserDelay — {selected_channel}")

    fig_cv = px.line(
        df,
        x          = "DateRun",
        y          = "LaserDelay",
        facet_row  = "FlowRate",
        markers    = True,
        hover_data = ["SourceFile","TestResultPassed"],
        labels     = {
            "LaserDelay" : "Laser Delay (µs)",
        }
    )

    fig_cv.update_traces(
        line   = dict(width=2),
        marker = dict(size=7)
    )
    fig_cv.update_yaxes(matches=None, showticklabels=True)
    fig_cv.update_layout(
        height     = 600,
        showlegend = False,
        margin     = dict(l=60, r=40, t=60, b=80)
    )
    fig_cv.for_each_annotation(
        lambda a: a.update(text=a.text.split("=")[-1] + " µL/min")
    )

    # ── apply month tick formatting ────────────────────────────────────────────
    fig_cv = format_x_axis(fig_cv, df)

    st.plotly_chart(fig_cv, use_container_width=True)


st.divider()

st.subheader(f"CV Summary Table — {selected_channel}")
st.caption("CV requires ≥ 2 tests per group to produce a non-zero value")

cv_df = (
    df
    .groupby(["DateRun", "Channel", "FlowRate", "TestResultPassed"], observed=True)
    .agg(
        Mean_RobustCV   = ("RobustCV",   "mean"),
        Mean_LaserDelay = ("LaserDelay", "mean"),
    )
    .reset_index()
    .round(3)
)

st.dataframe(cv_df, use_container_width=True)

st.download_button(
    label     = "Export CV Table as CSV",
    data      = cv_df.to_csv(index=False).encode("utf-8"),
    file_name = f"AttuneCytPix_{selected_channel}_{pd.Timestamp.today().date()}.csv",
    mime      = "text/csv"
)
df_clean = df.drop(columns=["BaselineTestId", "BeadlotId"])
with st.expander("View Raw Data"):
    st.dataframe(df_clean, use_container_width=True)