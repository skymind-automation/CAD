# Verification

Built on Delta 3D 0.5.0 (commit `f577ccd`) with `tools/build_engine.py`. All geometry is exact
(OCCT B-rep); masses use reference densities.

## Assembly checks (both assemblies: 0° and 90° crank)
| Check | Result |
|---|---|
| Components placed | 197 of 197, all valid single solids |
| Exact pairwise interference (boolean common volume) | **none** at 0° and at 90° |
| Moving-parts sweep (scratch study, earlier geometry) | none at 30°, 150°, 200°, 380°, 540°, 620° crank after the counterweight fix |
| Minimum valve-to-piston gap | 3.39 mm (cylinder 6 intake, 2° crank) |
| Gear train | centre distances from the meshing condition; cam-gear to crank-gear clearance 6.7 mm |
| Modelled mass | 999.28 kg |
| Bounding box | 1440 × 1007 × 930 mm (length × width × height) |

## Engine numbers
- Displacement: \(\tfrac{\pi}{4}\,126^2 \cdot 130 \cdot 6 = 9.726\) L — matches the published 9.726 L.
- Compression ratio 17.000:1 with a 15.18 mm bowl (clearance volume 101.3 cm³ per cylinder).
- Mean piston speed at 2200 rpm: \(2 \cdot 0.130 \cdot 2200 / 60 = 9.53\) m/s.
- Declared 247 kW at 2200 rpm implies BMEP 13.85 bar (derived, not a prediction).

## Comparison with published data (does not match exactly — concept model)
- **Mass:** published dry mass 850–875 kg; model 999.28 kg, i.e. about 14–18 % heavy. Largest contributors: cylinder block 333 kg, six heads 160 kg, crankshaft 118 kg; the turbocharger envelope is 40.5 kg against the catalog's 16 kg (both housings modelled in cast iron).
- **Envelope:** published figures disagree between sources (1530 × 660 × 965 mm and 1750 × 850 × 1400 mm). The model is 1440 × 1007 × 930 mm; its width is set by the manifolds, turbo and starter, which are positioned by assumption.

## Part-level comparison with catalog weights (indicative only — catalog weights are unverified)
| Part | Model kg | Catalog kg |
|---|---|---|
| Piston | 2.22 | 2.185 |
| Piston pin | 1.28 | 1.28 |
| Cylinder liner | 1.48 | 1.47 |
| Main cap bolt | 0.40 | 0.35 |
| Camshaft | 21.8 | 11.3 |
| Valves | 0.18–0.21 | 0.575–0.595 (likely shipping weight) |

## Bill of materials
50 lines (35 linked to catalog part numbers, all priced); linked list-price total KES 885,480. 15
modelled parts have no catalog match and are listed without a price. 25 further catalog lines (springs,
seals, sensors, hoses …) are listed in `engine/catalog_map.json` as not modelled.

## Not verified
Strength, stiffness, fatigue, sealing, lubrication, cooling, combustion, balance/vibration,
valvetrain dynamics, manufacturability and tolerances. Catalog prices, weights and fitment.
