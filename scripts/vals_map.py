# -*- coding: utf-8 -*-
"""Vals 模型名 → 致知 logic 模型名（只映射版本号完全一致的；preview/日期后缀视为同一版本）"""

VALS_MAP = {
    "deepseek/deepseek-v4-flash-0731": "DeepSeek V4 Flash 0731",
    "deepseek/deepseek-v4-pro-0813": "DeepSeek V4 Pro 0813",
    "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "deepseek/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash 1017",
    "anthropic/claude-fable-5-1": "Fable 5.1",
    "zai/glm-5.2": "GLM-5.2",
    "zai/glm-5.3": "GLM-5.3",
    "zai/glm-5.3-flash": "GLM-5.3-Flash",
    "openai/gpt-5.5": "GPT-5.5",
    "openai/gpt-5.6-luna": "GPT-5.6 Luna",
    "openai/gpt-5.6-sol": "GPT-5.6 Sol",
    "openai/gpt-6-astra": "GPT-6 Astra",
    "openai/gpt-6-luna": "GPT-6 Luna",
    "openai/gpt-6-sol": "GPT-6 Sol",
    "openai/gpt-6.1-sol": "GPT-6.1 Sol",
    "google/gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite",
    "google/gemini-3.1-pro-preview": "Gemini 3.1 Pro",
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "google/gemini-3.7-flash": "Gemini 3.7 Flash",
    "google/gemini-3.8-flash": "Gemini 3.8 Flash",
    "google/gemini-4-argon": "Gemini 4 Argon",
    "grok/grok-4.6": "Grok 4.6",
    "grok/grok-4.7": "Grok 4.7",
    "anthropic/claude-haiku-5-5": "Haiku 5.5",
    "kimi/kimi-k3": "Kimi-K3",
    "ant/ling-3.0-flash-2607": "Ling-3.0-flash",
    "xiaomi/mimo-v2.5-pro": "MiMo-V2.5-Pro",
    "minimax/MiniMax-M3": "MiniMax-M3",
    "minimax/MiniMax-M3.1-flash": "MiniMax-M3.1-Flash",
    "mistralai/mistral-large-4": "Mistral Large 4",
    "mistralai/mistral-medium-3.5": "Mistral Medium 3.5",
    "meta/muse_spark_1_2": "Muse Spark 1.2",
    "meta/muse_spark_1_3": "Muse Spark 1.3",
    "meta/muse-wonder": "Muse Wonder 1.0",
    "anthropic/claude-opus-5": "Opus 5",
    "anthropic/claude-opus-5-5": "Opus 5.5",
    "alibaba/qwen3.7-plus": "Qwen3.7-Plus",
    "alibaba/qwen3.8-27b": "Qwen3.8-27B",
    "alibaba/qwen3.8-max": "Qwen3.8-Max",
    "anthropic/claude-sonnet-5": "Sonnet 5",
    "anthropic/claude-sonnet-5-5": "Sonnet 5.5",
    "stepfun/step-5-preview": "Step 5 Preview",
}

# Vals 榜单 → 用途
VALS_PRIVATE = ["vibe-code", "code-migration-v1-1"]
VALS_TB4 = ["terminal-bench-4"]
VALS_REFERENCE = ["skillsbench", "programbench", "swebench", "ioi"]   # 公开题，仅参考不记分
