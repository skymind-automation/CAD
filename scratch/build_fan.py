
import sys
from types import SimpleNamespace as NS
sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
from delta3d import engine_layout as layout
from delta3d.domain import parse_spec
from delta3d.cad import BUILDERS
spec = layout.part_specs(layout.DEFAULT_ENGINE)["fan"]
parsed = parse_spec({"kind": "propeller", "material": "polymer-reference", "parameters": spec["parameters"]})
solid, _ = BUILDERS["propeller"](parsed)
box = solid.BoundingBox()
print("fan bbox", box.xmin, box.xmax, box.ymin, box.ymax, box.zmin, box.zmax)
solid.exportBrep(r"C:\Users\ICT\HowoEngine1\scratch\breps\fan.brep")
