# -*- coding: utf-8 -*-
"""LLM Benchmark Plane — 归一化管道（严格版本内比较）

规则：
  1. 每个来源按“版本”切分（致知=月榜，Vals=快照，屎山=阶梯榜整块）
  2. 一个版本只有在包含基准模型 DeepSeek V4.1 Flash 1017 时才可用，否则整版丢弃
  3. 缺基准的榜用次新 Flash 作链式锚点换算
  4. 同一版本内只做一次比值：score / anchor_score_in_that_version
  5. 不做跨版本取中位、不做跨版本桥接
"""
import csv, json, re, math, os
from collections import Counter
from vals_map import VALS_MAP

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

def months(sub):
    d = os.path.join(DATA, "zhizhi", sub)
    if not os.path.isdir(d): return []
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".csv"))

LOGIC_MONTHS = months("logic")
CODE_MONTHS = months("code_v3")

PAREN = re.compile(r"\s*[\(（][^)）]*[\)）]\s*$")
# 官方 API 的 deepseek-flash 是滚动别名（2026-09-10 -> V4.1 Flash，2026-10-17 -> 1017）；
# 经核实，屎山 2026-10-19 场测的是 V4.1 Flash，映射到次新 Flash 走链式基准。
ALIAS = {"混元3.0": "hy3", "deepseekflash": "deepseekv4.1flash"}
ANCHOR_KEY = "deepseekv4.1flash1017"
MIN_MODELS_PER_VERSION = 5      # 版本内至少这么多个模型才可用

SOURCES = {
    "logic":               ("致知 logic", "P", 0.50, "A"),
    "proof_bench":         ("Vals ProofBench", "P", 0.30, "A"),
    "mysterymechanism":    ("Vals MysteryMechanism", "P", 0.20, "A"),
    "shishan":             ("屎山挑战赛", "X", 0.32, "A"),
    "code_v3":             ("致知 code_v3", "X", 0.28, "A-"),
    "vibe-code":           ("Vals Vibe Code", "X", 0.14, "A"),
    "code-migration-v1-1": ("Vals Code Migration", "X", 0.09, "A"),
    "terminal-bench-4":    ("Terminal-Bench 4", "X", 0.04, "B"),
    "skillsbench":         ("SkillsBench", "X", 0.04, "B"),
    "ioi":                 ("IOI", "X", 0.01, "B"),
}
SECONDARY_KEY = "deepseekv4.1flash"   # 与基准不同的模型，但可作链式锚点

def norm(name):
    s = PAREN.sub("", name.strip())
    s = re.sub(r"[\s\-_·]+", "", s).lower()
    return ALIAS.get(s, s)

def display(name):
    return PAREN.sub("", name.strip())

# ---------- 原始数据（带版本号） ----------
def load_logic():
    out = []
    for m in LOGIC_MONTHS:
        p = os.path.join(DATA, "zhizhi", "logic", f"{m}.csv")
        if not os.path.exists(p): continue
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if "~Estimated" in r["模型"]: continue
            try: v = float(r["中位分数"])
            except (TypeError, ValueError): continue
            out.append({"key": norm(r["模型"]), "name": display(r["模型"]),
                        "version": m, "date": m, "value": v})
    return out

TASKS = ["Simple Model(H)", "iOS+Server(I)", "Animation(J)", "Data Process(K)",
         "Metal(L)", "Science(M)", "Rust App(N)"]
GMAP = {"A+": 1.00, "A": 0.85, "B+": 0.70, "B": 0.55, "C+": 0.35, "C": 0.20, "D+": 0.10, "D": 0.00}

def grade(cell):
    c = (cell or "").strip()
    if c in ("Skip", "Pending", "", "—", "-"): return None
    if c == "Failed": return 0.0
    if c.startswith("Perfect") or c == "Pass": return 1.0
    m = re.match(r"^\d*\s*/\s*([A-D][+]?)", c)
    return GMAP.get(m.group(1), 0.0) if m else 0.0

