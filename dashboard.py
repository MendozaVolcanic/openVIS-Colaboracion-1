"""
OpenVIS Dashboard - Southern Andes Case Study
Exploración personal de la metodología VIS aplicada a volcanes del sur de Chile.
Uso: streamlit run dashboard.py
"""
import os, glob, math
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone

st.set_page_config(
    page_title="OpenVIS · Andes del Sur",
    page_icon="🌋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CFG_DIR     = os.path.join(BASE_DIR, "cfg")
RESULT_ROOTS = [
    os.path.join(BASE_DIR, "data",     "results"),
    os.path.join(BASE_DIR, "examples", "results"),
]

# Erupciones reales conocidas para marcar en el gráfico
KNOWN_ERUPTIONS = {
    "Villarrica": [
        {"fecha": "2015-03-03", "label": "Erupción\n3 mar 2015"},
    ],
    "Calbuco": [
        {"fecha": "2015-04-22", "label": "Fase 1\n22 abr"},
        {"fecha": "2015-04-23", "label": "Fase 2\n23 abr"},
    ],
    "Puyehue-Cordon Caulle": [
        {"fecha": "2011-06-04", "label": "Inicio\n4 jun 2011"},
    ],
}

CONF_COLORS = {1: "#f4d03f", 2: "#e67e22", 3: "#c0392b"}
CONF_LABELS = {1: "Baja (1 estación)", 2: "Media (2 estaciones)", 3: "Alta (≥3 estaciones)"}

# ---------------------------------------------------------------------------
# FUNCIONES
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@st.cache_data
def load_run_meta(run_path):
    """Lee el .toml del run: volcán, coords, fechas, parámetros."""
    tomls = glob.glob(os.path.join(run_path, "*.toml"))
    meta = {"volcano": "Desconocido", "lat": -40.0, "lon": -72.0,
            "date_start": "", "date_end": "", "dazim": "?", "veff": "?",
            "stations": [], "label": os.path.basename(run_path)}
    if not tomls:
        return meta
    try:
        import toml
        cfg   = toml.load(tomls[0])
        volcs = cfg.get("VOLCANOES", {}).get("VolcanoesList", [])
        name  = volcs[0] if volcs else "Desconocido"
        vcfg  = pd.read_csv(os.path.join(CFG_DIR, "volcanoes.csv"),
                            sep=";", encoding="latin-1", decimal=",")
        row   = vcfg[vcfg["Volcano Name"] == name]
        if not row.empty:
            meta["lat"] = float(str(row.iloc[0]["Latitude"]).replace(",", "."))
            meta["lon"] = float(str(row.iloc[0]["Longitude"]).replace(",", "."))
        meta["volcano"]    = name
        meta["date_start"] = str(cfg["DATES"]["StartDate"])[:10]
        meta["date_end"]   = str(cfg["DATES"]["EndDate"])[:10]
        meta["dazim"]      = cfg["PROCESSING"].get("Dazim", "?")
        meta["veff"]       = cfg["FORMATS"].get("VeffFormat", "?")
        meta["stations"]   = cfg["STATIONS"].get("StationList", [])
        # Label legible para el selector
        veff_str = "sin veff" if not meta["veff"] else f"veff={meta['veff']}"
        meta["label"] = (
            f"{name}  |  {meta['date_start'][:7]}  |  "
            f"Dazim={meta['dazim']}°  {veff_str}"
        )
    except Exception:
        pass
    return meta


@st.cache_data
def load_run(run_path):
    return (pd.read_pickle(os.path.join(run_path, "ip_results.pkl")),
            pd.read_pickle(os.path.join(run_path, "eruption_results.pkl")),
            pd.read_pickle(os.path.join(run_path, "assoc_sta_er.pkl")))


@st.cache_data
def load_stations():
    return pd.read_csv(os.path.join(CFG_DIR, "stations.csv"))


def list_runs():
    runs = []
    for root in RESULT_ROOTS:
        if not os.path.isdir(root):
            continue
        for d in sorted(os.listdir(root), reverse=True):
            full = os.path.join(root, d)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "ip_results.pkl")):
                runs.append(full)
    return runs


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🌋 OpenVIS")
    st.caption("Andes del Sur — exploración personal")

    st.divider()

    with st.expander("ℹ️ ¿Qué es esto?", expanded=False):
        st.markdown("""
**OpenVIS** (Volcanic Information System) es una metodología científica
para detectar erupciones volcánicas a larga distancia usando **infrasonido** —
ondas de presión atmosférica de baja frecuencia (<20 Hz) que viajan
miles de kilómetros desde una erupción.

**¿Cómo funciona?**
La red IMS (International Monitoring System) tiene ~60 estaciones
infrasónicas globales. OpenVIS analiza sus datos para calcular el
**Parámetro Infrasónico (IP)**:

> **IP = Amplitud × Tasa de detección**

Cuando IP supera **100**, el sistema detecta una posible erupción.

**¿Qué muestran los gráficos?**
- Cada punto = una ventana de 2 horas procesada por el VIS
- El color indica la frecuencia media de la señal (1–3 Hz)
- La línea roja punteada = umbral IP 100
- Las franjas de colores = períodos eruptivos detectados
- Las líneas doradas = fecha real de la erupción (catálogo GVP)

**Código:** [openVIS (De Negri et al.)](https://github.com/rodrum/openVIS)
**Fork:** [MendozaVolcanic/openVIS-Colaboracion-1](https://github.com/MendozaVolcanic/openVIS-Colaboracion-1)
        """)

    st.divider()
    st.subheader("Seleccionar análisis")

    runs = list_runs()
    if not runs:
        st.error("No hay resultados disponibles.")
        st.stop()

    run_metas = {r: load_run_meta(r) for r in runs}
    sel_run = st.selectbox(
        "Ejecución VIS",
        runs,
        format_func=lambda r: run_metas[r]["label"],
        help="Cada ejecución corresponde a un volcán y configuración distintos"
    )
    meta = run_metas[sel_run]

    st.divider()
    st.subheader("Filtros")
    ip_df, er_df, sa_df = load_run(sel_run)
    sta_cfg = load_stations()

    ip_df["Datetime (UTC)"]   = pd.to_datetime(ip_df["Datetime (UTC)"], utc=True)
    er_df["Start Date (UTC)"] = pd.to_datetime(er_df["Start Date (UTC)"], utc=True)
    er_df["End Date (UTC)"]   = pd.to_datetime(er_df["End Date (UTC)"], utc=True)

    dmin = ip_df["Datetime (UTC)"].min().date()
    dmax = ip_df["Datetime (UTC)"].max().date()

    dr = st.date_input("Rango de fechas", value=(dmin, dmax),
                        min_value=dmin, max_value=dmax)
    ip_thr = st.slider("Umbral IP (detección)", 0, 500, 100,
                        help="IP ≥ 100 indica posible erupción según la metodología VIS")
    stas = st.multiselect(
        "Estaciones IMS",
        sorted(ip_df["Station Name"].unique()),
        default=sorted(ip_df["Station Name"].unique()),
        help="Estaciones de la red IMS usadas en este análisis"
    )

    st.divider()
    st.caption(f"**Volcán:** {meta['volcano']}")
    st.caption(f"**Período:** {meta['date_start']} → {meta['date_end']}")
    st.caption(f"**Dazim:** {meta['dazim']}° | **veff:** {meta['veff']}")

