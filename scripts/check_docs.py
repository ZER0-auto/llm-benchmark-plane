# -*- coding: utf-8 -*-
"""文档 ↔ 产物一致性自检（METHOD / README 里凡是跟着运行变的数字）。

为什么要有这个脚本：2026-10-26 清扫时发现 README / METHOD 里一大批"本轮 X"的数字与 `out/`
不符，而且过期了很久没人发现（钳位写 5 实际 20、P_sec 写 0.9291/0.5668 实际另一套、
校准写第 6 轮实际第 5 轮）。约定是"文档数字必须由产物生成"，那就得有个东西来证明它确实等于产物。

做法：每个事实先从 `sources.csv` / `out/*` 算出来，再要求文档里出现那段渲染好的文本。
所以这里比对的是**文档文本**，不是"产物等于我脑子里的常数"——数据一重跑，
文档没跟着改，这里就会 FAIL 并打印出应有的文本。

用法：
  python scripts/check_docs.py            # 跑完 pipeline / calibrate / bl_compare 之后自检
退出码：0 = 全部一致；1 = 有不符（逐项打印"应有的文本"）。
"""
import csv, json, os, re, statistics, sys
from collections import Counter

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANES = {}
checks = []


def read(*p):
    return open(os.path.join(BASE, *p), encoding="utf-8-sig").read()


def rows(*p):
    return list(csv.DictReader(read(*p).splitlines()))


def minus(s):
    """负号统一成文档里用的 U+2212（CSV 里是 ASCII '-'）。"""
    return str(s).replace("-", "−")


def need(label, doc_text, needle, docname):
    checks.append((needle in doc_text, f"{docname} · {label}", needle, "在文档里" if needle in doc_text else "文档里没有这段文本"))


def eq(label, want, got):
    checks.append((str(want) == str(got), label, want, got))


