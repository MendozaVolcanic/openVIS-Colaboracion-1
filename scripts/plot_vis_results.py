"""
plot_vis_results.py - Visualizacion generica de resultados VIS

Uso (desde la raiz del repo):
    python scripts/plot_vis_results.py CARPETA_RESULTADOS [--label TITULO]

Ejemplos:
    python scripts/plot_vis_results.py data/results/20260404T210517
    python scripts/plot_vis_results.py examples/results/20260404T205937 --label "Puyehue 2011 con veff"

Los archivos .pkl son el formato interno de openVIS (generados por vis_main.py).
"""

import sys, io, argparse, math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT          = Path(__file__).resolve().parent.parent
CFG_STATIONS  = ROOT / "cfg" / "stations.csv"
CFG_VOLCANOES = ROOT / "cfg" / "volcanoes.csv"
COLOR_LEVELS  = ["yellowgreen", "coral", "red", "purple"]
LABELS        = list("abcdefghijklmnop")

KNOWN_ERUPTIONS = {
    "Calbuco": [
        (datetime(2015,4,22,21,0,tzinfo=timezone.utc), datetime(2015,4,23,3,0,tzinfo=timezone.utc),  "Fase 1"),
        (datetime(2015,4,23, 4,0,tzinfo=timezone.utc), datetime(2015,4,23,10,0,tzinfo=timezone.utc), "Fase 2"),
    ],
    "Puyehue-Cordon Caulle": [
        (datetime(2011,6,4,18,0,tzinfo=timezone.utc), datetime(2011,6,5,6,0,tzinfo=timezone.utc), "Inicio erupcion"),
    ],
}

def haversine_km(lat1,lon1,lat2,lon2):
    R=6371.0; p1,p2=math.radians(lat1),math.radians(lat2)
    dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.atan2(math.sqrt(a),math.sqrt(1-a))

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("results_dir",type=Path)
    p.add_argument("--label",default="")
    p.add_argument("--date-start",default=None)
    p.add_argument("--date-end",  default=None)
    return p.parse_args()