# ---------------------------------------------------------------------------
# DATOS FILTRADOS
# ---------------------------------------------------------------------------
d0 = pd.Timestamp(dr[0], tz="UTC") if len(dr) >= 1 else pd.Timestamp(dmin, tz="UTC")
d1 = pd.Timestamp(dr[1], tz="UTC") if len(dr) == 2 else pd.Timestamp(dmax, tz="UTC")

ipf = ip_df[(ip_df["Datetime (UTC)"] >= d0) & (ip_df["Datetime (UTC)"] <= d1)
            & (ip_df["IP"] >= 1) & (ip_df["Station Name"].isin(stas))].copy()
erf = er_df[(er_df["Start Date (UTC)"] >= d0) & (er_df["End Date (UTC)"] <= d1)].copy()

# ---------------------------------------------------------------------------
# CABECERA PRINCIPAL
# ---------------------------------------------------------------------------
st.title(f"🌋 {meta['volcano']} — Detección infrasónica de largo alcance")
st.markdown(
    f"Análisis con **openVIS** · Red IMS · Datos BGR (Hupe et al., 2022) · "
    f"Período: **{d0.date()}** a **{d1.date()}**"
)

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("🔴 Erupciones VIS", len(erf),
          help="Períodos donde IP superó el umbral en al menos una estación")