def load_code_v3():
    out = []
    for m in CODE_MONTHS:
        p = os.path.join(DATA, "zhizhi", "code_v3", f"{m}.csv")
        if not os.path.exists(p): continue
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            pts, judged = 0.0, 0
            for t in TASKS:
                v = grade(r.get(t, ""))
                if v is None: continue
                judged += 1; pts += v
            if judged < 5: continue
            out.append({"key": norm(r["Model"]), "name": display(r["Model"]),
                        "version": m, "date": m, "value": 100.0 * pts / judged})
    return out

def load_shishan():
    d = json.load(open(os.path.join(DATA, "shishan", "assessment_data.json"), encoding="utf-8"))
    obs, models, items = [], [], set()
    for slug, v in d.items():
        if v.get("disputed"): continue
        models.append(v["name"])
        for t in v["topics"]:
            obs.append((v["name"], t["id"], 1 if t["verdicts"].startswith("W") else 0))
            items.add(t["id"])
    th = {m: 0.0 for m in models}; b = {i: 0.0 for i in items}
    sig = lambda z: 1 / (1 + math.exp(-z))
    for _ in range(3000):
        gt = {m: 0.0 for m in models}; gb = {i: 0.0 for i in items}
        for m, i, y in obs:
            r = y - sig(th[m] - b[i]); gt[m] += r; gb[i] -= r
        for m in models: th[m] += 0.08 * (gt[m] - 0.6 * th[m])
        for i in items:  b[i]  += 0.08 * (gb[i] - 0.6 * b[i])
    shift = sum(b.values()) / len(b)
    out, x2 = [], {}
    for slug, v in d.items():
        if v.get("disputed"): continue
        T = {t["id"]: t for t in v["topics"]}
        x2[norm(v["name"])] = 100.0 * sum(1 for t in T.values() if "W" in t["verdicts"] and t["score"] > 0) / len(T)
        out.append({"key": norm(v["name"]), "name": v["name"],
                    "version": "board", "date": (v.get("date") or "")[:10],
                    "value": 100.0 * sig(th[v["name"]] - shift)})
    return out, x2

def load_vals():
    rows = list(csv.DictReader(open(os.path.join(DATA, "vals", "vals_rows.csv"), encoding="utf-8-sig")))
    agg = {}
    for r in rows:
        name = VALS_MAP.get(r["model"])
        if not name: continue
        try: acc = float(r["accuracy"])
        except (TypeError, ValueError): continue
        a = agg.setdefault(r["slug"], {})
        cur = a.get(norm(name))
        if cur is None or acc > cur["value"]:
            a[norm(name)] = {"key": norm(name), "name": name,
                             "version": r.get("updated", ""), "date": (r.get("updated") or "")[:10], "value": acc}
    return {s: list(v.values()) for s, v in agg.items()}

# ---------- 版本筛选 ----------
def usable_versions(rows, label):
    by_ver = {}
    for r in rows: by_ver.setdefault(r["version"], []).append(r)
    keep = {}
    for ver, rs in sorted(by_ver.items()):
        has_anchor = any(r["key"] == ANCHOR_KEY for r in rs)
        n = len(rs)
        if has_anchor and n >= MIN_MODELS_PER_VERSION:
            keep[ver] = rs
            print(f"  {label} {ver}: {n} 个模型，含基准 OK")
        else:
            why = "缺基准" if not has_anchor else f"仅 {n} 个模型"
            print(f"  {label} {ver}: {n} 个模型，{why}，丢弃")
    return keep

ORDER = ["logic", "proof_bench", "mysterymechanism", "shishan", "code_v3",
         "vibe-code", "code-migration-v1-1", "terminal-bench-4", "skillsbench", "ioi"]

