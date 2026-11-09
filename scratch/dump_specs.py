
import json, sys
sys.path.insert(0, r"C:\Users\ICT\Untitled project\backend")
from delta3d import engine_layout as layout
specs = layout.part_specs(layout.DEFAULT_ENGINE)
print(json.dumps(specs))
