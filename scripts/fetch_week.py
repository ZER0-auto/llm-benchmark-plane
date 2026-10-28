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

**每一行都带 `fetch_status`**（`fresh` / `stale`）：抓取成功的那几个源的这一周是观测，
抓失败或压根没抓的源这一周只是把磁盘上的旧数据又抄了一遍——两者的区别必须留在数据里，
否则"这周没抓到"会被下游读成"这周分数没变"，正好是降智检测最怕的假阴性。
`stale` 行的 `fetched_at` 留空（写本周时间等于谎报抓取时刻）。

并打印一份**只作体检**的周环比：同 (source_id, model_key) 上周与本期的原始分差，最大跌幅前 10
（只比两边都是 fresh 的行）。这不是结论——单日重测噪声、榜单换版都会混进来；
真要判"降智"需要多周基线，那是要素齐了再做的事。

用法：
  python scripts/fetch_week.py                 # 抓全部 + 归档
  python scripts/fetch_week.py --only zhizhi aa
  python scripts/fetch_week.py --no-fetch      # 不联网，只把现有 out/ 证据归档到本周（全部标 stale）
"""
import csv, os, subprocess, sys
from datetime import date, datetime
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "out")
WEEK_DIR = os.path.join(BASE, "data", "weekly")
WEEK_CSV = os.path.join(WEEK_DIR, "observations.csv")
COLS = ["week", "fetched_at", "source_id", "model_key", "model_id", "version", "date",
        "raw", "anchor_raw", "ratio_raw", "zero_z", "ratio", "fetch_status"]
FRESH, STALE = "fresh", "stale"

FETCHERS = ["zhizhi", "shishan", "vals", "aa"]
# 源 → 抓取脚本：按 sources.csv 登记的主机名判定，不维护第二份 id 清单
# （id 清单会和 sources.csv 漂移；主机名是登记表里本来就有的字段）
HOST_FETCHER = {
    "llm2014.github.io": "zhizhi",
    "shishan.hellomeng.com": "shishan",
    "vals.ai": "vals", "www.vals.ai": "vals",
    "artificialanalysis.ai": "aa", "www.artificialanalysis.ai": "aa",
}


def iso_week(d=None):
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def fetcher_of_source():
    """{source_id: fetcher}；判不出来的是 None（那类源只能标 stale，并打一条告警）。"""
    out = {}
    p = os.path.join(BASE, "sources.csv")
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if r["status"] not in ("active", "guarded"):
            continue
        out[r["id"]] = HOST_FETCHER.get(urlparse(r["url"]).netloc)
    return out


def run_fetchers(only):
    ok, fail = [], []
    for name in only or FETCHERS:
        script = os.path.join(BASE, "scripts", f"fetch_{name}.py")
        if not os.path.exists(script):
            fail.append(f"{name}（脚本不存在）"); continue
        r = subprocess.run([sys.executable, script], cwd=BASE, capture_output=True, text=True)
        (ok if r.returncode == 0 else fail).append(name)
        tail = [l for l in (r.stdout or "").splitlines() if l.strip()][-2:]
        detail = " | ".join(x[:60] for x in tail)
        if r.returncode:
            # 失败时把**为什么**打出来。上一版只打最后一行 stdout，致知的 TLS 超时因此
            # 显示成"失败  "（后面空白），只能另开一次手工调试才知道原因
            err = [(l for l in (r.stderr or "").splitlines() if l.strip())]
            err = list(err[0]) if err else []
            detail = (err[-1][:120] if err else (detail or "（无输出）"))
        print(f"  fetch_{name}: {'ok  ' if r.returncode == 0 else '失败'}  {detail}")
    return ok, fail


def archive(week, fetched_at, fresh):
    """把当前 out/model_evidence.csv 的逐模型证据写进周表；同一周重复跑则替换该周。

    `fresh` 是本周**真正抓成功**的抓取脚本集合；不在里面的源一律标 stale。
    """
    src = os.path.join(OUT, "model_evidence.csv")
    if not os.path.exists(src):
        raise SystemExit("缺 out/model_evidence.csv：先跑 python scripts/pipeline.py")
    rows = [{c: r.get(c, "") for c in COLS} for r in csv.DictReader(open(src, encoding="utf-8-sig"))]
    fmap = fetcher_of_source()
    unknown = sorted({r["source_id"] for r in rows} - set(fmap))
    if unknown:
        print(f"  警告：{len(unknown)} 个 source_id 不在 sources.csv 里，只能标 stale：{'、'.join(unknown)}")
    nofetcher = sorted({s for s, f in fmap.items() if f is None and s in {r['source_id'] for r in rows}})
    if nofetcher:
        print(f"  警告：{len(nofetcher)} 个源在 sources.csv 里查不到对应的抓取主机，只能标 stale：{'、'.join(nofetcher)}")
    for r in rows:
        ok = fmap.get(r["source_id"]) in fresh
        r["fetch_status"] = FRESH if ok else STALE
        r["fetched_at"] = fetched_at if ok else ""      # stale 的行不写本周时间戳
        r["week"] = week
    old = []
    if os.path.exists(WEEK_CSV):
        old = [r for r in csv.DictReader(open(WEEK_CSV, encoding="utf-8-sig")) if r["week"] != week]
    os.makedirs(WEEK_DIR, exist_ok=True)
    with open(WEEK_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        for r in sorted(old + rows, key=lambda r: (r["week"], r["source_id"], r["model_key"])):
            w.writerow({c: r.get(c, "") for c in COLS})
    nf = sum(1 for r in rows if r["fetch_status"] == FRESH)
    print(f"  归档 {len(rows)} 行到 data/weekly/observations.csv"
          f"（本周 {week}，其中 fresh {nf} / stale {len(rows) - nf}；"
          f"历史共 {len(old) + len(rows)} 行 / {len({r['week'] for r in old}) + 1} 周）")
    return rows, [r for r in old if r["week"] == max((x["week"] for x in old), default=None)]


def wow(rows, prev):
    """周环比（只作体检）：同一 (source_id, model_key) 的原始分差，报最大跌幅。

    只比两边都是 fresh 的行——stale 行是同一批旧数据抄了两遍，差恒为 0，
    混进来会把"这周没抓到"粉饰成"没有变化"。
    """
    if not prev:
        print("  没有上一周数据可比（这是第一周）；先攒着，几周后再谈降智检测。")
        return
    def key(r): return (r["source_id"], r["model_key"])
    def f(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    p = {key(r): f(r.get("raw")) for r in prev if r.get("fetch_status") == FRESH}
    d, skipped = [], 0
    for r in rows:
        if r.get("fetch_status") != FRESH:
            continue
        a, b = p.get(key(r)), f(r.get("raw"))
        if a is None:
            skipped += 1; continue
        if b is not None:
            d.append((b - a, r["source_id"], r["model_id"], a, b))
    d.sort()
    print(f"  可比对 {len(d)} 条（上周 {sorted({r['week'] for r in prev})}；"
          f"因任一侧是 stale 而跳过 {skipped} 条）：")
    for delta, s, m, a, b in d[:10]:
        if delta < 0:
            print(f"    跌 {delta:8.2f}  {s:22} {m:26} {a:.2f} → {b:.2f}")
    print("    （这是体检不是结论：榜单换版、当日噪声、版本切换都混在里面。）")


def main():
    argv = sys.argv[1:]
    week = iso_week()
    fetched_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    print(f"周留档（{week}）：")
    fresh = set()
    if "--no-fetch" not in argv:
        only = None
        if "--only" in argv:
            i = argv.index("--only") + 1
            only = [x for x in argv[i:] if not x.startswith("--")]
        ok, fail = run_fetchers(only)
        fresh = set(ok)
        if fail:
            print(f"  抓取失败：{'、'.join(fail)}（这些源本周的数据仍是磁盘上的旧数据，"
                  f"归档时标 stale；不抓的源同理）")
        r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "pipeline.py")],
                           cwd=BASE, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("pipeline.py 失败，未归档：" + (r.stderr or "")[-500:])
    else:
        print("  --no-fetch：跳过抓取，只归档现有证据（全部标 stale：这不是本周观测）")
    rows, prev = archive(week, fetched_at, fresh)
    wow(rows, prev)
    print("-> data/weekly/observations.csv（不参与拟合与定档，只做将来多周对比的原料）")


if __name__ == "__main__":
    main()
