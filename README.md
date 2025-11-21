# Hackathon 2025
"Future City Hackathon" of the City of Heilbronn 2025

## Dataset
- Source: `https://bwsyncandshare.kit.edu/public.php/dav/files/8yJFQCEaFqYai3Y/Stadt%20Heilbronn/Hackathon2025.zip`
- Location: Place in `/dataset` folder
https://bwsyncandshare.kit.edu/public.php/dav/files/8yJFQCEaFqYai3Y/Stadt%20Heilbronn/Hackathon2025.zip

# Data Guide for Tree-Planting Heatmap

Goal: build a heatmap of candidate spots for planting new trees in Heilbronn using the provided open datasets.

## Datasets in `data/`

- `Baumkataster_OPENDATA/SHN_Baumkataster_open_UTM32N_EPSG25832.*` (shapefile)  
  Existing trees with attributes; CRS: UTM 32N / EPSG:25832.
- `ALKIS-oE_080910_Heilbronn_shp/*.shp`  
  ALKIS parcels, buildings, etc.; CRS likely EPSG:25832 (see `.prj`). Use to mask out buildings and private parcels.
- `Grünflächenkataster/*.shp`  
  Green space polygons and labels; EPSG:25832. Base layer for public green areas and maintenance zones.
- `Straßenkataster_Stand2015/*.shp`  
  Street centerlines, nodes, and labels; EPSG:25832. Use for setback/buffer rules from roads.
- `Feuerwehrflächen/*.shp`  
  Fire access, protection zones; EPSG:25832. Exclude or down-rank restricted areas.
- `dop20rgbi_*/*.(tif|tfw|csv)`  
  Orthophoto tiles (black/white) plus TFW/CSV georeference and metadata link (`Meta-ATKIS_DOP20.txt`). Use as raster base to derive surface context or background.
- Licenses/notes: `GOVDATA-Datenlizenz_Deutschland.pdf` (orthophoto), `readme_bka_open.txt` (Baumkataster).

## Recommended workflow

1) **Load data & set CRS**  
   - Verify layers: `python tools/quick_view.py --summary` (expects EPSG:25832). Reproject any outliers to 25832.  
   - Mosaic orthophotos: `gdalbuildvrt dop20.vrt dop20rgbi_*/*.tif` (or let the Python viewer mosaic on the fly).  
   - Quick visual check (PNG): `python tools/quick_view.py --plot --include-orthophoto --out-png tmp/preview.png`.
   - Interactive HTML (folium): `python tools/quick_view.py --folium-out tmp/map.html --folium-tiles ""` (empty tiles avoids web requests; use default tiles if you have connectivity). Attributes are trimmed and sanitized for browser viewing.

2) **Clean base layers**  
   - Select public/municipal parcels from ALKIS if attribute available; otherwise treat all parcels but mark ownership unknown.  
   - Extract building footprints and buffer by a safety distance to exclude planting on/immediately next to structures.  
   - From Straßenkataster, buffer roads/paths for setback rules.

3) **Tree inventory**  
   - Load Baumkataster points. Mark existing trees for exclusion and for spatial join (distance to nearest tree, canopy gaps).

4) **Constraints & suitability surfaces**  
   - Union constraints: buildings+buffers, roads+buffers, fire protection layers, and any restricted green areas; mark as “unsuitable”.  
   - Candidate area = green spaces and other open parcels minus unsuitable zones. Optionally use orthophoto intensity to down-rank paved surfaces.

5) **Scoring & heatmap**  
   - Create a grid (e.g., 10–20 m) over candidate area.  
   - For each cell, compute features: distance to nearest tree, distance to roads/paths, parcel/land-use type, fire restriction flag, existing green-space class.  
   - Apply a simple weighted score (e.g., prefer gaps > X m from trees, within parks, outside fire/road buffers).  
   - Export scored grid as GeoJSON/GeoTIFF and render as heatmap in QGIS or your web map stack.

6) **Outputs**  
   - Heatmap layer (raster or point grid with `score`).  
   - Vector of suggested planting spots (top-N cells) for inspection.

## Quick tips

- Keep everything in EPSG:25832 to avoid misalignment.  
- Inspect attribute tables (field names may be German abbreviations).  
- If you need NDVI but only have grayscale orthophotos, rely on vector constraints and distance-based scoring instead of spectral vegetation indices.
