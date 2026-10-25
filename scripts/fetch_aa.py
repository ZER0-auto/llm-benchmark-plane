# -*- coding: utf-8 -*-
"""抓 Artificial Analysis 的分项成绩（不使用它的综合指数）。

数据来自某个评测页里内嵌的 RSC 数据，页面同时包含所有模型的分项字段，
因此一次请求即可拿到全部模型 × 全部子项。
"""
import csv, os, re, urllib.request

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
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    page = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "ignore")
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
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["source_id", "model_slug", "model_name", "score"])
        w.writeheader(); w.writerows(rows)
    print("wrote", path, len(rows), "rows")

if __name__ == "__main__":
    main()
