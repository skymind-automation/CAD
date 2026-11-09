
import json
import sys
import time
from types import SimpleNamespace as NS

sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
from delta3d import engine_parts as ep
from delta3d import engine_layout as layout
from delta3d.cad import precise_mass_properties

BUILDERS = {
    "cylinder_block": ep._cylinder_block, "cylinder_liner": ep._cylinder_liner, "bearing_cap": ep._bearing_cap,
    "shaft": ep._shaft, "crankshaft": ep._crankshaft, "connecting_rod": ep._connecting_rod, "piston": ep._piston,
    "head_gasket": ep._head_gasket, "cylinder_head": ep._cylinder_head, "valve": ep._valve, "tappet": ep._tappet,
    "rocker_arm": ep._rocker_arm, "rocker_pedestal": ep._rocker_pedestal, "valve_cover": ep._valve_cover,
    "fastener": ep._fastener, "camshaft": ep._camshaft, "spur_gear": ep._spur_gear, "timing_case": ep._timing_case,
    "flywheel": ep._flywheel, "bell_housing": ep._bell_housing, "oil_pan": ep._oil_pan, "housing": ep._housing,
    "injection_pump": ep._injection_pump, "exhaust_manifold": ep._exhaust_manifold,
    "intake_manifold": ep._intake_manifold, "turbocharger": ep._turbocharger, "pulley": ep._pulley,
    "canister": ep._canister,
}
DENSITY = {"cast-iron-reference": 7200, "steel-reference": 7850, "al6061-t6": 2700, "aluminum-casting-reference": 2680, "polymer-reference": 1200}
engine = layout.DEFAULT_ENGINE
specs = layout.part_specs(engine)
out = {}
only = sys.argv[1:] or None
for name, spec in specs.items():
    if only and name not in only:
        continue
    if spec["kind"] not in BUILDERS:
        print(f"skip {name} ({spec['kind']})")
        continue
    started = time.time()
    try:
        solid, _ = BUILDERS[spec["kind"]](NS(parameters=NS(**spec["parameters"])))
    except Exception as error:
        print(f"FAIL {name}: {error}")
        continue
    volume, _ = precise_mass_properties(solid)
    box = solid.BoundingBox()
    mass = volume * 1e-9 * DENSITY[spec["material"]]
    print(f"{name:18s} {mass:9.3f} kg  bbox=({box.xlen:7.1f},{box.ylen:7.1f},{box.zlen:7.1f}) faces={len(solid.Faces()):5d} {time.time() - started:5.1f}s")
    solid.exportBrep(rf"C:\Users\ICT\HowoEngine1\scratch\breps\{name}.brep")
print(json.dumps(layout.summary(engine), indent=1, default=str))
