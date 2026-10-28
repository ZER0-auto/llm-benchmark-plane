# -*- coding: utf-8 -*-
"""抓取 Vals 榜单：从 astro-island props 解出逐模型 accuracy / harness"""
import csv, html, json, os, re

from fetchlib import get

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "vals", "vals_rows.csv")

SLUGS = ["vibe-code", "code-migration-v1-1", "terminal-bench-4",
         "skillsbench", "programbench", "swebench", "ioi",
         "proof_bench", "mysterymechanism"] + [
    # 2026-10-25 起接入：扫描过锚点（含 1017 或次新 Flash）的其余 Vals 榜
    "sage", "legal_bench", "medcode", "medscribe", "emb-v1-1", "fabv2-1",
    "legal_research", "tax_agent_bench", "cyber", "srebench",
    "public-benefits-bench", "hlab", "terminal-bench-science",
    "swebench-multimodal", "biomysterybench",
]

def dec(o):
    if isinstance(o, list):
        if len(o) == 2 and isinstance(o[0], int) and o[0] in (0, 1, 2, 3):
            return dec(o[1])
        return [dec(x) for x in o]
    if isinstance(o, dict):
        return {k: dec(v) for k, v in o.items()}
    return o

def fetch(slug):
    return get(f"https://www.vals.ai/benchmarks/{slug}", timeout=60)

def parse(page):
    for tag in re.findall(r"<astro-island[^>]*>", page):
        if "ScatterGraph" not in tag:
            continue
        m = re.search(r'props="([^"]*)"', tag)
        if not m:
            continue
        d = dec(json.loads(html.unescape(m.group(1))))
        bv = d.get("benchmarkView") or {}
        meta = bv.get("metadata") or {}
        rows = (bv.get("tasks") or {}).get("overall") or {}
        return meta, rows
    return None, None

FIELDS_COLS = ["benchmark", "slug", "dataset_type", "updated", "model",
               "accuracy", "harness", "stderr", "cost_per_test", "latency"]
allrows, failed = [], []
for slug in SLUGS:
    meta, rows = parse(fetch(slug))
    if not meta:
        print(f"{slug:22} PARSE-FAIL")
        failed.append(slug)
        continue
    print(f"{slug:22} {meta.get('benchmark','?'):34} models={len(rows):4} "
          f"type={meta.get('dataset_type')} updated={meta.get('updated')}")
    for mid, v in rows.items():
        allrows.append({"benchmark": meta.get("benchmark"), "slug": slug,
                        "dataset_type": meta.get("dataset_type"),
                        "updated": meta.get("updated"), "model": mid,
                        "accuracy": v.get("accuracy"), "harness": v.get("harness"),
                        "stderr": v.get("stderr"), "cost_per_test": v.get("cost_per_test"),
                        "latency": v.get("latency")})

# 解析失败的榜要**保住旧行**：整表是重写的，失败的一页直接消失就等于把这个榜的证据删了，
# 而流水线只会在下轮把该源当成"榜上没这些模型"，不会报错。所以先补回旧行，再非零退出
# （好让 fetch_week 把它标 stale：这一周不是完整观测）。
if failed and os.path.exists(OUT):
    keep = [r for r in csv.DictReader(open(OUT, encoding="utf-8-sig")) if r["slug"] in failed]
    print(f"  警告：{len(failed)} 个榜解析失败（{'、'.join(failed)}），沿用旧行 {len(keep)} 条")
    allrows.extend({c: r.get(c, "") for c in FIELDS_COLS} for r in keep)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS_COLS)
    w.writeheader(); w.writerows(allrows)
print("rows", len(allrows), "->", OUT)
if failed:
    raise SystemExit(f"{len(failed)} 个榜解析失败：{'、'.join(failed)}（旧行已保留，但本周不算完整抓取）")
