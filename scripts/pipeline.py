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
from aa_map import AA_MAP

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

def load_registry():
    reg = {}
    p = os.path.join(BASE, "sources.csv")
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if r["status"] not in ("active", "guarded"): continue
        if not r["alpha_p"].strip(): continue
        reg[r["id"]] = {"name": r["name"],
                        "w": float(r.get("weight_cal") or r["weight_prior"]),
                        "w_prior": float(r["weight_prior"]),
                        "grade": r["grade"], "alpha": float(r["alpha_p"])}
    return reg

SOURCES = load_registry()
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

def load_aa():
    p = os.path.join(DATA, "aa", "aa_rows.csv")
    if not os.path.exists(p): return {}
    agg = {}
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        key = AA_MAP.get(r["model_slug"])
        if not key: continue
        agg.setdefault(r["source_id"], []).append(
            {"key": key, "name": r["model_name"], "version": "aa-2026-10",
             "date": "2026-10-25", "value": float(r["score"])})
    return agg

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

ORDER = list(SOURCES)

def fit_px(items, lam=0.03):
    """items: [(w, alpha, ratio)]；解 r ≈ α·P + (1-α)·X，岭回归稳定。"""
    A = B = C = D = E = 0.0
    r0n = r0d = 0.0
    for w, a, r in items:
        A += w * a * a
        B += w * a * (1 - a)
        C += w * (1 - a) * (1 - a)
        D += w * a * r
        E += w * (1 - a) * r
        r0n += w * r
        r0d += w
    if r0d == 0:
        return None, None
    r0 = r0n / r0d
    A += lam; C += lam; D += lam * r0; E += lam * r0
    det = A * C - B * B
    return (D * C - E * B) / det, (E * A - D * B) / det


