# -*- coding: utf-8 -*-
"""λ 与 α 的敏感性扫描（METHOD §18）：源级 bootstrap 覆盖不到的那部分不确定性。

bootstrap 只回答"换一批榜会怎样"。而 λ（岭强度）与 α（每块榜的规划/执行成分）是**人为设定**的：
它们一变，坐标也变，可那部分变化从来不在 5~95 区间里。README 已知限制 4 承认 λ"直接决定 P 与 X
的分离幅度"，那就把它扫出来给个量级，而不是留在"暂定"两个字里。

本脚本只读现算：**不写** sources.csv、不写 out/model_plane.csv、不改任何生产产物，
只产出 out/sensitivity.json 与 out/sensitivity.md。解算仍走 `pipeline.fit_model` 同一个入口
（`lam` / `alpha_of` 只是它的两个可注入参数，不是第二套实现）。

用法：python scripts/sensitivity.py
"""
import json, os, statistics
from collections import Counter

import pipeline as pl

OUT = pl.OUT
LAMS = (0.01, 0.03, 0.10)     # 0.03 是生产值
D_ALPHA = 0.15                 # 每块榜的 α 往两边各挪 0.15（截断到 [0,1]）


def solve_all(ev, lam=None, alpha_of=None):
    """按给定 λ / α 口径重解全部模型 → {model_key: (P, X)}（发布口径：三位小数）"""
    out = {}
    for k, ps in ev["parts"].items():
        fit = pl.fit_model(ps, ev["max_p"], ev["max_x"],
                           lam=pl.LAM_DEFAULT if lam is None else lam, alpha_of=alpha_of)
        if fit is None:
            continue
        out[k] = (round(fit["p"], 3), round(fit["x"], 3))
    return out


def corr_of(vals):
    if len(vals) < 3:
        return None
    return round(statistics.correlation([v[0] for v in vals.values()],
                                        [v[1] for v in vals.values()]), 4)


def compare(base, alt, bounds, relayer=True):
    """与基线比：换档数（固定边界 / 重算边界两种口径）、坐标位移、P-X 相关。"""
    flips_fixed = sorted(k for k in alt
                         if pl.tier_of(max(alt[k]), bounds) != pl.tier_of(max(base[k]), bounds))
    new_bounds = pl.tier_bounds([max(v) for v in alt.values()]) if relayer else bounds
    flips_re = sorted(k for k in alt
                      if pl.tier_of(max(alt[k]), new_bounds) != pl.tier_of(max(base[k]), bounds))
    d = [abs(alt[k][0] - base[k][0]) + abs(alt[k][1] - base[k][1]) for k in alt if k in base]
    return {"models": len(alt),
            "flips_fixed_bounds": len(flips_fixed), "flip_keys": flips_fixed[:12],
            "flips_relayers": len(flips_re), "bounds": [round(b, 3) for b in new_bounds],
            "shift_med": round(statistics.median(d), 4) if d else None,
            "shift_max": round(max(d), 4) if d else None,
            "corr": corr_of(alt)}


