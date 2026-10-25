# -*- coding: utf-8 -*-
"""抓取 Vals 榜单：从 astro-island props 解出逐模型 accuracy / harness"""
import csv, html, json, os, re, urllib.request

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
    url = f"https://www.vals.ai/benchmarks/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")

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

allrows = []
for slug in SLUGS:
    meta, rows = parse(fetch(slug))
    if not meta:
        print(f"{slug:22} PARSE-FAIL")
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

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
    w.writeheader(); w.writerows(allrows)
print("rows", len(allrows), "->", OUT)
