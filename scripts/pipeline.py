# -*- coding: utf-8 -*-
"""LLM Benchmark Plane — 归一化管道（严格版本内比较）

规则：
  1. 每个来源按“版本”切分（致知=月榜，Vals=快照，屎山=阶梯榜整块）
  2. 一个版本只有在包含基准模型 DeepSeek V4.1 Flash 1017 时才可用，否则整版丢弃
  3. 缺基准的榜用次新 Flash 作链式锚点换算
  4. 同一版本内只做一次比值：score / anchor_score_in_that_version
  5. 不做跨版本取中位、不做跨版本桥接
"""
import csv, json, re, math, os, statistics
from collections import Counter
from vals_map import VALS_MAP
from aa_map import AA_MAP, AA_UNMAPPED

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
SECONDARY_KEY = "deepseekv4.1flash"
LAM_DEFAULT = 0.03
ZERO_KEY = "minimaxm3"      # 零点参照：1017=1 之外再钉一个 0（MiniMax-M3，14+ 个榜都在场）
ZERO_OK_MAX = 0.50          # 零点超过锚点一半 → 该榜动态范围太窄，按 (1−z)/0.5 降权
ZERO_APPLY_MAX = 0.75       # 零点超过锚点 3/4：这块榜根本分不开基准与弱模，不做零点修正（否则放大出 -4.6 这种数）   # 岭回归强度：证据少时把 P/X 拉向加权均值   # 与基准不同的模型，但可作链式锚点

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
                        "raw_name": r["模型"], "version": m, "date": m, "value": v})
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
            a[norm(name)] = {"key": norm(name), "name": name, "raw_name": r["model"],
                             "version": r.get("updated", ""), "date": (r.get("updated") or "")[:10], "value": acc}
    return {s: list(v.values()) for s, v in agg.items()}

def load_aa():
    p = os.path.join(DATA, "aa", "aa_rows.csv")
    if not os.path.exists(p): return {}
    agg, seen = {}, set()
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        seen.add(r["model_slug"])
        key = AA_MAP.get(r["model_slug"])
        if not key: continue
        agg.setdefault(r["source_id"], []).append(
            {"key": key, "name": r["model_name"], "raw_name": r["model_slug"], "version": "aa-2026-10",
             "date": "2026-10-25", "value": float(r["score"])})
    # 映射表漂移自检：这张表是手写的，抓取端的 slug 写法一变就会静默失去整片证据
    # （2026-10-26 实测 20 条里 11 条永不命中，AA 五个源各只剩 9 个模型，跑了很久没人发现）
    dead = sorted(set(AA_MAP) - seen)
    unknown = sorted(seen - set(AA_MAP) - AA_UNMAPPED)
    if dead:
        print(f"  aa: {len(dead)} 条映射在数据里永不命中（slug 写法漂移？）：{'、'.join(dead)}")
    if unknown:
        print(f"  aa: {len(unknown)} 个 slug 既没映射也不在 AA_UNMAPPED：{'、'.join(unknown)}")
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

def fit_px(items, lam=LAM_DEFAULT):
    """items: [(w, alpha, ratio)]；解 r ≈ α·P + (1-α)·X，岭回归稳定（无约束）。"""
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


def ratio_bounds(vals):
    """可校准的比值区间：≥4 个观测取 p10~p90（单个异常榜不能定天花板），否则 min~max。"""
    v = sorted(vals)
    if len(v) < 4:
        return v[0], v[-1]

    def q(frac):
        i = (len(v) - 1) * frac
        lo = int(i); hi = min(lo + 1, len(v) - 1)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)
    return q(0.10), q(0.90)


