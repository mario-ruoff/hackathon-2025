#!/usr/bin/env python3
"""
Quick viewer for Heilbronn tree-planting data.

Features:
- Summarize CRS for key layers.
- Plot Baumkataster trees, parcels/buildings, streets, and optional orthophoto mosaic.

Requirements (install in a virtualenv):
  pip install geopandas rasterio matplotlib

Usage examples (run from repo root):
  python tools/quick_view.py --summary
  python tools/quick_view.py --plot --max-trees 5000 --include-orthophoto
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.plot import show as rio_show
from datetime import datetime

TARGET_EPSG = 25832


def _data_dir(default: Path) -> Path:
    base = Path(default).resolve()
    if not base.exists():
        raise FileNotFoundError(f"data directory not found: {base}")
    return base


def _load_vector(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.empty:
        print(f"[warn] empty layer: {path}", file=sys.stderr)
    if gdf.crs is None:
        print(f"[warn] missing CRS on layer: {path.name}", file=sys.stderr)
    elif gdf.crs.to_epsg() != TARGET_EPSG:
        gdf = gdf.to_crs(epsg=TARGET_EPSG)
    return gdf


def _plot_vectors(ax, layers: List[Tuple[gpd.GeoDataFrame, dict]]):
    for gdf, style in layers:
        if gdf.empty:
            continue
        gdf.plot(ax=ax, **style)


def _orthophoto_mosaic(tifs: Iterable[Path]):
    sources = []
    for tif in tifs:
        src = rasterio.open(tif)
        if src.crs is None:
            print(f"[warn] orthophoto missing CRS (used as-is): {tif.name}", file=sys.stderr)
        elif src.crs.to_epsg() != TARGET_EPSG:
            print(f"[warn] orthophoto not EPSG:{TARGET_EPSG}, got {src.crs} ({tif.name})", file=sys.stderr)
        sources.append(src)
    if not sources:
        return None
    mosaic, transform = merge(sources)
    for src in sources:
        src.close()
    return mosaic, transform


def summarize_crs(data_dir: Path):
    layers = {
        "trees": data_dir / "Baumkataster_OPENDATA" / "SHN_Baumkataster_open_UTM32N_EPSG25832.shp",
        "parcels": data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "flurstueck.shp",
        "buildings": data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "gebaeudeBauwerke.shp",
        "streets": data_dir / "Straßenkataster_Stand2015" / "6300002_STK_Strassenknoten_Beschriftung.shp",
        "greens": data_dir / "Grünflächenkataster" / "700001000_GRF_Pflegegebiet_F.shp",
    }
    for name, path in layers.items():
        if not path.exists():
            print(f"{name}: missing ({path})")
            continue
        gdf = gpd.read_file(path, rows=1)
        print(f"{name}: CRS={gdf.crs} | {path}")

    tifs = sorted(data_dir.glob("dop20rgbi_*/*.tif"))
    tif_crs = set()
    for tif in tifs[:5]:
        with rasterio.open(tif) as src:
            tif_crs.add(src.crs)
    print(f"orthophoto tiles: {len(tifs)} found; sample CRS={tif_crs or 'n/a'}")


def plot_layers(data_dir: Path, max_trees: int, include_raster: bool, out_path: Optional[Path]):
    tree_file = data_dir / "Baumkataster_OPENDATA" / "SHN_Baumkataster_open_UTM32N_EPSG25832.shp"
    parcel_file = data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "flurstueck.shp"
    building_file = data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "gebaeudeBauwerke.shp"
    street_file = data_dir / "Straßenkataster_Stand2015" / "6300002_STK_Strassenknoten_Beschriftung.shp"

    layers = []

    if tree_file.exists():
        trees = _load_vector(tree_file)
        if max_trees and len(trees) > max_trees:
            trees = trees.sample(max_trees, random_state=42)
        layers.append((trees, {"markersize": 1, "color": "forestgreen"}))
    else:
        print(f"[warn] missing tree layer: {tree_file}", file=sys.stderr)

    if parcel_file.exists():
        parcels = _load_vector(parcel_file)
        layers.append((parcels.iloc[:5000], {"facecolor": "none", "edgecolor": "#999999", "linewidth": 0.2}))
    if building_file.exists():
        buildings = _load_vector(building_file)
        layers.append((buildings.iloc[:5000], {"facecolor": "#aa0000", "edgecolor": "none", "alpha": 0.3}))
    if street_file.exists():
        streets = _load_vector(street_file)
        layers.append((streets.iloc[:5000], {"color": "#0055aa", "linewidth": 0.3}))

    fig, ax = plt.subplots(figsize=(10, 10))

    if include_raster:
        raster_files = sorted(data_dir.glob("dop20rgbi_*/*.tif"))
        mosaic = _orthophoto_mosaic(raster_files)
        if mosaic:
            arr, transform = mosaic
            rio_show(arr, transform=transform, ax=ax, cmap="gray", alpha=0.6)
        else:
            print("[warn] no orthophoto tiles found", file=sys.stderr)

    _plot_vectors(ax, layers)
    ax.set_aspect("equal")
    ax.set_title("Heilbronn tree-planting context (EPSG:25832)")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    if out_path:
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=200, bbox_inches="tight")
        print(f"saved plot to {out_path}")
    else:
        plt.show()


def _to_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError("Cannot convert to WGS84; missing CRS")
    if gdf.crs.to_epsg() != 4326:
        return gdf.to_crs(epsg=4326)
    return gdf


def _sanitize_attributes(gdf: gpd.GeoDataFrame, keep_cols: Optional[List[str]] = None) -> gpd.GeoDataFrame:
    """Limit attributes and make them JSON-serializable for folium."""
    gdf = gdf.copy()
    if keep_cols is not None:
        keep_cols = [c for c in keep_cols if c in gdf.columns and c != gdf.geometry.name]
        gdf = gdf[[gdf.geometry.name] + keep_cols]
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        if pd.api.types.is_datetime64_any_dtype(gdf[col]) or pd.api.types.is_timedelta64_dtype(gdf[col]):
            gdf[col] = gdf[col].astype(str)
        else:
            gdf[col] = gdf[col].apply(lambda v: v.isoformat() if isinstance(v, (datetime, pd.Timestamp)) else v)
    return gdf


def export_folium_map(
    data_dir: Path,
    max_trees: int,
    tiles: Optional[str],
    out_path: Path,
):
    import folium

    tree_file = data_dir / "Baumkataster_OPENDATA" / "SHN_Baumkataster_open_UTM32N_EPSG25832.shp"
    parcel_file = data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "flurstueck.shp"
    building_file = data_dir / "ALKIS-oE_080910_Heilbronn_shp" / "gebaeudeBauwerke.shp"
    street_file = data_dir / "Straßenkataster_Stand2015" / "6300002_STK_Strassenknoten_Beschriftung.shp"
    green_file = data_dir / "Grünflächenkataster" / "700001000_GRF_Pflegegebiet_F.shp"

    # Load vectors
    trees = _load_vector(tree_file) if tree_file.exists() else gpd.GeoDataFrame(geometry=[])
    parcels = _load_vector(parcel_file) if parcel_file.exists() else gpd.GeoDataFrame(geometry=[])
    buildings = _load_vector(building_file) if building_file.exists() else gpd.GeoDataFrame(geometry=[])
    streets = _load_vector(street_file) if street_file.exists() else gpd.GeoDataFrame(geometry=[])
    greens = _load_vector(green_file) if green_file.exists() else gpd.GeoDataFrame(geometry=[])

    if max_trees and len(trees) > max_trees:
        trees = trees.sample(max_trees, random_state=42)

    # Determine map center from any available layer
    ref_layer = None
    for candidate in (trees, parcels, streets, greens, buildings):
        if not candidate.empty:
            ref_layer = candidate
            break
    if ref_layer is None or ref_layer.empty:
        raise ValueError("No vector data available to center map")
    ref_wgs84 = _to_wgs84(ref_layer)
    minx, miny, maxx, maxy = ref_wgs84.total_bounds
    center = [(miny + maxy) / 2, (minx + maxx) / 2]

    tile_source = tiles if tiles else None
    m = folium.Map(location=center, zoom_start=14, tiles=tile_source, control_scale=True)

    def add_geojson(gdf, name, style_function=None, point_style=None):
        if gdf.empty:
            return
        gdf_wgs84 = _sanitize_attributes(_to_wgs84(gdf))
        if point_style:
            for _, row in gdf_wgs84.iterrows():
                folium.CircleMarker(
                    location=[row.geometry.y, row.geometry.x],
                    radius=point_style.get("radius", 2),
                    color=point_style.get("color", "green"),
                    fill=True,
                    fill_opacity=point_style.get("fill_opacity", 0.8),
                    opacity=point_style.get("opacity", 0.8),
                ).add_to(m)
        else:
            folium.GeoJson(gdf_wgs84.to_json(), name=name, style_function=style_function).add_to(m)

    add_geojson(parcels, "Parcels", style_function=lambda _: {"color": "#999", "weight": 0.5, "fillOpacity": 0})
    add_geojson(buildings, "Buildings", style_function=lambda _: {"color": "#aa0000", "weight": 0.5, "fillOpacity": 0.3})
    add_geojson(greens, "Greens", style_function=lambda _: {"color": "#52a352", "weight": 0.6, "fillOpacity": 0.15})
    add_geojson(streets, "Streets", style_function=lambda _: {"color": "#0055aa", "weight": 0.8, "fillOpacity": 0})
    add_geojson(trees, "Trees", point_style={"radius": 2, "color": "darkgreen", "fill_opacity": 0.9})

    folium.LayerControl().add_to(m)
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(out_path)
    print(f"saved folium map to {out_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="Quick CRS summary and plotting for Heilbronn datasets.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data", help="Path to data directory")
    parser.add_argument("--summary", action="store_true", help="Print CRS summary for key layers")
    parser.add_argument("--plot", action="store_true", help="Plot selected layers")
    parser.add_argument("--max-trees", type=int, default=5000, help="Sample size for tree points when plotting")
    parser.add_argument("--include-orthophoto", action="store_true", help="Include orthophoto mosaic in plot")
    parser.add_argument("--out-png", type=Path, help="Write plot to PNG instead of showing interactively")
    parser.add_argument("--folium-out", type=Path, help="Write an interactive HTML map (folium) of key layers")
    parser.add_argument("--folium-tiles", type=str, default="OpenStreetMap", help="Tile source for folium (empty string for no basemap)")
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = _data_dir(args.data_dir)

    if not (args.summary or args.plot or args.folium_out):
        print("Nothing to do: specify --summary and/or --plot or --folium-out", file=sys.stderr)
        return 1

    if args.summary:
        summarize_crs(data_dir)
    if args.plot:
        plot_layers(data_dir, max_trees=args.max_trees, include_raster=args.include_orthophoto, out_path=args.out_png)
    if args.folium_out:
        tiles = args.folium_tiles if args.folium_tiles is not None else "OpenStreetMap"
        if tiles == "":
            tiles = None
        export_folium_map(data_dir, max_trees=args.max_trees, tiles=tiles, out_path=args.folium_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
