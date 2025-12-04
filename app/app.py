import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

import geopandas as gpd
from shapely.geometry import box, Point
import numpy as np
import osmnx as ox
import pandas as pd
import requests
import branca.colormap as cm
import streamlit.components.v1 as components


# -----------------------------------------------------------------------------
# GLOBALS
# -----------------------------------------------------------------------------
# Continuous colormap for scores 0..1
SCORE_COLORMAP = cm.linear.YlGnBu_09.scale(0, 1)
DISPLAY_LINE_BUFFER_M = 6.0


def get_color_from_score(score: float) -> str:
    try:
        return SCORE_COLORMAP(score)
    except Exception:
        return "#cccccc"


def geometry_to_wkt(series: pd.Series) -> pd.Series:
    """Convert geometry objects to WKT strings for display (Arrow-safe)."""
    return series.apply(lambda g: g.wkt if g is not None else None)


def buffered_union_3857(gdf: gpd.GeoDataFrame, buffer_m: float):
    """Return union in EPSG:3857, optionally buffered by buffer_m."""
    if gdf is None or gdf.empty:
        return None
    try:
        geom = gdf.to_crs(3857).geometry
        if buffer_m > 0:
            geom = geom.buffer(buffer_m)
        union_fn = getattr(geom, "union_all", None)
        if union_fn:
            return union_fn()
        return geom.unary_union
    except Exception:
        return None


# -----------------------------------------------------------------------------
# SESSION STATE INIT
# -----------------------------------------------------------------------------
def init_feature_config():
    """Initial baseline features if not already in session_state."""
    if "features" in st.session_state:
        return

    # Baseline features from OSM
    st.session_state["features"] = [
        {
            "name": "Buildings",
            "source": "osm",
            "osm_key": "building",
            "osm_value": None,
            "feature_type": "no_plant_zone",
            "distance_min": 0.0,
            "distance_max": 20.0,
            "optimum": 10.0,
            "relevance": 1.0,
            "block_planting": True,
            "scaling_type": None,
            "gdf": None,
        },
        {
            "name": "Roads",
            "source": "osm",
            "osm_key": "highway",
            "osm_value": None,
            "feature_type": "no_plant_zone",
            "distance_min": 0.0,
            "distance_max": 40.0,
            "optimum": 5.0,
            "relevance": 1.0,
            "block_planting": True,
            "block_buffer_m": 10.0,
            "scaling_type": "downscaling",
            "gdf": None,
        },
        {
            "name": "Parks",
            "source": "osm",
            "osm_key": "leisure",
            "osm_value": "park",
            "feature_type": "upscaling",
            "distance_min": 0.0,
            "distance_max": 300.0,
            "optimum": 30.0,
            "relevance": 1.5,
            "block_planting": False,
            "scaling_type": "upscaling",
            "gdf": None,
        },
        {
            "name": "Water",
            "source": "osm",
            "osm_key": "natural",
            "osm_value": "water",
            "feature_type": "no_plant_zone",
            "distance_min": 0.0,
            "distance_max": 120.0,
            "optimum": 30.0,
            "relevance": 1.0,
            "block_planting": True,
            "scaling_type": "downscaling",
            "gdf": None,
        },
        {
            "name": "Railways",
            "source": "osm",
            "osm_key": "railway",
            "osm_value": None,
            "feature_type": "no_plant_zone",
            "distance_min": 0.0,
            "distance_max": 60.0,
            "optimum": 15.0,
            "relevance": 1.0,
            "block_planting": True,
            "block_buffer_m": 12.0,
            "scaling_type": "downscaling",
            "gdf": None,
        },
    ]


