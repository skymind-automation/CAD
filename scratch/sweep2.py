
import subprocess
import sys
py = sys.executable
subprocess.run([py, r"C:\Users\ICT\HowoEngine1\scratch\build_parts.py", "crankshaft"], check=True)
for angle in (30, 150, 200, 380, 540, 620):
    subprocess.run([py, r"C:\Users\ICT\HowoEngine1\scratch\assembly_check.py", str(angle), "moving"], check=True)
