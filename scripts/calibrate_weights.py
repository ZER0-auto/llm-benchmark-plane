# -*- coding: utf-8 -*-
"""权重校准（METHOD §15）：留一残差 + 可信度先验，迭代到收敛。

误差没有真值，用留一残差定义：把某个来源从模型的回归里拿掉，重解 P/X，
再预测该来源的比值，与实测比值的差就是这个来源的“不合群程度”。
可信度先验（级别 × 覆盖 × 新鲜度）除以该误差，作为权重的下一轮猜测。

用法：先跑 pipeline.py，再跑本脚本，然后重跑 pipeline.py（它会优先用 weight_cal）。

注意：本脚本读的证据比值本身依赖 weight_cal（链式榜的等效基准由带权的 P_sec/X_sec 折算，§6），
所以单独跑一次留下的是**一步之差**的不自洽基线。要自洽请用
`python scripts/settle_weights.py`（交替跑 calibrate → pipeline 直到权重不再变化）。
"""
import csv, io, json, math, os
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(BASE, "out", "model_evidence.csv")
SRC = os.path.join(BASE, "sources.csv")
REPORT = os.path.join(BASE, "out", "weight_calibration.csv")

TODAY = date(2026, 10, 25)
EPS = 0.05
PUBLIC_CAP = 0.20          # 公开源权重占比上限
SINGLE_CAP = 0.22          # 单个来源最多占总权重这么多，避免一榜独大
MAX_ITER = 20
MIN_SRC_PER_MODEL = 4      # 留一至少要剩下的源数（两因子要够解）
GRADE = {"A": 1.00, "A-": 0.90, "B+": 0.80, "B": 0.70, "C+": 0.55, "C": 0.40}


# 与管道共用同一个估计器（有界 + 按残差降权）与同一个判档实现，否则留一残差量的是另一套模型
from pipeline import fit_px_robust, ratio_bounds, tier_of, LAM_DEFAULT

# 岭强度只有管道那一处定义（本脚本原来另写了一份 LAM = 0.03，改 λ 时迟早漏改）
LAM = LAM_DEFAULT


def fit_px(items, lam=LAM, bounds=None):
    """与管道同一个估计器（有界 + 按残差降权），界也同一套取法。"""
    return fit_px_robust(items, lam, bounds=bounds)[:2]


def parse_date(s):
    try:
        y, m, d = (int(x) for x in s.strip()[:10].split("-"))
        return date(y, m, d)
    except Exception:
        return None


def spearman(x, y):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    n = len(x)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else 1.0


