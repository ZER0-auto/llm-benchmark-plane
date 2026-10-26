# -*- coding: utf-8 -*-
"""BenchmarkList 交叉校验：BL 只作外部对照，**不参与拟合**。

为什么单独放一个脚本，而不是接进 pipeline（DECISIONS 2026-10-26）：
BL 的逐模型成绩基本来自厂商自己的发布稿（kimi.ai / minimax.io / x.com / mistral.ai），
同一篇博客会被拆成 6 个 benchmark 源、共用同一批 5~7 个模型。按项目口径
（"不做厂商自报榜单的加权平均"），这类数据不能进坐标；但它可以作为**外部对照**：
把 BL 观测到的比值和本项目已经解出的 P/X 预测值比一遍，看谁偏离、偏多少。

输入：
  data/bl/bl_rows.csv         fetch_bl.py 抓的快照（缺 snapshot_id 时按 version 分组）
  sources_bl_candidates.csv   候选源元信息（alpha_p / axis / name）
  out/model_plane.csv         当前平面（先跑 pipeline.py）
  out/metrics.json            链式副锚的 P/X（换算用，可缺）

输出：
  out/bl_crosscheck.csv          逐模型逐源的对照明细
  out/bl_crosscheck_sources.csv  逐源摘要（快照、模型数、自报占比、残差、弃用原因）
  out/bl_crosscheck.md           人读的汇总

用法：
  python scripts/bl_compare.py                     # 只生成 out/ 下的三份对照产物
  python scripts/bl_compare.py --update-registry   # 同时把 mapped_models / snapshot 回填候选清单

快照选择（与 pipeline 的"版本内必须含锚点"同源，排序键不同）：
  1. 只保留含主锚点（1017）或副锚点（次新 Flash）、锚点分 > 0、且映射后 ≥ MIN_MODELS 个模型的快照
     （锚点 0 分 = 该轮没测出东西，比值无定义，与 pipeline 的守卫同一条规则）
     门槛数的是**映射到的 key**（`mapped`）；其中平面里没有坐标的 key 过得了门槛却产不出残差，
     所以摘要另给 `in_plane`（= mapped 减去 ghost_keys）与 `ghost_keys`，别让「模型数」虚报样本量
  2. 同一 version 内出现"同 slug 同配置不同分"→ 该 version 是重复发布，整块弃用
     这一条只在旧数据（没有 snapshot_id、只能按天分组）上触发；新抓的数据按快照号分组，
     两份同日快照各自独立，挑一份用即可——比值在同一份表内自洽，不会再被 max 合并。
  3. 排序：日期新的优先 → 模型数多的优先 → 自报行占比低的优先 → snapshot_id 大的优先
     末级键不可省：同日两份快照若模型数与自报占比都相同，排序会退化成输入顺序，换次运行就可能换一份表。
     这里刻意保持"最新优先"（与 DECISIONS 2026-10-25「不取中位，只取最新值」一致）：
     上一版把"最新优先"和"含锚点 + ≥5 模型"捆在一起，结果 5 行的厂商小表会挤掉
     17 行的第三方大表；真正的修法是先剔掉重复发布的快照，而不是放弃最新优先。
     若将来要接进拟合，排序键必须再加一层"发布方聚簇"，否则同一篇厂商稿会被当成多条证据。
  4. 都没有 → 弃用，并把原因写进摘要

比值口径与 pipeline 对齐：主锚直接除；只有副锚的源先按 α 折算成"等效主锚"
（r = score / 副锚原分 × (α·P_sec + (1−α)·X_sec)）；榜上有 MiniMax-M3 时按
z≤0.75 做两点归一、z>0.75 只标注不修正。
"""
import csv, json, os, sys
from collections import Counter, defaultdict
from urllib.parse import urlparse

from bl_map import BL_MAP, BL_OVERRIDE, BL_SKIP

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "out")
ROWS = os.path.join(DATA, "bl", "bl_rows.csv")
CAND = os.path.join(BASE, "sources_bl_candidates.csv")
PLANE = os.path.join(OUT, "model_plane.csv")
METRICS = os.path.join(OUT, "metrics.json")

