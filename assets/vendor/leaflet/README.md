# Map dependencies

Unmodified distribution files from Leaflet 1.9.4 and Leaflet.markercluster 1.5.3.
`../../../monitor/outputs/map_renderer.py` reads these files once and embeds them in the map document,
so map initialization does not require access to a third-party script CDN.

- Leaflet: https://unpkg.com/.@1.9.4/dist/ — BSD-2-Clause, see `LEAFLET-LICENSE`.
- Leaflet.markercluster: https://unpkg.com/..markercluster@1.5.3/dist/ — MIT, see `MARKERCLUSTER-LICENSE`.

The map uses custom SVG icons rather than Leaflet's default PNG marker images.
Esri tiles and the optional screenshot library remain external resources.
