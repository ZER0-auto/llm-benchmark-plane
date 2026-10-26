# -*- coding: utf-8 -*-
"""为 bl_map.py 生成候选映射（只打印，不写文件、不改 bl_map.py）。

对 data/bl/bl_rows.csv 里每个 model_slug，用三条规则猜项目 key：
  direct : norm(display_name) 命中项目既有 key 集合
  drop1  : 去掉 display_name 第一个词再 norm（处理 "Claude Opus 5.5"→opus5.5）
  suffix : slug 去横线后以某已知 key 结尾（key 长度 ≥6，防误匹配）
三条都命不中的不映射（宁缺毋滥）。冲突/多解会标出，必须人工裁决。

用法：
  python scripts/bl_map_candidates.py            # 打印全部 slug 的候选与冲突
  python scripts/bl_map_candidates.py > draft.txt
审定后手工写进 scripts/bl_map.py，本脚本不落盘。
"""
import csv, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import pipeline as P

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "data", "bl", "bl_rows.csv")

# ---- 项目既有 key 集合（与 pipeline 的五个 Loader 同源：logic / code_v3 / vals / aa / shishan）----
known = {}
def add(rows):
    for r in rows:
        known.setdefault(r["key"], r.get("name", ""))
add(P.load_logic())
add(P.load_code_v3())
for _s, rs in P.load_vals().items(): add(rs)
for _s, rs in P.load_aa().items(): add(rs)
_, x2 = P.load_shishan()
for k in x2: known.setdefault(k, "")

def drop1(name):
    t = name.strip().split()
    return " ".join(t[1:]) if len(t) > 1 else name

slugs = {}
for r in csv.DictReader(open(ROWS, encoding="utf-8-sig")):
    slugs.setdefault(r["model_slug"], set()).add(r["model_name"])

PAREN = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")
def norm_local(s):
    s = PAREN.sub("", s.strip())
    s = re.sub(r"[\s\-_·]+", "", s).lower()
    return P.ALIAS.get(s, s)

draft, review = {}, []
for slug in sorted(slugs):
    names = sorted(slugs[slug])
    base = names[0]
    cands = {}
    k = P.norm(base)
    if k in known: cands["direct"] = k
    k2 = norm_local(drop1(base))
    if k2 in known and k2 != k: cands["drop1"] = k2
    sn = re.sub(r"-", "", slug).lower()
    for kk in known:
        if len(kk) >= 6 and sn.endswith(kk):
            cands.setdefault("suffix", kk)
            break
    if not cands:
        continue
    uniq = set(cands.values())
    tag = "OK " if len(uniq) == 1 else "冲突"
    key = sorted(uniq)[0] if len(uniq) == 1 else None
    review.append((tag, slug, " / ".join(names), cands, key))
    if key and len(uniq) == 1:
        draft[slug] = key

print(f"# 项目既有 key {len(known)} 个；slugs {len(slugs)} 个，有候选 {len(review)} 个，唯一解 {len(draft)} 个")
for tag, slug, names, cands, key in review:
    print(f"[{tag}] {slug}")
    print(f"     名字: {names}")
    print("     候选: " + ", ".join(f"{m}:{v}" for m, v in cands.items()))
print("\n# ---- 唯一解草稿（审定后再粘进 bl_map.BL_MAP）----")
for s in sorted(draft):
    print(f'    "{s}": "{draft[s]}",')