def main():
    args=parse_args()
    rd=args.results_dir if args.results_dir.is_absolute() else ROOT/args.results_dir
    if not rd.exists(): print(f"ERROR: {rd}"); sys.exit(1)

    # Config del run
    import toml
    tomls=list(rd.glob("*.toml"))
    cfg=toml.load(tomls[0]) if tomls else None

    def get_date(key, fallback):
        if args.__dict__[key.replace("-","_")]:
            return datetime.fromisoformat(args.__dict__[key.replace("-","_")]).replace(tzinfo=timezone.utc)
        if cfg: return cfg["DATES"][{"date-start":"StartDate","date-end":"EndDate"}[key]].replace(tzinfo=timezone.utc)
        return fallback

    date_start = get_date("date-start", datetime(2000,1,1,tzinfo=timezone.utc))
    date_end   = get_date("date-end",   datetime(2030,1,1,tzinfo=timezone.utc))
    volcano    = cfg["VOLCANOES"]["VolcanoesList"][0] if cfg and cfg["VOLCANOES"].get("VolcanoesList") else "Desconocido"

    print(f"Run : {rd.name}  |  {volcano}  |  {date_start.date()} -> {date_end.date()}")

    # Cargar resultados internos de openVIS
    ips       = pd.read_pickle(rd/"ip_results.pkl")
    eruptions = pd.read_pickle(rd/"eruption_results.pkl")
    assoc_sta = pd.read_pickle(rd/"assoc_sta_er.pkl")
    ips=ips[(ips["Datetime (UTC)"]>=date_start)&(ips["Datetime (UTC)"]<=date_end)]
    eruptions=eruptions[(eruptions["Start Date (UTC)"]>=date_start)&(eruptions["End Date (UTC)"]<=date_end)]

    sta_cfg  = pd.read_csv(CFG_STATIONS)
    volc_cfg = pd.read_csv(CFG_VOLCANOES,sep=";",encoding="latin-1",decimal=",")
    vrow=volc_cfg[volc_cfg["Volcano Name"]==volcano]
    vlat=float(str(vrow.iloc[0]["Latitude"]).replace(",",".")) if not vrow.empty else 0
    vlon=float(str(vrow.iloc[0]["Longitude"]).replace(",",".")) if not vrow.empty else 0

    dists={}
    for s in ips["Station Name"].unique():
        r=sta_cfg[sta_cfg["Station Name"]==s]
        dists[s]=haversine_km(vlat,vlon,float(r["Latitude"].values[0]),float(r["Longitude"].values[0])) if not r.empty else 9999

    stas=[s for s in sorted(dists,key=dists.get,reverse=True) if len(ips[(ips["Station Name"]==s)&(ips["IP"]>=1)])>0]
    N=len(stas)
    print(f"Estaciones con IP>=1 : {stas}")
    print(f"Periodos eruptivos   : {len(eruptions)}")
    if N==0: print("Sin detecciones."); return

    # Figura
    fig,axes=plt.subplots(N+1,3,figsize=(10,2.2*(N+1)),gridspec_kw={"width_ratios":[0.03,1,0.03]},sharex=True)
    vf=cfg["FORMATS"]["VeffFormat"] if cfg else "?"
    dz=cfg["PROCESSING"]["Dazim"] if cfg else "?"
    baz="con ARCADE" if cfg and cfg["PATHS"].get("BackAziInterp") not in [False,"false",None,False] else "sin ARCADE"
    titulo=args.label if args.label else f"VIS — {volcano}"
    fig.suptitle(f"{titulo}\nveff={vf}  |  Dazim={dz}  |  {baz}",fontsize=11,y=1.01)
    plt.rc("font",size=9)
    sc_ref=None
    phases=KNOWN_ERUPTIONS.get(volcano,[])

    for i,sta in enumerate(stas):
        ip_s=ips[(ips["Station Name"]==sta)&(ips["IP"]>=1)].copy()
        ax=axes[i,1]
        sc_ref=ax.scatter(ip_s["Datetime (UTC)"],np.log10(ip_s["IP"]),
            s=ip_s["Number of Detections"]*0.08,c=ip_s["Mean Frequency (Hz)"],
            cmap="viridis",marker=".",edgecolors="none",alpha=0.85,vmin=1,vmax=3,zorder=10)
        ax.axhline(y=2,color="red",lw=0.8,ls="--",alpha=0.6)
        for ps,pe,_ in phases: ax.axvspan(ps,pe,color="gold",alpha=0.3,zorder=1)
        ax.spines[["right","top"]].set_visible(False)
        ax.grid(axis="x",alpha=0.3)
        ax.set_ylabel("log(IP)",fontsize=8)
        ax.set_title(f"({LABELS[i]}) {sta}  {dists[sta]:.0f} km",loc="left",fontsize=9,fontweight="bold",pad=3)
        axes[i,0].axis("off"); axes[i,2].axis("off")

    ax_er=axes[N,1]
    ax_er.spines[["right","top"]].set_visible(False)
    ax_er.grid(axis="x",alpha=0.3)
    for _,er in eruptions.iterrows():
        t0,t1,amp,code=er["Start Date (UTC)"],er["End Date (UTC)"],er["Estimated Amplitude [Pa]"],er["Eruption Code"]
        det=assoc_sta[(assoc_sta["Eruption Code"]==code)&(assoc_sta["Detecting"]==1)]
        c=COLOR_LEVELS[min(len(det)-1,3)]
        ax_er.axvspan(t0,t1,color=c,alpha=0.85)
        ax_er.plot([t0,t1],[amp,amp],color="black",lw=1.5)
    for ps,pe,_ in phases: ax_er.axvspan(ps,pe,color="gold",alpha=0.3,zorder=0)
    ax_er.set_ylabel("Amp. [Pa]",fontsize=8)
    ax_er.set_title(f"({LABELS[N]}) Periodos eruptivos VIS  |  amplitud a 1 km",loc="left",fontsize=9,fontweight="bold",pad=3)
    axes[N,0].axis("off")

    ax_lg=axes[N,2]; ax_lg.axis("off")
    patches=[mpatches.Patch(color=COLOR_LEVELS[i],label=f"{i+1} estac.") for i in range(3)]
    patches.append(mpatches.Patch(color="gold",alpha=0.5,label="Erupcion real"))
    ax_lg.legend(handles=patches,loc="center left",fontsize=7.5,title="# estaciones",title_fontsize=8)

    if sc_ref:
        cax=fig.add_axes([0.92,0.35,0.013,0.50])
        cb=fig.colorbar(sc_ref,cax=cax); cb.set_label("Frec. media (Hz)",fontsize=9)

    ax_er.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax_er.xaxis.get_major_locator()))
    ax_er.set_xlim(date_start,date_end)
    plt.subplots_adjust(hspace=0.55,wspace=0.04,right=0.90)

    out=rd/f"{rd.name}-results.png"
    plt.savefig(out,dpi=200,bbox_inches="tight")
    print(f"\nFigura: {out}")

    print(f"\n{'-'*60}")
    print(f"  Periodos eruptivos VIS : {len(eruptions)}")
    for s in stas:
        n=len(ips[(ips["Station Name"]==s)&(ips["IP"]>=1)])
        mx=ips[ips["Station Name"]==s]["IP"].max()
        print(f"    {s:8s} | {dists[s]:6.0f} km | {n:4d} ventanas | IP_max={mx:.0f}")
    print("-"*60)

if __name__=="__main__":
    main()
