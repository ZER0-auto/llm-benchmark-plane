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

60 个模型，其中 **44 个画在图上**（另 16 个坐标为负，只进下方数据表），档位分布 **M0 10 / M1 6 / M2 15 / M3 29**。P 与 X 的相关系数 0.80。计分来源 27 个（私有 15、公开 12），平均每个模型 10.8 个来源。

| 档位 | 模型（P / X，仅列 M0 / M1） |
|---|---|
| M0 | GPT-6 Astra (1.932/0.431)、Opus 5 (1.794/0.806)、Gemini 4 Argon (1.733/0.865)、Fable 5.1 (1.731/0.936)、GPT-6.1 Sol (1.731/0.491)、Opus 5.5 (1.698/0.969)、Sonnet 5.5 (1.616/0.942)、GPT-6 Sol (1.425/0.456)、Muse Wonder 1.0 (1.365/0.789)、GPT-5.6 Sol (1.337/0.6) |
| M1 | Haiku 5.5 (1.243/0.539)、Kimi-K3 (1.169/0.395)、MiMo-V2.6-Pro (1.153/0.526)、Kimi-K3.1-Pro (1.104/0.764)、Sonnet 5 (1.066/0.409)、DeepSeek V4.1 Flash 1017 (1.0/1.0) |

## 快速开始

```bash
# 1) 抓数据（需要网络）
python scripts/fetch_zhizhi.py     # 致知月榜 CSV
python scripts/fetch_shishan.py    # 屎山挑战赛逐题 JSON
python scripts/fetch_vals.py       # Vals 榜单
python scripts/fetch_aa.py         # Artificial Analysis 分项

# 2) 归一化 + 定档
python scripts/pipeline.py         # -> out/model_evidence.csv, out/model_plane.csv

# 2b) 可选：按留一残差校准权重（结果写回 sources.csv 的 weight_cal）
python scripts/calibrate_weights.py

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
sources.csv      来源注册表：状态、公开性、锚点、权重（初猜 + 校准）、P 成分 α、测试机制
data/            抓取到的原始数据（按来源分目录）
  zhizhi/        致知月榜 CSV（logic / code_v3）
  shishan/       屎山挑战赛 assessment-data 快照
  vals/          Vals 逐模型 accuracy / harness
scripts/
  fetch_*.py     抓取脚本
  vals_map.py    Vals 模型名 → 统一模型名（只映射版本号一致的）
  aa_map.py      Artificial Analysis slug → 规范键（有歧义的不映射）
  pipeline.py    归一化与定档
  calibrate_weights.py  留一残差权重校准
  make_chart.py  生成自包含交互图
out/
  model_evidence.csv   逐源证据：model_key（规范键）、model_id（源站原名）、版本、日期、原始分、基准分、比值
  model_plane.csv      最终平面：model_key、P / X、档位、标签、来源、P / X 覆盖度
  model_plane.html     交互图
  metrics.json         本次运行的链式基准、守卫剔除与标注（注入图表脚注）
  weight_calibration.csv/.json  权重校准明细、收敛过程与扰动验证
```

## 口径摘要