def main():
    plane = rows("out", "model_plane.csv")
    ev = rows("out", "model_evidence.csv")
    met = json.loads(read("out", "metrics.json"))
    cal = json.loads(read("out", "weight_calibration.json"))
    src = rows("sources.csv")
    rd, mt = read("README.md"), read("METHOD.md")
    bl = rows("out", "bl_crosscheck_sources.csv")
    cand = rows("sources_bl_candidates.csv")
    blrows = rows("data", "bl", "bl_rows.csv")
    aarows = rows("data", "aa", "aa_rows.csv")

    def wcal(r): return float(r["weight_cal"] or 0)
    drop = list(met["dropped"])
    live = [r for r in src if r["status"] in ("active", "guarded") and r["id"] not in drop]
    drawn = [r for r in plane if float(r["P"]) >= 0 and float(r["X"]) >= 0]
    thin = [r for r in plane if float(r["P_coverage"]) < .35 and float(r["X_coverage"]) < .35]
    ns = [len(r["sources"].split("+")) for r in plane]
    pc = [float(r["P_coverage"]) for r in plane]
    xc = [float(r["X_coverage"]) for r in plane]
    tiers = Counter(r["tier"] for r in plane)
    corr = "%.2f" % statistics.correlation([float(r["P"]) for r in plane], [float(r["X"]) for r in plane])
    withm3 = {r["source_id"] for r in ev if r["model_key"] == "minimaxm3"}
    live_ids = [r["id"] for r in live]
    n_with = len([i for i in live_ids if i in withm3])
    n_wo = len(live_ids) - n_with
    tot_w = sum(wcal(r) for r in live)
    share = sum(wcal(r) for r in live if r["public"] == "public") / tot_w
    clamped = sum(1 for r in plane if r["clamped"] == "1")
    single = sum(1 for x in ns if x == 1)
    zz, zskip = met["zero_z"], met["zero_skip_z"]
    sec = met["sec"]
    near = "、".join(f"{s} {met['chained'][s]['equiv']:.2f}" for s in met["near_ceiling"])

    # ---------- README：快照段 ----------
    need("快照总数/上图/负坐标/档位/相关/来源/平均来源", rd,
         f"{len(plane)} 个模型，其中 **{len(drawn)} 个画在图上**（另 {len(plane) - len(drawn)} 个坐标为负，"
         f"只进下方数据表），档位分布 **M0 {tiers['M0']} / M1 {tiers['M1']} / M2 {tiers['M2']} / M3 {tiers['M3']}**。"
         f"P 与 X 的相关系数 {corr}。计分来源 {len(live)} 个"
         f"（私有 {sum(1 for r in live if r['public'] == 'private')}、公开 {sum(1 for r in live if r['public'] == 'public')}），"
         f"平均每个模型 {sum(ns) / len(ns):.1f} 个来源。", "README")
    for tier in ("M0", "M1"):
        rs = sorted([r for r in plane if r["tier"] == tier], key=lambda r: -max(float(r["P"]), float(r["X"])))
        need(f"{tier} 坐标表", rd,
             "| %s | %s |" % (tier, "、".join(f"{r['model_id']} ({r['P']}/{r['X']})" for r in rs)), "README")
    # ---------- README：口径摘要与已知限制 ----------
    need("两点归一/只降权/无 M3 计数", rd,
         f"{len(zz)} 个源做两点归一；零点过高（z>0.75）的 {len(zskip)} 个源只降权不修正；没有 MiniMax-M3 的 {n_wo} 个源保持单点比值", "README")
    need("钳位点数", rd, f"本轮钳位 {clamped} 个点", "README")
    need("公开源占比", rd, f"公开源占比按上限 0.20 配平（本轮 {share:.2f}）", "README")
    need("副锚因子", rd, f"（本轮 P {sec['P']:.4f} / X {sec['X']:.4f}）", "README")
    need("守卫剔除名单", rd, "本轮剔除：" + "、".join(drop), "README")
    need("证据薄计数", rd,
         f"两轴覆盖度都 <35% 的模型有 {len(thin)} 个（其中 {len([r for r in thin if r in drawn])} 个在图上", "README")
    need("单源模型数", rd, f"{single} 个模型只有一个来源", "README")
    need("near_ceiling 名单", rd, f"（本轮 `near_ceiling`：{near}）", "README")
    need("屎山等效基准", rd, f"（本轮等效基准 {met['chained']['shishan']['equiv']:.2f}）", "README")
    n_slug = len({r["model_slug"] for r in aarows})
    aa_map = len(re.findall(r'^\s*"[^"]+":\s*"', open(os.path.join(BASE, "scripts", "aa_map.py"), encoding="utf-8").read().split("AA_UNMAPPED")[0], re.M))
    need("AA 覆盖 slug 数", rd, f"**Artificial Analysis 覆盖 {aa_map} 个模型**：抓取端有 {n_slug} 个 slug", "README")
    need("平均覆盖度", rd, f"平均覆盖 P {sum(pc) / len(pc):.2f} / X {sum(xc) / len(xc):.2f}", "README")
    need("零点成立范围", rd,
         f"**零点只在 {n_with} 个源上成立**：其中 {len(zz)} 个做两点归一、{len(zskip)} 个 z>0.75 只降权；其余 {n_wo} 个源仍是单点归一", "README")
    need("当前档位分布（限制 12）", rd, f"本轮补上 AA 漏映射后是 M2 {tiers['M2']} / M3 {tiers['M3']}", "README")
    gaps = sorted([r for r in plane if r["next_tier_gap"]], key=lambda r: float(r["next_tier_gap"]))
    nxt = {"M0": None, "M1": "M0", "M2": "M1", "M3": "M2"}[gaps[0]["tier"]]
    need("最紧临界点", rd, f"当前最紧的是 {gaps[0]['model_id']} 差 {float(gaps[0]['next_tier_gap']):.3f} 到 {nxt}", "README")

    used = [s for s in bl if s["status"] == "对照"]
    publ = Counter(s["publisher"].replace("www.", "") for s in used)
    top3 = [k for k, _ in publ.most_common(3)]
    cw = {r["id"]: float(r["weight_prior"]) for r in cand}
    bl_tot = sum(cw[s["source_id"]] for s in used)
    bl_kimi = sum(cw[s["source_id"]] for s in used if s["publisher"].replace("www.", "") in top3[:1])
    snap_ids = {r["snapshot_id"] for r in blrows if r.get("snapshot_id")}
    gpqa = next(s for s in used if s["source_id"] == "gpqa_diamond_epoch")
    need("BL 候选/可用/三事件/自报/GPQA", rd,
         f"{len(bl)} 个候选里 {len(used)} 个能凑出“含锚点 + 映射后 ≥5 个模型”的快照，可用源里 {sum(publ[k] for k in top3)} 个来自同三个发布事件"
         f"（{'、'.join(f'{k} {publ[k]} 个' for k in top3)}），"
         f"{sum(1 for s in used if float(s['self_share']) > 0)} 个的快照里混着厂商自报行；连 GPQA Diamond 这种全量榜，"
         f"BL 的快照也只有 {gpqa['rows']} 行（榜上 {next(r['models'] for r in cand if r['id'] == 'gpqa_diamond_epoch')} 个模型），"
         f"映射到 {gpqa['mapped']} 个。", "README")

    # ---------- METHOD ----------
    need("§3 M3 在场源数", mt, f"（{len(live)} 个计分源里 {n_with} 个有它）", "METHOD")
    need("§3 两点归一轮数", mt, f"做上面的两点归一（本轮 {len(zz)} 个源）", "METHOD")
    zlist = sorted(zskip.items(), key=lambda kv: (-kv[1], kv[0]))
    need("§3 z>0.75 名单", mt, f"- `z_s > 0.75` 的 {len(zlist)} 个源（" +
         "、".join(f"{s} {z:.2f}" for s, z in zlist) + "）：", "METHOD")
    need("§3 无 M3 源数", mt, f"- 没有 MiniMax-M3 的 {n_wo} 个源（", "METHOD")
    need("§4 权重汇总", mt,
         f"当前进回归 {len(live)} 个来源（私有 {sum(1 for r in live if r['public'] == 'private')}、"
         f"公开 {sum(1 for r in live if r['public'] == 'public')}；另有 {len(drop)} 个登记在册但被守卫剔除），"
         f"`weight_cal` 合计 {tot_w:.2f}，公开源占比 {share:.3f}（上限 0.20）", "METHOD")
    for r in sorted([r for r in src if r["status"] in ("active", "guarded")], key=lambda r: (-wcal(r), r["name"])):
        need(f"§4 权重表 {r['name']}", mt,
             "| %s | %.3f | %.2f | %.2f | %s | %s | %s | %s | %s |" % (
                 r["name"], wcal(r), float(r["weight_prior"]), float(r["alpha_p"]), r["grade"],
                 "私有" if r["public"] == "private" else "公开",
                 "1017" if r["anchor"] == "1017" else "链式",
                 ("%.2f" % zz[r["id"]]) if r["id"] in zz else "",
                 "剔除" if r["id"] in drop else "计分"), "METHOD")
    need("§6 副锚因子", mt, f"P_sec = {sec['P']:.4f}    X_sec = {sec['X']:.4f}", "METHOD")
    ch = sorted(met["chained"].items(), key=lambda kv: (-kv[1]["equiv"], kv[0]))
    sname = {r["id"]: r["name"] for r in src}
    need("§6 链式榜数量", mt, f"本轮全部 {len(ch)} 个链式榜", "METHOD")
    for s, v in ch:
        need(f"§6 链式表 {s}", mt, "| %s | %.2f | %.4f | %.2f | %.2f |" % (
            sname[s], v["alpha"], v["r_anchor"], v["sec_raw"], v["equiv"]), "METHOD")
    need("§7 钳位点数", mt, f"本轮被钳位 {clamped} 个点", "METHOD")
    g6 = next(r for r in plane if r["model_key"] == "gpt6astra")
    need("§7 GPT-6 Astra 比值域", mt, f"GPT-6 Astra 的观测比值跨 {minus(g6['ratio_range'])}", "METHOD")
    need("§11 屎山等效基准", mt, f"等效基准 {met['chained']['shishan']['equiv']:.2f} 属于正常", "METHOD")
    need("§11 本轮剔除与接近满分", mt,
         "本轮结果：剔除 " + "、".join(f"{s}（等效基准 {met['dropped'][s]:.2f}" for s in drop[:1]) +
         f" > 满分）、srebench（{met['dropped'].get('srebench', 0):.2f}，不足满分 5%）"
         "、terminal-bench-science（副锚点原始分 0）；接近满分 " + near + "。", "METHOD")
    need("§12 证据薄计数", mt, f"两轴覆盖度都 < 35%（本轮 {len(thin)} 个模型，其中 {len([r for r in thin if r in drawn])} 个在图上）", "METHOD")
    need("§12 图上点数", mt, f"本轮图上一共 {len(drawn)} 个点", "METHOD")
    need("§12 负坐标数", mt, f"（{len(plane) - len(drawn)} 个，低于零点 MiniMax-M3）", "METHOD")
    need("§13 单源模型数", mt, f"2. **单一来源模型的位置是假设值**：{single} 个模型只有一个来源", "METHOD")
    need("§13 平均覆盖度", mt, f"（平均 P {sum(pc) / len(pc):.2f}、X {sum(xc) / len(xc):.2f}）", "METHOD")
    need("§13 GPT-6 Astra 明细", mt,
         f"GPT-6 Astra 观测比值 {minus(g6['ratio_range'])}，加权拟合 RMSE {g6['fit_rmse']}", "METHOD")
    need("§15 收敛轮", mt, f"当前从初猜出发第 {cal['converged_at']} 轮收敛", "METHOD")
    tc = cal["tier_changed_vs_prior"]
    moves = ["vibe-code", "logic", "code-migration-v1-1", "shishan"]
    need("§15 换档与权重变动", mt,
         f"初猜 → 校准：{len(tc)} 个模型换档（{100 * len(tc) / len(plane):.0f}%）：" + "、".join(tc) +
         "。最大权重变动是 " + "、".join(f"{s} {float(next(r['weight_prior'] for r in src if r['id'] == s)):.2f}→"
                                        f"{float(next(r['weight_cal'] or 0 for r in src if r['id'] == s)):.3f}" for s in moves), "METHOD")
    need("§15 扰动验证", mt,
         f"权重 ±{int(cal['perturb_rel'] * 100)}% 随机扰动（{cal['perturb_runs']} 次）：平均 {cal['perturb_flips_mean']:.1f} 个模型换档"
         f"（最少 {cal['perturb_flips_min']}、最多 {cal['perturb_flips_max']}）", "METHOD")

    def rng(sid):
        v = [float(r["ratio"]) for r in ev if r["source_id"] == sid]
        return minus("%.2f~%.2f" % (min(v), max(v)))
    need("§15 区分度名单与比值区间", mt,
         f"legal_bench（比值 {rng('legal_bench')}）与 aa_lcr（{rng('aa_lcr')}）掉到 0.01 以下；"
         f"proof_bench（{rng('proof_bench')}）、mysterymechanism（{rng('mysterymechanism')}）这类散布宽的榜上升", "METHOD")
    k = {r["model_key"]: r for r in plane}
    need("§16 相关系数与两例", mt,
         f"P/X 相关系数 {corr}；例如 Mistral Large 4 是 P {k['mistrallarge4']['P']} / X {k['mistrallarge4']['X']}，"
         f"Kimi-K3 是 P {k['kimik3']['P']} / X {k['kimik3']['X']}", "METHOD")
    need("§4.1 BL 抓取规模", mt,
         f"BL）的 {len(bl)} 个候选榜现已全部抓回（{len(blrows)} 行、{len(snap_ids)} 份快照）", "METHOD")
    need("§4.1 BL 可用/弃用", mt, f"可用 {len(used)} 个、弃用 {len(bl) - len(used)} 个", "METHOD")
    need("§4.1 发布方集中度", mt, f"里 {sum(publ[x] for x in top3)} 个来自同三个发布事件", "METHOD")
    need("§4.1 名义权重接入占比", mt,
         f"{len(used)} 个源合计 {bl_tot:.2f}、占 {bl_tot / (bl_tot + tot_w):.1%}，"
         f"其中 kimi.ai 一家 {bl_kimi:.2f}（{bl_kimi / (bl_tot + tot_w):.1%}）", "METHOD")
    nsat = sum(1 for s in used if s["ratio_spread"] and float(s["ratio_spread"]) < 0.15)
    need("§4.1 饱和源数", mt, f"{len(used)} 个可用源里 {nsat} 个的观测比值跨度 < 0.15", "METHOD")

    # ---------- 源级 bootstrap（METHOD §17 / README 口径摘要与限制 14） ----------
    bt = met.get("bootstrap")
    has_cells = any(r["tier_stability"] for r in plane)
    eq("bootstrap 开关与产物一致（metrics 有则表里必须有值，反之必须空）", bool(bt), has_cells)
    if bt:
        need("§17 规模与在场", mt,
             f"本轮（{bt['runs']} 次、seed={bt['seed']}、{bt['sources']} 个源，每次平均只有 "
             f"{bt['sources_covered_mean']} 个源在场）：{bt['models']} 个模型全部算出区间；"
             f"区间宽度中位 P {bt['width_med_p']} / X {bt['width_med_x']}", "METHOD")
        byt = "、".join(f"{t} {v['med']:.3f}（n={v['n']}）" for t, v in bt["stability_by_tier"].items())
        need("§17 分档稳定率", mt,
             f"分档看是：{byt}，全表中位 {bt['stability_med']}。", "METHOD")
        need("§17 名单", mt,
             f"稳定率 <0.5 的 {len(bt['unstable'])} 个（{'、'.join(bt['unstable'])}）；"
             f"多数派与标出档位不同的 {len(bt['modal_differs'])} 个", "METHOD")
        for k in bt["modal_differs"]:
            r = next(x for x in plane if x["model_key"] == k)
            need(f"§17 {k} 的多数派", mt, f"{r['model_id']} 标 {r['tier']}、多数派 {r['tier_mode']}", "METHOD")
        need("§17 在场率与退化", mt,
             f"证据在场率 <90% 的有 {len(bt['low_presence'])} 个模型，区间退化（宽度 0）的也是 {len(bt['degenerate'])} 个",
             "METHOD")
        a = next(r for r in plane if r["model_key"] == "deepseekv4.1flash1017")
        need("§17 1017 是同义反复而不是自检", mt,
             f"基准模型 1017 的区间同样是 {a['P_lo']}~{a['P_hi']}", "METHOD")
        eq("§17 点估计必须落在自己的区间内（outside_band 应为空）", [], bt.get("outside_band"))
        eq("§17 每个模型都有区间（no_evidence 应为空）", [], bt.get("no_evidence"))
        need("README 口径摘要 bootstrap", rd,
             f"源级 bootstrap（{bt['sources']} 个计分源有放回抽 {bt['runs']} 次，seed={bt['seed']}）给出 "
             f"P_lo / P_hi / X_lo / X_hi（{bt['interval']}）、tier_stability、tier_presence、tier_mode；"
             f"区间宽度中位 P {bt['width_med_p']} / X {bt['width_med_x']} 比一档带宽（0.25）还宽，"
             f"档位稳定率中位只有 {bt['stability_med']}", "README")
        worst = min([r for r in plane if r["tier_stability"]], key=lambda r: float(r["tier_stability"]))
        need("README 最不稳模型", rd,
             f"全场最低的 {worst['model_id']} 是 {worst['tier_stability']}（多数派 {worst['tier_mode']}）", "README")
        need("README 限制 14 在场率", rd,
             f"另有 {len(bt['low_presence'])} 个模型的证据在场率低于 90%", "README")
        # 文档里承诺的 bootstrap 列名必须真的在表头里（表头与文档脱钩是最容易发生的一种漂移）
        header = list(plane[0].keys())
        for col in ("P_lo", "P_hi", "X_lo", "X_hi", "tier_stability", "tier_presence", "tier_mode"):
            eq(f"表头含 {col}", True, col in header)
            need(f"README 列清单含 {col}", rd, col, "README")

    # ---------- BL 弃用原因（§4.1 的括号必须与产物的 reason 字段同一口径） ----------
    rej = [s for s in bl if s["status"] != "对照"]
    ns = {re.search(r"只有 (\d+) 个", s["note"]).group(1) for s in rej if re.search(r"只有 (\d+) 个", s["note"])}
    if len(ns) == 1:
        need("§4.1 弃用源与原因", mt, "（" + "、".join(s["name"] for s in rej) +
             f"：含锚点的快照只有 {ns.pop()} 个平面里有坐标的模型）", "METHOD")
    else:
        checks.append((False, "§4.1 弃用原因不是同一个口径", "所有弃用源同一句话", sorted(ns)))

    # ---------- 不动点（out/settle.json ↔ METHOD §15） ----------
    spath = os.path.join(BASE, "out", "settle.json")
    if os.path.exists(spath):
        se = json.loads(read("out", "settle.json"))
        eq("settle 已到不动点", True, se["converged"])
        need("§15 不动点轮数", mt, f"实测第 {se['rounds']} 轮即不动", "METHOD")
        m = re.search(r"直到 `max\|Δw\| < ([0-9.eE+\-]+)`", mt)
        eq("§15 容差与 settle.json 一致", se["tol"], float(m.group(1)) if m else None)
    else:
        print("  提示 out/settle.json 不存在：本轮没跑 settle_weights.py，"
              "无法证明基线在不动点上（改过权重或数据后必须跑）")

    bad = [c for c in checks if not c[0]]
    for ok, label, want, got in checks:
        if not ok:
            print(f"  FAIL {label}\n       应为：{want}\n       文档：{got}")
    print(f"文档 ↔ 产物断言 {len(checks) - len(bad)} / {len(checks)} 通过")
    if bad:
        print("有不符项：把上面「应为」的文本抄进文档，或修脚本；不要反向改产物去迁就文档。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
