# -*- coding: utf-8 -*-
"""抓取屎山挑战赛 /heroes/ 页面里内嵌的 assessment-data JSON"""
import html, json, os, re

from fetchlib import get

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "shishan", "assessment_data.json")
URL = "https://shishan.hellomeng.com/heroes/"

page = get(URL, timeout=60)

m = re.search(r'<script[^>]*id="assessment-data"[^>]*>(.*?)</script>', page, re.S)
if not m:
    raise SystemExit("未找到 assessment-data")

data = json.loads(html.unescape(m.group(1)))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(data, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"wrote {OUT}: {len(data)} 个模型")
