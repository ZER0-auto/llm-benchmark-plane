# LLM Benchmark Plane

把多个已有的大模型 benchmark **耦合**到一张二维平面上：**规划 P（想不想得明白）× 执行 X（做不做得对）**。

它不重新出题，也不把能力压成单一分数。每个模型是平面上的一个点，坐标是**相对基准的倍数**：`DeepSeek V4.1 Flash 1017 = 1.0`。

交互图：直接打开 [`out/model_plane.html`](out/model_plane.html)（自包含，无外部依赖）。

## 这个项目做什么

- **耦合**：把致知、屎山、Vals 等来源的逐模型成绩接进同一套坐标系。
- **归一**：每个来源先除以基准模型在该来源的分数，得到无量纲的倍数。
- **版本内比较**：只在同一版本内做比值，不跨版本取中位或桥接。
- **定档**：按两轴较高者给出 M0–M3，不要求两轴同时达标。

不做的事：不自建题库，不做厂商自报榜单的加权平均，不输出单指数排名。

## 当前快照（2026-10-25）

60 个模型，档位分布 **M0 10 / M1 8 / M2 17 / M3 25**。

| 档位 | 模型（P / X） |
|---|---|
| M0 | GPT-6 Astra (1.77/1.34)、Opus 5 (1.71/1.17)、Opus 5.5 (1.56/1.42)、Gemini 4 Argon (1.54/1.05)、GPT-6.1 Sol (1.54/1.28)、Sonnet 5.5 (1.48/1.28)、Fable 5.1 (1.48/1.22)、GPT-5.6 Sol (1.47/1.01)、GPT-6 Sol (1.41/1.11)、Sonnet 5 (1.35/0.79) |
| M1 | Muse Wonder 1.0、Kimi-K3、Kimi-K3.1-Pro、Grok 4.6、Haiku 5.5、Gemini 3.8 Flash、Gemini 3.7 Flash、DeepSeek V4.1 Flash 1017 (1.00/1.00) |

## 快速开始

```bash
# 1) 抓数据（需要网络）
python scripts/fetch_zhizhi.py     # 致知月榜 CSV
python scripts/fetch_shishan.py    # 屎山挑战赛逐题 JSON
python scripts/fetch_vals.py       # Vals 榜单

# 2) 归一化 + 定档
python scripts/pipeline.py         # -> out/model_evidence.csv, out/model_plane.csv

# 3) 画图
python scripts/make_chart.py       # -> out/model_plane.html
```

只依赖 Python 3 标准库，无需安装第三方包。

## 目录

```
data/            抓取到的原始数据（按来源分目录）
  zhizhi/        致知月榜 CSV（logic / code_v3）
  shishan/       屎山挑战赛 assessment-data 快照
  vals/          Vals 逐模型 accuracy / harness
scripts/
  fetch_*.py     抓取脚本
  vals_map.py    Vals 模型名 → 统一模型名（只映射版本号一致的）
  pipeline.py    归一化与定档
  make_chart.py  生成自包含交互图
out/
  model_evidence.csv   每个模型每个来源的原始分、版本、基准分、比值
  model_plane.csv      最终平面：P / X / 档位 / 标签 / 来源
  model_plane.html     交互图
```

## 口径摘要

- **P 轴**：致知 logic（0.50）+ Vals ProofBench（0.30）+ Vals MysteryMechanism（0.20）
- **X 轴**：屎山（0.32）+ 致知 code_v3（0.28）+ Vibe Code（0.14）+ Code Migration（0.09）+ Terminal-Bench 4（0.04）+ IOI（0.01）
- **版本规则**：致知按月切版本，版本内必须含基准模型，否则整版丢弃；屎山是阶梯加题，整块算一个版本
- **链式基准**：缺基准的榜用次新 Flash（`deepseek-v4.1-flash`）作锚点，先测出它相对基准的能力（P 0.946 / X 0.681），再折算其余模型
- **档位**：取两轴较高者 —— M0 ≥1.25、M1 ≥1.00、M2 ≥0.70，其余 M3
- **单轴模型**：画在 P=X 对角线上，空心标记（○ 仅 P、◇ 仅 X）

完整推导见 [METHOD.md](METHOD.md)，历次设计决策见 [DECISIONS.md](DECISIONS.md)。

## 数据来源与归属

| 来源 | 链接 | 性质 |
|---|---|---|
| 致知 | https://llm2014.github.io/llm_benchmark/ | 个人维护的私有滚动题库 |
| 屎山挑战赛 | https://shishan.hellomeng.com/ | 私有题库、阶梯式赛制 |
| Vals AI | https://www.vals.ai/benchmarks | 私有/公开测试集，第三方跑 |

原始数据版权归各来源所有，本仓库仅保存用于复现的分析快照。代码以 MIT 许可发布，见 [LICENSE](LICENSE)。

## 已知限制

1. **P 轴仍偏窄**：ARC-AGI-2 与 FrontierMath 的榜单是纯客户端渲染，静态页取不到逐模型数据；HLE 只有旧版厂商自报。目前 P 由致知 + 两个 Vals 推理榜支撑。
2. **单轴模型的位置是假设值**：画在 P=X 上只是为了可见，不代表另一轴真的等于该值。
3. **档位阈值是暂定值**：1.25 / 1.00 / 0.70 还没有经过多轮数据校准。
4. **公开题权重很低**：Terminal-Bench 4、IOI 等公开题合计权重 0.05，仅作补充。
5. **链式基准依赖次新 Flash**：次新模型自身的能力估计会随主榜更新而变，历史快照不可直接横比。
