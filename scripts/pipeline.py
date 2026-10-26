# -*- coding: utf-8 -*-
"""LLM Benchmark Plane — 归一化管道（严格版本内比较）

规则：
  1. 每个来源按“版本”切分（致知=月榜，Vals=快照，屎山=阶梯榜整块）
  2. 一个版本只有在包含基准模型 DeepSeek V4.1 Flash 1017 时才可用，否则整版丢弃
  3. 缺基准的榜用次新 Flash 作链式锚点换算
  4. 同一版本内只做一次比值：score / anchor_score_in_that_version
  5. 不做跨版本取中位、不做跨版本桥接
"""
import csv, json, re, math, os, statistics, sys
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
    agg, stat = {}, {}
    for r in rows:
        st = stat.setdefault(r["slug"], {"rows": 0, "names": set(), "unmapped": set(),
                                         "nonnum": set(), "keys": set()})
        st["rows"] += 1
        st["names"].add(r["model"])
        name = VALS_MAP.get(r["model"])
        if not name:
            st["unmapped"].add(r["model"]); continue
        try: acc = float(r["accuracy"])
        except (TypeError, ValueError):
            st["nonnum"].add(r["model"]); continue
        a = agg.setdefault(r["slug"], {})
        cur = a.get(norm(name))
        if cur is None or acc > cur["value"]:
            a[norm(name)] = {"key": norm(name), "name": name, "raw_name": r["model"],
                             "version": r.get("updated", ""), "date": (r.get("updated") or "")[:10], "value": acc}
        st["keys"].add(norm(name))
    # stat 带上映射失败的名单：只报映射后的模型数，"这张榜本来只有 4 个模型" 和
    # "榜上 40 个名字我们一个都没映射上" 会打印成同一句话（AA 漂移 11 条就是这么瞎的）
    return {s: list(v.values()) for s, v in agg.items()}, stat

def load_aa():
    p = os.path.join(DATA, "aa", "aa_rows.csv")
    if not os.path.exists(p): return {}, {}
    agg, seen, stat = {}, set(), {}
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        seen.add(r["model_slug"])
        st = stat.setdefault(r["source_id"], {"rows": 0, "names": set(), "unmapped": set(),
                                              "nonnum": set(), "keys": set()})
        st["rows"] += 1
        st["names"].add(r["model_slug"])
        key = AA_MAP.get(r["model_slug"])
        if not key:
            st["unmapped"].add(r["model_slug"]); continue
        try: val = float(r["score"])
        except (TypeError, ValueError):
            st["nonnum"].add(r["model_slug"]); continue
        agg.setdefault(r["source_id"], []).append(
            {"key": key, "name": r["model_name"], "raw_name": r["model_slug"], "version": "aa-2026-10",
             "date": "2026-10-25", "value": val})
        st["keys"].add(key)
    # 映射表漂移自检：这张表是手写的，抓取端的 slug 写法一变就会静默失去整片证据
    # （2026-10-26 实测 20 条里 11 条永不命中，AA 五个源各只剩 9 个模型，跑了很久没人发现）
    dead = sorted(set(AA_MAP) - seen)
    unknown = sorted(seen - set(AA_MAP) - AA_UNMAPPED)
    if dead:
        print(f"  aa: {len(dead)} 条映射在数据里永不命中（slug 写法漂移？）：{'、'.join(dead)}")
    if unknown:
        print(f"  aa: {len(unknown)} 个 slug 既没映射也不在 AA_UNMAPPED：{'、'.join(unknown)}")
    return agg, stat

# ---------- 版本筛选 ----------
def map_note(slug, stat):
    """映射覆盖的注脚：源表有多少行/多少个名字、其中多少个没映射、多少个折成同键变体。
    只报映射后的模型数，"这张榜本来只有 4 个模型" 和 "榜上 40 个名字一个都没映射上"
    会打印成同一句话——AA 漂移 11 条就是这么失明的（2026-10-26）。"""
    st = stat.get(slug)
    if not st: return ""
    un, nn = len(st["unmapped"]), len(st["nonnum"])
    var = len(st["names"]) - un - nn - len(st["keys"])
    parts = [f"源表 {st['rows']} 行 / {len(st['names'])} 个名字",
             (f"{un} 个没映射" if un else "名字全部映射上")]
    if var > 0: parts.append(f"{var} 个是同键变体")
    if nn: parts.append(f"{nn} 个分数取不到")
    return "（" + "，".join(parts) + "）"


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
    return quantile(v, 0.10), quantile(v, 0.90)


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