def main():
    logic_rows = load_logic()
    code_rows = load_code_v3()
    shi_rows, x2map = load_shishan()
    vals = load_vals()

    print("版本检查：")
    logic_ok = usable_versions(logic_rows, "logic")
    code_ok = usable_versions(code_rows, "code_v3")

    # 屎山整块算一个版本：含主基准可直接用，只含副锚点则走链式
    shi_ok, shi_chained = {}, {}
    shi_by_ver = {}
    for r in shi_rows: shi_by_ver.setdefault(r["version"], []).append(r)
    for ver, rs in shi_by_ver.items():
        if any(r["key"] == ANCHOR_KEY for r in rs) and len(rs) >= MIN_MODELS_PER_VERSION:
            shi_ok[ver] = rs
            print(f"  shishan {ver}: {len(rs)} 个模型，含基准 OK")
        elif any(r["key"] == SECONDARY_KEY for r in rs) and len(rs) >= MIN_MODELS_PER_VERSION:
            shi_chained[ver] = rs
            print(f"  shishan {ver}: {len(rs)} 个模型，含副锚点 DeepSeek V4.1 Flash -> 链式换算")
        else:
            print(f"  shishan {ver}: {len(rs)} 个模型，无可用锚点，丢弃")

    vals_ok, vals_chained = {}, {}
    for slug, rows in vals.items():
        if slug not in SOURCES: continue
        if any(r["key"] == ANCHOR_KEY for r in rows):
            vals_ok[slug] = rows
            print(f"  {slug}: {len(rows)} 个模型，含基准 OK")
        elif any(r["key"] == SECONDARY_KEY for r in rows):
            vals_chained[slug] = rows
            print(f"  {slug}: {len(rows)} 个模型，含副锚点 DeepSeek V4.1 Flash -> 链式换算")
        else:
            print(f"  {slug}: {len(rows)} 个模型，无可用锚点，丢弃")

    # 每个模型只取最新可用版本
    def latest(by_ver):
        best = {}
        for ver, rs in by_ver.items():
            for r in rs:
                if r["key"] not in best or ver > best[r["key"]]["version"]:
                    best[r["key"]] = r
        return best

    per_source = {}
    per_source["logic"] = latest(logic_ok)
    per_source["code_v3"] = latest(code_ok)
    per_source["shishan"] = latest(shi_ok)
    for slug, rows in vals_ok.items():
        per_source[slug] = {r["key"]: r for r in rows}

    # 每个版本内单独算基准分
    anchor_of = {}
    for s, rows in per_source.items():
        vers = {r["version"] for r in rows.values()}
        for ver in vers:
            a = [r["value"] for r in rows.values() if r["version"] == ver and r["key"] == ANCHOR_KEY]
            if a: anchor_of[(s, ver)] = a[0]

    # 副锚点自身在各轴上的相对能力（来自含主锚点的源）
    sec = {}
    for ax in ("P", "X"):
        vals_ax = []
        for s, rows in per_source.items():
            if SOURCES[s][1] != ax: continue
            if SECONDARY_KEY not in rows: continue
            r = rows[SECONDARY_KEY]
            a = anchor_of.get((s, r["version"]))
            if a: vals_ax.append((SOURCES[s][2], r["value"] / a))
        if vals_ax:
            sec[ax] = sum(w * v for w, v in vals_ax) / sum(w for w, _ in vals_ax)
    print("副锚点 DeepSeek V4.1 Flash 相对能力：P=%.4f X=%.4f" % (sec.get("P", 0), sec.get("X", 0)))

    # 链式：用副锚点把缺主锚点的榜单接进来（含屎山）
    chained = dict(vals_chained)
    if shi_chained:
        chained["shishan"] = [r for rs in shi_chained.values() for r in rs]
    dropped = {}
    for slug, rows in chained.items():
        ax = SOURCES[slug][1]
        if ax not in sec: 
            print(f"  {slug}: 副锚点无 {ax} 轴比值，跳过"); continue
        ref = next((r for r in rows if r["key"] == SECONDARY_KEY), None)
        if not ref: continue
        scale = ref["value"] / sec[ax]
        if scale > 100 and slug != "shishan":
            print(f"  {slug}: 等效基准 {scale:.2f} > 100%，比值法失效，丢弃")
            dropped[slug] = scale
            continue
        if scale > 100:
            print(f"  {slug}: 等效基准 {scale:.2f}（Rasch 分不是百分制，跳过 >100 守卫）")
        print(f"  {slug}: 副锚点原始 {ref['value']:.2f} / 相对 {sec[ax]:.4f} -> 等效基准 {scale:.2f}")
        for r in rows:
            if r["key"] == SECONDARY_KEY: continue
            per_source.setdefault(slug, {})[r["key"]] = r
            anchor_of[(slug, r["version"])] = scale

    metrics = {
        "sec": {k: round(v, 4) for k, v in sec.items()},
        "dropped": {k: round(v, 2) for k, v in dropped.items()},
        "thresholds": {"M0": 1.25, "M1": 1.00, "M2": 0.70},
    }
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as mf:
        json.dump(metrics, mf, ensure_ascii=False, indent=1)

    ev = open(os.path.join(OUT, "model_evidence.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(ev, lineterminator="\n")
    w.writerow(["model_key", "model_id", "source", "axis", "grade", "weight", "version", "date", "raw", "anchor_raw", "ratio"])

    names, parts = {}, {}
    for s, rows in per_source.items():
        ax = SOURCES[s][1]
        for k, r in rows.items():
            a = anchor_of.get((s, r["version"]))
            if not a: continue
            ratio = r["value"] / a
            names.setdefault(k, r["name"])
            parts.setdefault(k, []).append((SOURCES[s][2], ratio, s, ax))
            w.writerow([k, r["name"], SOURCES[s][0], ax, SOURCES[s][3], SOURCES[s][2],
                        r["version"], r.get("date", r["version"]), round(r["value"], 2), round(a, 2), round(ratio, 4)])
    ev.close()

    plane = []
    for k, ps in parts.items():
        p_parts = [(wt, r) for wt, r, s, ax in ps if ax == "P"]
        x_parts = [(wt, r) for wt, r, s, ax in ps if ax == "X"]
        if not p_parts and not x_parts: continue
        p = sum(wt * r for wt, r in p_parts) / sum(wt for wt, _ in p_parts) if p_parts else None
        x = sum(wt * r for wt, r in x_parts) / sum(wt for wt, _ in x_parts) if x_parts else None
        axis_only = ""
        if p is None: p, axis_only = x, "X"
        elif x is None: x, axis_only = p, "P"
        top = max(p, x)
        tier = "M0" if top >= 1.25 else "M1" if top >= 1.00 else "M2" if top >= 0.70 else "M3"
        tag = ("P+" if (p_parts and p >= 1.25) else "") + ("X+" if (x_parts and x >= 1.25) else "")
        rmap = {s: r for wt, r, s, ax in ps}
        row = [names[k], k, round(p, 3), round(x, 3), tier, tag, axis_only,
               round(sum(wt for wt, _ in x_parts), 2),
               "+".join(s for _, _, s, _ in ps),
               round(x2map.get(k, -1), 1) if k in x2map else ""]
        row += [round(rmap[s], 3) if s in rmap else "" for s in ORDER]
        plane.append(row)

    cols = ["model_id", "model_key", "P", "X", "tier", "tags", "axis_only", "X_coverage", "sources", "X2"] + \
           ["r_" + s.replace("-", "_") for s in ORDER]
    pl = open(os.path.join(OUT, "model_plane.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(pl, lineterminator="\n"); w.writerow(cols)
    for r in sorted(plane, key=lambda x: (-x[2], -x[3])): w.writerow(r)
    pl.close()

    print(f"\nplane={len(plane)} tiers={dict(Counter(r[4] for r in plane))}")
    print("基准分（各源各版本）：", {f"{k[0]}@{k[1]}": round(v, 2) for k, v in anchor_of.items()})

if __name__ == "__main__":
    main()
