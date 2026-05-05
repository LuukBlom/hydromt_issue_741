import xarray as xr
import matplotlib.pyplot as plt
from typing import Optional

def plot_precipitation_comparison(
    datasets: dict[str, xr.Dataset],
    variable: str,
    lat: float,
    lon: float,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    figsize: tuple[float, float] = (12, 5),
) -> plt.Figure:
    """Plot a comparison of a precipitation variable over time across multiple datasets.

    Parameters
    ----------
    datasets : dict[str, xr.Dataset]
        Mapping of label to xr.Dataset. Each dataset should contain the specified
        variable with time, latitude, and longitude dimensions.
    variable : str
        Name of the variable (column) to plot (e.g. "precip").
    lat : float
        Latitude of the point to extract.
    lon : float
        Longitude of the point to extract.
    start_time : str, optional
        Start of time range to plot (ISO format, e.g. "1990-01-01").
    end_time : str, optional
        End of time range to plot (ISO format, e.g. "1990-12-31").
    figsize : tuple, optional
        Figure size passed to matplotlib.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)

    for label, ds in datasets.items():
        da = ds[variable]

        # Select nearest lat/lon
        da = da.sel(
            **{_get_lat_dim(da): lat, _get_lon_dim(da): lon},
            method="nearest",
        )

        # Slice time
        time_dim = _get_time_dim(da)
        if start_time or end_time:
            da = da.sel(**{time_dim: slice(start_time, end_time)})

        da.plot(ax=ax, label=label)

    ax.set_title(f"{variable} at lat={lat}, lon={lon}")
    ax.set_xlabel("Time")
    ax.set_ylabel(variable)
    ax.legend()
    fig.tight_layout()
    return fig


def _get_dim_by_attrs(da: xr.DataArray, standard_names: list[str], fallback_names: list[str]) -> str:
    """Find a dimension name by CF standard_name attribute or common name patterns."""
    for dim in da.dims:
        coord = da.coords.get(dim)
        if coord is not None:
            sn = coord.attrs.get("standard_name", "")
            if sn in standard_names:
                return dim
    for dim in da.dims:
        if dim.lower() in fallback_names:
            return dim
    raise ValueError(
        f"Could not identify dimension from {list(da.dims)} "
        f"matching {standard_names} or {fallback_names}"
    )


def _get_lat_dim(da: xr.DataArray) -> str:
    return _get_dim_by_attrs(da, ["latitude"], ["lat", "latitude", "y"])


def _get_lon_dim(da: xr.DataArray) -> str:
    return _get_dim_by_attrs(da, ["longitude"], ["lon", "longitude", "x"])


def _get_time_dim(da: xr.DataArray) -> str:
    return _get_dim_by_attrs(da, ["time"], ["time", "t"])
