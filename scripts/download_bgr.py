#!/usr/bin/env python3
"""
download_bgr.py  —  Descarga automática de boletines infrasónicos BGR/IMS (Hupe et al., 2022)

Dataset: "Higher frequency data products of the International Monitoring System's
          infrasound stations" (DOI: 10.25928/bgrseis_bbhf-ifsd)
Paper:   Hupe et al. (2022), ESSD, https://doi.org/10.5194/essd-14-4201-2022

Uso:
    python scripts/download_bgr.py                          # configuración por defecto
    python scripts/download_bgr.py --stations IS02 IS41     # sólo esas estaciones
    python scripts/download_bgr.py --years 2015 2022        # sólo esos años
    python scripts/download_bgr.py --output data/bulletins  # carpeta de destino

Convención de nombres (openVIS):
    IS##_YYYY_hf_1-3Hz_5min.nc
"""

import argparse
import sys
import time
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Instala requests:  pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN POR DEFECTO
# ---------------------------------------------------------------------------

# Estaciones relevantes para la zona sur-andina (Chile/Argentina)
# I02AR  → Tierra del Fuego, Argentina   (~2000 km de Calbuco)
# I08BO  → Bolivia                       (~2000 km de Calbuco)
# I13CL  → Isla de Pascua, Chile         (~3200 km de Calbuco)
# I14CL  → Juan Fernández, Chile         (~1000 km de Calbuco)
# I41PY  → Paraguay                      (~1500 km de Calbuco)
DEFAULT_STATIONS = ["IS02", "IS08", "IS13", "IS14", "IS41"]

# 2015 = erupción Calbuco (22-23 abril 2015)
# 2022 = período reciente para validación
DEFAULT_YEARS = [2015, 2022]

DEFAULT_OUTPUT = Path("data/bulletins")

# ---------------------------------------------------------------------------
# POSIBLES URLS DEL GEOPORTAL BGR
# Los servidores de BGR pueden cambiar; se prueban en orden.
# ---------------------------------------------------------------------------
BGR_URL_PATTERNS = [
    # Patrón 1: servidor público directo (confirmado en algunas descargas manuales)
    "https://download.bgr.de/bgr/seismologie/ims_oa_bulletins/{filename}",
    # Patrón 2: geoportal API v1
    "https://geoportal.bgr.de/mapapps/resources/apps/geoportal/api/datasets/ims_bulletins_hf/{filename}",
    # Patrón 3: servidor alternativo ESSD
    "https://store.pangaea.de/Publications/Hupe-etal_2022/{filename}",
    # Patrón 4: zenodo mirror (si existe)
    "https://zenodo.org/record/bgrseis_bbhf-ifsd/files/{filename}",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; openVIS-downloader/1.0; "
        "+https://github.com/MendozaVolcanic/openVIS-Colaboracion-1)"
    ),
    "Accept": "application/x-netcdf, application/octet-stream, */*",
}

