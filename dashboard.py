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

# Conocimiento volcanológico — VEI documentado (catálogo GVP / SERNAGEOMIN)
KNOWN_VEI = {
    "Puyehue-Cordon Caulle": 5,
    "Calbuco":               4,
    "Chaiten":               4,
    "Chaiten ":              4,
    "Hudson. Cerro":         2,
    "Hudson, Cerro":         2,
    "Villarrica":            3,
}

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


def classify_run(ip_df, volcano_name, ip_thr=100):
    """Clasifica un run en DETECTADO / CROSS-CONTAMINATION / NO DETECTADO
    contra el catálogo KNOWN_ERUPTIONS (con padding de ±24h)."""
    pad = pd.Timedelta(hours=24)
    sig = ip_df[ip_df["IP"] >= ip_thr]
    if sig.empty:
        return "NO_DETECTADO", "❌", "#cccccc", \
               f"VIS no detectó actividad infrasónica (IP ≥ {ip_thr}) " \
               f"en este período. Útil como umbral inferior del método."
    own = KNOWN_ERUPTIONS.get(volcano_name, [])
    own_windows = [pd.Timestamp(e["fecha"], tz="UTC") for e in own]
    in_own = sig["Datetime (UTC)"].apply(
        lambda t: any(abs((t - w).total_seconds()) < pad.total_seconds() * 7 for w in own_windows)
    ).sum() if own_windows else 0
    cross_count = 0
    cross_targets = set()
    for other_volc, evs in KNOWN_ERUPTIONS.items():
        if other_volc == volcano_name: continue
        for ev in evs:
            w = pd.Timestamp(ev["fecha"], tz="UTC")
            mask = (sig["Datetime (UTC)"] - w).abs() < pad
            if mask.any():
                cross_count += int(mask.sum())
                cross_targets.add(other_volc)
    total = len(sig)
    if total > 0 and cross_count / total > 0.5:
        return "CROSS", "⚠️", "#e67e22", \
               f"**Posible contaminación cruzada** con {', '.join(cross_targets)}. " \
               f"{cross_count}/{total} ventanas IP≥{ip_thr} caen en la fecha de erupción " \
               f"de otro volcán cercano (mismo azimut desde la estación detectora)."
    if in_own > 0:
        return "DETECTADO", "✅", "#2ecc71", \
               f"Erupción detectada: {in_own}/{total} ventanas IP≥{ip_thr} dentro de la " \
               f"ventana eruptiva conocida del catálogo GVP."
    return "DETECTADO_INDIRECTO", "🔍", "#3498db", \
           f"{total} ventanas IP≥{ip_thr} encontradas, sin coincidencia con catálogo principal. " \
           f"Posible actividad secundaria o no documentada — revisar manualmente."


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
# Permalink (idea #4): leer query params al inicio
try:
    qp = st.query_params
