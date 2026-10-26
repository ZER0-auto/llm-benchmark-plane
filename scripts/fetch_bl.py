# -*- coding: utf-8 -*-
"""抓 BenchmarkList（benchmarklist.com）候选 benchmark 成绩（v1）。

数据走公开 JSON API：/api/v1/results/{benchmark_id}.json（全量历史快照）。
每个快照含全部参评模型行：model_id / display_name / score / raw_score /
configuration（推理档、harness）/ self_reported / source_url / sampled_at。

输出 data/bl/bl_rows.csv（列与 aa_rows.csv 对齐并附加工况字段）：
  source_id, model_slug, model_name, raw_name, score, version, snapshot_id, date,
  self_reported, source_url, rank
snapshot_id = "<benchmark>@<sampled_at>#<序号>"：同一天可能有两份快照（博客改版、
厂商与第三方同日各发一份），version 只到天、不能当唯一键。

映射到本项目 model_key 的动作在 scripts/bl_compare.py 的 key_of() 里完成
（经 bl_map.BL_SKIP / BL_OVERRIDE / BL_MAP）：本脚本只忠实抓取，不猜映射。

候选清单来自 2026-10-25 评估报告的 A/B 两类（30 个新源）：
  A 类 16 个：主锚 1017 有分，直接比值
  B 类 14 个：仅次新锚有分，走链式换算
Elo/指数/加速比类（GDPval-AA、AA-Briefcase、AIIQ 等 9 个）指标尺度不兼容，
不进本清单；同族重复源（TB4、HLE 全量、AA-LCR 等 11 个）项目已有，不进。

v2 变更（站点延迟 6~75s+ 波动大，单线程串行不可接受）：
  - 4 线程并发抓取（瓶颈是网络等待，不是 CPU）
  - 每个目标抓完立即全量重写 CSV（增量落盘，杀死不丢已完成进度）
  - 已在 CSV 里的 source_id 默认跳过（--force 强制重抓）
  - python -u 无缓冲进度打印
"""
import csv, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "bl")
API = "https://benchmarklist.com/api/v1/results/{}.json"
PAGE = "https://benchmarklist.com/benchmarks/{}/"
WORKERS = 4
TRIES = 3
TIMEOUT = 90

TARGETS = [
    # A 类：直接比值（1017 在榜）
    "gpqa_diamond_epoch", "mmmu_pro", "agents_last_exam", "deepswe_1_1",
    "nl2repo", "swe_marathon", "programbench", "officeqa_pro", "hle_tools",
    "hle_text_only", "babyvision", "zerobench", "charxiv_r", "chartography",
    "benchcad_vision2code_1000", "perceptionbench",
    # B 类：链式换算（仅次新锚在榜）
    "cwe_bench_v1", "cybergym", "terminal_bench_science", "matharena_apex",
    "arxivmath", "browsecomp", "multichallenge", "jobbench", "bankertoolbench",
    "draco", "posttrainbench", "sweatlas_codebase_qna", "terminal_bench_3",
    "chartqa_pro",
]

FIELDS = ["source_id", "model_slug", "model_name", "raw_name", "score",
          "version", "snapshot_id", "date", "self_reported", "source_url", "rank"]
NUM = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def fetch(bid):
    """带重试的 JSON 抓取，返回 (数据, 耗时, 失败原因)。

    404 与网络失败必须分开：混在一起打印成"无数据"，就没法回答"这个候选榜
    到底是不存在，还是今天没抓到"——文档里的"N 个有数据"因此无从验证。
    """
    url = API.format(bid)
    last = None
    for i in range(TRIES):
        t0 = time.time()
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8")), time.time() - t0, ""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, 0.0, "404"
            last = f"HTTP {e.code}"
            time.sleep(5 * (i + 1))
        except Exception as e:
            last = str(e) or type(e).__name__
            time.sleep(5 * (i + 1))
    print(f"  {bid}: 抓取失败（{last}），跳过", flush=True)
    return None, 0.0, f"网络失败：{last}"


def parse_score(row):
    """raw_score 优先（保留原榜刻度，取前导数值）；失败回退 normalized score。"""
    raw = (row.get("raw_score") or "").strip()
    m = NUM.match(raw)
    if m:
        return float(m.group(1))
    v = row.get("score")
    return float(v) if isinstance(v, (int, float)) else None


def cfg_label(row):
    c = row.get("configuration") or {}
    parts = [str(c[k]) for k in ("agent_harness", "reasoning_effort") if c.get(k)]
    return "/".join(parts)


