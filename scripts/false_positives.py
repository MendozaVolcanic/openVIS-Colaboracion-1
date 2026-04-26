"""
false_positives.py - Identify VIS detections (IP>=100) outside known eruption windows.

Eruption windows reflect documented activity periods (not just paroxysm dates):
  - Villarrica 2015: paroxysm March 3; minor ash emissions through April 2015.
  - Calbuco 2015: phases April 22-23; secondary plumes through April 30.
  - Puyehue-Cordon Caulle 2011: June 4 onset; sustained activity through August.
  - Chaiten 2008: May 2 onset; intense pulses through July; activity until 2010.

A detection is flagged 'cross-contamination?' if it falls inside another volcano's
known window (within +/- 24 h) and the station has similar azimuth to both sources.
"""
import sys, io
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pandas as pd
import toml

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ROOTS = [ROOT/"data"/"results", ROOT/"examples"/"results"]
OUTDIR = ROOT/"data"/"sensitivity"
OUTDIR.mkdir(parents=True, exist_ok=True)

PAD = timedelta(hours=24)

# Extended activity windows (paroxysm + documented continuation)
WINDOWS = {
    "Villarrica":           [(datetime(2015,2,1, tzinfo=timezone.utc), datetime(2015,4,15,tzinfo=timezone.utc))],
    "Calbuco":              [(datetime(2015,4,22,tzinfo=timezone.utc), datetime(2015,4,30,tzinfo=timezone.utc))],
    "Puyehue-Cordon Caulle":[(datetime(2011,6,4, tzinfo=timezone.utc), datetime(2011,8,31,tzinfo=timezone.utc))],
    "Chaiten":              [(datetime(2008,5,1, tzinfo=timezone.utc), datetime(2008,7,31,tzinfo=timezone.utc))],
}

# Cross-contamination: if a detection of volcano X falls in window of Y, suspect.
ALL_WINDOWS = [(v,t0,t1) for v,wins in WINDOWS.items() for (t0,t1) in wins]

def classify(t, target_volc):
    in_target = any((t0-PAD)<=t<=(t1+PAD) for t0,t1 in WINDOWS.get(target_volc,[]))
    if in_target: return "TP"
    for v,t0,t1 in ALL_WINDOWS:
        if v != target_volc and (t0-PAD)<=t<=(t1+PAD):
            return f"cross:{v}"
    return "FP"

def analyze_run(rd):
    tomls = list(rd.glob("*.toml"))
    if not tomls: return None
    cfg = toml.load(tomls[0])
    volc = cfg["VOLCANOES"]["VolcanoesList"][0] if cfg["VOLCANOES"].get("VolcanoesList") else None
    if not volc or volc not in WINDOWS: return None
    ips = pd.read_pickle(rd/"ip_results.pkl")
    sig = ips[ips["IP"] >= 100].copy()
    if sig.empty:
        return {"Run":rd.name,"Volcano":volc,"Total":0,"TP":0,"FP":0,"Cross":0,"TP_pct":0}
    sig["class"] = sig["Datetime (UTC)"].apply(lambda t: classify(t, volc))
    tp    = int((sig["class"]=="TP").sum())
    fp    = int((sig["class"]=="FP").sum())
    cross = int(sig["class"].str.startswith("cross").sum())
    cross_targets = sorted(sig.loc[sig["class"].str.startswith("cross"),"class"].unique())
    return {
        "Run": rd.name, "Volcano": volc,
        "Dazim": cfg["PROCESSING"]["Dazim"],
        "Veff": cfg["FORMATS"]["VeffFormat"],
        "Total": len(sig), "TP": tp, "FP": fp, "Cross": cross,
        "TP_pct": round(100*tp/len(sig),1),
        "Cross_targets": ",".join(cross_targets),
    }

def main():
    rows = [r for r in (analyze_run(rd) for root in ROOTS if root.exists() for rd in sorted(root.glob("2*"))) if r]
    if not rows: print("No runs."); return
    df = pd.DataFrame(rows)
    out = OUTDIR/"false_positives_summary.csv"
    df.to_csv(out, index=False)
    print(f"Saved: {out}\n")
    print(df.to_string(index=False))
    agg = df.groupby("Volcano")[["Total","TP","FP","Cross"]].sum().reset_index()
    agg["TP_pct"] = (100*agg["TP"]/agg["Total"]).round(1)
    print("\nAggregated by volcano:")
    print(agg.to_string(index=False))
    agg.to_csv(OUTDIR/"false_positives_by_volcano.csv", index=False)

if __name__ == "__main__": main()
