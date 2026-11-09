
import subprocess, sys
root = r"C:\Users\ICT\Untitled project"
subprocess.run([root + r"\.venv\Scripts\ruff.exe", "format", "backend", "tests"], cwd=root)
subprocess.run([root + r"\.venv\Scripts\ruff.exe", "check", "--fix", "backend", "tests"], cwd=root)
result = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "tests/test_catalog.py", "tests/test_engine.py", "-p", "no:cacheprovider"], cwd=root)
sys.exit(result.returncode)
