# Tech Context

- Stack:
  - Processing: Python with GeoPandas, Rasterio, Shapely; scripts under `processing/`.
  - Backend: FastAPI + Uvicorn scaffold under `backend/`.
  - Frontend: React + kepler.gl (Vite) under `frontend/` (requires Mapbox token).
- Assets: `data/` directory contains geospatial/open datasets (Baumkataster, orthophotos, green areas, streets, ALKIS).
- Tooling: Quick viewer in `tools/quick_view.py` for CRS summaries/plots/folium; processing and backend each have their own requirements files; frontend uses npm with Vite.
- Setup notes: Keep processing in EPSG:25832; reproject outputs to WGS84 for web map display.
