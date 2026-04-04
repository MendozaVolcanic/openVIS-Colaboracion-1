"""
OpenVIS Dashboard - OVDAS
Uso: cd openVIS-code && streamlit run dashboard.py
Requiere: pip install streamlit plotly pandas
"""
import os, pandas as pd, numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="OpenVIS - OVDAS", page_icon="V", layout="wide")

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "examples", "results")
CFG_DIR     = os.path.join(os.path.dirname(__file__), "cfg")
CONF_COLORS = {1: "#f4d03f", 2: "#e67e22", 3: "#c0392b"}

def list_runs():
    return sorted([d for d in os.listdir(RESULTS_DIR)
                   if os.path.isdir(os.path.join(RESULTS_DIR, d))], reverse=True)

@st.cache_data
def load_run(run):
    b = os.path.join(RESULTS_DIR, run)
    return (pd.read_pickle(os.path.join(b, "ip_results.pkl")),
            pd.read_pickle(os.path.join(b, "eruption_results.pkl")),
            pd.read_pickle(os.path.join(b, "assoc_sta_er.pkl")))

@st.cache_data
def load_stations():
    return pd.read_csv(os.path.join(CFG_DIR, "stations.csv"))

# ---- Sidebar ----
st.sidebar.title("OpenVIS - OVDAS")
runs = list_runs()
if not runs:
    st.error("Sin resultados en examples/results/")
    st.stop()

sel_run = st.sidebar.selectbox("Ejecucion", runs)
ip_df, er_df, sa_df = load_run(sel_run)
sta_cfg = load_stations()

ip_df["Datetime (UTC)"]   = pd.to_datetime(ip_df["Datetime (UTC)"], utc=True)
er_df["Start Date (UTC)"] = pd.to_datetime(er_df["Start Date (UTC)"], utc=True)
er_df["End Date (UTC)"]   = pd.to_datetime(er_df["End Date (UTC)"], utc=True)

dmin = ip_df["Datetime (UTC)"].min().date()
dmax = ip_df["Datetime (UTC)"].max().date()

st.sidebar.divider()
dr = st.sidebar.date_input("Rango fechas",
    value=(datetime(2011,5,1).date(), datetime(2011,9,30).date()),
    min_value=dmin, max_value=dmax)
ip_min  = st.sidebar.slider("IP minimo", 0, 500, 1)
ip_thr  = st.sidebar.slider("Umbral erupcion", 0, 500, 100)
stas    = st.sidebar.multiselect("Estaciones",
    sorted(ip_df["Station Name"].unique()), default=sorted(ip_df["Station Name"].unique()))

d0 = pd.Timestamp(dr[0], tz="UTC") if len(dr) >= 1 else pd.Timestamp(dmin, tz="UTC")
d1 = pd.Timestamp(dr[1], tz="UTC") if len(dr) == 2 else pd.Timestamp(dmax, tz="UTC")

ipf = ip_df[(ip_df["Datetime (UTC)"]>=d0)&(ip_df["Datetime (UTC)"]<=d1)
            &(ip_df["IP"]>=ip_min)&(ip_df["Station Name"].isin(stas))].copy()
erf = er_df[(er_df["Start Date (UTC)"]>=d0)&(er_df["End Date (UTC)"]<=d1)].copy()

# ---- Header ----
st.title("OpenVIS - Dashboard OVDAS")
st.caption(f"Ejecucion: {sel_run} | Periodo: {d0.date()} a {d1.date()} | Datos ejemplo: Puyehue-Cordon Caulle 2011")

# ---- KPIs ----
c1,c2,c3,c4 = st.columns(4)
c1.metric("Erupciones", len(erf))
c2.metric(f"IP>={ip_thr}", len(ipf[ipf["IP"]>=ip_thr]))
c3.metric("IP max", f"{ipf['IP'].max():.1f}" if len(ipf) else "0")
c4.metric("Estaciones", len(stas))
st.divider()

