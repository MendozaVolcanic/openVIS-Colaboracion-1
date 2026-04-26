"""
ims_coverage_map.py — IMS infrasound coverage for Chilean volcanoes

For each Chilean volcano in cfg/volcanoes.csv, computes:
  - Closest IMS station (from cfg/stations.csv)
  - Distance (great-circle, km)
  - Detectability tier:
      Tier A (<1500 km)  : within published VIS sensitivity
      Tier B (1500-2500) : marginal — Calbuco/Villarrica regime
      Tier C (>2500)     : long-range only large eruptions (VEI 4+)

Outputs:
  data/coverage/chile_ims_coverage.csv
  data/coverage/chile_ims_coverage.png   (matplotlib map)
  data/coverage/chile_ims_coverage.html  (interactive plotly map)
"""

import sys, io, math
from pathlib import Path
import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
STATIONS = ROOT / "cfg" / "stations.csv"
VOLCANOES = ROOT / "cfg" / "volcanoes.csv"
OUTDIR = ROOT / "data" / "coverage"
OUTDIR.mkdir(parents=True, exist_ok=True)

# Stations relevant for South America (avoid pairing Chilean volcanoes with NZ stations)
SA_STATIONS = ["I01AR", "I02AR", "I08BO", "I09BR", "I13CL", "I14CL", "I41PY", "I27DE"]

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def tier(dist):
    if dist < 1500: return "A (<1500 km)"
    if dist < 2500: return "B (1500-2500)"
    return "C (>2500)"

def main():
    sta = pd.read_csv(STATIONS)
    sta = sta[sta["Station Name"].isin(SA_STATIONS)].reset_index(drop=True)
    print(f"Stations considered: {sta['Station Name'].tolist()}")

    volc = pd.read_csv(VOLCANOES, sep=";", encoding="latin-1", decimal=",")
    chl = volc[volc["Country"] == "Chile"].copy()
    for col in ["Latitude", "Longitude"]:
        chl[col] = pd.to_numeric(chl[col].astype(str).str.replace(",", "."), errors="coerce")
    chl = chl.dropna(subset=["Latitude", "Longitude"])
    print(f"Chilean volcanoes in catalog: {len(chl)}")

    rows = []
    for _, v in chl.iterrows():
        dists = sta.apply(
            lambda s: haversine(v["Latitude"], v["Longitude"], s["Latitude"], s["Longitude"]),
            axis=1,
        )
        # rank stations by distance
        ranked = sta.assign(dist=dists).sort_values("dist").reset_index(drop=True)
        rows.append({
            "Volcano": v["Volcano Name"],
            "Lat": v["Latitude"],
            "Lon": v["Longitude"],
            "LastEruption": v.get("Last Known Eruption", ""),
            "Closest": ranked.loc[0, "Station Name"],
            "Dist_km": round(ranked.loc[0, "dist"], 1),
            "Tier": tier(ranked.loc[0, "dist"]),
            "2nd": ranked.loc[1, "Station Name"],
            "Dist2_km": round(ranked.loc[1, "dist"], 1),
            "3rd": ranked.loc[2, "Station Name"],
            "Dist3_km": round(ranked.loc[2, "dist"], 1),
        })
    df = pd.DataFrame(rows).sort_values("Dist_km").reset_index(drop=True)
    csv_path = OUTDIR / "chile_ims_coverage.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved: {csv_path}  ({len(df)} volcanoes)")

    # Stats
    print("\nDistribution by tier:")
    print(df["Tier"].value_counts().to_string())
    print("\nClosest 10:")
    print(df[["Volcano", "Closest", "Dist_km", "Tier"]].head(10).to_string(index=False))

    # ------- Matplotlib map -------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 11))
    colors = {"A (<1500 km)": "#2ecc71", "B (1500-2500)": "#f39c12", "C (>2500)": "#e74c3c"}
    for tname, sub in df.groupby("Tier"):
        ax.scatter(sub["Lon"], sub["Lat"], s=35, c=colors[tname], label=f"{tname}  (n={len(sub)})",
                   edgecolors="black", linewidths=0.4, alpha=0.85, zorder=3)
    ax.scatter(sta["Longitude"], sta["Latitude"], s=180, c="purple", marker="^",
               edgecolors="black", linewidths=1, label="IMS station", zorder=4)
    for _, s in sta.iterrows():
        ax.annotate(s["Station Name"], (s["Longitude"], s["Latitude"]),
                    xytext=(6, 6), textcoords="offset points", fontsize=8,
                    fontweight="bold", color="purple")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("IMS Infrasound Coverage — Chilean Volcanoes\nTier by distance to closest IMS station",
                 fontsize=11)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(-115, -50)
    ax.set_ylim(-58, -15)
    png_path = OUTDIR / "chile_ims_coverage.png"
    plt.savefig(png_path, dpi=150, bbox_inches="tight")
    print(f"Saved: {png_path}")

    # ------- Plotly interactive -------
    try:
        import plotly.graph_objects as go
        fig = go.Figure()
        for tname, sub in df.groupby("Tier"):
            fig.add_trace(go.Scattermapbox(
                lat=sub["Lat"], lon=sub["Lon"], mode="markers",
                marker=dict(size=8, color=colors[tname]),
                name=f"{tname} (n={len(sub)})",
                text=[f"{r.Volcano}<br>Closest: {r.Closest} ({r.Dist_km:.0f} km)<br>Last: {r.LastEruption}"
                      for r in sub.itertuples()],
                hoverinfo="text",
            ))
        fig.add_trace(go.Scattermapbox(
            lat=sta["Latitude"], lon=sta["Longitude"], mode="markers+text",
            marker=dict(size=14, color="purple", symbol="triangle"),
            text=sta["Station Name"], textposition="top right",
            name="IMS stations",
        ))
        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox=dict(center=dict(lat=-37, lon=-72), zoom=2.6),
            margin=dict(l=0, r=0, t=40, b=0),
            title="IMS Infrasound Coverage — Chilean Volcanoes",
            height=750,
        )
        html_path = OUTDIR / "chile_ims_coverage.html"
        fig.write_html(str(html_path))
        print(f"Saved: {html_path}")
    except ImportError:
        print("Plotly not installed; skipped interactive map.")

if __name__ == "__main__":
    main()
