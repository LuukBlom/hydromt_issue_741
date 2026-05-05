# Investigation: hydromt_wflow Issue #741

**Issue:** [Deltares/hydromt_wflow#741](https://github.com/Deltares/hydromt_wflow/issues/741)

Precipitation forcing built on the h7 cluster has broken years — a single spatial pattern repeated for all 365 days. Windows/WSL builds are fine.

## Bug description

Running `setup_precip_forcing` with MSWEP V316 daily data on h7 produces years where every timestep contains the same spatial field. Broken years in the reporter's model: **1991, 2000, 2009, 2013, 2015, 2018**.

Each broken year's constant pattern comes from day 0 of an adjacent year:

| Broken year | Source of repeated pattern |
|-------------|---------------------------|
| 1991 | 1990 day 0 |
| 2000 | 2001 day 0 |
| 2009 | 2010 day 0 |
| 2013 | 2014 day 0 |
| 2015 | 2016 day 0 |
| 2018 | 2017 day 0 |

The direction isn't consistent (+1 or -1), which points to chunk data being assigned to the wrong position rather than an off-by-one.

## Plots

Generated with:
```bash
pixi run python scripts/plot_issue_comparison.py --start 2010 --end 2020
```

### WSL rebuild vs cluster (broken)

![WSL vs Cluster](issue_741_comparison_wsl_vs_cluster.png)

WSL (orange) has normal daily variation. The cluster build (green) flatlines during 2013, 2015, and 2018.

### WSL rebuild vs raw MSWEP source

![WSL vs Raw](issue_741_comparison_wsl_vs_raw.png)

Nearly identical — difference is ±0.005 mm/day from nearest-neighbor reprojection.

### Cluster (broken) vs raw MSWEP source

![Cluster vs Raw](issue_741_comparison_cluster_vs_raw.png)

Differences reach -30 to -50 mm/day during broken years. Real rainfall completely lost.

## Environments

| Package | Cluster (broken) | WSL/pixi (works) |
|---------|-------------------|-------------------|
| Python | 3.14.3 | 3.13.13 |
| hydromt | 1.3.0 | 1.4.0.dev0 |
| hydromt_wflow | 1.0.1 | 1.0.3.dev0 |
| xarray | 2026.2.0 | 2026.4.0 |
| dask | 2026.1.2 | 2026.3.0 |
| **distributed** | **2026.1.2** | **not installed** |
| numpy | 2.3.5 | 2.4.3 |
| pandas | 2.3.3 | 3.0.2 |
| rioxarray | 0.21.0 | 0.22.0 |
| rasterio | 1.5.0 | 1.5.0 |
| netCDF4 | 1.7.4 | 1.7.4 |

Full env listings: `conda_list.txt` / `pip_list.txt` (reporter), `conda_list_h7.txt` / `pip_list_h7.txt` (older env, same cluster).

## What was investigated

### 1. File ordering via `set()` — eliminated

`convention_resolver.py` resolves wildcard URIs into a `set()`, giving non-deterministic order. But `open_mfdataset` uses `combine='by_coords'` so files get sorted by time coordinate regardless. Not the cause.

### 2. Source data integrity — OK

All 47 source files (1979–2025) have proper `datetime64` time coords. Loading and reprojecting any single file gives correct temporal variation.

### 3. Yearly resample boundaries — eliminated

`resample_time` in `meteo.py` uses `YE` grouping. With daily-in/daily-out the frequency ratio is ~1 so no resampling happens.

### 4. Single-file reproject — works

One year → clip → `reproject_like(method='nearest_index')` → days differ correctly.

### 5. Multi-file reproject — works on WSL

Three years loaded via `open_mfdataset(combine='by_coords', parallel=True, chunks={time:1})` → clip → reproject → all correct. Bug does not appear without `distributed`.

### 6. Full WSL rebuild — all years correct

Complete model (1988–2021) built on WSL produces correct forcing for all years including 2013, 2015, 2018.

## Hypothesis

`dask.distributed` misroutes chunk data during `map_blocks` in `reindex2d()` (called from `reproject_like(method='nearest_index')`).

Why this fits:
- Time coordinates are always correct, only data values are wrong
- Affected years are non-deterministic
- Does not reproduce without `distributed`
- `reindex2d` creates a task per time chunk: with `chunks={time: 1}` over 47 years that's 17k+ tasks
- Distributed scheduling is non-deterministic

Other possible factors:
- Bug in dask 2026.1.2 fixed by 2026.3.0
- Bug in xarray 2026.2.0 `map_blocks` fixed by 2026.4.0
- Python 3.14 GIL/threading changes

## Reproduction

### Prerequisites

- pixi (for default dev env)
- conda/mamba (for reproduce env)
- Access to `/p/wflow_global/`
- `hydromt` and `hydromt_wflow` repos cloned as siblings (dev env only)

### Default env (WSL — does NOT reproduce the bug)

```bash
pixi run full-reproduce
pixi run python scripts/plot_issue_comparison.py --no-raw --start 2010 --end 2020
```

### Reporter's env

`environment_reproduce.yml` pins the versions from `conda_list_h7.txt`:

```bash
mamba env create -f environment_reproduce.yml
conda activate hydromt-issue-741-reproduce
hydromt update wflow_sbm ./.updated -i ./config/wflow_update_forcing.yml -d ./config/deltares_data.yml -vvv
```

Versions: hydromt 1.3.1, hydromt_wflow 1.0.2, dask+distributed 2024.11.2, xarray 2024.11.0, Python 3.12.

### Generating plots

```bash
# Without raw MSWEP (fast)
pixi run python scripts/plot_issue_comparison.py --no-raw --start 2010 --end 2020

# With raw MSWEP (needs /p/ mount)
pixi run python scripts/plot_issue_comparison.py --start 2010 --end 2020

# Custom point / range
pixi run python scripts/plot_issue_comparison.py --lat 45.85 --lon 2.69 --start 1988 --end 2021 -o my_plot.png
```

Output files:
- `*_wsl_vs_cluster.png`
- `*_wsl_vs_raw.png` (only when raw is loaded)
- `*_cluster_vs_raw.png` (only when raw is loaded)

## Next steps

1. Run `hydromt update` in the reproduce env locally — see if `distributed` alone triggers it
2. Try with an explicit `dask.distributed.Client()` to force the distributed scheduler
3. Check dask/xarray changelogs (2024.11 → 2026.3) for `map_blocks` fixes
4. Disable `parallel: true` in the data catalog
5. Use larger time chunks (`{time: 365}` instead of `{time: 1}`) to reduce the task graph from 17k to 47 tasks
