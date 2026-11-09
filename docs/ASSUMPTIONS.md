# Assumptions and provenance

This is a **concept model** of a WD615-class engine assembled from exact parametric solids. It is
not OEM geometry and has not been validated for manufacture, strength, sealing, lubrication or
performance. Every number below is labelled with where it came from.

## Published (WD615 / WD615.69 data, several supplier spec sheets)
| Item | Value | Use in the model |
|---|---|---|
| Layout | in-line 6, four-stroke, water-cooled DI diesel | engine architecture |
| Bore × stroke | 126 × 130 mm | liner bore, piston, crank throw (65 mm) |
| Displacement | 9.726 L | checked: \(\tfrac{\pi}{4}\,126^2 \cdot 130 \cdot 6 = 9.726\) L |
| Firing order | 1-5-3-6-2-4 | crank throw phases 0/240/120/120/240/0° |
| Compression ratio | ≈ 17:1 | piston bowl depth solved to 15.18 mm for 17.000:1 |
| Rated power (WD615.69) | 247 kW @ 2200 rpm | declared input only; BMEP 13.85 bar derived, not predicted |
| Dry mass | 850–875 kg | comparison only (model is heavier, see VERIFICATION) |

## Secondary source
- Connecting-rod centre distance **219 mm** (Chinese structural article). Not confirmed in an OEM manual.

## Assumptions (no source found — change in `engine/wd615.json` / `engine_layout.InlineEngine`)
- Cylinder spacing 150 mm; deck height derived (364 mm).
- Compression height 80 mm — chosen so the modelled piston (2.224 kg) matches the catalog piston (2.185 kg).
- Main journal Ø100 mm, crank pin Ø82 mm; counterweight radius 88 mm (sized to clear the piston skirt at BDC).
- Head gasket 1.2 mm compressed.
- Valve timing IVO 20° BTDC / IVC 46° ABDC / EVO 50° BBDC / EVC 20° ATDC; rocker ratio 1.15; flat-follower cam with constant-acceleration lift law, max valve lift 9.85 mm.
- Two valves per cylinder, pushrods from a block camshaft, individual heads (WD615 architecture); port layout counter-flow (not verified).
- Rear gear train: crank 36T, idler 24T, cam 72T, injection-pump 72T, module 4, 0.2 mm backlash.
- Materials are reference materials (cast iron, steel, cast aluminium) with handbook densities; no grade is claimed.
- Turbocharger, pumps, alternator, starter, filters and coolers are **envelope models** (housings with representative hollowing), not functional internals. The turbo models both housings in cast iron; real compressor housings are aluminium, so its mass (40.5 kg) is above the catalog's 16 kg.

## Catalog data (`data/source/buffalo_parts.csv`, scraped by the user from buffalo.co.ke)
- 2,475 rows → 2,308 unique part numbers; 152 duplicate rows (147 with conflicting values), 15 rejected rows.
- Weights are present for only ~14 % of parts and several are placeholders (0.001 kg); package dimensions are packaging, not part geometry; three part numbers were mangled by Excel into scientific notation.
- Prices are list prices in KSh at scrape time. **Weights and prices are not verified**; the BOM never estimates a missing price.
- Some listed weights look like shipping weights (e.g. valves 0.575–0.595 kg vs ≈ 0.2 kg modelled), so model-vs-catalog mass ratios are indicative only.
- Part-number links are in `engine/catalog_map.json`; every linked number was confirmed present in the CSV. Lines such as the water pump (`VG1062060351`, "Prince EGR") may be variant-specific and should be checked against the actual engine plate.

## Not modelled
Valve springs/retainers/collets, piston rings as separate parts, bearings' oil grooves, belts, hoses, wiring, fuel lines, gaskets other than the head gasket, sensors, brackets and most fasteners other than head and main-cap bolts. `engine/catalog_map.json` lists 25 such catalog lines with per-engine quantities for completeness.
