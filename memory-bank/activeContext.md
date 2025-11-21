# Active Context

- Focus: Document loading/CRS handling and provide a Python viewer for the datasets (tree-planting heatmap prep).
- Recent actions: Added guidance in `data/README.md` for loading/CRS/mosaicking plus quick-view commands; created `tools/quick_view.py` (handles orthophoto tiles without CRS) to summarize CRS, plot sample layers with optional orthophoto mosaic, and export a folium HTML map (attributes sanitized for JSON; map centering via bounds to avoid deprecation warning).
- Next steps:
  - Clarify project objectives, target users, and expected deliverables for the hackathon.
  - Inventory datasets in `data/` with metadata (formats, spatial reference, coverage) to inform solution design.
  - Decide on initial tech stack and workflow once requirements are known.
- Open questions: What product or insights should be delivered from the provided datasets? What constraints (time, hosting, privacy) apply?