MANUAL_INSTRUCTIONS = """
╔══════════════════════════════════════════════════════════════════════════════╗
║           DESCARGA MANUAL — BGR GEOPORTAL                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  1. Abre en tu navegador:                                                   ║
║     https://geoportal.bgr.de/mapapps/resources/apps/geoportal/             ║
║     index.html?lang=en#/search?term=10.5194%2Fessd-14-4201-2022&core       ║
║     &filter=%7B%22md_type_facet%22%3A%5B%22Daten%22%5D%7D                  ║
║                                                                              ║
║  2. Busca el dataset:                                                        ║
║     "Higher frequency data products of the International Monitoring         ║
║      System's infrasound stations"                                          ║
║                                                                              ║
║  3. Acepta los términos de uso (OPEN DATA / OA)                             ║
║                                                                              ║
║  4. Descarga los archivos con el siguiente patrón de nombre:                ║
║     IS##_YYYY_hf_1-3Hz_5min.nc                                              ║
║                                                                              ║
║     Estaciones para Calbuco 2015:                                           ║
║       IS02_2015_hf_1-3Hz_5min.nc   (I02AR, Tierra del Fuego)              ║
║       IS08_2015_hf_1-3Hz_5min.nc   (I08BO, Bolivia)                       ║
║       IS13_2015_hf_1-3Hz_5min.nc   (I13CL, Isla de Pascua)               ║
║       IS14_2015_hf_1-3Hz_5min.nc   (I14CL, Juan Fernández)               ║
║       IS41_2015_hf_1-3Hz_5min.nc   (I41PY, Paraguay)                      ║
║                                                                              ║
║  5. Copia los archivos .nc descargados a:                                   ║
║     data/bulletins/                                                          ║
║     (o la carpeta que hayas configurado en vis_config.toml → [PATHS])      ║
║                                                                              ║
║  Alternativa — DOI directo:                                                 ║
║     https://doi.org/10.25928/bgrseis_bbhf-ifsd                             ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# FUNCIONES
# ---------------------------------------------------------------------------

def make_session(retries: int = 3, backoff: float = 1.0) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def filename_for(station: str, year: int) -> str:
    """Devuelve el nombre estándar del boletín BGR."""
    return f"{station}_{year}_hf_1-3Hz_5min.nc"


def try_download(session: requests.Session, filename: str, dest: Path) -> bool:
    """Intenta descargar desde cada patrón de URL. Devuelve True si lo logra."""
    for pattern in BGR_URL_PATTERNS:
        url = pattern.format(filename=filename)
        try:
            resp = session.get(url, timeout=30, stream=True)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                # Rechazar páginas HTML (redirección a login, etc.)
                if "html" in content_type.lower():
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                        size += len(chunk)
                if size < 1000:          # archivo vacío o HTML pequeño
                    dest.unlink(missing_ok=True)
                    continue
                return True
        except requests.RequestException:
            continue
        time.sleep(0.5)
    return False


def validate_nc(path: Path) -> bool:
    """Comprueba que el archivo sea un NetCDF válido (signature HDF5/NetCDF4)."""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
        # NetCDF-4 / HDF5 magic bytes
        return header[:4] == b"\x89HDF" or header[:3] == b"CDF"
    except OSError:
        return False


def download_bulletins(
    stations: list,
    years: list,
    output_dir: Path,
    skip_existing: bool = True,
) -> dict:
    """
    Descarga los boletines de las estaciones/años indicados.
    Devuelve dict con listas 'ok', 'exists', 'failed'.
    """
    results = {"ok": [], "exists": [], "failed": []}
    session = make_session()
    total = len(stations) * len(years)
    done = 0

    for year in years:
        for station in stations:
            done += 1
            fname = filename_for(station, year)
            dest = output_dir / fname

            print(f"[{done:2d}/{total}] {fname}", end="  ")

            if skip_existing and dest.exists():
                if validate_nc(dest):
                    print("✓ ya existe")
                    results["exists"].append(fname)
                    continue
                else:
                    print("⚠ archivo corrupto, reintentando...")
                    dest.unlink()

            success = try_download(session, fname, dest)

            if success and validate_nc(dest):
                size_mb = dest.stat().st_size / 1_048_576
                print(f"✓ descargado ({size_mb:.1f} MB)")
                results["ok"].append(fname)
            else:
                if dest.exists():
                    dest.unlink(missing_ok=True)
                print("✗ no disponible")
                results["failed"].append(fname)

            time.sleep(0.3)   # pausa cortés al servidor

    return results


def print_summary(results: dict, output_dir: Path) -> None:
    total = sum(len(v) for v in results.values())
    ok = len(results["ok"]) + len(results["exists"])
    failed = len(results["failed"])

    print("\n" + "─" * 60)
    print(f"  Archivos disponibles : {ok}/{total}")
    print(f"  Descargados ahora    : {len(results['ok'])}")
    print(f"  Ya existían          : {len(results['exists'])}")
    print(f"  No descargados       : {failed}")

    if results["ok"] or results["exists"]:
        print(f"\n  Carpeta de datos     : {output_dir.resolve()}")

    if failed:
        print(f"\n  Archivos faltantes ({failed}):")
        for f in results["failed"]:
            print(f"    • {f}")
        print(MANUAL_INSTRUCTIONS)

    print("─" * 60)


def list_existing(output_dir: Path, stations: list, years: list) -> None:
    """Muestra qué archivos ya hay en la carpeta de salida."""
    print(f"\nArchivos encontrados en {output_dir}:")
    found = 0
    for year in years:
        for station in stations:
            fname = filename_for(station, year)
            path = output_dir / fname
            if path.exists():
                size_mb = path.stat().st_size / 1_048_576
                valid = "✓" if validate_nc(path) else "✗ CORRUPTO"
                print(f"  {valid}  {fname}  ({size_mb:.1f} MB)")
                found += 1
    if found == 0:
        print("  (ninguno)")
    print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(
        description="Descarga boletines infrasónicos BGR (Hupe et al., 2022)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--stations",
        nargs="+",
        default=DEFAULT_STATIONS,
        metavar="ISxx",
        help=f"Estaciones IMS (default: {' '.join(DEFAULT_STATIONS)})",
    )
    p.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=DEFAULT_YEARS,
        metavar="YYYY",
        help=f"Años a descargar (default: {' '.join(map(str, DEFAULT_YEARS))})",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="CARPETA",
        help=f"Carpeta de destino (default: {DEFAULT_OUTPUT})",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="Sólo listar archivos existentes, no descargar",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-descargar aunque el archivo ya exista",
    )
    p.add_argument(
        "--instructions",
        action="store_true",
        help="Mostrar instrucciones de descarga manual y salir",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if args.instructions:
        print(MANUAL_INSTRUCTIONS)
        return

    stations = [s.upper() for s in args.stations]
    years = sorted(args.years)

    print("=" * 60)
    print("  BGR IMS Infrasound Bulletin Downloader")
    print("  openVIS-OVDAS  —  MendozaVolcanic/openVIS-Colaboracion-1")
    print("=" * 60)
    print(f"  Estaciones : {', '.join(stations)}")
    print(f"  Años       : {', '.join(map(str, years))}")
    print(f"  Destino    : {args.output}")
    print("=" * 60 + "\n")

    if args.list:
        list_existing(args.output, stations, years)
        return

    results = download_bulletins(
        stations=stations,
        years=years,
        output_dir=args.output,
        skip_existing=not args.force,
    )

    print_summary(results, args.output)

    if results["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
