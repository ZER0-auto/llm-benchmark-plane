# -*- coding: utf-8 -*-
"""Artificial Analysis 的模型 slug → 本项目的规范 model_key。

只映射能确认是同一份权重的条目；名称有歧义的（Muse Wonder / Muse Spark 变体）
一律不映射，宁缺毋滥。
"""

AA_MAP = {
    "claude-opus-5-5":         "opus5.5",
    "claude-sonnet-5-5":       "sonnet5.5",
    "claude-fable-5-1":        "fable5.1",
    "claude-haiku-5-5":        "haiku5.5",
    "gpt-6-astra":             "gpt6astra",
    "gpt-6.1-sol":             "gpt6.1sol",
    "gpt-6-luna":              "gpt6luna",
    "gemini-4-argon":          "gemini4argon",
    "gemini-3.8-flash":        "gemini3.8flash",
    "grok-4.7":                "grok4.7",
    "kimi-k3.1-pro":           "kimik3.1pro",
    "deepseek-v4-1-flash-1017": "deepseekv4.1flash1017",
    "glm-5.3":                 "glm5.3",
    "glm-5.3-flash":           "glm5.3flash",
    "step-5-preview":          "step5preview",
    "minimax-m3.1-flash":      "minimaxm3.1flash",
    "qwen3-8-27b":             "qwen3.827b",
    "qwen3-8-max-0902":        "qwen3.8max0902",
    "mimo-v2.6-pro":           "mimov2.6pro",
    "mistral-large-4-preview": "mistrallarge4",
}
