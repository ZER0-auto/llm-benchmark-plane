# -*- coding: utf-8 -*-
"""一键跑完：pipeline -> chart -> 文档数字自检（不抓数据；抓数据用 scripts/fetch_*.py）

check_docs.py 会 FAIL 是有意为之：本仓库的约定是"文档里跟着运行变的数字必须由产物生成"，
重跑数据后文档没跟着改，就该在这里挡住（改文档，不要反向改产物去迁就文档）。
"""
import subprocess, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
for step in ("pipeline.py", "make_chart.py", "check_docs.py"):
    print(f"== {step}")
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", step)], cwd=BASE)
    if r.returncode != 0:
        if step == "check_docs.py":
            print("   文档与产物不一致：把 check_docs.py 打印的「应为」文本抄进 README / METHOD")
        raise SystemExit(r.returncode)
print("done -> out/model_plane.html")
