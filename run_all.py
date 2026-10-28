# -*- coding: utf-8 -*-
"""一键跑完：pipeline（含源级 bootstrap）-> λ/α 敏感性 -> chart -> 文档数字自检

不抓数据；抓数据用 scripts/fetch_*.py。权重要重新校准用 scripts/settle_weights.py。

check_docs.py 会 FAIL 是有意为之：本仓库的约定是"文档里跟着运行变的数字必须由产物生成"，
重跑数据后文档没跟着改，就该在这里挡住（改文档，不要反向改产物去迁就文档）。
"""
import subprocess, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
STEPS = [
    ("pipeline.py", ["--bootstrap", "1000"]),   # 默认 1000 次源级重采样，约 10s
    ("sensitivity.py", []),                     # λ / α 扫描，约 1s；§18 的数字由它产出
    ("make_chart.py", []),
    ("check_docs.py", []),
]

def main():
    argv = sys.argv[1:]
    bootstrap = int(argv[argv.index("--bootstrap") + 1]) if "--bootstrap" in argv else 1000
    for script, args in STEPS:
        if script == "pipeline.py":
            args = ["--bootstrap", str(bootstrap)]
        print(f"== {script} {' '.join(args)}")
        r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", script)] + args, cwd=BASE)
        if r.returncode != 0:
            if script == "check_docs.py":
                print("   文档与产物不一致：把 check_docs.py 打印的「应为」文本抄进 README / METHOD")
            raise SystemExit(r.returncode)
    print("done -> out/model_plane.html")

if __name__ == "__main__":
    main()