ANCHOR_KEY = "deepseekv4.1flash1017"
SECONDARY_KEY = "deepseekv4.1flash"
ZERO_KEY = "minimaxm3"
ZERO_APPLY_MAX = 0.75
MIN_MODELS = 5      # 与 pipeline.MIN_MODELS_PER_VERSION 保持一致

# 明细表的列顺序只定义一次：detail 是按位置 append 的列表，列名与位置一旦不同步，
# 汇总里的"涉及 N 个模型"这类计数就会静默算错（加 snapshot_id 列时踩过一次）。
DETAIL_COLS = ["source_id", "source_name", "publisher", "snapshot", "snapshot_id",
               "mapped_models", "self_share", "model_key", "model_name", "score",
               "anchor_kind", "anchor_used", "zero_z", "ratio", "pred", "residual", "note"]
COL = {c: i for i, c in enumerate(DETAIL_COLS)}


def load_rows():
    if not os.path.exists(ROWS):
        raise SystemExit(f"缺 {ROWS}，先跑 python scripts/fetch_bl.py")
    return list(csv.DictReader(open(ROWS, encoding="utf-8-sig")))


def load_candidates():
    reg = {}
    for r in csv.DictReader(open(CAND, encoding="utf-8-sig")):
        if not r.get("id"):
            continue
        reg[r["id"]] = {"name": r["name"], "axis": r["axis"],
                        "alpha": float(r["alpha_p"]) if r["alpha_p"].strip() else 0.5}
    return reg


def load_plane():
    if not os.path.exists(PLANE):
        raise SystemExit(f"缺 {PLANE}，先跑 python scripts/pipeline.py")
    return {r["model_key"]: {"p": float(r["P"]), "x": float(r["X"]), "tier": r["tier"]}
            for r in csv.DictReader(open(PLANE, encoding="utf-8-sig"))}


def load_sec():
    if not os.path.exists(METRICS):
        return {}
    return json.load(open(METRICS, encoding="utf-8")).get("sec") or {}


def key_of(r):
    if (r["model_slug"], r["model_name"]) in BL_SKIP:
        return None
    return BL_OVERRIDE.get((r["model_slug"], r["model_name"])) or BL_MAP.get(r["model_slug"])


def groups_of(rows):
    """按 snapshot_id 分组；没有这一列（旧数据）则退回按 version 分组。"""
    has_id = any(r.get("snapshot_id") for r in rows)
    g = defaultdict(list)
    for r in rows:
        # 续传抓取可能留下"部分行有 snapshot_id"的文件，空值退回 version，避免出现空分组
        g[(r.get("snapshot_id") if has_id else "") or r["version"]].append(r)
    return g, has_id


def is_duplicated(rows):
    """同一 version 内同 slug 同配置出现两个不同分数 → 两份快照被并成了一组。"""
    seen = defaultdict(set)
    for r in rows:
        seen[(r["model_slug"], r["raw_name"])].add(r["score"])
    return any(len(v) > 1 for v in seen.values())


def snapshot_candidates(rows, alpha, sec):
    """产出一个源的全部快照候选，附带可用性与排序键。"""
    groups, _has_id = groups_of(rows)
    cands = []
    for ver in sorted({r["version"] for r in rows}, reverse=True):
        picked = [g for g in groups.values() if g[0]["version"] == ver]
        for g in picked:
            by_key = {}
            for r in g:
                k = key_of(r)
                if not k:
                    continue
                try:
                    v = float(r["score"])
                except (TypeError, ValueError):
                    continue
                if k not in by_key or v > by_key[k][0]:
                    by_key[k] = (v, r)
            n = len(by_key)
            anchor = None
            # 锚点分必须 > 0：0 分说明该轮根本没测出东西，比值无定义——与 pipeline
            # 的"副锚点原始分为 0 → 丢弃"同一条规则。只判断 key 在不在，
            # 会让后面的 v / anchor 直接把整套对照打崩（ZeroDivisionError）。
            if ANCHOR_KEY in by_key and by_key[ANCHOR_KEY][0] > 0:
                anchor = ("primary", by_key[ANCHOR_KEY][0])
            elif SECONDARY_KEY in by_key and sec and by_key[SECONDARY_KEY][0] > 0:
                # 只有副锚：折算成"等效主锚"，否则比值与 P/X 不在同一尺度
                equiv = alpha * sec.get("P", 0) + (1 - alpha) * sec.get("X", 0)
                if equiv > 0:
                    anchor = ("secondary", by_key[SECONDARY_KEY][0] / equiv)
            cands.append({
                "version": ver,
                "snapshot_id": g[0].get("snapshot_id") or ver,
                "rows": g,
                "by_key": by_key,
                "n": n,
                "anchor": anchor,
                "self_share": sum(1 for r in g if r["self_reported"] == "1") / len(g),
                "publisher": urlparse(g[0].get("source_url") or "").netloc,
                # 单快照分组天然不会命中；按 version 分组的旧数据才会靠这条识别重复发布
                "dup": is_duplicated(g),
            })
    return cands