# -----------------------------------------------------------------------------
# GEOCODING / AOI / OSM HELPERS
# -----------------------------------------------------------------------------
def geocode_city(city_name: str):
    """Geocode a city name via Nominatim (OSM). Returns (lat, lon, bbox)."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    headers = {"User-Agent": "urban-tree-planner/0.1 (chatgpt-demo)"}

    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise ValueError(f"No results for '{city_name}'")

    hit = data[0]
    lat = float(hit["lat"])
    lon = float(hit["lon"])
    # boundingbox: [south, north, west, east]
    bbox = [float(x) for x in hit["boundingbox"]]
    return lat, lon, bbox


def make_aoi_polygon(center_lat: float, center_lon: float, radius_km: float):
    """Create a simple square AOI (in EPSG:4326) around a center & radius."""
    # Approximate conversion: 1° lat ≈ 111 km
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * np.cos(np.radians(center_lat)))
    return box(center_lon - dlon, center_lat - dlat, center_lon + dlon, center_lat + dlat)


def fetch_osm_layer(aoi_poly_4326, key: str, value: str | None = None) -> gpd.GeoDataFrame:
    """
    Fetch an OSM layer (buildings, roads, etc.) within the AOI using osmnx.
    AOI polygon must be EPSG:4326.
    """
    if value:
        tags = {key: value}
    else:
        tags = {key: True}

    fetch_fn = getattr(ox, "features_from_polygon", None)
    if fetch_fn is None:
        st.warning("OSM fetch unavailable: osmnx lacks features_from_polygon.")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")

    try:
        gdf = fetch_fn(aoi_poly_4326, tags=tags)
        if gdf.empty:
            return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
        gdf = gdf[["geometry"]].reset_index(drop=True)
        gdf = gdf.set_crs("EPSG:4326")
        return gdf
    except Exception as e:
        st.warning(f"OSM query failed for {key}={value}: {e}")
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")


def make_candidate_grid(aoi_3857, spacing_m: float) -> gpd.GeoDataFrame:
    """
    Create a regular grid of points inside AOI (in EPSG:3857).
    Returns GeoDataFrame in EPSG:4326 so Folium can use it.
    """
    minx, miny, maxx, maxy = aoi_3857.bounds
    xs = np.arange(minx, maxx, spacing_m)
    ys = np.arange(miny, maxy, spacing_m)

    pts = []
    for x in xs:
        for y in ys:
            p = Point(x, y)
            if aoi_3857.contains(p):
                pts.append(p)

    if not pts:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:3857").to_crs(4326)

    gdf = gpd.GeoDataFrame(geometry=pts, crs="EPSG:3857")
    return gdf.to_crs(4326)


# -----------------------------------------------------------------------------
# SCORING HEURISTIC
# -----------------------------------------------------------------------------
def triangular_score_vector(distances, dmin, dopt, dmax):
    """
    Piecewise-linear "triangle" score:
    - 0 outside [dmin, dmax]
    - rises from dmin -> dopt
    - falls from dopt -> dmax
    """
    distances = np.asarray(distances, dtype=float)
    scores = np.zeros_like(distances)

    if dmax <= dmin:
        return scores

    mask = (distances >= dmin) & (distances <= dmax)
    if not np.any(mask):
        return scores

    mid_mask = mask & (distances <= dopt)
    right_mask = mask & (distances > dopt)

    if dopt > dmin:
        scores[mid_mask] = (distances[mid_mask] - dmin) / (dopt - dmin)
    if dmax > dopt:
        scores[right_mask] = (dmax - distances[right_mask]) / (dmax - dopt)

    return np.clip(scores, 0.0, 1.0)


def compute_scores(candidates_4326: gpd.GeoDataFrame, features: list[dict]) -> gpd.GeoDataFrame:
    """
    Compute heuristic scores for candidate planting points based on features.

    Feature types:
      - no_plant_zone: mask out points inside these geometries
      - plant_zone: keep only points inside these geometries
      - upscaling: score += relevance * triangular(dist)
      - downscaling: score -= relevance * triangular(dist)
    """
    if candidates_4326.empty:
        return candidates_4326.assign(score=[], valid=[])

    cand_3857 = candidates_4326.to_crs(3857)
    scores = np.zeros(len(cand_3857), dtype=float)
    valid = np.ones(len(cand_3857), dtype=bool)

    # First pass: apply blocking zones (explicit no_plant_zone or block_planting flag)
    for feat in features:
        gdf = feat.get("gdf")
        if gdf is None or gdf.empty:
            continue
        ftype = feat["feature_type"]
        block = feat.get("block_planting", False) or ftype == "no_plant_zone"
        if not block:
            continue
        buffer_for_mask = float(feat.get("block_buffer_m", 0.0))
        if buffer_for_mask <= 0:
            buffer_for_mask = max(
                float(feat.get("distance_max", 0.0)),
                float(feat.get("distance_min", 0.0)),
            )
        geom_union = buffered_union_3857(gdf, buffer_for_mask)
        if geom_union is None or geom_union.is_empty:
            continue
        inside = cand_3857.geometry.apply(lambda g: g.within(geom_union)).to_numpy()
        valid &= ~inside

    # Second pass: scoring and plant_zone filters
    for feat in features:
        gdf = feat.get("gdf")
        if gdf is None or gdf.empty:
            continue

        ftype = feat["feature_type"]
        geom_union = buffered_union_3857(gdf, 0.0)
        if geom_union is None or geom_union.is_empty:
            continue

        if ftype == "plant_zone":
            inside = cand_3857.geometry.apply(lambda g: g.within(geom_union)).to_numpy()
            valid &= inside

        scaling_type = feat.get("scaling_type")
        if scaling_type is None and ftype in ("upscaling", "downscaling"):
            scaling_type = ftype

        if scaling_type:
            distances = cand_3857.geometry.apply(lambda g: g.distance(geom_union)).to_numpy()
            dmin = float(feat.get("distance_min", 0.0))
            dmax = float(feat.get("distance_max", 0.0))
            dopt = float(feat.get("optimum", 0.0))
            weight = float(feat.get("relevance", 1.0))

            tri = triangular_score_vector(distances, dmin, dopt, dmax)
            if scaling_type == "upscaling":
                scores += weight * tri
            elif scaling_type == "downscaling":
                scores -= weight * tri

    # Mask invalid candidates
    scores[~valid] = np.nan

    # Normalize to 0..1 on valid points
    valid_scores = scores[~np.isnan(scores)]
    if len(valid_scores) > 0:
        smin = valid_scores.min()
        smax = valid_scores.max()
        if smax > smin:
            scores_norm = (scores - smin) / (smax - smin)
        else:
            scores_norm = np.ones_like(scores) * 0.5
        scores_norm[~valid] = 0.0
    else:
        scores_norm = np.zeros_like(scores)

    out = candidates_4326.copy()
    out["score"] = scores_norm
    out["valid"] = valid
    return out


# -----------------------------------------------------------------------------
# MAP BUILDER
# -----------------------------------------------------------------------------
def build_map(center_lat, center_lon, aoi_poly_4326, features, points_gdf, top_n):
    """Create the Folium map with layers, heatmap, and top-N markers."""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=14,
        tiles="cartodbpositron",
    )

    # AOI outline
    folium.GeoJson(
        data=gpd.GeoSeries([aoi_poly_4326], crs="EPSG:4326").__geo_interface__,
        name="Analysis area",
        style_function=lambda x: {
            "fillOpacity": 0.0,
            "weight": 1,
            "color": "black",
            "dashArray": "5,5",
        },
    ).add_to(m)

    # Feature layers (for toggling)
    for feat in features:
        gdf = feat.get("gdf")
        if gdf is None or gdf.empty:
            continue

        ftype = feat["feature_type"]
        if ftype == "no_plant_zone":
            color = "red"
        elif ftype == "plant_zone":
            color = "green"
        elif ftype == "upscaling":
            color = "blue"
        else:
            color = "orange"

        disp_geom = gdf.to_crs(3857).geometry
        if disp_geom.geom_type.isin(["LineString", "MultiLineString"]).any():
            disp_geom = disp_geom.buffer(DISPLAY_LINE_BUFFER_M)
        disp_gdf = gpd.GeoDataFrame(geometry=disp_geom, crs="EPSG:3857").to_crs(4326)

        fg = folium.FeatureGroup(
            name=f"{feat['name']} ({ftype})",
            show=False,
        )

        folium.GeoJson(
            disp_gdf.__geo_interface__,
            style_function=lambda x, c=color: {
                "fillOpacity": 0.2 if ftype in ("plant_zone", "no_plant_zone") else 0.1,
                "weight": 1,
                "color": c,
            },
            tooltip=feat["name"],
        ).add_to(fg)

        fg.add_to(m)

    # Candidate points & heatmap
    valid_points = points_gdf[points_gdf["valid"] & (points_gdf["score"] > 0)]
    pts_fg = folium.FeatureGroup(name="Candidate planting spots", show=False)

    for _, row in valid_points.iterrows():
        lat = row.geometry.y
        lon = row.geometry.x
        s = float(row["score"])
        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            fill=True,
            fill_opacity=0.8,
            weight=0,
            fill_color=get_color_from_score(s),
            popup=folium.Popup(f"Score: {s:.3f}", max_width=200),
        ).add_to(pts_fg)

    pts_fg.add_to(m)

    # Heatmap
    heat_data = [
        [row.geometry.y, row.geometry.x, float(row["score"])]
        for _, row in valid_points.iterrows()
    ]
    if heat_data:
        heat_fg = folium.FeatureGroup(name="Score heatmap", show=True)
        HeatMap(
            heat_data,
            radius=25,
            blur=15,
            max_zoom=17,
        ).add_to(heat_fg)
        heat_fg.add_to(m)

    # Top N markers
    if not valid_points.empty:
        n = min(top_n, len(valid_points))
        top = valid_points.sort_values("score", ascending=False).head(n)
        top_fg = folium.FeatureGroup(name=f"Top {n} spots", show=True)

        for i, (_, row) in enumerate(top.iterrows(), start=1):
            lat = row.geometry.y
            lon = row.geometry.x
            s = float(row["score"])
            folium.Marker(
                location=[lat, lon],
                icon=folium.Icon(color="red", icon="star"),
                popup=folium.Popup(
                    f"<b>Rank #{i}</b><br>Score: {s:.3f}",
                    max_width=200,
                ),
            ).add_to(top_fg)

        top_fg.add_to(m)

    # Color legend
    SCORE_COLORMAP.caption = "Suitability score"
    SCORE_COLORMAP.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


# -----------------------------------------------------------------------------
# ANALYSIS PIPELINE
# -----------------------------------------------------------------------------
def run_analysis(center_lat, center_lon, radius_km, grid_spacing_m, features, top_n):
    """
    1. Build AOI polygon
    2. Load OSM layers for each OSM-based feature
    3. Clip uploaded layers
    4. Build candidate grid
    5. Score candidates
    6. Build Folium map
    """
    aoi_poly = make_aoi_polygon(center_lat, center_lon, radius_km)
    aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_poly], crs="EPSG:4326")

    updated_features = []
    warnings: list[str] = []
    for feat in features:
        f = feat.copy()

        if f["source"] == "osm":
            gdf = fetch_osm_layer(aoi_poly, f["osm_key"], f.get("osm_value"))
            f["gdf"] = gdf
            if gdf.empty:
                warnings.append(
                    f"OSM layer '{f['name']}' returned no features (offline or no data in area)."
                )

        elif f["source"] == "upload" and f.get("gdf") is not None:
            gdf = f["gdf"]
            try:
                if gdf.crs is None:
                    gdf = gdf.set_crs("EPSG:4326")
                gdf_clip = gpd.clip(gdf.to_crs(4326), aoi_gdf)
                f["gdf"] = gdf_clip
            except Exception:
                # Best-effort; if clip fails we keep original
                f["gdf"] = gdf

        updated_features.append(f)

    st.session_state["features"] = updated_features

    aoi_3857 = aoi_gdf.to_crs(3857).geometry.iloc[0]
    candidates = make_candidate_grid(aoi_3857, grid_spacing_m)
    if candidates.empty:
        raise RuntimeError("No candidate points generated – try increasing radius or grid spacing.")

    scored = compute_scores(candidates, updated_features)
    m = build_map(center_lat, center_lon, aoi_poly, updated_features, scored, top_n)
    return m, scored, warnings


# -----------------------------------------------------------------------------
# STREAMLIT UI
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="Urban Tree Planting Explorer",
        layout="wide",
    )

    init_feature_config()

    st.title("Urban Tree Planting Explorer 🌳")
    st.markdown(
        "Choose a city, adjust the heuristic, and explore suitable street tree planting spots."
    )

    # -------------------------------------------------------------------------
    # SIDEBAR – city, parameters, feature table, add features
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.header("1. City & analysis area")

        default_label = st.session_state.get("city_label", "Berlin, Germany")
        city_name = st.text_input("Search city", default_label)

        st.caption("Offline? Enter lat/lon manually below.")
        if st.button("Geocode city"):
            try:
                lat, lon, _ = geocode_city(city_name)
                st.session_state["city_center"] = (lat, lon)
                st.session_state["city_label"] = city_name
                st.success(f"Using {city_name} (lat={lat:.3f}, lon={lon:.3f})")
            except Exception as e:
                st.error(f"Geocoding failed: {e}")

        manual_lat = st.number_input(
            "Latitude (manual override)",
            value=st.session_state.get("city_center", (52.52, 13.405))[0],
            format="%.6f",
        )
        manual_lon = st.number_input(
            "Longitude (manual override)",
            value=st.session_state.get("city_center", (52.52, 13.405))[1],
            format="%.6f",
        )
        if st.button("Set center from lat/lon"):
            st.session_state["city_center"] = (manual_lat, manual_lon)
            st.session_state["city_label"] = f"{manual_lat:.4f}, {manual_lon:.4f}"
            st.success("Updated analysis center from manual coordinates.")

        radius_km = st.slider(
            "Analysis radius around center (km)",
            min_value=0.1,
            max_value=1.0,
            value=0.5,
            step=0.1,
        )

        grid_spacing_m = st.slider(
            "Grid spacing for candidate spots (m)",
            min_value=4,
            max_value=20,
            value=6,
            step=2,
        )

        top_n = st.slider(
            "Top N spots to highlight",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
        )

        st.markdown("---")
        st.header("2. Feature parameters")

        features = st.session_state["features"]

        st.info(
            """
            **Feature types:** 
            `plant_zone` keeps only candidates inside the geometry. 
            `no_plant_zone` masks out candidates inside or near it. 
            `upscaling` boosts scores near the geometry, 
            `downscaling` reduces scores nearby.

            **Distances (m):** 
            `distance_min` to `optimum` to `distance_max` form a triangle curve; scores rise toward `optimum` then fall away. `relevance` is the weight applied to that curve. For blocking layers you can still set a distance buffer in the table.
            """
        )

        cfg_df = pd.DataFrame(
            [
                {
                    "name": f["name"],
                    "feature_type": f["feature_type"],
                    "distance_min": f["distance_min"],
                    "distance_max": f["distance_max"],
                    "optimum": f["optimum"],
                    "relevance": f["relevance"],
                    "source": f["source"],
                    "osm_tag": (
                        f"{f['osm_key']}={f['osm_value'] or '*'}"
                        if f["source"] == "osm"
                        else ""
                    ),
                }
                for f in features
            ]
        )

        st.caption("Edit how each baseline layer contributes to the score:")
        edited_df = st.data_editor(
            cfg_df,
            key="features_editor",
            width="stretch",
            num_rows="fixed",
            column_config={
                "feature_type": st.column_config.SelectboxColumn(
                    "feature_type",
                    options=["plant_zone", "no_plant_zone", "upscaling", "downscaling"],
                )
            },
        )

        # Push edited parameters back into session_state
        for i, row in edited_df.iterrows():
            features[i]["feature_type"] = row["feature_type"]
            features[i]["distance_min"] = float(row["distance_min"])
            features[i]["distance_max"] = float(row["distance_max"])
            features[i]["optimum"] = float(row["optimum"])
            features[i]["relevance"] = float(row["relevance"])

        st.session_state["features"] = features

        st.markdown("### 3. Add new feature")

        # --- Upload GeoJSON feature ---
        with st.expander("Upload GeoJSON feature"):
            up_file = st.file_uploader(
                "GeoJSON file",
                type=["geojson", "json"],
                key="upload_geojson",
            )
            up_name = st.text_input("Name for this feature", key="upload_name")
            up_ftype = st.selectbox(
                "Feature type",
                ["plant_zone", "no_plant_zone", "upscaling", "downscaling"],
                key="upload_ftype",
            )
            up_dmin = st.number_input("Distance min (m)", value=0.0, key="upload_dmin")
            up_dmax = st.number_input("Distance max (m)", value=200.0, key="upload_dmax")
            up_opt = st.number_input("Optimum distance (m)", value=50.0, key="upload_opt")
            up_rel = st.number_input("Relevance (weight)", value=1.0, key="upload_rel")

            if st.button("Add uploaded feature"):
                if up_file and up_name:
                    gdf = gpd.read_file(up_file)
                    feature = {
                        "name": up_name,
                        "source": "upload",
                        "osm_key": None,
                        "osm_value": None,
                        "feature_type": up_ftype,
                        "distance_min": up_dmin,
                        "distance_max": up_dmax,
                        "optimum": up_opt,
                        "relevance": up_rel,
                        "gdf": gdf,
                    }
                    st.session_state["features"].append(feature)
                    st.success(f"Added uploaded feature '{up_name}'")
                else:
                    st.warning("Please provide both a name and a GeoJSON file.")

        # --- Add OSM tag-based feature ---
        with st.expander("Add feature from OSM (tag search)"):
            osm_name = st.text_input("Name (optional)", value="", key="osm_name")
            osm_key = st.text_input("OSM key", value="landuse", key="osm_key")
            osm_value = st.text_input("OSM value (optional)", value="forest", key="osm_value")
            st.caption(
                "Find keys/values on the [OSM map features page](https://wiki.openstreetmap.org/wiki/Map_features)."
            )
            osm_ftype = st.selectbox(
                "Feature type",
                ["plant_zone", "no_plant_zone", "upscaling", "downscaling"],
                key="osm_ftype",
            )
            osm_dmin = st.number_input("Distance min (m)", value=0.0, key="osm_dmin")
            osm_dmax = st.number_input("Distance max (m)", value=300.0, key="osm_dmax")
            osm_opt = st.number_input("Optimum distance (m)", value=100.0, key="osm_opt")
            osm_rel = st.number_input("Relevance (weight)", value=1.0, key="osm_rel")

            if st.button("Add OSM feature"):
                fname = osm_name or f"{osm_key}={osm_value or '*'}"
                feature = {
                    "name": fname,
                    "source": "osm",
                    "osm_key": osm_key,
                    "osm_value": osm_value or None,
                    "feature_type": osm_ftype,
                    "distance_min": osm_dmin,
                    "distance_max": osm_dmax,
                    "optimum": osm_opt,
                    "relevance": osm_rel,
                    "gdf": None,
                }
                st.session_state["features"].append(feature)
                st.success(f"Added OSM feature '{fname}'")

    # -------------------------------------------------------------------------
    # MAIN AREA – city map picker + run analysis + results
    # -------------------------------------------------------------------------
    center_lat, center_lon = st.session_state.get("city_center", (52.52, 13.405))

    st.subheader("1. Pick city & analysis center")
    st.write("Search the city in the sidebar, then click on the map to refine the center.")

    selector_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=13,
        tiles="cartodbpositron",
    )
    folium.Marker([center_lat, center_lon], tooltip="Analysis center").add_to(selector_map)

    map_data = st_folium(selector_map, key="city_picker", height=350)
    if map_data and map_data.get("last_clicked"):
        center_lat = map_data["last_clicked"]["lat"]
        center_lon = map_data["last_clicked"]["lng"]
        st.session_state["city_center"] = (center_lat, center_lon)

    st.markdown("---")
    st.subheader("2. Run heuristic and inspect the heatmap")

    run = st.button("Run analysis / recompute heatmap")
    if run:
        try:
            with st.spinner("Computing candidate spots and scores..."):
                m, scored_points, warn_msgs = run_analysis(
                    center_lat=center_lat,
                    center_lon=center_lon,
                    radius_km=radius_km,
                    grid_spacing_m=grid_spacing_m,
                    features=st.session_state["features"],
                    top_n=top_n,
                )
            st.session_state["result_map_html"] = m.get_root().render()
            st.session_state["result_scored"] = scored_points
            st.session_state["result_top_n"] = top_n
            st.session_state["result_warnings"] = warn_msgs
            st.session_state["result_error"] = None
        except Exception as e:
            st.session_state["result_error"] = str(e)

    if st.session_state.get("result_error"):
        st.error(f"Analysis failed: {st.session_state['result_error']}")
    elif "result_map_html" in st.session_state and "result_scored" in st.session_state:
        st.markdown("#### Suitability map")
        components.html(st.session_state["result_map_html"], height=600)

        warn_msgs = st.session_state.get("result_warnings") or []
        for msg in warn_msgs:
            st.warning(msg)

        st.markdown("#### Top candidates (by score)")
        scored_points = st.session_state["result_scored"]
        top_n_display = st.session_state.get("result_top_n", top_n)
        top_df = (
            scored_points[scored_points["valid"]]
            .sort_values("score", ascending=False)
            .head(top_n_display)
        )
        display_top = pd.DataFrame(
            {
                "score": top_df["score"].to_numpy(),
                "lat": top_df.geometry.y.to_numpy(),
                "lon": top_df.geometry.x.to_numpy(),
                "geometry_wkt": geometry_to_wkt(top_df.geometry),
            }
        )
        st.dataframe(display_top)

        st.markdown("#### Feature list & parameters")
        feat_table = pd.DataFrame(
            [
                {
                    "name": f["name"],
                    "type": f["feature_type"],
                    "distance_min": f["distance_min"],
                    "distance_max": f["distance_max"],
                    "optimum": f["optimum"],
                    "relevance": f["relevance"],
                    "source": f["source"],
                    "osm_tag": (
                        f"{f['osm_key']}={f['osm_value'] or '*'}"
                        if f["source"] == "osm"
                        else "upload"
                    ),
                }
                for f in st.session_state["features"]
            ]
        )
        st.dataframe(feat_table)


if __name__ == "__main__":
    main()
