# -*- coding: utf-8 -*-
"""抓 Artificial Analysis 的分项成绩（不使用它的综合指数）。

数据来自某个评测页里内嵌的 RSC 数据，页面同时包含所有模型的分项字段，
因此一次请求即可拿到全部模型 × 全部子项。
"""
import csv, os, re
from datetime import datetime

from fetchlib import get

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "aa")
URL = "https://artificialanalysis.ai/evaluations/humanitys-last-exam"

FIELDS = {
    "aa_hle": "hle",
    "aa_lcr": "lcr",
    "aa_critpt": "critpt",
    "aa_scicode": "scicode",
    "aa_omniscience": "omniscience",
    "aa_automation": "automationBenchPartialScore",
}

def main():
    page = get(URL, timeout=90)
    u = page.replace('\\"', '"')

    heads = list(re.finditer(r'"slug":"([a-z0-9\-]+)","name":"([^"]+)","shortName"', u))
    rows = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(u)
        chunk = u[m.start():end]
        rec = {"model_slug": m.group(1), "model_name": m.group(2)}
        got = False
        for sid, field in FIELDS.items():
            mm = re.search(r'"%s":([0-9.]+)' % field, chunk)
            if mm:
                rows.append({"source_id": sid, "model_slug": rec["model_slug"],
                             "model_name": rec["model_name"], "score": float(mm.group(1))})
                got = True
        if got and rec["model_slug"].startswith("deepseek"):
            print("anchor:", rec["model_slug"])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "aa_rows.csv")
    # fail-closed：页面结构一变（或整个榜下架），解析可能"成功"但一行都没有。
    # 那样会把现有的 AA 证据整片冲掉，而且退出码还是 0——周表会把它记成 fresh。
    if not rows:
        raise SystemExit("AA 页面没解析出任何分数（结构变了？），不覆盖现有数据")
    anchor = "deepseek-v4-1-flash-1017"
    if not any(r["model_slug"] == anchor for r in rows):
        # 五个 AA 分项都挂在同一个 version 上，缺了基准这一版会被整体丢弃（usable_versions）
        raise SystemExit(f"AA 数据里没有基准 slug {anchor}：整版证据会被丢弃，不覆盖现有数据")
    old = 0
    if os.path.exists(path):
        old = sum(1 for _ in csv.DictReader(open(path, encoding="utf-8-sig")))
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M")
    for r in rows:
        r["fetched_at"] = stamp          # 活榜没有版本日期，证据日期只能记抓取时刻
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["source_id", "model_slug", "model_name", "score", "fetched_at"])
        w.writeheader(); w.writerows(rows)
    print("wrote", path, len(rows), "rows")
    if old and len(rows) < old * 0.8:
        print(f"  注意：行数从 {old} 掉到 {len(rows)}（>20%），确认是榜单真的瘦了而不是抓取端漏了一半")

if __name__ == "__main__":
    main()