def main():
    logic_rows = load_logic()
    code_rows = load_code_v3()
    shi_rows, x2map = load_shishan()
    vals = load_vals()
    vals.update(load_aa())

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

    # 副锚点自身在各轴上的相对能力：按 P/X 成分加权
    sec = {}
    items = []
    for s, rows in per_source.items():
        if SECONDARY_KEY not in rows: continue
        r = rows[SECONDARY_KEY]
        a = anchor_of.get((s, r["version"]))
        if a: items.append((SOURCES[s]["w"], SOURCES[s]["alpha"], r["value"] / a))
    if items:
        sp, sx = fit_px(items)
        sec = {"P": sp, "X": sx}
    print("副锚点 DeepSeek V4.1 Flash 相对能力：P=%.4f X=%.4f" % (sec.get("P", 0), sec.get("X", 0)))

    # 链式：用副锚点把缺主锚点的榜单接进来（含屎山）
    chained = dict(vals_chained)
    if shi_chained:
        chained["shishan"] = [r for rs in shi_chained.values() for r in rs]
    dropped = {}
    near = []
    for slug, rows in chained.items():
        if "P" not in sec or "X" not in sec: continue
        a = SOURCES[slug]["alpha"]
        r_anchor = a * sec["P"] + (1 - a) * sec["X"]
        ref = next((r for r in rows if r["key"] == SECONDARY_KEY), None)
        if not ref: continue
        # 该榜满分是多少：0–1 制还是百分制（看全榜最大值；Rasch 榜另算）
        ceiling = 1.0 if max(r["value"] for r in rows) <= 1.05 else 100.0
        scale = ref["value"] / r_anchor
        if ref["value"] <= 0:
            print(f"  {slug}: 副锚点在该榜原始分为 0，比值无定义，丢弃")
            dropped[slug] = 0.0
            continue
        if scale < 0.05 * ceiling:
            print(f"  {slug}: 等效基准 {scale:.2f} 低于该榜满分 {ceiling:g} 的 5%，比值被极端放大，丢弃")
            dropped[slug] = scale
            continue
        if scale > ceiling and slug != "shishan":
            print(f"  {slug}: 等效基准 {scale:.2f} 超过该榜满分 {ceiling:g}，比值法失效，丢弃")
            dropped[slug] = scale
            continue
        if scale > 100:
            print(f"  {slug}: 等效基准 {scale:.2f}（Rasch 分不是百分制，跳过 >100 守卫）")
        elif scale > 0.9 * ceiling:
            near.append(slug)
            print(f"  {slug}: 等效基准 {scale:.2f} 接近该榜满分 {ceiling:g}，比值放大有风险")
        print(f"  {slug}: 副锚点原始 {ref['value']:.2f} / 混合相对 {r_anchor:.4f} -> 等效基准 {scale:.2f}")
        for r in rows:
            if r["key"] == SECONDARY_KEY: continue
            per_source.setdefault(slug, {})[r["key"]] = r
            anchor_of[(slug, r["version"])] = scale

    metrics = {
        "sec": {k: round(v, 4) for k, v in sec.items()},
        "dropped": {k: round(v, 2) for k, v in dropped.items()},
        "near_ceiling": near,
        "thresholds": {"M0": 1.25, "M1": 1.00, "M2": 0.70},
    }
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as mf:
        json.dump(metrics, mf, ensure_ascii=False, indent=1)

    ev = open(os.path.join(OUT, "model_evidence.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(ev, lineterminator="\n")
    w.writerow(["model_key", "model_id", "source_id", "source", "axis", "alpha_p", "grade",
                "weight", "version", "date", "raw", "anchor_raw", "ratio"])

    names, parts = {}, {}
    for s, rows in per_source.items():
        alpha = SOURCES[s]["alpha"]
        ax = "P" if alpha >= 0.5 else "X"
        for k, r in rows.items():
            a = anchor_of.get((s, r["version"]))
            if not a: continue
            ratio = r["value"] / a
            names.setdefault(k, r["name"])
            parts.setdefault(k, []).append((SOURCES[s]["w"], ratio, s))
            w.writerow([k, r["name"], s, SOURCES[s]["name"], ax, alpha, SOURCES[s]["grade"],
                        SOURCES[s]["w"], r["version"], r.get("date", r["version"]),
                        round(r["value"], 2), round(a, 2), round(ratio, 4)])
    ev.close()

    used = set(per_source)
    max_p = sum(SOURCES[s]["w"] * SOURCES[s]["alpha"] for s in used)
    max_x = sum(SOURCES[s]["w"] * (1 - SOURCES[s]["alpha"]) for s in used)
    plane = []
    for k, ps in parts.items():
        p_parts = [(SOURCES[s]["w"] * SOURCES[s]["alpha"], r) for w, r, s in ps]
        x_parts = [(SOURCES[s]["w"] * (1 - SOURCES[s]["alpha"]), r) for w, r, s in ps]
        pw = sum(w for w, _ in p_parts); xw = sum(w for w, _ in x_parts)
        if pw <= 0 and xw <= 0: continue
        p, x = fit_px([(SOURCES[s]["w"], SOURCES[s]["alpha"], r) for w, r, s in ps])
        if p is None: continue
        axis_only = ""
        top = max(p, x)
        tier = "M0" if top >= 1.25 else "M1" if top >= 1.00 else "M2" if top >= 0.70 else "M3"
        tag = ("P+" if (p is not None and p >= 1.25) else "") + ("X+" if (x is not None and x >= 1.25) else "")
        rmap = {s: r for w, r, s in ps}
        pcov = pw / max_p if max_p else 0
        xcov = xw / max_x if max_x else 0
        row = [names[k], k, round(p, 3), round(x, 3), tier, tag, axis_only,
               round(pcov, 3), round(xcov, 3),
               "+".join(s for _, _, s in ps),
               round(x2map.get(k, -1), 1) if k in x2map else ""]
        row += [round(rmap[s], 3) if s in rmap else "" for s in ORDER]
        plane.append(row)

    cols = ["model_id", "model_key", "P", "X", "tier", "tags", "axis_only",
            "P_coverage", "X_coverage", "sources", "X2"] + \
           ["r_" + s.replace("-", "_") for s in ORDER]
    pl = open(os.path.join(OUT, "model_plane.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(pl, lineterminator="\n"); w.writerow(cols)
    for r in sorted(plane, key=lambda x: (-x[2], -x[3])): w.writerow(r)
    pl.close()

    print(f"\nplane={len(plane)} tiers={dict(Counter(r[4] for r in plane))}")
    print("基准分（各源各版本）：", {f"{k[0]}@{k[1]}": round(v, 2) for k, v in anchor_of.items()})

if __name__ == "__main__":
    main()