# ---------- 装配证据：加载 + 版本筛选 + 守卫 + 锚点 / 链式 / 零点（不写文件） ----------
def build():
    """返回 state（per_source / anchor_of / sec / zero_* / metrics）。

    拆成 build ↔ evidence ↔ fit_all 是 bootstrap 的前提：重采样只改"哪些源在场、来几次"，
    版本选取、链式等效基准、零点 z 全部固定复用（每次重采样都重估锚点会把二阶不确定性
    混进区间里）。解算入口只有 `fit_model` 一个，管道和 bootstrap 走同一条路径。
    """
    logic_rows = load_logic()
    code_rows = load_code_v3()
    shi_rows, x2map = load_shishan()
    vals, vstat = load_vals()
    aa, aastat = load_aa()
    vals.update(aa)
    vstat.update(aastat)
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
        note = map_note(slug, vstat)
        has_pri = any(r["key"] == ANCHOR_KEY for r in rows)
        has_sec = any(r["key"] == SECONDARY_KEY for r in rows)
        # 模型数下限与 usable_versions / 屎山分支一致：含锚点但只有个位数模型的
        # 快照不得进比值——否则锚点自己会被钉成 1.0/1.0，这条源的全部权重就压在
        # 一个没有信息量的点上。此前只有 1~4 个模型的尾巴源能悄悄影响基准坐标。
        if has_pri and n >= MIN_MODELS_PER_VERSION:
            vals_ok[slug] = rows
            print(f"  {slug}: {n} 个模型{note}，含基准 OK")
        elif has_sec and n >= MIN_MODELS_PER_VERSION:
            vals_chained[slug] = rows
            print(f"  {slug}: {n} 个模型{note}，含副锚点 DeepSeek V4.1 Flash -> 链式换算")
        else:
            why = f"仅 {n} 个模型" if (has_pri or has_sec) else "无可用锚点"
            un = len(vstat[slug]["unmapped"]) if slug in vstat and vstat[slug]["unmapped"] else 0
            hint = (f"；{un} 个名字没映射上，先查映射表再断定这榜是不是真的没有锚点"
                    if (not (has_pri or has_sec)) and un else "")
            print(f"  {slug}: {n} 个模型{note}，{why}，丢弃{hint}")

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
    chain_info = {}
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
        chain_info[slug] = {"alpha": a, "r_anchor": round(r_anchor, 4),
                            "sec_raw": round(ref["value"], 2), "equiv": round(scale, 2),
                            "ceiling": ceiling, "near": slug in near}
        for r in rows:
            if r["key"] == SECONDARY_KEY: continue
            per_source.setdefault(slug, {})[r["key"]] = r
            anchor_of[(slug, r["version"])] = scale

    # 零点参照：该榜上 MiniMax-M3 相对基准的位置 z，用来把比值重标定成 0..1..
    #   r′ = (r − z) / (1 − z)   → 1017 仍是 1.0，MiniMax-M3 变成 0
    # z 越接近 1 说明这块榜分不出基准与弱模，放大系数 1/(1−z) 也越大 → 同时按 ZERO_OK_MAX 降权。
    zero_of, zero_pen, zero_skip, zero_skip_z = {}, {}, set(), {}
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
                zero_skip_z[s] = z         # 但 z 本身要留在产物里，文档才不是手抄的
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
        # 链式换算的每个榜都写进产物：METHOD §6 的表和 README 的 near_ceiling 数字
        # 都要能由产物生成，手抄一遍就会漂移
        "chained": {k: v for k, v in sorted(chain_info.items())},
        "zero_ref": ZERO_KEY,
        "zero_z": {s: round(z, 4) for s, z in
                   sorted({k[0]: v for k, v in zero_of.items()}.items())},
        "zero_penalty": {s: round(v, 3) for s, v in sorted(zero_pen.items())},
        "zero_skip": sorted(zero_skip),
        "zero_skip_z": {s: round(z, 4) for s, z in sorted(zero_skip_z.items())},
        "thresholds": {"M0": 1.25, "M1": 1.00, "M2": 0.70},
    }
    return {"per_source": per_source, "anchor_of": anchor_of, "sec": sec,
            "zero_of": zero_of, "zero_pen": zero_pen, "x2map": x2map,
            "dropped": dropped, "near": near, "metrics": metrics}