def rows_of(bid, d):
    out = []
    for idx, snap in enumerate(d.get("snapshots", [])):
        ver = (snap.get("sampled_at") or "")[:10]
        src = snap.get("source_url") or PAGE.format(bid)
        # 同一天可能有多份快照（同一篇博客改版、或厂商与第三方同日各发一份）。
        # version 只能到天，不能当唯一键，必须带快照序号，否则下游会把两份表
        # 按 (version, model) 合并且取 max，等于把两次读数里高的那次当成成绩。
        sid = f"{bid}@{ver}#{idx}"
        for r in snap.get("results", []):
            v = parse_score(r)
            if v is None:
                continue
            mid = r.get("model_id") or ""
            if not mid:
                continue
            cfg = cfg_label(r)
            name = r.get("display_name") or mid
            raw_name = f"{name} [{cfg}]" if cfg else name
            out.append({
                "source_id": bid, "model_slug": mid, "model_name": name,
                "raw_name": raw_name, "score": v,
                "version": ver, "snapshot_id": sid, "date": ver,
                "self_reported": "1" if r.get("self_reported") else "0",
                "source_url": src, "rank": r.get("rank", ""),
            })
    return out


def write_status(ok, missing, failed):
    """记录本轮每个目标的结果，覆盖式合并（一个源只留最近一次状态）。

    抓不到 ≠ 不存在：这个文件是"N 个候选里 M 个有数据"这类说法的唯一凭据。
    """
    path = os.path.join(OUT, "fetch_status.json")
    st = {}
    if os.path.exists(path):
        try:
            st = json.load(open(path, encoding="utf-8"))
        except (ValueError, OSError):
            st = {}
    day = time.strftime("%Y-%m-%d")
    for b in ok:
        st[b] = {"status": "ok", "at": day}
    for b, e in missing.items():
        st[b] = {"status": "404", "reason": e, "at": day}
    for b, e in failed.items():
        st[b] = {"status": "failed", "reason": e, "at": day}
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1, sort_keys=True)


def write_csv(rows):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "bl_rows.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main():
    global TIMEOUT
    force = "--force" in sys.argv
    workers = WORKERS
    for i, a in enumerate(sys.argv):
        if a == "--workers" and i + 1 < len(sys.argv):
            workers = max(1, int(sys.argv[i + 1]))
        if a == "--timeout" and i + 1 < len(sys.argv):
            TIMEOUT = max(10, int(sys.argv[i + 1]))
    done = set()
    rows = []
    path = os.path.join(OUT, "bl_rows.csv")
    if os.path.exists(path) and not force:
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        # 旧版 CSV 没有 snapshot_id 列：那时同一天的两份快照会被下游按 max 合并，
        # 数据本身已不自洽。这种文件不能当作"已完成"续传，否则快照号永远补不出来。
        if rows and "snapshot_id" not in rows[0]:
            print("续传：CSV 是 snapshot_id 上线前的旧格式，全量重抓", flush=True)
            rows, done = [], set()
        else:
            done = {r["source_id"] for r in rows}
            if done:
                print(f"续传：CSV 已有 {len(done)} 个源 {len(rows)} 行，跳过（--force 重抓）", flush=True)
    todo = [b for b in TARGETS if b not in done]
    if not todo:
        print("全部目标已在 CSV，无事可做", flush=True)
        return
    ok, missing, failed = [], {}, {}
    print(f"待抓 {len(todo)} 个目标，{workers} 线程并发，超时 {TIMEOUT}s×{TRIES} 次", flush=True)
    t_all = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch, b): b for b in todo}
        for fut in as_completed(futs):
            bid = futs[fut]
            d, dt, err = fut.result()
            if not d:
                if err == "404":
                    missing[bid] = "404（候选 id 不存在）"
                    print(f"  {bid}: 404，候选 id 不存在", flush=True)
                else:
                    failed[bid] = err
                    print(f"  {bid}: {err}，本轮放弃（下次运行自动续抓）", flush=True)
                continue
            rs = rows_of(bid, d)
            rows.extend(rs)
            write_csv(rows)     # 增量落盘：每个目标完成即重写
            ok.append(bid)
            snaps = len(d.get("snapshots", []))
            print(f"  ✓ {bid}: {len(rs)} 行 / {snaps} 快照（{dt:.0f}s）", flush=True)
    write_status(ok, missing, failed)
    seen = {}
    for r in rows:
        seen.setdefault(r["model_slug"], r["model_name"])
    print(f"\n完成，用时 {time.time()-t_all:.0f}s；{path} 共 {len(rows)} 行，"
          f"{len(seen)} 个 distinct model_slug", flush=True)
    print(f"本轮结果：成功 {len(ok)} / 404 {len(missing)} / 网络失败 {len(failed)}"
          f"（明细见 data/bl/fetch_status.json）", flush=True)
    if failed:
        print("  网络失败的源：" + "、".join(sorted(failed)), flush=True)
    print("模型清单（供 bl_map.BL_MAP 对照）：", flush=True)
    for mid in sorted(seen):
        print(f"  {mid} | {seen[mid]}", flush=True)


if __name__ == "__main__":
    main()
