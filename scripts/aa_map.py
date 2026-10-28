# -*- coding: utf-8 -*-
"""Artificial Analysis 的模型 slug → 本项目的规范 model_key。

只映射能确认是同一份权重的条目；名称有歧义的（Muse Wonder / Muse Spark 变体）
一律不映射，宁缺毋滥。

**key 必须逐字等于 data/aa/aa_rows.csv 里 fetch_aa.py 实际产出的 model_slug。**
2026-10-26 发现这张表有 11 条是手写的点号写法（`gemini-3.8-flash`），而抓取端
产出的是横线（`gemini-3-8-flash`），永不命中也不报错——AA 五个计分源因此每个只带
9 个模型。现在 load_aa() 会把"永不命中的映射"和"未映射的 slug"都打印出来。

命中与否不能靠 slug 字面猜版本，要看 display name：AA 的 `step-5` 写的是
"Step 5 Preview"、`qwen3-8-max` 写的是 "Qwen3.8 Max (0902)"、`mistral-large-4`
写的是 "Mistral Large 4 Preview"——所以它们分别对应 step5preview / qwen3.8max0902 /
mistrallarge4，而不是字面看起来的 GA 版本。
"""

AA_MAP = {
    "claude-opus-5-5":          "opus5.5",
    "claude-sonnet-5-5":        "sonnet5.5",
    "claude-fable-5-1":         "fable5.1",
    "claude-haiku-5-5":         "haiku5.5",
    "gpt-6-astra":              "gpt6astra",
    "gpt-6-1-sol":              "gpt6.1sol",
    "gpt-6-luna":               "gpt6luna",
    "gemini-4-argon":           "gemini4argon",
    "gemini-3-8-flash":         "gemini3.8flash",
    "grok-4-7":                 "grok4.7",
    "kimi-k3-1-pro":            "kimik3.1pro",
    "deepseek-v4-1-flash-1017": "deepseekv4.1flash1017",
    "glm-5-3":                  "glm5.3",
    "glm-5-3-flash":            "glm5.3flash",
    "step-5":                   "step5preview",     # display name = "Step 5 Preview"
    "minimax-m3-1-flash":       "minimaxm3.1flash",
    "qwen3-8-27b":              "qwen3.827b",
    "qwen3-8-max":              "qwen3.8max0902",   # display name = "Qwen3.8 Max (0902)"
    "mimo-v2-6-pro":            "mimov2.6pro",
    "mistral-large-4":          "mistrallarge4",    # display name = "Mistral Large 4 Preview"
    # —— 只有 AA 证据的模型（DECISIONS 2026-10-26：按既有"非填充"口径处理，不单独设规则）——
    #    key 取 display name 的 norm 写法，这样别处（致知 / Vals）以后出现同一模型时能自动并上
    "inkling":                  "inkling",           # "Inkling (Xhigh)"
    "reflection-beam":          "beam1.0",           # "Beam 1.0"
    "nemotron-3-5-super-vl":    "nemotron3.5supervl",
    "k2-horizon-375b-a23b":     "k2horizon375ba23b",
}

# 刻意不映射的 slug。写出来是为了让 load_aa 的自检能区分"漏了"和"故意不要"：
#   muse-wonder / muse-wonder-full / muse-spark-open：Muse 系列变体名有歧义，无法确认是哪份权重
#   omniscience*：分数跨度太大，暂缓（见 README 已知限制 7）
# 2026-10-26：inkling / reflection-beam / nemotron-3-5-super-vl / k2-horizon-375b-a23b 已改判为映射。
# 当初拦下的理由是"会挤占 0.20 的公开源占比上限"，那句话是错的：占比约束的是**来源权重**，
# 模型数量进不进平面都不改变 sources.csv 里的任何权重。它们只是"只有 AA 证据"的模型，
# 按既有口径处理即可（缺哪轴就不填、覆盖度低、图上标虚线白心环），不需要单独设规则。
AA_UNMAPPED = {
    "muse-wonder", "muse-wonder-full", "muse-spark-open",
}
