# System Patterns

- Current state: Scaffolds created for three layers:
  - Processing: Python/GeoPandas pipeline to build candidate grids/heatmaps from city datasets.
  - Backend: FastAPI service placeholder to serve processed outputs (health/info and stub candidates endpoint).
  - Frontend: React + kepler.gl app to visualize candidates/heatmap (Mapbox token required).
- Pending decisions: Data storage/tiling approach, API payload formats, front-end data loading from backend, deployment targets.
- Constraints/assumptions: Use EPSG:25832 for processing; reproject to WGS84 for web display.
