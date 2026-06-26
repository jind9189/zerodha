import subprocess
import sys

stock = sys.argv[1] if len(sys.argv) > 1 else None

steps = [
    "getdata.py",
    "atr_report.py",
    "derivative_analyse.py",
    # "volume_analysis.py",
    # "breakout_scan.py",
    # "export_excel.py",
]

for script in steps:

    cmd = ["python", script]

    if stock:
        cmd.append(stock)

    print(f"\nRunning: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        capture_output=False,
        text=True
    )

    if result.returncode != 0:
        print(f"\nPipeline stopped at {script}")
        sys.exit(result.returncode)

print("\nPipeline completed successfully.")