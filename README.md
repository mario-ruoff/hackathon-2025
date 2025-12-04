# Hackathon 2025 – Urban Tree Planting Explorer

Streamlit app to explore candidate tree-planting spots using OpenStreetMap (OSM) data and simple distance-based heuristics. It fetches OSM features, scores a grid of candidate points, and renders a Folium heatmap with the top-ranked suggestions.

## Demo and presentation
![Urban Tree Planting Explorer demo](BBT.gif)

[Download the presentation (PDF)](BBT%20-%20Winning%20Hackathon%20Solution1.pdf)

## Quick start
- Prerequisites: Python 3.10+ and a working `pip`.
- Install: `python -m venv .venv && source .venv/bin/activate` then `pip install -r requirements.txt`.
- Run the app: `streamlit run app/app.py` (starts a local server and opens the UI).

## How to use the UI
- **Choose a city** in the sidebar (geocode or set lat/lon) and set the analysis radius and grid spacing.
- **Tune feature parameters** in the table; adjust `feature_type`, distances, and `relevance` weight.
- **Add layers**:
  - Upload GeoJSON and label it with a feature type and distances.
  - Add OSM layers by key/value (see the in-app link to OSM map features for available tags).
- **Run analysis** to generate the heatmap and the ranked list of candidate spots. Toggle layers in the map legend.

### Feature types and parameters
- `plant_zone`: keeps only candidates that fall inside the geometry.
- `no_plant_zone`: masks out candidates inside/near the geometry (use distance fields as a buffer).
- `upscaling`: boosts scores near the geometry using a triangular curve from `distance_min` → `optimum` → `distance_max`.
- `downscaling`: reduces scores near the geometry with the same triangular curve.
- `relevance`: weight multiplier for the up/downscaling curves.

## Components (code pointers)
- `app/app.py`: Streamlit UI, OSM fetching via `osmnx`, scoring (`triangular_score_vector` and `compute_scores`), Folium map builder, and session-scoped feature configuration.
- `app/kepler_test.py`: quick kepler.gl experiment for visualizing sample data.
- `tools/`: assorted helpers for inspecting geospatial data (not needed to run the Streamlit app).
- `requirements.txt`: Python dependencies for the Streamlit experience.

## Data
- OSM features are pulled live based on the selected key/value. The UI links to the OSM map features page for tag discovery.
- Optional local datasets (e.g., Heilbronn hackathon zip) can be placed under `data/` if you extend the app to ingest them.

## Possible extensions
- Persist and load saved feature presets per city.
- Add caching for OSM queries and scoring results to speed up iteration.
- Support additional data sources (e.g., city parcel/road/tree layers) with layer-specific default parameters.
- Export scored points as GeoJSON/GeoPackage for downstream GIS analysis.
- Add tests for scoring edge cases and UI utilities.
