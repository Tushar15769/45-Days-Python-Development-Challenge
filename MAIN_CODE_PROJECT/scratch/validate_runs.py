import os
import subprocess
import sys
from pathlib import Path

src_dir = Path(r"C:\Users\risha\Documents\GitHub\45-Days-Python-Development-Challenge\MAIN_CODE_PROJECT\src")

success = 0
failed = 0
failed_list = []

# Clear outputs directory first to verify clean generation
outputs_dir = Path(r"C:\Users\risha\Documents\GitHub\45-Days-Python-Development-Challenge\MAIN_CODE_PROJECT\outputs")
if outputs_dir.exists():
    for f in outputs_dir.glob("*"):
        try:
            f.unlink()
        except Exception:
            pass

for filepath in sorted(src_dir.glob("*.py")):
    print(f"Running {filepath.name}...")
    # Run the script as a subprocess in MAIN_CODE_PROJECT directory so it finds imports correctly
    res = subprocess.run(
        [sys.executable, str(filepath)],
        cwd=str(src_dir.parent),
        capture_output=True,
        text=True
    )
    if res.returncode == 0:
        print(f"  {filepath.name}: SUCCESS")
        success += 1
    else:
        print(f"  {filepath.name}: FAILED (code {res.returncode})")
        print("STDOUT:")
        print(res.stdout)
        print("STDERR:")
        print(res.stderr)
        failed += 1
        failed_list.append(filepath.name)

print("\n" + "="*40)
print(f"Validation completed. Success: {success}, Failed: {failed}")
if failed_list:
    print(f"Failed scripts: {failed_list}")
else:
    print("All scripts executed successfully!")