# ---------- 二、逐模型证据条目 ----------
def evidence(st):
    """把 state 摊成"每个模型手上有哪些源"：parts[k] = [(weight_eff, ratio, source, 做过零点修正)]。"""
    per_source, anchor_of, zero_of, zero_pen = (st["per_source"], st["anchor_of"],
                                                st["zero_of"], st["zero_pen"])

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
    return {"names": names, "parts": parts, "ev_rows": ev_rows, "max_p": max_p, "max_x": max_x}


# ---------- 三、解算（唯一入口） ----------
def fit_model(ps, max_p, max_x):
    """一个模型 → {p, x, clamp…, rmse, pcov, xcov, ps}；没有有效证据返回 None。

    管道出点估计、bootstrap 出区间，都调这一个函数：METHOD §15 的"只允许一套估计器"
    就是靠这个入口保证的——复制一份解算代码，两处就会各自漂移。
    """
    # 覆盖度必须与 max_p / max_x 同口径（都用 weight_eff）：分子若用原始权重，
    # 被零点惩罚降权过的源会把覆盖度算到 1 以上（实测出现 1.04）。
    # 注意 weight_eff 只含零点惩罚，不含 IRLS 的按模型降权 fac——两轴分子分母
    # 一致即可，fac 是"这个模型在该源上不可信"，不是"没有证据"。
    p_parts = [(w * SOURCES[s]["alpha"], r) for w, r, s, _f in ps]
    x_parts = [(w * (1 - SOURCES[s]["alpha"]), r) for w, r, s, _f in ps]
    pw = sum(w for w, _ in p_parts); xw = sum(w for w, _ in x_parts)
    if pw <= 0 and xw <= 0: return None
    items = [(w, SOURCES[s]["alpha"], r) for w, r, s, _f in ps]
    # 界只由做过零点修正的榜决定：没修正的榜零点不同（多半是原始 0），
    # 让它们去顶天花板就等于把坐标重新拉回外推（Mistral Large 4 的 X=1.235 是这么来的）
    zsrc = [r for w, r, s, f in ps if f]
    bounds = ratio_bounds(zsrc) if len(zsrc) >= 4 else ratio_bounds([r for _, r, _, _ in ps])
    p, x, clamp, fac = fit_px_robust(items, bounds=bounds)
    if p is None: return None
    rs = [r for _, r, _, _f in ps]
    return {"p": p, "x": x, "fac": fac, "clamp": 1 if clamp else 0, "clamp_note": clamp,
            "rmse": fit_rmse(items, p, x),
            "dw": "+".join(f"{ps[i][2]}×{fac[i]:.2f}" for i in sorted(fac)),
            "lo": min(rs), "hi": max(rs),
            "pcov": pw / max_p if max_p else 0,
            "xcov": xw / max_x if max_x else 0,
            "ps": ps}


def tier_of(top):
    """档位判定的唯一实现（§8：拿发布出来的三位小数坐标比阈值，不拿原始浮点值）。"""
    return "M0" if top >= 1.25 else "M1" if top >= 1.00 else "M2" if top >= 0.70 else "M3"


def fit_all(ev):
    """逐个模型求解；钳位与按残差降权只在这里打印（bootstrap 复用 fit_model 时保持安静）。"""
    fits = {}
    for k, ps in ev["parts"].items():
        fit = fit_model(ps, ev["max_p"], ev["max_x"])
        if fit is None: continue
        if fit["clamp_note"]: print(f"  {ev['names'][k]}: {fit['clamp_note']}")
        if fit["fac"]:
            print(f"  {ev['names'][k]}: 剖面不一致，按残差降权 → " +
                  "、".join(f"{ps[i][2]}×{fit['fac'][i]:.2f}" for i in sorted(fit["fac"])))
        fits[k] = fit
    return fits


# ---------- 四、源级 bootstrap：坐标区间 + 档位稳定率 ----------
BOOT_COLS = ["P_lo", "P_hi", "X_lo", "X_hi", "tier_stability", "tier_presence", "tier_mode"]
BOOT_SEED = 20261026


def quantile(sv, frac):
    """线性插值分位数（与 ratio_bounds 同一套取法）。sv 必须已排序。"""
    i = (len(sv) - 1) * frac
    lo = int(i); hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (i - lo)


def resample(parts, counts, max_p, max_x):
    """按"源被抽到几次"调整权重，重解每个模型；返回 {(p, x, tier)} 子集。"""
    out = {}
    for k, ps in parts.items():
        sub = [(w * counts[s], r, s, f) for (w, r, s, f) in ps if s in counts]
        fit = fit_model(sub, max_p, max_x) if sub else None
        if fit is None: continue
        P3, X3 = round(fit["p"], 3), round(fit["x"], 3)
        out[k] = (P3, X3, tier_of(max(P3, X3)))
    return out