def main():
    src_rows = list(csv.DictReader(io.open(SRC, encoding="utf-8-sig")))
    meta = {r["id"]: r for r in src_rows if r["status"] in ("active", "guarded")}

    # 档位边界取自管道这一轮发布的 out/metrics.json（由 tier_bounds 从数据算出，不是写死的常数）。
    # 读不到就退出：没有边界就没法判"换档"，悄悄退回旧常数是最容易骗过人的那类错误。
    mpath = os.path.join(BASE, "out", "metrics.json")
    if not os.path.exists(mpath):
        raise SystemExit("缺 out/metrics.json：先跑 python scripts/pipeline.py 再跑权重校准")
    th = json.load(open(mpath, encoding="utf-8")).get("thresholds") or {}
    if not th.get("values"):
        raise SystemExit("out/metrics.json 里没有 thresholds.values（旧版管道写的固定常数？）："
                         "先跑 python scripts/pipeline.py 再跑校准")
    BOUNDS = tuple(th["values"])
    print("判档边界（来自 out/metrics.json，由数据算出）：", " / ".join(f"{b:+.3f}" for b in BOUNDS))

    # 逐模型证据
    per_model = {}
    per_src = {}
    for r in csv.DictReader(io.open(EVID, encoding="utf-8-sig")):
        sid = r["source_id"]
        if sid not in meta:
            continue
        try:
            ratio = float(r["ratio"])
        except ValueError:
            continue
        alpha = float(r["alpha_p"])
        per_model.setdefault(r["model_key"], []).append((sid, alpha, ratio, r["zero_z"] != ""))
        per_src.setdefault(sid, []).append(ratio)

    ids = sorted(per_src)
    n_src = {s: len(per_src[s]) for s in ids}

    # 可信度先验：级别 × 覆盖 × 新鲜度
    quality = {}
    for s in ids:
        g = GRADE.get((meta[s]["grade"] or "B").strip(), 0.7)
        cover = math.sqrt(n_src[s] / (n_src[s] + 8.0))
        d = parse_date(meta[s]["updated"] or "")
        age = (TODAY - d).days if d else 999
        fresh = 1.0 if age <= 14 else (0.9 if age <= 45 else 0.8)
        quality[s] = g * cover * fresh

    # 区分度：一个源自己的比值散布。只用“合群程度”当误差会奖励平庸的榜
    # （大家都差不多分的榜留一残差天然小），所以按 可信度 × 区分度 / 留一残差 定权。
    spread = {}
    for s in ids:
        v = per_src[s]
        m = sum(v) / len(v)
        spread[s] = math.sqrt(sum((x - m) ** 2 for x in v) / len(v))

    # 起点：注册表里的先验权重
    w = {s: float(meta[s]["weight_prior"]) for s in ids}   # 起点固定为先验，保证可复现
    total = sum(w.values())

    def bounds_of(items):
        z = [it[2] for it in items if it[3]]
        return ratio_bounds(z) if len(z) >= 4 else ratio_bounds([it[2] for it in items])

    def loo_errors(weights):
        """留一残差：每个源在多少模型上被其余源反驳。"""
        res = {s: [] for s in ids}
        for _, items in per_model.items():
            if len(items) < MIN_SRC_PER_MODEL:
                continue
            bd = bounds_of(items)
            for i, (sid, alpha, ratio, _f) in enumerate(items):
                rest = [(weights[sid2], a2, r2) for j, (sid2, a2, r2, _g) in enumerate(items) if j != i]
                p, x = fit_px(rest, LAM, bd)
                if p is None:
                    continue
                res[sid].append(ratio - (alpha * p + (1 - alpha) * x))
        err = {}
        for s in ids:
            v = res[s]
            err[s] = math.sqrt(sum(t * t for t in v) / len(v)) if v else float("nan")
        return err, res

    def composite(weights):
        out = []
        for _, items in per_model.items():
            num = sum(weights[s] * r for s, _a, r, _f in items)
            den = sum(weights[s] for s, _a, r, _f in items)
            if den:
                out.append(num / den)
        return out

    def normalize(weights):
        """保持总量不变：单源占比不超过 SINGLE_CAP，公开源占比不超过 PUBLIC_CAP。"""
        sc = total / sum(weights.values())
        v = {s: weights[s] * sc for s in ids}
        cap1 = SINGLE_CAP * total
        for s in ids:
            if v[s] > cap1:
                v[s] = cap1
        pub = [s for s in ids if meta[s]["public"] == "public"]
        pri = [s for s in ids if meta[s]["public"] != "public"]
        share = sum(v[s] for s in pub) / sum(v.values())
        if share > PUBLIC_CAP:
            base = sum(v.values())
            cap = PUBLIC_CAP * base
            f = cap / sum(v[s] for s in pub)
            for s in pub:
                v[s] *= f
            rest = base - cap
            fp = rest / sum(v[s] for s in pri)
            for s in pri:
                v[s] *= fp
        s2 = sum(v.values())
        return {s: x * total / s2 for s, x in v.items()}

    hist = []
    prev_composite = composite(w)
    prev_rmse = None
    converged = None
    for it in range(1, MAX_ITER + 1):
        err, _ = loo_errors(w)
        cand = {s: (quality[s] * spread[s] / (err[s] + EPS) if err[s] == err[s] else w[s]) for s in ids}
        w_new = normalize(cand)
        dmax = max(abs(w_new[s] - w[s]) for s in ids)
        comp = composite(w_new)
        rho = spearman(prev_composite, comp)
        rmse = math.sqrt(sum((c - p) ** 2 for c, p in zip(comp, prev_composite)) / len(comp))
        rel = (rmse / prev_rmse) if prev_rmse else (0.0 if rmse == 0 else 1.0)
        hist.append({"iter": it, "max_dw": round(dmax, 4), "spearman": round(rho, 5),
                     "shift": round(rmse, 5)})
        print(f"iter {it:2}  max|Δw|={dmax:.4f}  ρ={rho:.5f}  composite 位移={rmse:.5f}")
        w = w_new
        prev_composite = comp
        if prev_rmse is not None and dmax < 0.02 and rho > 0.995 and (rel < 0.02 or rmse < 1e-4):
            converged = it
            break
        prev_rmse = rmse

    err, res = loo_errors(w)

    # ---------- 验证：先验权重 vs 校准权重 ----------
    def pxtier(weights):
        out = {}
        for k, items in per_model.items():
            p, x = fit_px([(weights[s], a, r) for s, a, r, _f in items], LAM, bounds_of(items))
            if p is None:
                continue
            # 判档只用管道那一份实现 + 管道那一轮发布出来的边界（§8、§17）。
            # 原来这里自己写了一份 "top >= 1.25 …" 且用未取整的值，边界模型会与 CSV 的档位打架
            out[k] = tier_of(max(round(p, 3), round(x, 3)), BOUNDS)
        return out

    import random
    prior = {s: float(meta[s]["weight_prior"]) for s in ids}
    tp, tc = pxtier(prior), pxtier(w)
    tier_changed = sorted(k for k in tc if tp.get(k) != tc[k])
    random.seed(7)
    flips = []
    for _ in range(20):
        noisy = {s: w[s] * random.uniform(0.8, 1.2) for s in ids}
        tn = pxtier(noisy)
        flips.append(sum(1 for k in tn if tn[k] != tc[k]))
    print(f"\n验证：先验 → 校准，档位变化 {len(tier_changed)} 个模型：{', '.join(tier_changed)}")
    print(f"验证：权重 ±20% 扰动（20 次）平均档位翻转 {sum(flips)/len(flips):.1f} 个模型"
          f"（最少 {min(flips)}、最多 {max(flips)}）")

    # 写回注册表
    if "weight_cal" not in src_rows[0]:
        for r in src_rows:
            r["weight_cal"] = ""
    for r in src_rows:
        if r["id"] in w:
            r["weight_cal"] = f"{w[r['id']]:.4f}"
        elif r["status"] in ("active", "guarded"):
            # 进不了回归的源（守卫剔除 / 权重算不出来）不该留下一个数字：
            # 那会被读成"它有校准权重"。留空 = 它不参与加权。
            # （settle 默认会把 weight_cal 重置成 weight_prior，所以这里必须显式清掉）
            r["weight_cal"] = ""
    with io.open(SRC, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(src_rows[0].keys()))
        wr.writeheader(); wr.writerows(src_rows)

    with io.open(REPORT, "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["source_id", "name", "public", "grade", "models", "updated",
                     "quality", "spread", "loo_rmse", "w_prior", "w_cal", "delta"])
        for s in sorted(ids, key=lambda k: -w[k]):
            wr.writerow([s, meta[s]["name"], meta[s]["public"], meta[s]["grade"],
                         n_src[s], meta[s]["updated"], round(quality[s], 3),
                         round(spread[s], 3),
                         round(err[s], 4) if err[s] == err[s] else "",
                         float(meta[s]["weight_prior"]), round(w[s], 4),
                         round(w[s] - float(meta[s]["weight_prior"]), 4)])
    with open(os.path.join(BASE, "out", "weight_calibration.json"), "w", encoding="utf-8") as f:
        json.dump({"iterations": hist, "converged_at": converged,
                   "public_share": round(sum(w[s] for s in ids
                                             if meta[s]["public"] == "public") / total, 4),
                   "tier_changed_vs_prior": tier_changed,
                   "perturb_flips_mean": round(sum(flips) / len(flips), 2),
                   "perturb_flips_min": min(flips), "perturb_flips_max": max(flips),
                   "perturb_runs": len(flips), "perturb_rel": 0.20,
                   "lam": LAM, "eps": EPS, "public_cap": PUBLIC_CAP,
                   "single_cap": SINGLE_CAP}, f, ensure_ascii=False, indent=1)

    pub = sum(w[s] for s in ids if meta[s]["public"] == "public")
    print(f"\n来源 {len(ids)} 个 · 权重合计 {total:.2f} · 公开占比 {pub/total:.3f}"
          f" · 收敛 {'第 '+str(converged)+' 轮' if converged else '未收敛（已到上限）'}")
    print(f"{'source':24} {'n':>4} {'quality':>7} {'spread':>7} {'looRMSE':>7} {'prior':>6} {'cal':>6}")
    for s in sorted(ids, key=lambda k: -w[k]):
        e = err[s]
        print(f"{s:24} {n_src[s]:4} {quality[s]:7.3f} {spread[s]:7.3f} "
              f"{(f'{e:7.3f}' if e == e else '    nan')} {float(meta[s]['weight_prior']):6.3f} {w[s]:6.3f}")


if __name__ == "__main__":
    main()
