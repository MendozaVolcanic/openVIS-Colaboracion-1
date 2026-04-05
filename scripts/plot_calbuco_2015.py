"""
plot_calbuco_2015.py - Visualizacion de resultados VIS para Calbuco (abril 2015)

Uso (desde la raiz del repo):
    python scripts/plot_calbuco_2015.py

Guarda la figura en:
    data/figures/calbuco_2015_results.png

Nota: lee archivos .pkl generados por openVIS (formato interno del proyecto).
"""

import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

# ---------------------------------------------------------------------------
# RUTAS
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR  = ROOT / "data" / "results" / "20260404T210517"
FIGURES_DIR  = ROOT / "data" / "figures"
CFG_STATIONS = ROOT / "cfg" / "stations.csv"
CFG_VOLCANOES= ROOT / "cfg" / "volcanoes.csv"
OUTPUT_FIG   = FIGURES_DIR / "calbuco_2015_results.png"

FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# FECHAS
# ---------------------------------------------------------------------------
DATE_START = datetime(2015, 4,  1, tzinfo=timezone.utc)
DATE_END   = datetime(2015, 6,  1, tzinfo=timezone.utc)

# Fases reales confirmadas (GVP / De Negri & Matoza 2023)
ERUPTION_PHASES = [
    (datetime(2015, 4, 22, 21, 0, tzinfo=timezone.utc),
     datetime(2015, 4, 23,  3, 0, tzinfo=timezone.utc), "Fase 1"),
    (datetime(2015, 4, 23,  4, 0, tzinfo=timezone.utc),
     datetime(2015, 4, 23, 10, 0, tzinfo=timezone.utc), "Fase 2"),
]

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# CARGA DE DATOS
# ---------------------------------------------------------------------------
print("Cargando datos...")

stations_cfg  = pd.read_csv(CFG_STATIONS)
volcanoes_cfg = pd.read_csv(CFG_VOLCANOES, sep=";", encoding="latin-1", decimal=",")

calb = volcanoes_cfg[volcanoes_cfg["Volcano Name"] == "Calbuco"].iloc[0]
CALB_LAT = float(str(calb["Latitude"]).replace(",", "."))
CALB_LON = float(str(calb["Longitude"]).replace(",", "."))

# openVIS genera estos pkl como formato interno del proyecto
ips        = pd.read_pickle(RESULTS_DIR / "ip_results.pkl")
eruptions  = pd.read_pickle(RESULTS_DIR / "eruption_results.pkl")
assoc_sta  = pd.read_pickle(RESULTS_DIR / "assoc_sta_er.pkl")

ips = ips[(ips["Datetime (UTC)"] >= DATE_START) & (ips["Datetime (UTC)"] <= DATE_END)]
eruptions = eruptions[
    (eruptions["Start Date (UTC)"] >= DATE_START) &
    (eruptions["End Date (UTC)"]   <= DATE_END)
]

# Distancias a Calbuco
station_dists = {}
for sta in ips["Station Name"].unique():
    row = stations_cfg[stations_cfg["Station Name"] == sta]
    if row.empty:
        station_dists[sta] = 9999
        continue
    station_dists[sta] = haversine_km(
        CALB_LAT, CALB_LON,
        float(row["Latitude"].values[0]),
        float(row["Longitude"].values[0])
    )

# Ordenar mayor a menor distancia; filtrar estaciones con al menos un IP >= 1
stations_sorted = [
    s for s in sorted(station_dists, key=station_dists.get, reverse=True)
    if len(ips[(ips["Station Name"] == s) & (ips["IP"] >= 1)]) > 0
]
num_sta = len(stations_sorted)
print(f"Estaciones con IP >= 1: {stations_sorted}")

# ---------------------------------------------------------------------------
# FIGURA
# ---------------------------------------------------------------------------
COLOR_LEVELS   = ["yellowgreen", "coral", "red", "purple"]
SUBPLOT_LABELS = list("abcdefghij")

fig, axes = plt.subplots(
    num_sta + 1, 3,
    figsize=(10, 2.2 * (num_sta + 1)),
    gridspec_kw={"width_ratios": [0.03, 1, 0.03]},
    sharex=True,
)
fig.suptitle(
    "VIS  -  Erupcion Calbuco  |  abril-mayo 2015\n"
    "veff = 1  |  sin correccion de azimut  |  5 estaciones IMS",
    fontsize=11, y=1.01
)

plt.rc("font", size=9)
sc_ref = None   # para la colorbar