except Exception:
    qp = {}

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

    # Permalink: si hay ?run=<basename>, intentar pre-seleccionarlo
    default_run_idx = 0
    if qp.get("run"):
        wanted = qp["run"]
        for i, r in enumerate(runs):
            if os.path.basename(r) == wanted:
                default_run_idx = i; break

    sel_run = st.selectbox(
        "Ejecución VIS",
        runs,
        index=default_run_idx,
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

    # Vista evento (idea #2): si hay erupción conocida, ofrecer zoom ±48h
    known_dates = [pd.Timestamp(e["fecha"]).date() for e in KNOWN_ERUPTIONS.get(meta["volcano"], [])
                   if dmin <= pd.Timestamp(e["fecha"]).date() <= dmax]
    view_options = ["Panorámica (todo el período)"]
    if known_dates:
        view_options.append(f"Zoom evento (±48 h alrededor de {known_dates[0]})")
    default_view = qp.get("view", view_options[0])
    if default_view not in view_options: default_view = view_options[0]
    view_mode = st.radio("Vista temporal", view_options,
                          index=view_options.index(default_view),
                          help="Zoom centra el gráfico en la fecha eruptiva conocida del catálogo GVP")

    from datetime import timedelta as _td
    if view_mode.startswith("Zoom") and known_dates:
        ev_date = known_dates[0]
        suggested = (max(dmin, ev_date - _td(days=2)), min(dmax, ev_date + _td(days=2)))
    else:
        suggested = (dmin, dmax)

    # Permalink fechas
    if qp.get("d0") and qp.get("d1"):
        try:
            from datetime import date as _date
            qd0 = _date.fromisoformat(qp["d0"]); qd1 = _date.fromisoformat(qp["d1"])
            if dmin <= qd0 <= dmax and dmin <= qd1 <= dmax:
                suggested = (qd0, qd1)
        except Exception: pass

    dr = st.date_input("Rango de fechas", value=suggested,
                        min_value=dmin, max_value=dmax)

    default_ip = int(qp.get("ip", "100")) if str(qp.get("ip", "100")).isdigit() else 100
    ip_thr = st.slider("Umbral IP (detección)", 0, 500, default_ip,
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

    # Persistir filtros en query params (permalink, idea #4)
    try:
        st.query_params.update({
            "run":  os.path.basename(sel_run),
            "d0":   str(dr[0]) if len(dr) >= 1 else str(dmin),
            "d1":   str(dr[1]) if len(dr) == 2 else str(dmax),
            "ip":   str(ip_thr),
            "view": view_mode,
        })
    except Exception: pass

    st.divider()
    st.subheader("📤 Exportar")
    # NOTA: ipf y erf se calculan más abajo. Aquí preparamos placeholders y los rellenamos al final.
    export_placeholder = st.empty()

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

# Banner de estado (idea #3) — clasifica el run en DETECTADO/CROSS/NO
status, icon, color, msg = classify_run(ipf, meta["volcano"], ip_thr)
st.markdown(
    f"""
    <div style="background:{color}22; border-left:5px solid {color};
                padding:12px 18px; border-radius:6px; margin:10px 0;">
        <div style="font-size:1.2em; font-weight:600; color:{color};">
            {icon} Estado del análisis: {status.replace('_', ' ')}
        </div>
        <div style="margin-top:6px; color:#444;">{msg}</div>
    </div>
    """,
    unsafe_allow_html=True,
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
# ANÁLISIS AVANZADO (ideas #9, #10, #12, #14)
# ---------------------------------------------------------------------------
st.divider()
st.subheader("🔬 Análisis avanzado")
st.caption(
    "Vistas complementarias para inspección detallada: panorámica temporal, "
    "distribución de IP, geometría de detección y comparación entre casos de estudio."
)

tab_heat, tab_hist, tab_bear, tab_vei = st.tabs([
    "🌡️ Heatmap tiempo-estación",
    "📊 Histograma de IP",
    "🧭 Diagrama de azimutes",
    "📈 VEI vs IP máx (todos los runs)",
])

# --- IDEA #10: Heatmap único tiempo-estación ---
with tab_heat:
    st.caption(
        "Una sola vista panorámica: filas = estaciones, columnas = tiempo, color = log(IP). "
        "Permite detectar pulsos eruptivos que reaparecen en distintas estaciones."
    )
    if ipf.empty:
        st.info("Sin datos en el rango actual.")
    else:
        hm = ipf.copy()
        hm["t_bin"] = hm["Datetime (UTC)"].dt.floor("6h")
        pivot = hm.pivot_table(index="Station Name", columns="t_bin", values="IP", aggfunc="max")
        pivot = pivot.reindex(sorted(pivot.index, key=lambda s: -haversine_km(
            meta["lat"], meta["lon"],
            float(sta_cfg[sta_cfg["Station Name"]==s]["Latitude"].values[0]) if not sta_cfg[sta_cfg["Station Name"]==s].empty else 0,
            float(sta_cfg[sta_cfg["Station Name"]==s]["Longitude"].values[0]) if not sta_cfg[sta_cfg["Station Name"]==s].empty else 0,
        )))
        z = np.log10(pivot.values.astype(float).clip(min=0.1))
        fig_hm = go.Figure(data=go.Heatmap(
            z=z, x=pivot.columns, y=pivot.index,
            colorscale="Inferno",
            colorbar=dict(title="log₁₀(IP)"),
            hovertemplate="%{y}<br>%{x|%Y-%m-%d %H:%M}<br>log(IP)=%{z:.2f}<extra></extra>",
            zmin=0, zmax=4,
        ))
        # Línea dorada en fechas conocidas
        for ev in KNOWN_ERUPTIONS.get(meta["volcano"], []):
            fig_hm.add_vline(x=pd.Timestamp(ev["fecha"], tz="UTC").value / 1e6,
                             line_color="gold", line_width=2, line_dash="dot")
        fig_hm.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                             xaxis_title="Fecha (UTC)", yaxis_title="Estación (lejos→cerca)")
        st.plotly_chart(fig_hm, use_container_width=True)

# --- IDEA #12: Histograma log(IP) ---
with tab_hist:
    st.caption(
        "Distribución logarítmica de los valores de IP. "
        "El umbral IP=100 (línea roja) separa ruido de fondo de detecciones significativas. "
        "Una cola larga a la derecha indica eventos eruptivos en el período."
    )
    ip_all = ip_df[ip_df["IP"] >= 1]["IP"].values
    if len(ip_all) == 0:
        st.info("Sin datos.")
    else:
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(
            x=np.log10(ip_all), nbinsx=40,
            marker_color="#3498db", marker_line_color="white", marker_line_width=0.5,
            name="Todas las ventanas",
        ))
        fig_h.add_vline(x=np.log10(ip_thr), line_color="red", line_dash="dash", line_width=2,
                        annotation_text=f"Umbral IP={ip_thr}", annotation_position="top right",
                        annotation_font_color="red")
        n_below = int((ip_all < ip_thr).sum())
        n_above = int((ip_all >= ip_thr).sum())
        fig_h.update_layout(
            height=320, margin=dict(l=10, r=10, t=30, b=10),
            xaxis_title="log₁₀(IP)", yaxis_title="N° de ventanas (2h)",
            title=f"Bajo umbral: {n_below}  ·  Sobre umbral: {n_above}  "
                  f"({100*n_above/(n_below+n_above):.1f}% señal)",
            plot_bgcolor="#fafafa",
        )
        st.plotly_chart(fig_h, use_container_width=True)

# --- IDEA #9: Diagrama de azimutes (cross-contamination) ---
with tab_bear:
    st.caption(
        "Para cada estación IMS detectora, muestra el **bearing geométrico** hacia el volcán "
        "objetivo (rojo) y hacia los volcanes vecinos del catálogo Smithsonian (gris). "
        "Cuando dos volcanes caen dentro del mismo cono de tolerancia Dazim, "
        "una erupción de uno puede atribuirse al otro (cross-contamination)."
    )
    def bearing_deg(lat1, lon1, lat2, lon2):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dl = math.radians(lon2 - lon1)
        x = math.sin(dl) * math.cos(p2)
        y = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
        return (math.degrees(math.atan2(x, y)) + 360) % 360

    try:
        volc_all = pd.read_csv(os.path.join(CFG_DIR, "volcanoes.csv"),
                               sep=";", encoding="latin-1", decimal=",")
        # Volcanes chilenos cercanos (radio 800 km del objetivo)
        nearby = []
        for _, vr in volc_all[volc_all["Country"]=="Chile"].iterrows():
            try:
                vlat = float(str(vr["Latitude"]).replace(",","."))
                vlon = float(str(vr["Longitude"]).replace(",","."))
            except Exception: continue
            d = haversine_km(meta["lat"], meta["lon"], vlat, vlon)
            if 5 < d < 800:
                nearby.append((vr["Volcano Name"], vlat, vlon, d))

        dazim = float(meta["dazim"]) if str(meta["dazim"]).replace(".","").isdigit() else 5
        active_stas = [s for s in stas if not sta_cfg[sta_cfg["Station Name"]==s].empty]
        n = len(active_stas)
        if n == 0:
            st.info("Sin estaciones activas.")
        else:
            fig_b = go.Figure()
            for i, s in enumerate(active_stas):
                row_s = sta_cfg[sta_cfg["Station Name"]==s].iloc[0]
                slat, slon = float(row_s["Latitude"]), float(row_s["Longitude"])
                target_baz = bearing_deg(slat, slon, meta["lat"], meta["lon"])
                # Cono de tolerancia Dazim
                fig_b.add_trace(go.Barpolar(
                    r=[1], theta=[target_baz], width=[2*dazim],
                    marker_color=f"rgba(231,76,60,0.25)",
                    name=f"{s}: cono ±{dazim}°", showlegend=(i==0),
                ))
                # Bearing al objetivo
                fig_b.add_trace(go.Scatterpolar(
                    r=[0,1], theta=[target_baz, target_baz], mode="lines+markers",
                    line=dict(color="#c0392b", width=2),
                    marker=dict(size=[0,8], color="#c0392b"),
                    name=f"{s} → {meta['volcano']}", showlegend=False,
                    hovertemplate=f"{s} → {meta['volcano']}<br>Bearing: {target_baz:.1f}°<extra></extra>",
                ))
                # Bearings a vecinos
                for nm, nlat, nlon, nd in nearby:
                    nbaz = bearing_deg(slat, slon, nlat, nlon)
                    diff = abs((nbaz - target_baz + 180) % 360 - 180)
                    if diff < 30:  # solo mostrar los azimutalmente cercanos
                        col = "#e67e22" if diff < dazim else "#888"
                        fig_b.add_trace(go.Scatterpolar(
                            r=[0,0.7], theta=[nbaz, nbaz], mode="lines",
                            line=dict(color=col, width=1.2, dash="dot"),
                            opacity=0.6, showlegend=False,
                            hovertemplate=f"{s} → {nm} ({nd:.0f} km)<br>Bearing: {nbaz:.1f}°<br>Δ azimut: {diff:.1f}°<extra></extra>",
                        ))
            fig_b.update_layout(
                height=480,
                polar=dict(
                    radialaxis=dict(visible=False, range=[0,1]),
                    angularaxis=dict(direction="clockwise", rotation=90, tickmode="array",
                                     tickvals=[0,90,180,270],
                                     ticktext=["N","E","S","W"]),
                ),
                title=f"Bearings desde estaciones IMS hacia {meta['volcano']} (rojo) "
                      f"y volcanes vecinos (naranja=dentro de Dazim, gris=fuera)",
                margin=dict(l=20, r=20, t=60, b=20),
            )
            st.plotly_chart(fig_b, use_container_width=True)
    except Exception as e:
        st.warning(f"No se pudo generar el diagrama: {e}")

# --- IDEA #14: VEI vs IP_max ---
with tab_vei:
    st.caption(
        "Compara los casos de estudio cargados: VEI documentado (catálogo GVP) "
        "versus IP_máx alcanzado en cada análisis. Permite calibrar empíricamente "
        "qué magnitud eruptiva es detectable por VIS desde las estaciones IMS sudamericanas."
    )
    pts = []
    for r in runs:
        m = run_metas[r]
        try:
            ip_r, _, _ = load_run(r)
            vei = KNOWN_VEI.get(m["volcano"])
            if vei is None: continue
            pts.append({
                "Run": m["label"],
                "Volcano": m["volcano"].replace(".", ","),
                "VEI": vei,
                "IP_max": float(ip_r["IP"].max()) if len(ip_r) else 0.0,
                "Stations": ip_r[ip_r["IP"]>=1]["Station Name"].nunique(),
            })
        except Exception: continue
    if not pts:
        st.info("Aún no hay suficientes runs cargados.")
    else:
        df_v = pd.DataFrame(pts)
        df_v["IP_plot"] = df_v["IP_max"].clip(lower=0.5)
        fig_v = go.Figure()
        fig_v.add_trace(go.Scatter(
            x=df_v["VEI"], y=df_v["IP_plot"],
            mode="markers+text",
            marker=dict(size=14 + df_v["Stations"]*4, color=df_v["VEI"],
                        colorscale="YlOrRd", line=dict(color="black", width=1)),
            text=df_v["Volcano"], textposition="top center",
            textfont=dict(size=10),
            customdata=np.stack([df_v["IP_max"], df_v["Stations"], df_v["Run"]], axis=-1),
            hovertemplate="<b>%{customdata[2]}</b><br>VEI: %{x}<br>IP_max: %{customdata[0]:.1f}"
                          "<br>Estaciones detectoras: %{customdata[1]}<extra></extra>",
        ))
        fig_v.add_hline(y=ip_thr, line_dash="dash", line_color="red",
                        annotation_text=f"Umbral IP={ip_thr}", annotation_position="bottom right")
        fig_v.update_layout(
            height=420, margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(title="VEI documentado", dtick=1, range=[0.5, 6]),
            yaxis=dict(title="IP máximo alcanzado", type="log"),
            plot_bgcolor="#fafafa",
        )
        st.plotly_chart(fig_v, use_container_width=True)

# ---------------------------------------------------------------------------
# EXPORT (idea #5) — rellenar el placeholder del sidebar con datos filtrados
# ---------------------------------------------------------------------------
def _build_csv(df):
    return df.to_csv(index=False).encode("utf-8")

def _build_ical(eruptions, volcano):
    """Genera un calendario .ics con un VEVENT por período eruptivo VIS."""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//openVIS//Southern Andes//ES",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for _, e in eruptions.iterrows():
        t0 = e["Start Date (UTC)"].strftime("%Y%m%dT%H%M%SZ")
        t1 = e["End Date (UTC)"].strftime("%Y%m%dT%H%M%SZ")
        uid = f"{e.get('Eruption Code','vis')}-{t0}@openvis"
        lines += [
            "BEGIN:VEVENT", f"UID:{uid}",
            f"DTSTAMP:{t0}", f"DTSTART:{t0}", f"DTEND:{t1}",
            f"SUMMARY:VIS detection — {volcano}",
            f"DESCRIPTION:Confidence={e.get('Confidence Level','?')}\\,"
            f"Amplitude={e.get('Estimated Amplitude [Pa]', '?'):.2f} Pa",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")

with st.sidebar:
    with export_placeholder.container():
        st.download_button(
            "⬇️ IP (CSV)",
            data=_build_csv(ipf),
            file_name=f"openvis_ip_{meta['volcano'].replace(' ','_')}_{d0.date()}_{d1.date()}.csv",
            mime="text/csv",
            help="Todas las ventanas IP≥1 con frecuencia, amplitud, persistencia",
            use_container_width=True,
        )
        st.download_button(
            "⬇️ Erupciones VIS (CSV)",
            data=_build_csv(erf) if not erf.empty else b"",
            file_name=f"openvis_eruptions_{meta['volcano'].replace(' ','_')}_{d0.date()}_{d1.date()}.csv",
            mime="text/csv", use_container_width=True,
            disabled=erf.empty,
        )
        st.download_button(
            "📅 Períodos eruptivos (iCal)",
            data=_build_ical(erf, meta["volcano"]) if not erf.empty else b"",
            file_name=f"openvis_eruptions_{meta['volcano'].replace(' ','_')}.ics",
            mime="text/calendar",
            help="Importa a Google Calendar / Outlook para revisar eventos",
            use_container_width=True,
            disabled=erf.empty,
        )

# ---------------------------------------------------------------------------
# DOCUMENTACIÓN — idea #19 (lee HALLAZGOS.md y BUGS_FOUND.md)
# ---------------------------------------------------------------------------
st.divider()
with st.expander("📚 Documentación científica del proyecto", expanded=False):
    doc_tab, bugs_tab = st.tabs(["🔬 Hallazgos científicos", "🐛 Bugs encontrados"])
    for fname, tab in [("HALLAZGOS.md", doc_tab), ("BUGS_FOUND.md", bugs_tab)]:
        with tab:
            fpath = os.path.join(BASE_DIR, fname)
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    st.markdown(f.read())
            else:
                st.info(f"{fname} no encontrado en el repo.")

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