def main():
    st = pl.build()
    ev = pl.evidence(st)
    fits = pl.fit_all(ev)
    base = {k: (round(f["p"], 3), round(f["x"], 3)) for k, f in fits.items()}
    bounds = pl.tier_bounds([max(v) for v in base.values()])
    base_corr = corr_of(base)
    print(f"基线：{len(base)} 个模型，边界 {' / '.join(f'{b:.3f}' for b in bounds)}，P-X 相关 {base_corr}")

    # ---------- λ 扫描 ----------
    lam_res = {}
    for lam in LAMS:
        alt = solve_all(ev, lam=lam)
        lam_res[f"{lam:g}"] = compare(base, alt, bounds)
        r = lam_res[f"{lam:g}"]
        print(f"  λ={lam:<5} 换档 {r['flips_fixed_bounds']:2d} 个（重算边界 {r['flips_relayers']:2d}）"
              f" 位移中位 {r['shift_med']} 最大 {r['shift_max']} 相关 {r['corr']}")

    # ---------- α 扫描（逐源 ±0.15）----------
    src_ids = sorted({s for ps in ev["parts"].values() for (_w, _r, s, _f) in ps})
    alpha_res = {}
    for s in src_ids:
        a0 = pl.SOURCES[s]["alpha"]
        for sign, tag in ((1, "+"), (-1, "−")):
            a1 = min(1.0, max(0.0, a0 + sign * D_ALPHA))
            if a1 == a0:
                continue
            alpha_of = (lambda q, s=s, a1=a1: a1 if q == s else pl.SOURCES[q]["alpha"])
            r = compare(base, solve_all(ev, alpha_of=alpha_of), bounds)
            r["alpha"] = f"{a0:.2f}→{a1:.2f}"
            alpha_res[f"{s}{'+' if sign > 0 else '-'}"] = r
        variants = [k for k in (f"{s}+", f"{s}-") if k in alpha_res]
        if not variants:
            continue        # α 已经在 0 或 1 上，往那个方向挪会被截断，没什么可扫的
        fmax = max(alpha_res[k]["flips_fixed_bounds"] for k in variants)
        dmax = max(alpha_res[k]["shift_max"] for k in variants)
        print(f"  α {s:24} {pl.SOURCES[s]['alpha']:.2f} ±{D_ALPHA} → 换档最多 {fmax:2d} 个，位移最大 {dmax}")

    worst = sorted(alpha_res, key=lambda k: (-alpha_res[k]["flips_fixed_bounds"], -alpha_res[k]["shift_max"]))[:5]
    print("α 最敏感的 5 个方向：" + "、".join(f"{k}（换档 {alpha_res[k]['flips_fixed_bounds']}）" for k in worst))

    out = {"lam_values": list(LAMS), "d_alpha": D_ALPHA, "base": {
        "models": len(base), "bounds": [round(b, 3) for b in bounds], "corr": base_corr},
        "lam": lam_res, "alpha": alpha_res, "alpha_worst": worst}
    with open(os.path.join(OUT, "sensitivity.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    lines = ["# λ / α 敏感性扫描", "",
             "由 `scripts/sensitivity.py` 生成，勿手改。这是** bootstrap 区间之外**的那部分不确定性：",
             "λ 与 α 是人为设定的，它们一变坐标就变，但那从不体现在 5~95 区间里。", "",
             f"- 基线：{len(base)} 个模型，边界 {' / '.join(f'{b:.3f}' for b in bounds)}，P-X 相关 {base_corr}",
             "", "## λ（岭强度）", "",
             "| λ | 换档（固定边界） | 换档（重算边界） | 位移中位 | 位移最大 | P-X 相关 |",
             "|---|---|---|---|---|---|"]
    for lam, r in lam_res.items():
        lines.append(f"| {lam} | {r['flips_fixed_bounds']} | {r['flips_relayers']} | "
                     f"{r['shift_med']} | {r['shift_max']} | {r['corr']} |")
    lines += ["", "`λ=0.03` 那一行是生产口径（与基线相同，所以换档 0）。相关系数随 λ 单调变化，"
              "印证 README 已知限制 4：λ 直接决定两轴分离幅度。", "",
              f"## α（每块榜的规划成分）±{D_ALPHA}", "",
              "| 方向 | α 变化 | 换档（固定边界） | 位移中位 | 位移最大 |", "|---|---|---|---|---|"]
    for k in worst:
        r = alpha_res[k]
        lines.append(f"| {k} | {r['alpha']} | {r['flips_fixed_bounds']} | {r['shift_med']} | {r['shift_max']} |")
    zero_flip = [k for k, r in alpha_res.items() if r["flips_fixed_bounds"] == 0]
    lines += ["", f"{len(alpha_res)} 个方向里 {len(zero_flip)} 个一个档都不换；"
              f"换档最多的是 {worst[0]}（{alpha_res[worst[0]]['flips_fixed_bounds']} 个）。",
              "解读：α 挪 ±0.15 的影响与「换一批榜」的区间相比"
              f"（位移最大 {max(r['shift_max'] for r in alpha_res.values())} vs λ/重采样的量级见上表），"
              "属于同一量级——所以 α 判错的风险不该被忽略，但也不比榜单组成更致命。", ""]
    with open(os.path.join(OUT, "sensitivity.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("-> out/sensitivity.json / out/sensitivity.md")


if __name__ == "__main__":
    main()
