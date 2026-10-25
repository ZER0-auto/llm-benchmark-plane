# LLM Benchmark Plane

把多个已有的大模型 benchmark **耦合**到一张二维平面上：**规划 P（想不想得明白）× 执行 X（做不做得对）**。

它不重新出题，也不把能力压成单一分数。每个模型是平面上的一个点，坐标是**相对基准的倍数**：`DeepSeek V4.1 Flash 1017 = 1.0`。

交互图：直接打开 [`out/model_plane.html`](out/model_plane.html)（自包含，无外部依赖）。

## 这个项目做什么

- **耦合**：把致知、屎山、Vals 等来源的逐模型成绩接进同一套坐标系。
- **归一**：每个来源先除以基准模型在该来源的分数，得到无量纲的倍数。
- **版本内比较**：只在同一版本内做比值；不跨版本取中位，也不跨版本桥接（链式基准只跨榜单，不跨版本）。
- **定档**：按两轴较高者给出 M0–M3，不要求两轴同时达标。

不做的事：不自建题库，不做厂商自报榜单的加权平均，不输出单指数排名。

## 当前快照（2026-10-25）

60 个模型，档位分布 **M0 10 / M1 8 / M2 15 / M3 27**。P 与 X 的相关系数 0.805——两个轴分开但不独立。

| 档位 | 模型（P / X，仅列 M0 / M1） |
|---|---|
| M0 | GPT-6 Astra (1.687/1.147)、Opus 5 (1.656/0.886)、Gemini 4 Argon (1.479/0.88)、GPT-6.1 Sol (1.478/1.223)、Opus 5.5 (1.473/1.397)、GPT-5.6 Sol (1.42/0.774)、Fable 5.1 (1.393/1.128)、Sonnet 5.5 (1.376/1.331)、GPT-6 Sol (1.35/1.033)、Sonnet 5 (1.269/0.582) |
| M1 | Muse Wonder 1.0 (1.18/1.067)、Kimi-K3 (1.144/0.453)、Kimi-K3.1-Pro (1.1/1.1)、Grok 4.6 (1.018/0.721)、Gemini 3.8 Flash (1.002/0.698)、DeepSeek V4.1 Flash 1017 (1.0/1.0)、Haiku 5.5 (0.985/1.027)、Mistral Large 4 (0.147/1.048) |

## 快速开始

```bash
# 1) 抓数据（需要网络）
python scripts/fetch_zhizhi.py     # 致知月榜 CSV
python scripts/fetch_shishan.py    # 屎山挑战赛逐题 JSON
python scripts/fetch_vals.py       # Vals 榜单
python scripts/fetch_aa.py         # Artificial Analysis 分项

# 2) 归一化 + 定档
python scripts/pipeline.py         # -> out/model_evidence.csv, out/model_plane.csv

# 3) 画图
python scripts/make_chart.py       # -> out/model_plane.html
```

只依赖 Python 3 标准库，无需安装第三方包。

也可以一条命令跑完后两步：

```bash
python run_all.py
```

## 目录

```
sources.csv      来源注册表：状态、公开性、锚点、权重、P 成分 α、测试机制
data/            抓取到的原始数据（按来源分目录）
  zhizhi/        致知月榜 CSV（logic / code_v3）
  shishan/       屎山挑战赛 assessment-data 快照
  vals/          Vals 逐模型 accuracy / harness
scripts/
  fetch_*.py     抓取脚本
  vals_map.py    Vals 模型名 → 统一模型名（只映射版本号一致的）
  aa_map.py      Artificial Analysis slug → 规范键（有歧义的不映射）
  pipeline.py    归一化与定档
  make_chart.py  生成自包含交互图
out/
  model_evidence.csv   逐源证据：model_key（规范键）、model_id（源站原名）、版本、日期、原始分、基准分、比值
  model_plane.csv      最终平面：model_key、P / X、档位、标签、来源、P / X 覆盖度
  model_plane.html     交互图
  metrics.json         本次运行算出的链式基准与守卫值（注入图表脚注）
```