# ---- Un panel por estacion ------------------------------------------------
for ax_i, sta in enumerate(stations_sorted):
    ip_sta = ips[(ips["Station Name"] == sta) & (ips["IP"] >= 1)].copy()
    dist_km = station_dists[sta]
    ax = axes[ax_i, 1]

    sc_ref = ax.scatter(
        ip_sta["Datetime (UTC)"],
        np.log10(ip_sta["IP"]),
        s          = ip_sta["Number of Detections"] * 0.08,
        c          = ip_sta["Mean Frequency (Hz)"],
        cmap       = "viridis",
        marker     = ".",
        edgecolors = "none",
        alpha      = 0.85,
        vmin=1, vmax=3,
        zorder=10,
    )

    # Umbral IP = 100 -> log10 = 2
    ax.axhline(y=2, color="red", linewidth=0.8, linestyle="--", alpha=0.6)

    # Franjas doradas: fases reales de la erupcion
    for ph_start, ph_end, _ in ERUPTION_PHASES:
        ax.axvspan(ph_start, ph_end, color="gold", alpha=0.3, zorder=1)

    ax.spines[["right", "top"]].set_visible(False)
    ax.grid(axis="x", alpha=0.3)
    ax.set_ylabel("log(IP)", fontsize=8)
    ax.set_title(
        f"({SUBPLOT_LABELS[ax_i]}) {sta}  {dist_km:.0f} km",
        loc="left", fontsize=9, fontweight="bold", pad=3
    )
    axes[ax_i, 0].axis("off")
    axes[ax_i, 2].axis("off")

# ---- Panel de periodos eruptivos VIS --------------------------------------
ax_er = axes[num_sta, 1]
ax_er.spines[["right", "top"]].set_visible(False)
ax_er.grid(axis="x", alpha=0.3)

for _, er in eruptions.iterrows():
    t0, t1 = er["Start Date (UTC)"], er["End Date (UTC)"]
    amp     = er["Estimated Amplitude [Pa]"]
    code    = er["Eruption Code"]
    detecting = assoc_sta[(assoc_sta["Eruption Code"] == code) & (assoc_sta["Detecting"] == 1)]
    n = len(detecting)
    color = COLOR_LEVELS[min(n - 1, len(COLOR_LEVELS) - 1)]
    ax_er.axvspan(t0, t1, color=color, alpha=0.85)
    ax_er.plot([t0, t1], [amp, amp], color="black", linewidth=1.5)

for ph_start, ph_end, _ in ERUPTION_PHASES:
    ax_er.axvspan(ph_start, ph_end, color="gold", alpha=0.3, zorder=0)

ax_er.set_ylabel("Amp. [Pa]", fontsize=8)
ax_er.set_title(
    f"({SUBPLOT_LABELS[num_sta]}) Periodos eruptivos VIS  |  amplitud estimada a 1 km",
    loc="left", fontsize=9, fontweight="bold", pad=3
)
axes[num_sta, 0].axis("off")

# Leyenda inferior derecha
ax_legend = axes[num_sta, 2]
ax_legend.axis("off")
patches = [mpatches.Patch(color=COLOR_LEVELS[i], label=f"{i+1} estac.") for i in range(3)]
patches.append(mpatches.Patch(color="gold", alpha=0.5, label="Erupcion real"))
ax_legend.legend(handles=patches, loc="center left", fontsize=7.5,
                 title="# estaciones", title_fontsize=8)

# Colorbar frecuencia
if sc_ref is not None:
    cax = fig.add_axes([0.92, 0.35, 0.013, 0.50])
    cb  = fig.colorbar(sc_ref, cax=cax)
    cb.set_label("Frec. media (Hz)", fontsize=9)

ax_er.xaxis.set_major_formatter(
    mdates.ConciseDateFormatter(ax_er.xaxis.get_major_locator())
)
ax_er.set_xlim(DATE_START, DATE_END)

plt.subplots_adjust(hspace=0.55, wspace=0.04, right=0.90)
plt.savefig(OUTPUT_FIG, dpi=200, bbox_inches="tight")
print(f"\nFigura guardada: {OUTPUT_FIG}")

# ---------------------------------------------------------------------------
# RESUMEN EN CONSOLA
# ---------------------------------------------------------------------------
sep = "-" * 58
print(f"\n{sep}")
print(f"  Periodos eruptivos detectados por VIS : {len(eruptions)}")
if len(eruptions) > 0:
    print(f"  Primero : {eruptions['Start Date (UTC)'].min()}")
    print(f"  Ultimo  : {eruptions['End Date (UTC)'].max()}")
    # cuantos coinciden con la erupcion real?
    real_start = datetime(2015, 4, 22, tzinfo=timezone.utc)
    real_end   = datetime(2015, 4, 24, tzinfo=timezone.utc)
    hit = eruptions[
        (eruptions["Start Date (UTC)"] >= real_start) &
        (eruptions["Start Date (UTC)"] <= real_end)
    ]
    print(f"  Coincidencias con 22-23 abril      : {len(hit)}")
print(f"\n  Estaciones con IP >= 1              : {num_sta}")
for s in stations_sorted:
    n = len(ips[(ips["Station Name"] == s) & (ips["IP"] >= 1)])
    max_ip = ips[ips["Station Name"] == s]["IP"].max() if n > 0 else 0
    print(f"    {s:8s} | {station_dists[s]:6.0f} km | {n:4d} ventanas | IP_max = {max_ip:.1f}")
print(sep)