k2.metric(f"📡 Ventanas IP≥{ip_thr}", int((ipf["IP"] >= ip_thr).sum()),
          help="Ventanas de 2h donde el IP superó el umbral configurado")
k3.metric("📈 IP máximo", f"{ipf['IP'].max():.0f}" if len(ipf) else "—",
          help="Valor máximo del Parámetro Infrasónico en el período")
k4.metric("🗼 Estaciones", len(stas),
          help="Estaciones IMS incluidas en el análisis")
k5.metric("📏 Dist. mínima",
          f"{min([haversine_km(meta['lat'], meta['lon'], float(sta_cfg[sta_cfg['Station Name']==s]['Latitude'].values[0]), float(sta_cfg[sta_cfg['Station Name']==s]['Longitude'].values[0])) for s in stas if not sta_cfg[sta_cfg['Station Name']==s].empty], default=0):.0f} km",
          help="Distancia de la estación más cercana al volcán")

st.divider()

# ---------------------------------------------------------------------------
# GRÁFICO IP + MAPA
# ---------------------------------------------------------------------------
col_chart, col_map = st.columns([3, 2])

with col_chart:
    st.subheader("📊 Serie temporal del Parámetro Infrasónico (IP)")
    st.caption(
        "Cada punto representa una ventana de 2 horas. "
        "El **color** indica la frecuencia media (Hz). "
        "El **tamaño** es proporcional al número de detecciones PMCC. "
        "La **línea roja** marca el umbral de erupción (IP = 100)."
    )

    fig = go.Figure()

    colors_sta = px.colors.qualitative.Set2
    for i, s in enumerate(stas):
        d = ipf[ipf["Station Name"] == s]
        if d.empty:
            continue
        dist_km = 0
        row_s = sta_cfg[sta_cfg["Station Name"] == s]
        if not row_s.empty:
            dist_km = haversine_km(meta["lat"], meta["lon"],
                                   float(row_s["Latitude"].values[0]),
                                   float(row_s["Longitude"].values[0]))
        fig.add_trace(go.Scatter(
            x=d["Datetime (UTC)"], y=d["IP"],
            mode="markers",
            name=f"{s} ({dist_km:.0f} km)",
            marker=dict(
                size=np.clip(d["Number of Detections"] / 5, 3, 18),
                color=d["Mean Frequency (Hz)"],
                colorscale="Viridis", cmin=1, cmax=3,
                showscale=(i == 0),
                colorbar=dict(title="Freq (Hz)", x=1.01, len=0.6, thickness=12),
                opacity=0.85,
            ),
            customdata=np.stack([
                d["Mean Source Amplitude (Pa)"],
                d["Persistency"],
                d["Mean Frequency (Hz)"],
                d["Number of Detections"],
            ], axis=-1),
            hovertemplate=(
                "<b>%{x|%Y-%m-%d %H:%M} UTC</b><br>"
                "IP: <b>%{y:.1f}</b><br>"
                "Amplitud fuente: %{customdata[0]:.1f} Pa<br>"
                "Persistencia: %{customdata[1]:.1f}%<br>"
                "Frecuencia media: %{customdata[2]:.2f} Hz<br>"
                "N° detecciones PMCC: %{customdata[3]:.0f}"
                "<extra>" + s + "</extra>"
            ),
        ))

    # Umbral IP
    fig.add_hline(y=ip_thr, line_dash="dash", line_color="red", line_width=1.5,
                  annotation_text=f"Umbral erupción (IP={ip_thr})",
                  annotation_position="top left",
                  annotation_font_color="red")

    # Períodos eruptivos VIS (franjas de color por confianza)
    for _, r in erf.iterrows():
        n_sta = len(sa_df[(sa_df["Eruption Code"] == r["Eruption Code"]) & (sa_df["Detecting"] == 1)])
        color = CONF_COLORS.get(min(n_sta, 3), "#c0392b")
        fig.add_vrect(
            x0=r["Start Date (UTC)"], x1=r["End Date (UTC)"],
            fillcolor=color, opacity=0.15, layer="below", line_width=0,
        )

    # Erupción real conocida (línea dorada)
    for ev in KNOWN_ERUPTIONS.get(meta["volcano"], []):
        fig.add_vline(
            x=pd.Timestamp(ev["fecha"], tz="UTC").value / 1e6,
            line_color="gold", line_width=2, line_dash="dot",
            annotation_text=ev["label"],
            annotation_position="top",
            annotation_font_color="goldenrod",
        )

    fig.update_layout(
        height=420,
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis_title="Fecha (UTC)",
        yaxis_title="Parámetro Infrasónico (IP)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="#fafafa",
        paper_bgcolor="#fafafa",
    )
    st.plotly_chart(fig, use_container_width=True)

