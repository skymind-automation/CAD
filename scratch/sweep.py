
import subprocess
import sys
py = sys.executable
for name in ("cylinder_block", "timing_case", "exhaust_manifold", "intake_manifold", "alternator"):
    pass
subprocess.run([py, r"C:\Users\ICT\HowoEngine1\scratch\build_parts.py", "cylinder_block", "timing_case", "exhaust_manifold", "intake_manifold", "alternator"], check=True)
subprocess.run([py, r"C:\Users\ICT\HowoEngine1\scratch\assembly_check.py", "0"], check=True)
for angle in (30, 90, 150, 200, 270, 330, 380, 460, 540, 620, 690):
    subprocess.run([py, r"C:\Users\ICT\HowoEngine1\scratch\assembly_check.py", str(angle), "moving"], check=True)