def bootstrap(ev, point_tier, runs=1000, seed=BOOT_SEED):
    """源级 bootstrap：有放回抽"计分源"，每次重解全部模型，取 5~95 分位与档位稳定率。

    重采样单位是**源**而不是证据行——某个模型在一张榜上有 30 行是 30 条读数，
    不是 30 次独立观测；按行抽会把这张榜的自相关当成信息的量。
    版本、链式等效基准、零点 z 全部沿用 build 的结果（不重估），
    解算走 fit_model 同一条路径（含 p10~p90 钳位与 IRLS 按模型降权）。
    注意它量的是**跨榜组成敏感性**：27 个源有放回抽 27 次，每次平均只有约 17 个源在场
    （单个源被抽到的概率 ≈ 1 − (26/27)^27 ≈ 0.63），所以区间回答的是"换一批约 17 块榜，
    坐标会差多少"，不是"同一批数据的抽样误差"；锚点选取、版本切分、z≤0.75 阈值、λ、
    档位阈值都不体现在区间里（见 METHOD §17）。
    复制 k 次会让那张榜的权重也乘 k、从而相对削弱岭正则——实测把每次重采样的权重质量
    归一回全量质量，中位宽度只从 P 0.431 变到 0.418 / X 0.536 变到 0.566，
    不是主因，所以这里保留朴素的可复制加权（少一层解释成本）。

    `tier_stability` 的分母是**全部重采样次数**：抽不到任何证据的那几次算"没落回原档"。
    用"有证据的次数"当分母会把结论反过来——只有一个源的模型在源被抽到时按构造必然同档
    （区间退化成一点），于是最没证据的模型稳定率最高（实测 12 个单源模型全报 1.000）。
    所以另给 `tier_presence`（该模型的证据在本次重采样里在场的比例）：单源模型约 0.63，
    意思是"三分之一多的次数里它根本没有坐标"。
    """
    import random
    src_ids = sorted({s for ps in ev["parts"].values() for (_w, _r, s, _f) in ps})
    rng = random.Random(seed)
    seq = {k: [] for k in ev["parts"]}      # 每次重采样一个槽：None = 这次抽不到该模型的任何源
    cover = []
    for _ in range(runs):
        counts = Counter(rng.choices(src_ids, k=len(src_ids)))
        cover.append(len(counts))
        got = resample(ev["parts"], counts, ev["max_p"], ev["max_x"])
        for k in seq:
            seq[k].append(got.get(k))
    out = {}
    for k, sl in seq.items():
        v = [t for t in sl if t is not None]
        if not v: continue
        pv = sorted(x[0] for x in v); xv = sorted(x[1] for x in v)
        tiers = [x[2] for x in v]
        out[k] = {"P_lo": round(quantile(pv, 0.05), 3), "P_hi": round(quantile(pv, 0.95), 3),
                  "X_lo": round(quantile(xv, 0.05), 3), "X_hi": round(quantile(xv, 0.95), 3),
                  "stability": round(sum(1 for t in tiers if t == point_tier.get(k)) / runs, 3),
                  "presence": round(len(v) / runs, 3),
                  "n": len(v), "modal_tier": Counter(tiers).most_common(1)[0][0]}
    by_tier = {}
    for k, b in out.items():
        by_tier.setdefault(point_tier.get(k, "?"), []).append(b["stability"])
    out["_meta"] = {
        "runs": runs, "seed": seed, "unit": "source", "sources": len(src_ids),
        "interval": "5-95%", "models": len(out), "models_total": len(ev["parts"]),
        "no_evidence": sorted(k for k in ev["parts"] if k not in out),
        "width_med_p": round(statistics.median([b["P_hi"] - b["P_lo"] for b in out.values()]), 3),
        "width_med_x": round(statistics.median([b["X_hi"] - b["X_lo"] for b in out.values()]), 3),
        "stability_med": round(statistics.median([b["stability"] for b in out.values()]), 3),
        # 分档报告：混在一起的中位数会被 M0/M3 那两头（一侧无界 + 区间退化的单源模型）抬起来
        "stability_by_tier": {t: {"n": len(v), "med": round(statistics.median(v), 3),
                                  "min": round(min(v), 3)} for t, v in sorted(by_tier.items())},
        "presence_med": round(statistics.median([b["presence"] for b in out.values()]), 3),
        "low_presence": sorted(k for k, b in out.items() if b["presence"] < 0.9),
        "degenerate": sorted(k for k, b in out.items()
                             if b["P_hi"] == b["P_lo"] and b["X_hi"] == b["X_lo"]),
        "sources_covered_mean": round(statistics.mean(cover), 1),
        "unstable": sorted(k for k, b in out.items() if b["stability"] < 0.5),
        "modal_differs": sorted(k for k, b in out.items() if b["modal_tier"] != point_tier.get(k))}
    return out


