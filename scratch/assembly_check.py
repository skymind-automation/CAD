
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
BREPS = Path(r"C:\Users\ICT\HowoEngine1\scratch\breps")
_cache = {}


def load(name):
    import cadquery as cq
    if name not in _cache:
        _cache[name] = cq.Shape.importBrep(str(BREPS / f"{name}.brep"))
    return _cache[name]


def placed(item):
    import cadquery as cq
    shape = load(item["library"])
    for axis, angle in zip(((1, 0, 0), (0, 1, 0), (0, 0, 1)), item["rotation_deg"]):
        if angle:
            shape = shape.rotate((0, 0, 0), axis, angle)
    return shape.translate(cq.Vector(*item["position_mm"]))


def check_pair(args):
    a, b = args
    sa, sb = placed(a), placed(b)
    common = sa.intersect(sb)
    volume = common.Volume() if common.Solids() else 0.0
    return a["name"], b["name"], volume


def main():
    from delta3d import engine_layout as layout

    angle = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    moving_only = len(sys.argv) > 2 and sys.argv[2] == "moving"
    moving = {"crankshaft", "connecting_rod", "rod_shell", "piston", "piston_pin", "intake_valve", "exhaust_valve", "tappet", "pushrod", "rocker_arm", "camshaft", "crank_gear", "idler_gear", "cam_gear", "pump_gear", "flywheel", "crank_pulley", "vibration_damper"}
    engine = layout.DEFAULT_ENGINE
    names = {path.stem for path in BREPS.glob("*.brep")}
    revisions = {name: name for name in names}
    items = layout.placements(engine, revisions, angle)
    print(f"{len(items)} components at {angle} deg")
    started = time.time()
    boxes = []
    for item in items:
        box = placed(item).BoundingBox()
        boxes.append((box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax))
    pairs = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = boxes[i], boxes[j]
            if moving_only and items[i]["library"] not in moving and items[j]["library"] not in moving:
                continue
            if all(a[k] <= b[k + 3] and b[k] <= a[k + 3] for k in range(3)):
                pairs.append((items[i], items[j]))
    print(f"{len(pairs)} candidate pairs, bbox {time.time() - started:.1f}s")
    hits = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        for name_a, name_b, volume in pool.map(check_pair, pairs, chunksize=8):
            if volume > 1e-3:
                hits.append((name_a, name_b, round(volume, 2)))
    print(f"exact checks done in {time.time() - started:.1f}s; {len(hits)} interferences")
    for hit in hits:
        print("  ", hit)
    Path(rf"C:\Users\ICT\HowoEngine1\scratch\interference_{int(angle)}.json").write_text(json.dumps(hits, indent=1))


if __name__ == "__main__":
    main()