def fit_px_bounded(items, lam=LAM_DEFAULT, bounds=None):
    """同 fit_px，但把 P、X 限制在该模型观测比值的区间 [min r, max r] 内。

    无约束解会外推：某模型所有榜的比值最高只有 0.94，回归却可能给出 X=1.2——
    那是 α 混合方程折中的产物，没有任何榜支持。界约束用活跃集枚举求精确解：
    先试内部解，不可行就依次把 P 或 X 钉在边界上、另一个取条件极值，再退到四角。
    返回 (P, X, 说明)；说明为空表示内部解本来就在界内。
    """
    if not items:
        return None, None, ""
    rs = [r for _, _, r in items]
    lo, hi = bounds if bounds else (min(rs), max(rs))
    p0, x0 = fit_px(items, lam)
    if p0 is None:
        return None, None, ""
    tol = 1e-3
    if lo - tol <= p0 <= hi + tol and lo - tol <= x0 <= hi + tol:
        return p0, x0, ""
    tw = sum(w for w, _, _ in items)
    r0 = sum(w * r for w, _, r in items) / tw

    def obj(pp, xx):
        return sum(w * (r - (a * pp + (1 - a) * xx)) ** 2 for w, a, r in items) \
               + lam * ((pp - r0) ** 2 + (xx - r0) ** 2)

    def cond_x(P):
        num = den = 0.0
        for w, a, r in items:
            num += w * (1 - a) * (r - a * P); den += w * (1 - a) ** 2
        return (num + lam * r0) / (den + lam) if den + lam else P

    def cond_p(X):
        num = den = 0.0
        for w, a, r in items:
            num += w * a * (r - (1 - a) * X); den += w * a ** 2
        return (num + lam * r0) / (den + lam) if den + lam else X

    cands = []
    for P in (lo, hi):
        X = cond_x(P)
        if lo <= X <= hi: cands.append((P, X))
    for X in (lo, hi):
        P = cond_p(X)
        if lo <= P <= hi: cands.append((P, X))
    cands += [(P, X) for P in (lo, hi) for X in (lo, hi)]
    p1, x1 = min(cands, key=lambda t: obj(t[0], t[1]))
    return p1, x1, f"钳位到 [{lo:.2f},{hi:.2f}]（无约束解 P {p0:.3f}/X {x0:.3f} 越界）"


def fit_px_robust(items, lam=LAM_DEFAULT, min_n=6, k=2.0, floor=0.25, rounds=8, bounds=None):
    """有界解 + IRLS：某个源在**这个模型**上残差特别大，就只在这个模型上降它的权。

    §15 的全局权重管的是“这个榜整体值不值得信”；这里管的是另一回事——同一个模型
    在不同榜上的剖面打架（GPT-6 Astra 的观测比值跨 0.45~2.20），普通最小二乘会把
    两个轴都往中间拉，让少数离谱的榜决定坐标。

    稳健尺度取残差的加权 MAD（1.345×MAD），残差超过 k 倍尺度的源按 k·scale/|e| 降权，
    最多降到 floor（0.25 倍）为止，不会被悄悄抹掉；少于 min_n 个源不做——
    两三个源拟合两个参数，残差必然接近 0，降权没有意义。
    返回 (P, X, 钳位说明, {源下标: 系数})。
    """
    p0, x0, clamp = fit_px_bounded(items, lam, bounds)
    if p0 is None or len(items) < min_n:
        return p0, x0, clamp, {}
    w0 = [it[0] for it in items]
    tw = sum(w0)
    fac = [1.0] * len(items)
    p, x = p0, x0
    for _ in range(rounds):
        pr, xr, _ = fit_px_bounded([(w0[i] * fac[i], items[i][1], items[i][2])
                                    for i in range(len(items))], lam, bounds)
        if pr is None:
            break
        res = [abs(items[i][2] - (items[i][1] * pr + (1 - items[i][1]) * xr))
               for i in range(len(items))]
        med = statistics.median(res)
        dev = statistics.median([abs(v - med) for v in res])
        scale = (1.345 * dev if dev > 0 else
                 math.sqrt(sum(w0[i] * res[i] ** 2 for i in range(len(items))) / tw))
        if scale <= 0:
            break
        new = [min(1.0, max(floor, k * scale / res[i])) if res[i] > 1e-9 else 1.0
               for i in range(len(items))]
        delta = max(abs(new[i] - fac[i]) for i in range(len(items)))
        fac, p, x = new, pr, xr
        if delta < 1e-3:
            break
    out = {i: f for i, f in enumerate(fac) if f < 0.999}
    if not out:
        return p0, x0, clamp, {}      # 没人被降权 → 保持原来的有界解
    return p, x, clamp, out