# ---------- 五、落盘 ----------
def plane_rows(st, ev, fits, boot=None):
    names, x2map = ev["names"], st["x2map"]
    plane = []
    for k, fit in fits.items():
        p, x = fit["p"], fit["x"]
        ps = fit["ps"]
        # 档位按**发布出来的三位小数坐标**判定。基准模型 P/X 按构造等于 1.0，但浮点解可能给
        # 0.99999999；直接拿原始值比阈值会让 1017 自己在 CSV 里显示成 "1.0 / M2"，
        # 读者无法核对，而且权重第 5 位小数的抖动就能翻档。
        P3, X3 = round(p, 3), round(x, 3)
        top = max(P3, X3)
        tier = tier_of(top)
        # 距下一档还差多少：档位带宽 0.25，差值只有 0.01 量级就说明是临界点
        nxt = {"M0": None, "M1": 1.25, "M2": 1.00, "M3": 0.70}[tier]
        gap = "" if nxt is None else round(max(0.0, nxt - top), 3)
        tag = ("P+" if P3 >= 1.25 else "") + ("X+" if X3 >= 1.25 else "") + ("0锚" if k == ZERO_KEY else "")
        rmap = {s: r for w, r, s, _f in ps}
        row = [names[k], k, P3, X3, tier, tag, "",
               round(fit["pcov"], 3), round(fit["xcov"], 3), round(fit["rmse"], 3), gap,
               f"{fit['lo']:.2f}~{fit['hi']:.2f}", fit["clamp"], fit["dw"],
               "+".join(s for _, _, s, _f in ps),
               round(x2map.get(k, -1), 1) if k in x2map else ""]
        row += [round(rmap[s], 3) if s in rmap else "" for s in ORDER]
        if boot is not None:
            b = boot.get(k)
            row += ([b["P_lo"], b["P_hi"], b["X_lo"], b["X_hi"], b["stability"], b["presence"],
                     b["modal_tier"]] if b else [""] * 7)
        else:
            row += [""] * 7          # 表头恒含这 7 列：下游不用同时伺候两种 schema
        plane.append(row)
    return plane


def plane_cols():
    """表头恒含 bootstrap 的 7 列（没跑 `--bootstrap` 就是空串）：
    列集合随开关变的话，下游每个读表的地方都要同时伺候两种 schema（迟早出错）。"""
    return (["model_id", "model_key", "P", "X", "tier", "tags", "axis_only",
             "P_coverage", "X_coverage", "fit_rmse", "next_tier_gap", "ratio_range", "clamped",
             "downweighted", "sources", "X2"] +
            ["r_" + s.replace("-", "_") for s in ORDER] + BOOT_COLS)


def write_evidence(st, ev, fits):
    zero_pen = st["zero_pen"]
    evf = open(os.path.join(OUT, "model_evidence.csv"), "w", newline="", encoding="utf-8-sig")
    cw = csv.writer(evf, lineterminator="\n")
    cw.writerow(["model_key", "model_id", "source_model", "source_id", "source", "axis",
                 "alpha_p", "grade", "weight", "weight_eff", "version", "date",
                 "raw", "anchor_raw", "ratio_raw", "zero_z", "ratio"])
    for (k, r, s, ax, alpha, a, ratio, base, z) in ev["ev_rows"]:
        idx = [i for i, (ww, rr, ss, _f) in enumerate(fits[k]["ps"]) if ss == s] if k in fits else []
        f = fits[k]["fac"].get(idx[0], 1.0) if idx else 1.0
        cw.writerow([k, r["name"], r.get("raw_name", r["name"]), s, SOURCES[s]["name"],
                     ax, alpha, SOURCES[s]["grade"], SOURCES[s]["w"],
                     round(SOURCES[s]["w"] * zero_pen.get(s, 1.0) * f, 4), r["version"],
                     r.get("date", r["version"]), round(r["value"], 2), round(a, 2),
                     round(base, 4), "" if z is None else round(z, 4), round(ratio, 4)])
    evf.close()


