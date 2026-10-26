# -*- coding: utf-8 -*-
"""BenchmarkList 的 model_id → 本项目的规范 model_key。

与 aa_map / vals_map 同一惯例：只映射能确认是同一份权重的条目；
名称有歧义的一律不映射，宁缺毋滥。

三张表（scripts/bl_compare.py 的 key_of() 按 skip → override → BL_MAP 顺序应用）：
  BL_MAP      slug → key，一对一且 slug 内 display 全是同一模型（不同推理档）
  BL_OVERRIDE (slug, display) → key，slug 混装了不同模型时的显示级修正
  BL_SKIP     (slug, display)，项目未收录的模型，跳过不折入别的 key

生成方式：scripts/bl_map_candidates.py 对 bl_rows.csv 生成候选
（norm(display) / 去首词再 norm / slug 后缀三条规则），再逐条人工审定。
2026-10-25 v1：53 个候选全部唯一解；审掉 1 个混装 slug，补 3 条 override、1 条 skip。
2026-10-26 v2：补 1 条 skip（第三方产品名混入）；明确 preview 口径。

版本口径：preview 与正式版本项目里一直共用同一个 key（vals_map 的
`google/gemini-3.1-pro-preview` → Gemini 3.1 Pro、aa_map 的 `mistral-large-4-preview`
→ mistrallarge4 都是这么处理的），所以 BL 沿用，不单独拆 key。但**第三方产品名
不得折进模型**：draco 那份 arXiv 表把 "Perplexity Deep Research (Opus 4.6)"
挂在 anthropic-claude-opus-4.6 这个 slug 下，属于别的系统，必须 skip。
"""

BL_MAP = {
    # —— 三大参照（主锚 / 次新锚 / 零点）——
    "deepseek-deepseek-v4.1-flash-1017": "deepseekv4.1flash1017",
    "deepseek-deepseek-v4.1-flash":      "deepseekv4.1flash",
    "minimax-minimax-m3":                "minimaxm3",
    # —— DeepSeek 家族（裸 v4-flash slug 混装 0420/0731/Preview 三个检查点，不映射）——
    "deepseek-deepseek-v4-flash-0731":       "deepseekv4flash0731",
    "deepseek-deepseek-v4-flash-vision-exp": "deepseekv4flashvisionexp",
    "deepseek-deepseek-v4-pro-0813":         "deepseekv4pro0813",
    # —— Anthropic（项目 key 不带 Claude 前缀，display 去首词命中）——
    "anthropic-claude-opus-5":     "opus5",
    "anthropic-claude-opus-5.5":   "opus5.5",
    "anthropic-claude-sonnet-5":   "sonnet5",
    "anthropic-claude-sonnet-5.5": "sonnet5.5",
    "anthropic-claude-haiku-5.5":  "haiku5.5",
    "anthropic-claude-fable-5.1":  "fable5.1",
    "anthropic-claude-opus-4.6":   "claudeopus4.6",   # 项目该型号恰有带前缀的 key
    "claude-sonnet-5":             "sonnet5",         # 无 org 前缀的同模型另一 id
    # —— OpenAI ——
    "openai-gpt-5.5":      "gpt5.5",
    "openai-gpt-5.6-luna": "gpt5.6luna",
    "openai-gpt-5.6-sol":  "gpt5.6sol",
    "openai-gpt-6-astra":  "gpt6astra",
    "openai-gpt-6-luna":   "gpt6luna",
    "openai-gpt-6-sol":    "gpt6sol",
    "openai-gpt-6.1-sol":  "gpt6.1sol",
    # —— Google ——
    "google-gemini-3.8-flash":           "gemini3.8flash",
    "google-gemini-3.7-flash":           "gemini3.7flash",
    "google-gemini-4-argon":             "gemini4argon",
    "google-gemini-3.5-flash-lite":      "gemini3.5flashlite",
    "google-gemini-3.1-flash-lite":      "gemini3.1flashlite",
    "google-gemini-3.1-flash-lite-preview": "gemini3.1flashlite",
    "google-gemini-3.1-pro-preview":     "gemini3.1pro",
    "google-gemma-4-31b-it":             "gemma431b",
    # —— 其他厂商 ——
    "x-ai-grok-4.6":            "grok4.6",
    "x-ai-grok-4.7":            "grok4.7",
    "moonshotai-kimi-k3":       "kimik3",
    "moonshotai-kimi-k3.1-pro": "kimik3.1pro",
    "z-ai-glm-5.2":             "glm5.2",
    "z-ai-glm-5.3":             "glm5.3",
    "z-ai-glm-5.3-flash":       "glm5.3flash",
    "qwen-qwen3.7-plus":        "qwen3.7plus",
    "qwen-qwen3.8-27b":         "qwen3.827b",
    "qwen-qwen3.8-max":         "qwen3.8max",
    "qwen-qwen3.8-max-0902":    "qwen3.8max0902",
    "xiaomi-mimo-v2.5-pro":     "mimov2.5pro",
    "minimax-minimax-m3.1-flash": "minimaxm3.1flash",
    "mistralai-mistral-large-4":  "mistrallarge4",
    "mistralai-mistral-medium-3-5": "mistralmedium3.5",
    "meta-muse-spark-1.2":      "musespark1.2",
    "meta-muse-spark-1.3":      "musespark1.3",
    "inclusionai-ling-3.0-flash": "ling3.0flash",
    "inclusionai-ling-3.1-flash": "ling3.1flash",
    "meituan-longcat-2.0":      "longcat2.0",
    "stepfun-step-3.7-flash":    "step3.7flash",
    "stepfun-step-5-preview":    "step5preview",
    "tencent-hy3":              "hy3",
    # —— 重试轮新数据补入（2026-10-25）——
    "seed-2.1-pro":             "seed2.1pro",
    "xiaomi-mimo-v2.6-pro":     "mimov2.6pro",
}

# 同一 slug 混装不同模型：按 display 精确修正
BL_OVERRIDE = {
    ("openai-gpt-5.5", "GPT-5.5 Instant (June 2026)"): "gpt5.5instant",
    ("openai-gpt-5.5", "GPT-5.5 Instant (May 2026)"):  "gpt5.5instant",
    ("qwen-qwen3.8-max", "Qwen3.8 Max (0902)"):        "qwen3.8max0902",
}

# 项目未收录的模型：跳过，不折入任何 key
BL_SKIP = {
    ("openai-gpt-5.6-sol", "GPT-5.6 Sol Ultra"),   # 项目无 Sol Ultra 这个 key
    # 第三方产品（Perplexity 的 deep research 系统）挂在 Opus 4.6 的 slug 下，不是裸模型
    ("anthropic-claude-opus-4.6", "Perplexity Deep Research (Opus 4.6)"),
}