def fit_rmse(items, px, x_):
    tw = sum(w for w, _, _ in items)
    if not tw: return 0.0
    return math.sqrt(sum(w * (r - (a * px + (1 - a) * x_)) ** 2 for w, a, r in items) / tw)


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
        n = len(rows)
        has_pri = any(r["key"] == ANCHOR_KEY for r in rows)
        has_sec = any(r["key"] == SECONDARY_KEY for r in rows)
        # 模型数下限与 usable_versions / 屎山分支一致：含锚点但只有个位数模型的
        # 快照不得进比值——否则锚点自己会被钉成 1.0/1.0，这条源的全部权重就压在
        # 一个没有信息量的点上。此前只有 1~4 个模型的尾巴源能悄悄影响基准坐标。
        if has_pri and n >= MIN_MODELS_PER_VERSION:
            vals_ok[slug] = rows
            print(f"  {slug}: {n} 个模型，含基准 OK")
        elif has_sec and n >= MIN_MODELS_PER_VERSION:
            vals_chained[slug] = rows
            print(f"  {slug}: {n} 个模型，含副锚点 DeepSeek V4.1 Flash -> 链式换算")
        else:
            why = f"仅 {n} 个模型" if (has_pri or has_sec) else "无可用锚点"
            print(f"  {slug}: {n} 个模型，{why}，丢弃")

    # 每个模型只取最新可用版本
    def latest(by_ver):
        best = {}
        for ver, rs in by_ver.items():
            for r in rs:
                cur = best.get(r["key"])
                if cur is None or ver > cur["version"] or (ver == cur["version"] and r["value"] > cur["value"]):
                    best[r["key"]] = r   # 同键多配置取最高分（最强档），被丢的配置由 warn_variants 打印
        return best

    def warn_variants(rows, label):
        """同一版本里同一个键出现多行（不同推理档位/配置）：取用的是第一行，必须可见。"""
        by = {}
        for r in rows: by.setdefault((r["version"], r["key"]), []).append(r)
        for (ver, key), rs in sorted(by.items()):
            if len(rs) < 2: continue
            vals = [f"{r['name']}={r['value']:.2f}" for r in rs]
            print(f"  ⚠ {label} {ver} 同键多配置（取最高分那档）：{key} → {' / '.join(vals)}")

    warn_variants(logic_rows, "logic")
    warn_variants(code_rows, "code_v3")

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
        sp, sx, note = fit_px_bounded(items)
        sec = {"P": sp, "X": sx}
        if note: print(f"  副锚点 {note}")
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

    # 零点参照：该榜上 MiniMax-M3 相对基准的位置 z，用来把比值重标定成 0..1..
    #   r′ = (r − z) / (1 − z)   → 1017 仍是 1.0，MiniMax-M3 变成 0
    # z 越接近 1 说明这块榜分不出基准与弱模，放大系数 1/(1−z) 也越大 → 同时按 ZERO_OK_MAX 降权。
    zero_of, zero_pen, zero_skip = {}, {}, set()
    for s, rows in per_source.items():
        for ver in {r["version"] for r in rows.values()}:
            a = anchor_of.get((s, ver))
            zr = [r["value"] / a for r in rows.values() if r["version"] == ver and r["key"] == ZERO_KEY]
            if not a or not zr: continue
            z = zr[0]
            zero_pen[s] = min(1.0, max(0.10, (1 - z) / ZERO_OK_MAX))
            if z <= ZERO_APPLY_MAX:
                zero_of[(s, ver)] = z      # 修正后量程仍可接受
            else:
                zero_skip.add(s)           # 只降权，不放大
    print("零点参照（MiniMax-M3）：")
    for s in sorted({k[0] for k in zero_of}):
        z = [v for (ss, _), v in zero_of.items() if ss == s][0]
        print(f"  {s:24} z={z:5.2f}  放大 {1/(1-z) if z < 1 else 0:5.2f}×  权重×{zero_pen[s]:.2f}")
    print("  零点过高、只降权不做零点修正：" + ("、".join(sorted(zero_skip)) or "无") +
          "；无 MiniMax-M3：" + "、".join(sorted(set(SOURCES) - {k[0] for k in zero_of} - zero_skip)))

    metrics = {
        "sec": {k: round(v, 4) for k, v in sec.items()},
        "dropped": {k: round(v, 2) for k, v in dropped.items()},
        "near_ceiling": near,
        "zero_ref": ZERO_KEY,
        "zero_z": {s: round(z, 4) for s, z in
                   sorted({k[0]: v for k, v in zero_of.items()}.items())},
        "zero_penalty": {s: round(v, 3) for s, v in sorted(zero_pen.items())},
        "zero_skip": sorted(zero_skip),
        "thresholds": {"M0": 1.25, "M1": 1.00, "M2": 0.70},
    }
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as mf:
        json.dump(metrics, mf, ensure_ascii=False, indent=1)

    def w_eff(s):
        return SOURCES[s]["w"] * zero_pen.get(s, 1.0)

    names, parts, ev_rows = {}, {}, []
    for s, rows in per_source.items():
        alpha = SOURCES[s]["alpha"]
        ax = "P" if alpha >= 0.5 else "X"
        for k, r in rows.items():
            a = anchor_of.get((s, r["version"]))
            if not a: continue
            z = zero_of.get((s, r["version"]))
            base = r["value"] / a
            ratio = base if z is None else (base - z) / (1 - z)
            names.setdefault(k, r["name"])
            parts.setdefault(k, []).append((w_eff(s), ratio, s, z is not None))
            ev_rows.append((k, r, s, ax, alpha, a, ratio, base, z))

    used = set(per_source)
    max_p = sum(w_eff(s) * SOURCES[s]["alpha"] for s in used)
    max_x = sum(w_eff(s) * (1 - SOURCES[s]["alpha"]) for s in used)

    fits = {}
    for k, ps in parts.items():
        # 覆盖度必须与 max_p / max_x 同口径（都用 weight_eff）：分子若用原始权重，
        # 被零点惩罚降权过的源会把覆盖度算到 1 以上（实测出现 1.04）。
        # 注意 weight_eff 只含零点惩罚，不含 IRLS 的按模型降权 fac——两轴分子分母
        # 一致即可，fac 是"这个模型在该源上不可信"，不是"没有证据"。
        p_parts = [(w * SOURCES[s]["alpha"], r) for w, r, s, _f in ps]
        x_parts = [(w * (1 - SOURCES[s]["alpha"]), r) for w, r, s, _f in ps]
        pw = sum(w for w, _ in p_parts); xw = sum(w for w, _ in x_parts)
        if pw <= 0 and xw <= 0: continue
        items = [(w, SOURCES[s]["alpha"], r) for w, r, s, _f in ps]
        # 界只由做过零点修正的榜决定：没修正的榜零点不同（多半是原始 0），
        # 让它们去顶天花板就等于把坐标重新拉回外推（Mistral Large 4 的 X=1.235 是这么来的）
        zsrc = [r for w, r, s, f in ps if f]
        bounds = ratio_bounds(zsrc) if len(zsrc) >= 4 else ratio_bounds([r for _, r, _, _ in ps])
        p, x, clamp, fac = fit_px_robust(items, bounds=bounds)
        if p is None: continue
        if clamp: print(f"  {names[k]}: {clamp}")
        if fac:
            print(f"  {names[k]}: 剖面不一致，按残差降权 → " +
                  "、".join(f"{ps[i][2]}×{fac[i]:.2f}" for i in sorted(fac)))
        rs = [r for _, r, _, _f in ps]
        fits[k] = {"p": p, "x": x, "fac": fac, "clamp": 1 if clamp else 0,
                   "rmse": fit_rmse(items, p, x),
                   "dw": "+".join(f"{ps[i][2]}×{fac[i]:.2f}" for i in sorted(fac)),
                   "lo": min(rs), "hi": max(rs),
                   "pcov": pw / max_p if max_p else 0,
                   "xcov": xw / max_x if max_x else 0,
                   "ps": ps}

    ev = open(os.path.join(OUT, "model_evidence.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(ev, lineterminator="\n")
    w.writerow(["model_key", "model_id", "source_model", "source_id", "source", "axis",
                "alpha_p", "grade", "weight", "weight_eff", "version", "date",
                "raw", "anchor_raw", "ratio_raw", "zero_z", "ratio"])
    for (k, r, s, ax, alpha, a, ratio, base, z) in ev_rows:
        idx = [i for i, (ww, rr, ss, _f) in enumerate(fits[k]["ps"]) if ss == s] if k in fits else []
        f = fits[k]["fac"].get(idx[0], 1.0) if idx else 1.0
        w.writerow([k, r["name"], r.get("raw_name", r["name"]), s, SOURCES[s]["name"],
                    ax, alpha, SOURCES[s]["grade"], SOURCES[s]["w"],
                    round(SOURCES[s]["w"] * zero_pen.get(s, 1.0) * f, 4), r["version"],
                    r.get("date", r["version"]), round(r["value"], 2), round(a, 2),
                    round(base, 4), "" if z is None else round(z, 4), round(ratio, 4)])
    ev.close()

    plane = []
    for k, fit in fits.items():
        p, x = fit["p"], fit["x"]
        ps = fit["ps"]
        top = max(p, x)
        tier = "M0" if top >= 1.25 else "M1" if top >= 1.00 else "M2" if top >= 0.70 else "M3"
        # 距下一档还差多少：档位带宽 0.25，差值只有 0.01 量级就说明是临界点
        nxt = {"M0": None, "M1": 1.25, "M2": 1.00, "M3": 0.70}[tier]
        gap = "" if nxt is None else round(max(0.0, nxt - top), 3)
        tag = ("P+" if p >= 1.25 else "") + ("X+" if x >= 1.25 else "") + ("0锚" if k == ZERO_KEY else "")
        rmap = {s: r for w, r, s, _f in ps}
        row = [names[k], k, round(p, 3), round(x, 3), tier, tag, "",
               round(fit["pcov"], 3), round(fit["xcov"], 3), round(fit["rmse"], 3), gap,
               f"{fit['lo']:.2f}~{fit['hi']:.2f}", fit["clamp"], fit["dw"],
               "+".join(s for _, _, s, _f in ps),
               round(x2map.get(k, -1), 1) if k in x2map else ""]
        row += [round(rmap[s], 3) if s in rmap else "" for s in ORDER]
        plane.append(row)

    cols = ["model_id", "model_key", "P", "X", "tier", "tags", "axis_only",
            "P_coverage", "X_coverage", "fit_rmse", "next_tier_gap", "ratio_range", "clamped",
            "downweighted", "sources", "X2"] + \
           ["r_" + s.replace("-", "_") for s in ORDER]
    pl = open(os.path.join(OUT, "model_plane.csv"), "w", newline="", encoding="utf-8-sig")
    w = csv.writer(pl, lineterminator="\n"); w.writerow(cols)
    for r in sorted(plane, key=lambda x: (-x[2], -x[3])): w.writerow(r)
    pl.close()

    print(f"\nplane={len(plane)} tiers={dict(Counter(r[4] for r in plane))}")
    print("基准分（各源各版本）：", {f"{k[0]}@{k[1]}": round(v, 2) for k, v in anchor_of.items()})

if __name__ == "__main__":
    main()
