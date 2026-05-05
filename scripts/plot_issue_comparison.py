"""
Reproduce the plot from hydromt_wflow issue #741.

Shows precipitation (mm/day) over time for a specific lat/lon, comparing:
- The issue model (built on Linux cluster, broken)
- The WSL rebuild (.updated, correct)
- The raw MSWEP source data

Usage:
    pixi run python scripts/plot_issue_comparison.py
    pixi run python scripts/plot_issue_comparison.py --start 2013 --end 2015
    pixi run python scripts/plot_issue_comparison.py --no-raw
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


def load_forcing(inmaps_dir: Path, year_start: int, year_end: int) -> xr.DataArray:
    """Load precip forcing from a model's inmaps directory for a year range."""
    files = sorted(inmaps_dir.glob("mswep_precip_era5_temp_pet_daily_*.nc"))
    files = [
        f
        for f in files
        if year_start <= int(f.stem.split("_")[-1][:4]) <= year_end
    ]
    if not files:
        raise FileNotFoundError(
            f"No forcing files found in {inmaps_dir} for {year_start}-{year_end}"
        )
    datasets = [xr.open_dataset(f) for f in files]
    ds = xr.concat(datasets, dim="time")
    return ds["precip"]


def load_raw_mswep(year_start: int, year_end: int) -> xr.DataArray:
    """Load raw MSWEP source data for comparison."""
    base = Path("/p/wflow_global/forcing/MSWEP_V316_test/Past/Yearly")
    files = [base / f"mswep_v316_{y}.nc" for y in range(year_start, year_end + 1)]
    files = [f for f in files if f.exists()]
    if not files:
        raise FileNotFoundError(f"No MSWEP source files found for {year_start}-{year_end}")
    ds = xr.open_mfdataset(
        files,
        combine="by_coords",
        chunks={"time": 365, "latitude": 200, "longitude": 200},
    )
    return ds["precipitation"]


def _plot_pair(ts_a, ts_b, label_a, label_b, color_a, color_b, lat, lon, output):
    """Plot a pair of timeseries with their difference."""
    fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharex=True, height_ratios=[2, 1])
    ax_main, ax_diff = axes

    ts_a.plot(ax=ax_main, label=label_a, color=color_a, linewidth=0.5)
    ts_b.plot(ax=ax_main, label=label_b, color=color_b, linewidth=0.5)

    ax_main.set_ylabel("Precipitation [mm/day]")
    ax_main.set_xlabel("")
    ax_main.set_title(f"{label_a} vs {label_b} at lat={lat:.3f}, lon={lon:.3f}")
    ax_main.legend(loc="upper right")

    common_time = np.intersect1d(ts_a.time.values, ts_b.time.values)
    if len(common_time) > 0:
        diff = ts_a.sel(time=common_time) - ts_b.sel(time=common_time)
        diff.plot(ax=ax_diff, color="black", linewidth=0.3)
        ax_diff.axhline(0, color="gray", linewidth=0.5, linestyle="--")
        ax_diff.set_ylabel(f"Difference [mm/day]\n({label_a} - {label_b})")
        ax_diff.set_xlabel("Time")
        ax_diff.set_title("")

    fig.tight_layout()
    fig.savefig(output, dpi=150)
    print(f"Saved: {output}")
    plt.close(fig)


def plot_issue_comparison(
    lat: float,
    lon: float,
    year_start: int = 2010,
    year_end: int = 2020,
    include_raw: bool = True,
    issue_dir: Path = Path("model_from_issue/wflow_sbm/inmaps"),
    updated_dir: Path = Path(".updated/inmaps"),
    output: str = "issue_741_comparison.png",
):
    """Create the issue #741 comparison plots."""
    # Load issue model (Linux cluster build)
    print(f"Loading issue model forcing ({year_start}-{year_end})...")
    issue_precip = load_forcing(issue_dir, year_start, year_end)
    ts_issue = issue_precip.sel(latitude=lat, longitude=lon, method="nearest")

    # Load WSL rebuild
    print(f"Loading WSL rebuild forcing ({year_start}-{year_end})...")
    updated_precip = load_forcing(updated_dir, year_start, year_end)
    ts_updated = updated_precip.sel(latitude=lat, longitude=lon, method="nearest")

    # Load raw MSWEP
    ts_raw = None
    if include_raw:
        print(f"Loading raw MSWEP source ({year_start}-{year_end})...")
        try:
            raw_precip = load_raw_mswep(year_start, year_end)
            ts_raw = raw_precip.sel(latitude=lat, longitude=lon, method="nearest").compute()
        except Exception as e:
            print(f"  Warning: Could not load raw MSWEP: {e}")

    # Plot 1: WSL vs Cluster
    stem = output.replace(".png", "")
    _plot_pair(
        ts_updated, ts_issue,
        "WSL rebuild (correct)", "Linux cluster (broken)",
        "orange", "green", lat, lon,
        f"{stem}_wsl_vs_cluster.png",
    )

    # Plot 2: WSL vs Raw
    if ts_raw is not None:
        _plot_pair(
            ts_updated, ts_raw,
            "WSL rebuild", "Raw MSWEP source",
            "orange", "black", lat, lon,
            f"{stem}_wsl_vs_raw.png",
        )

    # Plot 3: Cluster vs Raw
    if ts_raw is not None:
        _plot_pair(
            ts_issue, ts_raw,
            "Linux cluster (broken)", "Raw MSWEP source",
            "green", "black", lat, lon,
            f"{stem}_cluster_vs_raw.png",
        )


def main():
    parser = argparse.ArgumentParser(description="Plot issue #741 comparison")
    parser.add_argument("--lat", type=float, default=45.8525, help="Latitude (default: model center)")
    parser.add_argument("--lon", type=float, default=2.6908, help="Longitude (default: model center)")
    parser.add_argument("--start", type=int, default=2010, help="Start year")
    parser.add_argument("--end", type=int, default=2020, help="End year")
    parser.add_argument("--no-raw", action="store_true", help="Skip raw MSWEP source data")
    parser.add_argument("-o", "--output", default="issue_741_comparison.png", help="Output filename")
    args = parser.parse_args()

    plot_issue_comparison(
        lat=args.lat,
        lon=args.lon,
        year_start=args.start,
        year_end=args.end,
        include_raw=not args.no_raw,
        output=args.output,
    )


if __name__ == "__main__":
    main()
