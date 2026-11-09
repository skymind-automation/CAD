# HOWO WD615-class engine — concept assembly

A complete in-line six diesel engine (WD615-class, 9.7 L) assembled from exact parametric solids in
Delta 3D (`C:\Users\ICT\Untitled project`) and linked to the Buffalo (buffalo.co.ke) HOWO parts
catalog for a priced bill of materials.

**Status: concept model.** Headline dimensions follow published WD615 data; internal sizes are
labelled assumptions (see `docs/ASSUMPTIONS.md`). Not OEM geometry, not validated for manufacture.

## What is here
| Path | Content |
|---|---|
| `engine/wd615.json` | Engine parameters with provenance for every value |
| `engine/catalog_map.json` | Library part → catalog part number links, plus non-modelled BOM lines |
| `data/source/` | The user's scraped catalog (`buffalo_parts.csv`, `.xlsx`) and scraper scripts, unchanged |
| `tools/build_engine.py` | Idempotent driver: imports the catalog, generates 49 parts, builds both assemblies, downloads STEP and reports |
| `outputs/` | `WD615_engine_000deg.step`, `WD615_engine_090deg.step` (not in git, ~34 MB each), assembly reports, `bom.json`, `bom.csv`, `engine-summary.json`, `catalog-import-report.json`, `build-summary.json` |
| `docs/ASSUMPTIONS.md` | Published vs secondary vs assumed values; catalog data quality |
| `docs/VERIFICATION.md` | What was checked and the results |

## The model
- 197 placed solids in 11 subsystems: engine block (block, 6 wet liners, 7 main caps, 14 cap bolts, 7 main shells), crank train (crankshaft with 1-5-3-6-2-4 throws and counterweights, 6 rods, pistons, pins, rod shells, flywheel, damper, pulley), 6 individual cylinder heads with gaskets and 24 head bolts, valvetrain (12 valves, tappets, pushrods, rocker arms, pedestals, shafts, covers, block camshaft), rear gear train (crank 36T / idler 24T / cam 72T / pump 72T, module 4), fuel (injection pump, 6 injectors, filters), air & exhaust (manifolds, turbocharger), cooling, lubrication (oil pan, pump, cooler, filters), electrical (alternator, starter) and accessories (air compressor).
- Two assemblies from the same parts: cylinder 1 at firing TDC (0°) and 90° crank; both interference-free (exact boolean check), 999.28 kg modelled (published dry mass 850–875 kg — see `docs/VERIFICATION.md`).
- 35 BOM lines linked to real catalog part numbers; priced linked total KES 885,480 (list prices at scrape time, linked lines only).

## Rebuild
```powershell
$env:DELTA_USER = "<your Delta 3D user>"
$env:DELTA_PASSWORD = "<password>"
& "C:\Users\ICT\Untitled project\.venv\Scripts\python.exe" tools\build_engine.py
```
The Delta 3D service must be running (`start.ps1`). Change a parameter in `engine/wd615.json` /
`InlineEngine` and rerun: only changed parts regenerate, then both assemblies rebuild with exact
interference checks.