## 口径摘要

- **不硬切轴**：每个来源带一个 P 成分 α，同一个比值按 `r ≈ α·P + (1−α)·X` 同时进入两轴，用岭回归（λ=0.03）解出每个模型的 P 与 X
- **权重与 α**：全部登记在 [sources.csv](sources.csv)，管道直接读表；当前计分来源 15 个（私有 7 个权重合计 1.83 / 公开 8 个合计 0.21），其中 Artificial Analysis 5 个分项合计 0.12
- **Artificial Analysis** 只取分项（HLE / LCR / CritPT / SciCode / AutomationBench），不用它的综合指数
- **版本规则**：致知按月切版本，版本内必须含基准模型，否则整版丢弃；屎山是阶梯加题，整块算一个版本，锚点为 V4.1 Flash
- **链式基准**：缺基准的榜用次新 Flash（`deepseek-v4.1-flash`）作锚点，先测出它相对基准的能力（P 0.929 / X 0.567），再按该榜成分 α 折算其余模型
- **档位**：取两轴较高者 —— M0 ≥1.25、M1 ≥1.00、M2 ≥0.70，其余 M3
- **单轴模型**：画在 P=X 对角线上，空心标记（○ 仅 P、◇ 仅 X）

完整推导见 [METHOD.md](METHOD.md)，历次设计决策见 [DECISIONS.md](DECISIONS.md)。

## 数据来源与归属

| 来源 | 链接 | 性质 |
|---|---|---|
| 致知 | https://llm2014.github.io/llm_benchmark/ | 个人维护的私有滚动题库 |
| 屎山挑战赛 | https://shishan.hellomeng.com/ | 私有题库、阶梯式赛制；锚点为 V4.1 Flash |
| Vals AI | https://www.vals.ai/benchmarks | 私有/公开测试集，第三方跑 |
| Artificial Analysis | https://artificialanalysis.ai/evaluations | 第三方跑的分项成绩；综合指数不用 |

原始数据版权归各来源所有，本仓库仅保存用于复现的分析快照。代码以 MIT 许可发布，见 [LICENSE](LICENSE)；数据快照的授权范围见 [NOTICE](NOTICE)。

## 已知限制

1. **P 轴仍偏窄**：ARC-AGI-2 与 FrontierMath 的榜单是纯客户端渲染，静态页取不到逐模型数据；HLE 只有旧版厂商自报。目前 P 由致知 + 两个 Vals 推理榜支撑。
2. **单轴模型的位置是假设值**：画在 P=X 上只是为了可见，不代表另一轴真的等于该值。
3. **档位阈值是暂定值**：1.25 / 1.00 / 0.70 还没有经过多轮数据校准。
4. **α 是先验不是测量**：α 目前靠任务结构人工判定，尚未用双因子模型反推；λ=0.03 同样是暂定，它直接决定 P 与 X 的分离幅度。
5. **链式基准依赖次新 Flash**：次新模型自身的能力估计会随主榜更新而变，历史快照不可直接横比；等效基准接近 100 的源（SkillsBench 98.08）对锚点估计很敏感。
6. **屎山的锚点是 V4.1 Flash**：榜单只写官方滚动别名 `DeepSeek Flash`，经核实 2026-10-19 场测试的是 DeepSeek-V4.1-Flash（不是 1017），因此按链式基准换算（等效基准 105.53）。它的分数是 Rasch 映射，不是百分制，不适用 >100% 守卫。
7. **Artificial Analysis 只覆盖 21 个模型**：名称有歧义的（Muse Wonder / Muse Spark 变体）一律不映射；Omniscience 因分数跨度过大暂缓。
8. **公开源权重合计 0.21、私有 1.83**（归一后公开约 10%）：还没按“私有 0.8 / 公开 0.2”配平，等权重校准时一起处理。
9. **覆盖度低的模型会被抬高**：只有少数几个执行类榜的模型（X 覆盖 <30%）会被先验拉向均值，尚未设最低覆盖门槛。