def arg_int(name, default):
    """命令行取整数：--flag 缺值或值不是数字就直接退出，别静默退回默认值
    （"以为跑了 1000 次其实跑了 0 次"是最难发现的那类错误）。"""
    if name not in sys.argv: return default
    i = sys.argv.index(name)
    if i + 1 >= len(sys.argv): raise SystemExit(f"{name} 缺参数值")
    try:
        return int(sys.argv[i + 1])
    except ValueError:
        raise SystemExit(f"{name} 的值不是整数：{sys.argv[i + 1]!r}")


def main():
    runs = arg_int("--bootstrap", 0)
    seed = arg_int("--boot-seed", BOOT_SEED)

    st = build()
    ev = evidence(st)
    fits = fit_all(ev)
    write_evidence(st, ev, fits)

    point_tier = {k: tier_of(max(round(f["p"], 3), round(f["x"], 3))) for k, f in fits.items()}
    boot = None
    if runs:
        import time
        t0 = time.time()
        boot = bootstrap(ev, point_tier, runs, seed)
        meta = boot["_meta"]
        # 点估计必须落在自己的 5~95 区间里；不落就是实现有问题（分位数取法、缺次数的分母、
        # 重采样与点估计不同路径），当场数出来并写进产物，别等读者发现
        outside = []
        for k, f in fits.items():
            b = boot.get(k)
            if not b: continue
            P3, X3 = round(f["p"], 3), round(f["x"], 3)
            if not (b["P_lo"] - 1e-9 <= P3 <= b["P_hi"] + 1e-9): outside.append(f"{k}:P")
            if not (b["X_lo"] - 1e-9 <= X3 <= b["X_hi"] + 1e-9): outside.append(f"{k}:X")
        meta["outside_band"] = outside
        st["metrics"]["bootstrap"] = {k: meta[k] for k in meta}
        print(f"bootstrap：{meta['runs']} 次 × {meta['models_total']} 个模型"
              f"（重采样单位={meta['unit']}，{meta['sources']} 个源，seed={meta['seed']}，"
              f"区间 {meta['interval']}），耗时 {time.time() - t0:.0f}s")
        print(f"  每次重采样平均在场 {meta['sources_covered_mean']} 个源（不是 27 个）；"
              f"区间宽度中位 P {meta['width_med_p']} / X {meta['width_med_x']}（一档带宽 0.25）")
        print("  档位稳定率（分母=全部重采样）中位 " + f"{meta['stability_med']}" + "，分档：" +
              "、".join(f"{t} {v['med']:.2f}(n={v['n']})" for t, v in meta["stability_by_tier"].items()))
        print(f"  稳定率 <0.5 的 {len(meta['unstable'])} 个；多数派与点估计不同的 {len(meta['modal_differs'])} 个；"
              f"证据在场率 <90% 的 {len(meta['low_presence'])} 个；区间退化（宽度 0）的 {len(meta['degenerate'])} 个；"
              f"点估计落在自己区间外的 {len(meta['outside_band'])} 处")
        worst = sorted((k for k in boot if k != "_meta"), key=lambda k: boot[k]["stability"])[:5]
        for k in worst:
            b = boot[k]
            print(f"  最不稳：{ev['names'][k]:24s} {point_tier[k]}（多数派 {b['modal_tier']}）"
                  f" 稳定率 {b['stability']:.2f} 在场 {b['presence']:.2f}"
                  f"  P [{b['P_lo']}~{b['P_hi']}] X [{b['X_lo']}~{b['X_hi']}]")

    plane = plane_rows(st, ev, fits, boot)
    pl = open(os.path.join(OUT, "model_plane.csv"), "w", newline="", encoding="utf-8-sig")
    cw = csv.writer(pl, lineterminator="\n"); cw.writerow(plane_cols())
    for r in sorted(plane, key=lambda x: (-x[2], -x[3])): cw.writerow(r)
    pl.close()
    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as mf:
        json.dump(st["metrics"], mf, ensure_ascii=False, indent=1)

    print(f"\nplane={len(plane)} tiers={dict(Counter(r[4] for r in plane))}")
    print("基准分（各源各版本）：", {f"{k[0]}@{k[1]}": round(v, 2) for k, v in st["anchor_of"].items()})


if __name__ == "__main__":
    main()