with col_map:
    st.subheader("🗺️ Red de estaciones IMS")
    st.caption(
        "Azul: estaciones infrasónicas IMS usadas en el análisis. "
        "Rojo: volcán monitoreado. El tamaño indica el total de detecciones."
    )

    mrows = []
    for _, r in sta_cfg[sta_cfg["Station Name"].isin(stas)].iterrows():
        nd = int(ipf[ipf["Station Name"] == r["Station Name"]]["Number of Detections"].sum())
        dist = haversine_km(meta["lat"], meta["lon"],
                            float(r["Latitude"]), float(r["Longitude"]))
        mrows.append(dict(
            Nombre=r["Station Name"],
            Lat=float(r["Latitude"]), Lon=float(r["Longitude"]),
            Tipo="Estación IMS",
            Detecciones=nd,
            Distancia_km=round(dist),
        ))
    mrows.append(dict(
        Nombre=meta["volcano"],
        Lat=meta["lat"], Lon=meta["lon"],
        Tipo="Volcán",
        Detecciones=0,
        Distancia_km=0,
    ))
    mdf = pd.DataFrame(mrows)

    # Líneas estación → volcán
    fig_map = go.Figure()
    for _, r in mdf[mdf["Tipo"] == "Estación IMS"].iterrows():
        fig_map.add_trace(go.Scattermapbox(
            lat=[r["Lat"], meta["lat"]],
            lon=[r["Lon"], meta["lon"]],
            mode="lines",
            line=dict(width=1, color="#90CAF9"),
            hoverinfo="skip", showlegend=False,
        ))
    # Estaciones
    sta_df_map = mdf[mdf["Tipo"] == "Estación IMS"]
    fig_map.add_trace(go.Scattermapbox(
        lat=sta_df_map["Lat"], lon=sta_df_map["Lon"],
        mode="markers+text",
        marker=dict(size=10, color="#1565C0"),
        text=sta_df_map["Nombre"],
        textposition="top right",
        textfont=dict(size=9, color="#1565C0"),
        customdata=np.stack([sta_df_map["Detecciones"], sta_df_map["Distancia_km"]], axis=-1),
        hovertemplate="<b>%{text}</b><br>Detecciones: %{customdata[0]}<br>Distancia: %{customdata[1]} km<extra></extra>",
        name="Estación IMS",
        showlegend=True,
    ))
    # Volcán
    volc_df = mdf[mdf["Tipo"] == "Volcán"]
    fig_map.add_trace(go.Scattermapbox(
        lat=volc_df["Lat"], lon=volc_df["Lon"],
        mode="markers+text",
        marker=dict(size=16, color="#C62828"),
        text=volc_df["Nombre"],
        textposition="top right",
        textfont=dict(size=10, color="#C62828"),
        hovertemplate="<b>%{text}</b><extra>Volcán</extra>",
        name="Volcán",
        showlegend=True,
    ))
    fig_map.update_layout(
        mapbox_style="carto-positron",
        mapbox=dict(center=dict(lat=meta["lat"], lon=meta["lon"]), zoom=1.8),
        height=420,
        margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation="h", y=1.05, bgcolor="rgba(255,255,255,0.8)"),
    )
    st.plotly_chart(fig_map, use_container_width=True)

