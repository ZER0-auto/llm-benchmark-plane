# -*- coding: utf-8 -*-
"""每周抓一遍数据并留档（为将来的"模型末期降智"检测攒多周对照，本身不做时间结论）。

为什么留档：厂商模型发布后期常被悄悄降精度，同一模型几周后会变弱。本项目的每个榜只有一天快照，
这种漂移现在完全测不到（源级 bootstrap 只回答"换一批榜会差多少"，不回答"同一榜换个时间会差多少"）。
所以先把每周的逐模型证据存成 `data/weekly/observations.csv`，等攒够几周再谈检测——
到时候有原始多周数据，不用回头补。

做三件事：
  1. 依次跑 `scripts/fetch_*.py`（可用 --only 指定；--no-fetch 只归档现有数据）
  2. 跑 `scripts/pipeline.py`（不带 bootstrap，只要证据表）
  3. 把 `out/model_evidence.csv` 的窄表按 ISO 周写进 `data/weekly/observations.csv`
     （同一周重复跑就覆盖该周；一周一条，不追加重复行）

并打印一份**只作体检**的周环比：同 (source_id, model_key) 上周与本期的原始分差，最大跌幅前 10。
这不是结论——单日重测噪声、榜单换版都会混进来；真要判"降智"需要多周基线，那是要素齐了再做的事。

用法：
  python scripts/fetch_week.py                 # 抓全部 + 归档
  python scripts/fetch_week.py --only zhizhi aa
  python scripts/fetch_week.py --no-fetch      # 不联网，只把现有 out/ 证据归档到本周
"""
import csv, json, os, subprocess, sys
from datetime import date, datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
WEEK_DIR = os.path.join(BASE, "data", "weekly")
WEEK_CSV = os.path.join(WEEK_DIR, "observations.csv")
COLS = ["week", "fetched_at", "source_id", "model_key", "model_id", "version", "date",
        "raw", "anchor_raw", "ratio_raw", "zero_z", "ratio"]

FETCHERS = ["zhizhi", "shishan", "vals", "aa"]


def iso_week(d=None):
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def run_fetchers(only):
    ok, fail = [], []
    for name in only or FETCHERS:
        script = os.path.join(BASE, "scripts", f"fetch_{name}.py")
        if not os.path.exists(script):
            fail.append(f"{name}（脚本不存在）"); continue
        r = subprocess.run([sys.executable, script], cwd=BASE, capture_output=True, text=True)
        (ok if r.returncode == 0 else fail).append(name)
        last = [l for l in (r.stdout or "").splitlines() if l.strip()][-1:]
        print(f"  fetch_{name}: {'ok' if r.returncode == 0 else '失败'}  {last[0][:80] if last else ''}")
    return ok, fail


def archive(week, fetched_at):
    """把当前 out/model_evidence.csv 的逐模型证据写进周表；同一周重复跑则替换该周。"""
    src = os.path.join(OUT, "model_evidence.csv")
    if not os.path.exists(src):
        raise SystemExit("缺 out/model_evidence.csv：先跑 python scripts/pipeline.py")
    rows = [{c: r.get(c, "") for c in COLS} for r in csv.DictReader(open(src, encoding="utf-8-sig"))]
    for r in rows:
        r["week"], r["fetched_at"] = week, fetched_at
    old = []
    if os.path.exists(WEEK_CSV):
        old = [r for r in csv.DictReader(open(WEEK_CSV, encoding="utf-8-sig")) if r["week"] != week]
    os.makedirs(WEEK_DIR, exist_ok=True)
    with open(WEEK_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        for r in sorted(old + rows, key=lambda r: (r["week"], r["source_id"], r["model_key"])):
            w.writerow(r)
    print(f"  归档 {len(rows)} 行到 data/weekly/observations.csv"
          f"（本周 {week}，历史共 {len(old) + len(rows)} 行 / {len({r['week'] for r in old}) + 1} 周）")
    return rows, [r for r in old if r["week"] == max((x["week"] for x in old), default=None)]


def wow(rows, prev):
    """周环比（只作体检）：同一 (source_id, model_key) 的原始分差，报最大跌幅。"""
    if not prev:
        print("  没有上一周数据可比（这是第一周）；先攒着，几周后再谈降智检测。")
        return
    def key(r): return (r["source_id"], r["model_key"])
    def f(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    p = {key(r): f(r.get("raw")) for r in prev}
    d = []
    for r in rows:
        a, b = p.get(key(r)), f(r.get("raw"))
        if a is not None and b is not None:
            d.append((b - a, r["source_id"], r["model_id"], a, b))
    d.sort()
    print(f"  可比对 {len(d)} 条（上周 {sorted({r['week'] for r in prev})}）：")
    for delta, s, m, a, b in d[:10]:
        if delta < 0:
            print(f"    跌 {delta:8.2f}  {s:22} {m:26} {a:.2f} → {b:.2f}")
    print("    （这是体检不是结论：榜单换版、当日噪声、版本切换都混在里面。）")


def main():
    argv = sys.argv[1:]
    week = iso_week()
    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    print(f"周留档（{week}）：")
    if "--no-fetch" not in argv:
        only = None
        if "--only" in argv:
            i = argv.index("--only") + 1
            only = [x for x in argv[i:] if not x.startswith("--")]
        ok, fail = run_fetchers(only)
        if fail:
            print(f"  抓取失败：{'、'.join(fail)}（归档仍会做，用的是磁盘上现有的数据）")
        r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "pipeline.py")],
                           cwd=BASE, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("pipeline.py 失败，未归档：" + (r.stderr or "")[-500:])
    else:
        print("  --no-fetch：跳过抓取，只归档现有证据")
    rows, prev = archive(week, fetched_at)
    wow(rows, prev)
    print("-> data/weekly/observations.csv（不参与拟合与定档，只做将来多周对比的原料）")


if __name__ == "__main__":
    main()
