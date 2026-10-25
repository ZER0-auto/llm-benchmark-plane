# -*- coding: utf-8 -*-
"""下载致知（llm2014/llm_benchmark）的月榜 CSV 到 data/zhizhi/"""
import json, os, urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data", "zhizhi")
API = "https://api.github.com/repos/llm2014/llm_benchmark/contents/docs/data/{sub}"
RAW = "https://raw.githubusercontent.com/llm2014/llm_benchmark/main/docs/data/{sub}/{name}"
SUBS = ["logic", "code_v3"]

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "llm-benchmark-plane"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

for sub in SUBS:
    out = os.path.join(DATA, sub)
    os.makedirs(out, exist_ok=True)
    listing = json.loads(get(API.format(sub=sub)))
    files = [x["name"] for x in listing if x["name"].endswith(".csv")]
    for name in files:
        if "-lang" in name:
            continue
        blob = get(RAW.format(sub=sub, name=name))
        open(os.path.join(out, name), "wb").write(blob)
        print(f"{sub}/{name}: {len(blob)} bytes")
print("done")
