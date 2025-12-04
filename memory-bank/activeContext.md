# Active Context

- Focus: Establish project scaffolding across processing, backend, and frontend for the tree-planting heatmap workflow.
- Recent actions: Added processing scaffold (GeoPandas pipeline, requirements, example run), backend scaffold (FastAPI health/info and placeholder candidates endpoint), and frontend scaffold (React + kepler.gl via Vite). Added base-layer cleaning prototype (`test/clean_base_layers.py`), tree inventory (`test/tree_inventory.py`), constraints/suitability (`test/constraints.py`), scoring/top-candidates (`test/scoring.py`, smoother scoring + point outputs), plotting overlays in quick_view (including folium toggles), Kepler.gl quick view without token (`tools/quick_view_kepler.py`), plus clip/simplify options to lighten views; updated README/test docs with commands.
- Next steps:
  - Clarify project objectives, target users, and expected deliverables for the hackathon.
  - Inventory datasets in `data/` with metadata (formats, spatial reference, coverage) to inform solution design.
  - Decide on initial tech stack and workflow once requirements are known.
- Open questions: What product or insights should be delivered from the provided datasets? What constraints (time, hosting, privacy) apply?