- **不硬切轴**：每个来源带一个 P 成分 α，同一个比值按 `r ≈ α·P + (1−α)·X` 同时进入两轴，用岭回归（λ=0.03）解出每个模型的 P 与 X
- **两个参照点**：1.0 = DeepSeek V4.1 Flash 1017，0.0 = MiniMax-M3。11 个源做两点归一；零点过高（z>0.75）的 6 个源只降权不修正；没有 MiniMax-M3 的 14 个源保持单点比值，且不参与决定坐标边界
- **坐标不外推**：P、X 被限制在该模型观测比值的区间内（无约束解会造出榜上没出现的分数），本轮钳位 5 个点；每个模型另有加权拟合 RMSE 可查
- **权重与 α**：全部登记在 [sources.csv](sources.csv)，管道直接读表；权重按留一残差校准（`scripts/calibrate_weights.py`），初猜与校准值并排存着，公开源占比按上限 0.20 配平（本轮 0.20）
- **Artificial Analysis** 只取分项（HLE / LCR / CritPT / SciCode / AutomationBench），不用它的综合指数
- **版本规则**：致知按月切版本，版本内必须含基准模型，否则整版丢弃；屎山是阶梯加题，整块算一个版本，锚点为 V4.1 Flash
- **链式基准**：缺基准的榜用次新 Flash（`deepseek-v4.1-flash`）作锚点，先测出它相对基准的两个因子（本轮 P 0.902 / X 0.729），再按该榜成分 α 折算其余模型
- **失效守卫**：等效基准超过该榜满分、不足满分 5%、或副锚点得 0 分 → 该榜丢弃；接近满分（>0.9×满分）只标注不剔除。本轮剔除：medscribe、srebench、terminal-bench-science
- **按模型降权**：同一个模型在不同榜上剖面打架时，残差特别大的源只在该模型上降权（下限 0.25×），生效权重见 `model_evidence.csv` 的 `weight_eff`
- **档位**：取两轴较高者 —— M0 ≥1.25、M1 ≥1.00、M2 ≥0.70，其余 M3
- **图上标记**：两轴覆盖度都 <35% 的点画成虚线白心环（本轮 19 个），只标记不剔除——单一来源也是证据，只是数值靠先验撑住
- **同模型多档位**：致知月榜同月对同一模型给思考档与非思考档两条，取分值高的那档（与 Vals / AA 默认开启思考一致），被丢的会打印，证据行保留来源原名

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

1. **P 轴仍偏窄**：ARC-AGI-2、FrontierMath、GAIA、OSWorld 的榜单是纯客户端渲染，静态页取不到逐模型数据。目前 P 由致知 logic、Vals 的 ProofBench / MysteryMechanism / SAGE、AA 的 HLE / CritPT 支撑。
2. **单一来源模型的位置是假设值**：13 个模型只有一个来源，落在 P=X 对角线上只是为了可见，不代表另一轴真等于该值；图上已标为虚线环。
3. **档位阈值是暂定值**：1.25 / 1.00 / 0.70 还没有经过多轮数据校准。
4. **α 是先验不是测量**：α 目前靠任务结构人工判定，尚未用双因子模型反推；λ=0.03 同样是暂定，它直接决定 P 与 X 的分离幅度。
5. **链式基准依赖次新 Flash**：次新模型自身的能力估计会随主榜更新而变，历史快照不可直接横比；等效基准接近该榜满分的源（SkillsBench、legal_bench、cyber、屎山）对锚点估计很敏感，`metrics.json` 的 `near_ceiling` 会列出。
6. **屎山的锚点是 V4.1 Flash**：榜单只写官方滚动别名 `DeepSeek Flash`，经核实 2026-10-19 场测试的是 DeepSeek-V4.1-Flash（不是 1017），因此按链式基准换算（等效基准 105.53）。它的分数是 Rasch 映射，不是百分制，不适用 >100% 守卫。
7. **Artificial Analysis 只覆盖 21 个模型**：名称有歧义的（Muse Wonder / Muse Spark 变体）一律不映射；Omniscience 因分数跨度过大暂缓。
8. **权重校准只看“合群 + 区分度”**：α 判错的源会被误降权；`weight_prior` 与 `weight_cal` 并排存着，可随时对比、退回。
9. **覆盖度仍不均**：平均覆盖 P 0.47 / X 0.47；已定策：不设剔除门槛，低覆盖点在图上标为虚线白心环并在 tooltip 里给出两轴覆盖度。
10. **有些模型跨榜剖面不一致**（观测比值跨度大、拟合 RMSE 高），双因子模型只能折中；这类点的两轴距离比单榜距离粗，看 tooltip 的 RMSE 判断可信度。
11. **零点只在 17 个源上成立**：其余 14 个源仍是单点归一（零点=原始 0），与修正过的源混在同一套坐标里是主要的近似来源；已用“不让它们决定边界 + 按 z 降权”压住，但没消除。
12. **档位阈值沿用 1.25 / 1.00 / 0.70**：引入零点后语义更严，分布随之变化（M2 20→15，M3 23→29），还没有重定档。