def pick(cands):
    ok = [c for c in cands if c["n"] >= MIN_MODELS and c["anchor"] and not c["dup"]]
    if not ok:
        return None
    # 最新 → 模型数多 → 自报占比低 → snapshot_id 大（同日两份快照里取后 ingest 的那份）。
    # 最后一级是必须的：前三键全等时排序会退化成"输入顺序"，同一份数据换次运行就可能换快照。
    return sorted(ok, key=lambda c: (c["version"], c["n"], -c["self_share"], c["snapshot_id"]),
                  reverse=True)[0]


def reason_of(cands):
    if not cands:
        return "无数据"
    with_anchor = [c for c in cands if c["anchor"]]
    if not with_anchor:
        if any((ANCHOR_KEY in c["by_key"] or SECONDARY_KEY in c["by_key"]) for c in cands):
            return "锚点分数为 0，比值无定义"
        return "全部快照都没有主锚或副锚"
    clean = [c for c in with_anchor if not c["dup"]]
    best = max((c["n"] for c in clean), default=0)
    if best and best < MIN_MODELS:
        return f"含锚点的快照最多只有 {best} 个可映射模型（<{MIN_MODELS}）"
    return "快照重复发布（同日两份表，数值不自洽）"


def main():
    rows = load_rows()
    reg = load_candidates()
    plane = load_plane()
    sec = load_sec()

    by_source = defaultdict(list)
    for r in rows:
        by_source[r["source_id"]].append(r)

    detail, summary = [], []
    for sid in sorted(reg, key=lambda s: reg[s]["name"]):
        meta = reg[sid]
        cands = snapshot_candidates(by_source.get(sid, []), meta["alpha"], sec) \
            if by_source.get(sid) else []
        best = pick(cands)
        if not best:
            summary.append({"source_id": sid, "name": meta["name"], "status": "弃用",
                            "snapshot": "", "snapshot_id": "", "anchor_kind": "",
                            "publisher": "", "rows": 0, "mapped": 0, "in_plane": 0, "ghost": [],
                            "self_share": "", "checked": 0, "med": "", "max": "",
                            "max_model": "", "z": "", "spread": "", "reason": reason_of(cands)})
            continue

        # mapped 里可能混着"映射得到、但平面里没有坐标"的 key（BL_MAP 覆盖的模型比平面广，
        # 那些 key 从未在带锚点的榜上出现过）。它们过得了 ≥5 门槛、却产不出残差，
        # 所以必须单独计数，否则摘要里的"模型"数是在虚报对照的样本量。
        ghost = sorted(k for k in best["by_key"] if k not in plane)
        z = None
        if ZERO_KEY in best["by_key"] and best["anchor"][1]:
            z = best["by_key"][ZERO_KEY][0] / best["anchor"][1]
        resid = []
        ratios = []
        for k, (v, r) in sorted(best["by_key"].items()):
            # 锚点与零点不参与残差统计：前者按构造等于 1，后者按构造是坐标系原点，
            # 它们的"残差"只反映该源的零点差异，不是模型偏离。
            if k in (ANCHOR_KEY, SECONDARY_KEY, ZERO_KEY):
                continue
            base = v / best["anchor"][1]
            ratio = base if (z is None or z > ZERO_APPLY_MAX) else (base - z) / (1 - z)
            ratios.append(ratio)
            px = plane.get(k)
            if not px:
                continue
            pred = meta["alpha"] * px["p"] + (1 - meta["alpha"]) * px["x"]
            resid.append((abs(ratio - pred), k, ratio, pred))
            detail.append([sid, meta["name"], best["publisher"], best["version"],
                           best["snapshot_id"],
                           best["n"], round(best["self_share"], 3), k, r["model_name"],
                           round(v, 2), best["anchor"][0], round(best["anchor"][1], 2),
                           "" if z is None else round(z, 4), round(ratio, 4),
                           round(pred, 4), round(ratio - pred, 4),
                           "zero_skip" if (z is not None and z > ZERO_APPLY_MAX) else ""])
        resid.sort(reverse=True)
        # pick() 已经把重复发布的快照排除，所以 best["dup"] 永远是 False；
        # 真正要报告的是"有更新的快照因重复发布被弃用"，否则读者会以为没抓过。
        newer_dup = sorted({c["version"] for c in cands
                            if c["dup"] and c["version"] > best["version"]}, reverse=True)
        summary.append({
            "source_id": sid, "name": meta["name"], "status": "对照",
            "snapshot": best["version"], "snapshot_id": best["snapshot_id"],
            "anchor_kind": best["anchor"][0],
            "publisher": best["publisher"],
            "rows": len(best["rows"]), "mapped": best["n"],
            "in_plane": best["n"] - len(ghost), "ghost": ghost,
            "self_share": round(best["self_share"], 3),
            "checked": len(resid),
            "z": "" if z is None else round(z, 3),
            "spread": round(max(ratios) - min(ratios), 3) if ratios else "",
            "med": round(sorted(x[0] for x in resid)[len(resid) // 2], 4) if resid else "",
            "max": round(resid[0][0], 4) if resid else "",
            "max_model": resid[0][1] if resid else "",
            "reason": ("更新的快照因重复发布弃用：" + "、".join(newer_dup)) if newer_dup else "",
        })

    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "bl_crosscheck.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(DETAIL_COLS)
        w.writerows(detail)

    cols = ["source_id", "name", "status", "snapshot", "snapshot_id", "anchor_kind",
            "publisher", "rows", "mapped", "in_plane", "ghost_keys", "self_share", "zero_z",
            "ratio_spread", "checked", "median_abs_residual", "max_abs_residual", "max_model", "note"]
    with open(os.path.join(OUT, "bl_crosscheck_sources.csv"), "w", newline="",
              encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for s in summary:
            w.writerow([s["source_id"], s["name"], s["status"], s["snapshot"],
                        s["snapshot_id"], s["anchor_kind"], s["publisher"], s["rows"],
                        s["mapped"], s["in_plane"], "、".join(s["ghost"]),
                        s["self_share"], s["z"], s["spread"], s["checked"], s["med"],
                        s["max"], s["max_model"], s["reason"]])

    used = [s for s in summary if s["status"] == "对照"]
    pub = Counter(s["publisher"] for s in used)
    ghosts = sorted({k for s in used for k in s["ghost"]})
    ghost_line = ([f"- {len(ghosts)} 个 key 在快照里映射得到、但平面里没有坐标，不参与残差"
                   f"（就是 `mapped` 比 `in_plane` 多出来的部分）：{'、'.join(ghosts)}", ""]
                  if ghosts else [])
    lines = ["# BenchmarkList 交叉校验", "",
             "由 `scripts/bl_compare.py` 生成，勿手改。BL **不参与拟合**，只作外部对照：",
             "把 BL 观测到的比值与本项目已解出的 P/X 预测值相比，残差大说明该源与现有证据打架。", "",
             f"- 候选源 {len(summary)} 个，可用 {len(used)} 个，弃用 {len(summary) - len(used)} 个",
             f"- 对照明细 {len(detail)} 条，涉及 {len({d[COL['model_key']] for d in detail})} 个模型", "",
             *ghost_line,
             "## 发布方集中度", "",
             "同一个发布方的一篇稿子会被 BL 拆成多个 benchmark 源，等于同一批模型被重复计入。", ""]
    for k, v in pub.most_common():
        lines.append(f"- `{k or '未知'}`：{v} 个源")
    lines += ["", "## 逐源", "",
              "| 源 | 快照 | 锚点 | 发布方 | 模型（有坐标） | 自报占比 | 零点 z | 比值跨度 | 中位\\|残差\\| | 最大偏离 | 判读 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(used, key=lambda s: -float(s["max"] or 0)):
        sp = float(s["spread"]) if s["spread"] != "" else None
        verdict = "已饱和，无区分度" if (sp is not None and sp < 0.15) else ""
        if s["ghost"]:
            verdict = " ".join(x for x in (verdict,
                          f"另有 {len(s['ghost'])} 个映射无平面坐标不计入：{'、'.join(s['ghost'])}") if x)
        shown = str(s["in_plane"]) + ("" if s["in_plane"] == s["mapped"] else f"（映射 {s['mapped']}）")
        lines.append(f"| {s['name']} | {s['snapshot']} | "
                     f"{'1017' if s['anchor_kind'] == 'primary' else '链式(副锚)'} | "
                     f"`{s['publisher']}` | {shown} | "
                     f"{s['self_share']:.0%} | {s['z'] or '—'} | {s['spread']} | {s['med']} | "
                     f"{s['max']} ({s['max_model']}) | {verdict} |")
    bad = [s for s in summary if s["status"] == "弃用"]
    if bad:
        lines += ["", "## 弃用", "", "| 源 | 原因 |", "|---|---|"]
        for s in bad:
            lines.append(f"| {s['name']} | {s['reason']} |")
    lines += ["", "## 残差怎么读", "",
              "- `residual = BL 比值 − (α·P + (1−α)·X)`，正数表示 BL 认为该模型比本项目的位置更强。",
              "- 比值跨度 < 0.15 ≈ 该榜已饱和（模型全挤在基准附近），对定位没有区分度：残差大说明"
              "平面期望的差距更大，不等于 BL 的读数错。",
              "- 零点 z 越接近 1，该榜越分不开基准与弱模，残差越不该当真（z>0.75 的源不做零点修正，只标注）。",
              "- 5~7 个模型的小表残差天然大：一个模型偏 0.5 就足以让整张表看起来不可信；"
              "不要用单条残差去改坐标。",
              "- 若要接进拟合，排序键必须改成「先洁净度（自报占比 / 发布方聚簇）、后模型数」，"
              "并按发布方聚簇计权，否则同一篇厂商稿会被当成 6 条独立证据。"]
    open(os.path.join(OUT, "bl_crosscheck.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    if "--update-registry" in sys.argv:
        # 回填候选清单的实际覆盖：models 列是榜单总模型数，这两个列才是本项目真正用到的
        cand = list(csv.DictReader(open(CAND, encoding="utf-8-sig")))
        fields = list(cand[0].keys())
        for col in ("mapped_models", "plane_models", "snapshot", "anchor_kind"):
            if col not in fields:
                fields.append(col)
        by_id = {s["source_id"]: s for s in summary}
        for r in cand:
            s = by_id.get(r["id"], {})
            r["mapped_models"] = s.get("mapped", 0) if s else 0
            # mapped_models 是"榜上映射得到的模型数"（含平面里没有坐标的），
            # plane_models 才是真正参与对照的数量——两者的差额就是映射白捡的名字
            r["plane_models"] = s.get("in_plane", 0) if s else 0
            r["snapshot"] = s.get("snapshot", "")
            # 候选表的 anchor 列写的是"这个榜理论上含哪个锚"，
            # 实际选中的快照可能只有副锚（走链式），不回填就会误导。
            r["anchor_kind"] = s.get("anchor_kind", "")
        with open(CAND, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader(); w.writerows(cand)
        print(f"-> 已回填 {len(cand)} 行到 sources_bl_candidates.csv")

    print(f"候选 {len(summary)} 个 → 可用 {len(used)} 个 / 弃用 {len(summary) - len(used)} 个")
    if ghosts:
        print("注意：映射到但平面里没有坐标的 key（不过 ≥5 门槛的计数、也不产出残差）：" + "、".join(ghosts))
    print("发布方集中度：" + "、".join(f"{k or '未知'} {v}" for k, v in pub.most_common()))
    print("残差最大的源：")
    for s in sorted(used, key=lambda s: -float(s["max"] or 0))[:5]:
        print(f"  {s['name']:26s} 中位 {s['med']}  最大 {s['max']}（{s['max_model']}）")
    print("-> out/bl_crosscheck.csv / bl_crosscheck_sources.csv / bl_crosscheck.md")


if __name__ == "__main__":
    main()
