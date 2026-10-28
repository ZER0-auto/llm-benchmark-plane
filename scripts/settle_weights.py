# -*- coding: utf-8 -*-
"""权重 ↔ 管道的不动点迭代（METHOD §15）。

为什么要单独有个脚本：`calibrate_weights.py` 读的是 `out/model_evidence.csv`，而那份证据里的
比值本身依赖 `weight_cal` —— 链式榜的等效基准是用**带权的**副锚因子 P_sec / X_sec 折算出来的
（§6）。所以"跑一次 calibrate 就写回 sources.csv"留下的是不自洽的基线：权重是拿**旧权重**
生成的证据校准出来的。2026-10-26 实测这种一步之差会让基准模型 1017 的坐标落到 1.0 以下、
在 CSV 里显示成 "1.0 / M2"，并把 P_sec 从 0.9171 推到 0.9170。

本脚本交替跑 calibrate → pipeline，直到 `sources.csv` 的 `weight_cal` 不再变化，最后把收敛证据
写进 `out/settle.json`（谁跑了几轮、最后的 max|Δw| 是多少），再出图。
收敛后就是自洽基线：再跑多少次都不动（实测 max|Δw| = 0，逐轮比特级一致）。

用法：
  python scripts/settle_weights.py                # 最多 8 轮
  python scripts/settle_weights.py --max-rounds 5
退出码：0 = 到不动点；1 = 到达轮数上限仍未收敛（不重出图，交给人工判断）。
"""
import csv, json, os, subprocess, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(BASE, "sources.csv")
SETTLE = os.path.join(BASE, "out", "settle.json")
TOL = 1e-9


def weights():
    out = {}
    for r in csv.DictReader(open(SRC, encoding="utf-8-sig")):
        if r["status"] in ("active", "guarded"):
            out[r["id"]] = float(r["weight_cal"] or 0)
    return out


def run(script, grep=None):
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", script)],
                       cwd=BASE, capture_output=True, text=True)
    if r.returncode:
        sys.stdout.write(r.stdout[-2000:] + r.stderr[-2000:])
        raise SystemExit(f"{script} 失败（退出码 {r.returncode}）")
    if grep:
        for line in r.stdout.splitlines():
            if grep in line: print("   ", line)


def record(rounds, final_dw, converged, tol, n_src, start):
    """把"基线是在不动点上重算的"落成产物：只打印在 stdout 等于没说过，没人会翻日志。
    check_docs.py 拿这个文件去核对 METHOD §15 里那句"实测第 N 轮即不动"。"""
    with open(SETTLE, "w", encoding="utf-8") as f:
        json.dump({"rounds": rounds, "final_max_dw": final_dw, "tol": tol,
                   "converged": converged, "start": start, "sources": n_src},
                  f, ensure_ascii=False, indent=1)
    print(f"   -> out/settle.json（rounds={rounds}, final_max_dw={final_dw}, "
          f"converged={converged}, start={start}）")


def reset_to_prior():
    """把 weight_cal 重置成 weight_prior，让每轮都从同一个起点复算。

    默认这么做，是因为 `out/settle.json` 的 `start` 字段声称就是 `weight_prior`：
    原来它其实从**上一次留下的** weight_cal 起步（第二次跑就只需 2 轮），
    于是"第 N 轮即不动"这个数字取决于上一轮跑过什么——那就是产物在说谎。
    想从当前权重继续（省几轮、验证"再跑也不动"），加 `--keep`。
    """
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    for r in rows:
        if r["status"] in ("active", "guarded"):
            r["weight_cal"] = r["weight_prior"]
    with open(SRC, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def main():
    max_rounds = 8
    if "--max-rounds" in sys.argv:
        max_rounds = int(sys.argv[sys.argv.index("--max-rounds") + 1])
    start = "settled_weights"
    if "--keep" not in sys.argv:
        reset_to_prior()
        start = "weight_prior"
    print(f"不动点迭代（calibrate → pipeline，起点 {start}）：")
    prev, last_d = None, None
    for it in range(1, max_rounds + 1):
        run("calibrate_weights.py", grep="来源 ")
        cur = weights()
        run("pipeline.py")
        if prev is not None:
            last_d = max(abs(cur[k] - prev.get(k, -1.0)) for k in cur)
            print(f"  第 {it} 轮：max|Δw| = {last_d:.10f}")
            if last_d < TOL:
                print(f"  第 {it} 轮权重不再变化 → 已到不动点"
                      f"（{sum(1 for v in cur.values() if v > 0)} 个源有权重 / 登记 {len(cur)} 个）")
                record(it, last_d, True, TOL, len(cur), start)
                run("make_chart.py")
                return 0
        prev = cur
    print(f"  警告：{max_rounds} 轮仍未收敛（最后一轮 max|Δw| = {last_d}）；"
          f"再加大 --max-rounds 或人工看 sources.csv；本次不重出图")
    record(max_rounds, last_d, False, TOL, len(prev or {}), start)
    return 1


if __name__ == "__main__":
    sys.exit(main())
