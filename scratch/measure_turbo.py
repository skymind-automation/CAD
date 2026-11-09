
import json
import sys
sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
from delta3d import engine_layout as layout
from delta3d.cad import generate

engine = layout.InlineEngine()
specs = layout.part_specs(engine)
result = generate(specs["turbocharger"])
props = result.get("properties", result)
print(json.dumps({key: props.get(key) for key in ("mass_kg", "volume_mm3", "valid", "solid_count")}))
