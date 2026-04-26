"""
dazim_sweep.py - Sensitivity analysis of Dazim parameter on Calbuco 2015.

For each Dazim in {3, 5, 7, 10, 15} deg:
  1. Patch cfg/vis_config.toml
  2. Run src/vis_main.py
  3. Read result tables (openVIS internal binary format) and summarize.
"""
import sys, io, subprocess, shutil
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import toml

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "cfg" / "vis_config.toml"
BASE_CFG = ROOT / "cfg" / "calbuco_2015.toml"
RESULTS_ROOT = ROOT / "data" / "results"
COMPILED = ROOT / "data" / "compiled"
OUTDIR = ROOT / "data" / "sensitivity"
OUTDIR.mkdir(parents=True, exist_ok=True)
PYTHON = sys.executable
DAZIMS = [3, 5, 7, 10, 15]

KNOWN_START = datetime(2015,4,22,21,0,tzinfo=timezone.utc)
KNOWN_END   = datetime(2015,4,23,10,0,tzinfo=timezone.utc)

def run_one(dz):
    print(f"\n{'='*60}\n  Dazim = {dz} deg\n{'='*60}")
    base = toml.load(BASE_CFG)
    base["PROCESSING"]["Dazim"] = dz
    base["PROCESSING"]["ForceDazim"] = True
    with open(CFG, "w") as f: toml.dump(base, f)
    if COMPILED.exists(): shutil.rmtree(COMPILED)

    before = set(p.name for p in RESULTS_ROOT.glob("2*"))
    r = subprocess.run([PYTHON, str(ROOT/"src/vis_main.py")], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print("  ERROR"); print(r.stderr[-800:]); return None
    after = set(p.name for p in RESULTS_ROOT.glob("2*"))
    new = sorted(after - before)
    if not new: return None
    rd = RESULTS_ROOT / new[-1]
    print(f"  -> {rd.name}")

    ips = pd.read_pickle(rd/"ip_results.pkl")
    erup = pd.read_pickle(rd/"eruption_results.pkl")
    in_w = ips[(ips["Datetime (UTC)"]>=KNOWN_START) & (ips["Datetime (UTC)"]<=KNOWN_END) & (ips["IP"]>=100)]
    sta_w = sorted(in_w["Station Name"].unique())
    fps = sum(1 for _,e in erup.iterrows() if e["End Date (UTC)"]<KNOWN_START or e["Start Date (UTC)"]>KNOWN_END)
    return {
        "Dazim": dz, "RunID": rd.name,
        "Stations_active": ips[ips["IP"]>=1]["Station Name"].nunique(),
        "Eruption_periods": len(erup),
        "IP_max": round(float(ips["IP"].max()),1) if len(ips) else 0,
        "N_in_true_window": len(sta_w),
        "Stations_in_true_window": ",".join(sta_w),
        "False_positive_periods": fps,
    }

def main():
    rows = [r for r in (run_one(dz) for dz in DAZIMS) if r]
    if not rows: print("No runs."); return
    df = pd.DataFrame(rows)
    csv_path = OUTDIR/"dazim_sweep_summary.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n{'='*60}\nSaved: {csv_path}\n{'='*60}")
    print(df.to_string(index=False))

    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8,4.5))
    ax.plot(df["Dazim"], df["N_in_true_window"], "o-", color="#2ecc71", lw=2, label="Stations detecting known eruption")
    ax.plot(df["Dazim"], df["Eruption_periods"], "s-", color="#3498db", lw=2, label="Total eruption periods")
    ax.plot(df["Dazim"], df["False_positive_periods"], "^--", color="#e74c3c", lw=2, label="False-positive periods")
    ax.set_xlabel("Dazim (degrees)"); ax.set_ylabel("Count")
    ax.set_title("Calbuco 2015 - Dazim sensitivity sweep\n(IS02/IS08/IS13/IS14/IS41 - veff=1 - IP threshold=100)")
    ax.legend(fontsize=9); ax.grid(alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(df["Dazim"], df["IP_max"], "d:", color="#9b59b6", lw=1.5)
    ax2.set_ylabel("IP_max", color="#9b59b6")
    png = OUTDIR/"dazim_sweep_summary.png"
    plt.savefig(png, dpi=150, bbox_inches="tight")
    print(f"Saved: {png}")

if __name__ == "__main__": main()