# ---------------------------------------------------------------------------
# ERUPCIONES DETECTADAS
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🔴 Períodos eruptivos detectados por VIS")
st.caption(
    "El VIS agrupa las ventanas donde IP ≥ umbral en 'períodos eruptivos'. "
    "El nivel de confianza depende de cuántas estaciones detectan simultáneamente."
)

if erf.empty:
    st.info("No se detectaron períodos eruptivos en el rango seleccionado con los filtros actuales.")
else:
    es = erf[["Eruption Code", "Start Date (UTC)", "End Date (UTC)",
              "Confidence Level", "Estimated Amplitude [Pa]"]].copy()
    es["Duración (h)"]  = ((es["End Date (UTC)"] - es["Start Date (UTC)"]).dt.total_seconds() / 3600).round(1)
    es["Confianza"]     = es["Confidence Level"].map(CONF_LABELS).fillna("Alta")
    es["Amplitud (Pa)"] = es["Estimated Amplitude [Pa]"].round(1)
    es["Inicio (UTC)"]  = es["Start Date (UTC)"].dt.strftime("%Y-%m-%d %H:%M")
    es["Fin (UTC)"]     = es["End Date (UTC)"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(
        es[["Eruption Code", "Inicio (UTC)", "Fin (UTC)", "Duración (h)", "Confianza", "Amplitud (Pa)"]],
        use_container_width=True, hide_index=True,
    )

# ---------------------------------------------------------------------------
# ESTADÍSTICAS POR ESTACIÓN
# ---------------------------------------------------------------------------
st.divider()
st.subheader("📡 Estadísticas por estación")
st.caption(
    "Resumen del comportamiento de cada estación IMS en el período analizado. "
    "La amplitud está corregida por distancia (estimada en la fuente a 1 km)."
)

rows = []
for s in stas:
    d = ipf[ipf["Station Name"] == s]
    if d.empty:
        continue
    row_s = sta_cfg[sta_cfg["Station Name"] == s]
    dist = haversine_km(meta["lat"], meta["lon"],
                        float(row_s["Latitude"].values[0]),
                        float(row_s["Longitude"].values[0])) if not row_s.empty else 0
    rows.append({
        "Estación": s,
        "Distancia (km)": round(dist),
        "Ventanas con IP≥1": len(d),
        f"Ventanas IP≥{ip_thr}": len(d[d["IP"] >= ip_thr]),
        "IP máximo": round(d["IP"].max(), 1),
        "Amp. fuente máx. (Pa)": round(d["Mean Source Amplitude (Pa)"].max(), 1),
        "Freq. media (Hz)": round(d["Mean Frequency (Hz)"].mean(), 2),
        "Persistencia media (%)": round(d["Persistency"].mean(), 1),
    })
if rows:
    st.dataframe(pd.DataFrame(rows).sort_values("Distancia (km)"),
                 use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# PIE DE PÁGINA
# ---------------------------------------------------------------------------
st.divider()
c1, c2 = st.columns(2)
with c1:
    st.caption(
        "**Metodología:** De Negri et al. (openVIS) · "
        "**Datos:** Hupe et al. (2022) — BGR IMS open-access bulletins · "
        "**Atenuación:** Le Pichon et al. (2012)"
    )
with c2:
    st.caption(
        "Exploración personal · N. Mendoza · Chile · "
        "[GitHub](https://github.com/MendozaVolcanic/openVIS-Colaboracion-1)"
    )
