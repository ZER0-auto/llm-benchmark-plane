# -*- coding: utf-8 -*-
"""一键跑完：pipeline -> chart（不抓数据；抓数据用 scripts/fetch_*.py）"""
import subprocess, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
for step in ("pipeline.py", "make_chart.py"):
    print(f"== {step}")
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", step)], cwd=BASE)
    if r.returncode != 0:
        raise SystemExit(r.returncode)
print("done -> out/model_plane.html")