# ---- Serie temporal + Mapa ----
ct, cm = st.columns([2,1])
with ct:
    st.subheader("Parametro Infrasounico (IP)")
    fig = go.Figure()
    colors = px.colors.qualitative.Set2
    for i, s in enumerate(stas):
        d = ipf[ipf["Station Name"]==s]
        if d.empty: continue
        fig.add_trace(go.Scatter(
            x=d["Datetime (UTC)"], y=d["IP"], mode="markers", name=s,
            marker=dict(
                size=np.clip(d["Number of Detections"]/5, 3, 20),
                color=d["Mean Frequency (Hz)"],
                colorscale="Viridis", cmin=1, cmax=3,
                showscale=(i==0),
                colorbar=dict(title="Freq Hz", x=1.02, len=0.5),
                opacity=0.8),
            customdata=np.stack([d["Mean Source Amplitude (Pa)"],
                                  d["Persistency"],d["Mean Frequency (Hz)"],
                                  d["Number of Detections"]], axis=-1),
            hovertemplate=(
                "<b>%{x|%Y-%m-%d %H:%M}</b><br>IP: %{y:.1f}<br>"
                "Amp fuente: %{customdata[0]:.1f} Pa<br>"
                "Persistencia: %{customdata[1]:.1f}%%<br>"
                "Freq: %{customdata[2]:.2f} Hz<br>"
                "N det: %{customdata[3]:.0f}<extra>"+s+"</extra>")))
    fig.add_hline(y=ip_thr, line_dash="dash", line_color="red",
                  annotation_text=f"Umbral {ip_thr}", annotation_position="top left")
    for _, r in erf.iterrows():
        fig.add_vrect(x0=r["Start Date (UTC)"], x1=r["End Date (UTC)"],
                      fillcolor=CONF_COLORS.get(r["Confidence Level"],"#c0392b"),
                      opacity=0.15, layer="below", line_width=0)
    fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10),
                      xaxis_title="Fecha (UTC)", yaxis_title="IP", hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=1))
    st.plotly_chart(fig, use_container_width=True)

with cm:
    st.subheader("Red de estaciones")
    mrows = []
    for _, r in sta_cfg[sta_cfg["Station Name"].isin(stas)].iterrows():
        nd = int(ipf[ipf["Station Name"]==r["Station Name"]]["Number of Detections"].sum())
        mrows.append(dict(Nombre=r["Station Name"],Lat=r["Latitude"],Lon=r["Longitude"],
                          Tipo="Estacion IMS",Detecciones=nd))
    mrows.append(dict(Nombre="Puyehue-Cordon Caulle",Lat=-40.59,Lon=-72.12,
                      Tipo="Volcan",Detecciones=0))
    mdf = pd.DataFrame(mrows)
    fmap = px.scatter_mapbox(mdf,lat="Lat",lon="Lon",color="Tipo",
        color_discrete_map={"Estacion IMS":"#2196F3","Volcan":"#FF5722"},
        size=[20 if t=="Volcan" else 14 for t in mdf["Tipo"]],
        hover_name="Nombre", hover_data={"Detecciones":True,"Tipo":False,"Lat":False,"Lon":False},
        mapbox_style="carto-positron", zoom=2.5,
        center={"lat":-35,"lon":-65}, height=380)
    fmap.update_layout(margin=dict(l=0,r=0,t=0,b=0),
                       legend=dict(orientation="h",y=1.05))
    st.plotly_chart(fmap, use_container_width=True)

# ---- Erupciones ----
st.divider()
st.subheader("Erupciones detectadas")
if erf.empty:
    st.info("Sin erupciones en el rango seleccionado.")
else:
    es = erf[["Eruption Code","Start Date (UTC)","End Date (UTC)",
              "Confidence Level","Estimated Amplitude [Pa]","Status","Revision"]].copy()
    es["Duracion (h)"] = ((es["End Date (UTC)"]-es["Start Date (UTC)"]).dt.total_seconds()/3600).round(1)
    es["Start Date (UTC)"] = es["Start Date (UTC)"].dt.strftime("%Y-%m-%d %H:%M")
    es["End Date (UTC)"]   = es["End Date (UTC)"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(es, use_container_width=True, hide_index=True)
    st.caption("Confianza: 1=1 estacion | 2=2 estaciones | 3=varias cercanas")

# ---- Stats ----
st.divider()
st.subheader("Estadisticas por estacion")
rows=[]
for s in stas:
    d=ipf[ipf["Station Name"]==s]
    if d.empty: continue
    rows.append({"Estacion":s,"Total IP":len(d),f"IP>={ip_thr}":len(d[d["IP"]>=ip_thr]),
                 "IP max":round(d["IP"].max(),1),"Amp max (Pa)":round(d["Mean Source Amplitude (Pa)"].max(),1),
                 "Freq Hz":round(d["Mean Frequency (Hz)"].mean(),2),
                 "Persist%":round(d["Persistency"].mean(),1)})
if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.caption("openVIS (De Negri et al.) | MendozaVolcanic/openVIS | OVDAS/SERNAGEOMIN Chile")
