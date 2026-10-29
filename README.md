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

## 当前快照（2026-10-26）

66 个模型，其中 **51 个画在图上**（另 15 个坐标为负，只进下方数据表），档位分布 **M0 10 / M1 28 / M2 17 / M3 11**。P 与 X 的相关系数 0.87。计分来源 27 个（私有 15、公开 12），平均每个模型 10.9 个来源。

| 档位 | 模型（P / X，仅列 M0 / M1） |
|---|---|
| M0 | GPT-6 Astra (1.818/0.819)、Opus 5 (1.755/0.937)、Gemini 4 Argon (1.649/0.951)、Fable 5.1 (1.623/1.073)、Opus 5.5 (1.62/1.114)、GPT-6.1 Sol (1.586/0.889)、Sonnet 5.5 (1.453/1.139)、GPT-6 Sol (1.308/0.772)、GPT-5.6 Sol (1.305/0.77)、Muse Wonder 1.0 (1.301/0.918) |
| M1 | Kimi-K3.1-Pro (1.194/0.801)、Kimi-K3 (1.122/0.439)、GPT-6.1 Terra (Max) (1.101/0.964)、MiMo-V2.6-Pro (1.085/0.651)、Haiku 5.5 (1.069/0.77)、Sonnet 5 (1.037/0.51)、DeepSeek V4.1 Flash 1017 (1.0/1.0)、Grok 4.6 (0.907/0.601)、Qwen3.8-Max (0.905/0.446)、Grok 4.7 (0.854/0.84)、MiniMax-M3.1-Flash (0.835/0.563)、GLM-5.3 (0.821/0.778)、Mistral Large 4 (0.038/0.808)、Seed-2.1-pro 0915 (0.804/0.804)、Muse Spark 1.3 (0.803/0.762)、DeepSeek V4.1 Flash (0.8/0.737)、Gemini 3.8 Flash (0.782/0.54)、GPT-5.6 Luna (0.779/0.536)、Qwen3.8-Max-0902 (0.758/0.629)、DeepSeek V4 Flash 0731 (0.749/0.457)、GPT-6 Luna (0.747/0.553)、Beam 1.0 (0.672/0.739)、DeepSeek V4 Pro 0813 (0.721/0.653)、Gemini 3.7 Flash (0.702/0.326)、Step 5 Preview (0.678/0.584)、Muse Spark 1.2 (0.596/0.671)、DeepSeek V4 Flash (0.626/0.626)、GLM-5.3-Flash (0.452/0.422) |

## 快速开始

```bash
# 1) 抓数据（需要网络）
python scripts/fetch_zhizhi.py     # 致知月榜 CSV
python scripts/fetch_shishan.py    # 屎山挑战赛逐题 JSON
python scripts/fetch_vals.py       # Vals 榜单
python scripts/fetch_aa.py         # Artificial Analysis 分项

# 2) 归一化 + 定档
python scripts/pipeline.py         # -> out/model_evidence.csv, out/model_plane.csv
python scripts/pipeline.py --bootstrap 1000   # 同上，再加源级 bootstrap：坐标区间 + 档位稳定率（约 10s）

# 2b) 可选：按留一残差校准权重（结果写回 sources.csv 的 weight_cal）
python scripts/settle_weights.py      # 推荐：交替跑 calibrate + pipeline 到权重不动点
python scripts/calibrate_weights.py   # 只跑一轮：权重是拿"旧权重生成的证据"校准的，别直接当基线

# 3) 画图
python scripts/make_chart.py       # -> out/model_plane.html

# 4) 文档数字自检（run_all.py 末尾会自动跑）
python scripts/check_docs.py       # README / METHOD 的每个数字都要等于 out/ 的产物

# 5) 可选：λ / α 敏感性扫描（只读现算，不改生产产物）
python scripts/sensitivity.py      # -> out/sensitivity.json / .md

# 6) 可选：每周抓数据并留档（为将来的"降智"检测攒多周对照）
python scripts/fetch_week.py       # 抓 fetch_* + 跑管道 + 写 data/weekly/observations.csv
python scripts/fetch_week.py --no-fetch    # 不联网，只把现有证据归档到本周
```

只依赖 Python 3 标准库，无需安装第三方包。

也可以一条命令跑完"管道 + bootstrap + λ/α 敏感性 + 出图 + 文档自检"：

```bash
python run_all.py
```

### 可选：BenchmarkList 交叉校验（不进计分）

```bash
python scripts/fetch_bl.py                    # 抓快照；站点慢且不稳，失败源不写库，重跑自动续抓
python scripts/bl_compare.py                  # -> out/bl_crosscheck.csv / .md
python scripts/bl_compare.py --update-registry  # 把实际覆盖回填进候选清单
```

单源 JSON 有 200 KB 以上、下载约 8 KB/s，默认 4 线程会把每个连接压到超时；实测 `--workers 1 --timeout 600`
才把 30 个源全部抓齐。每轮的成功/404/网络失败记在 `data/bl/fetch_status.json`，"多少个源有数据"以它为准。

BL 的逐模型成绩基本来自厂商自己的发布稿，按口径不能进坐标；这个工具把它当外部对照，
用残差看“哪些源与现有证据打架”。为什么不接进拟合见 [METHOD.md](METHOD.md) §4.1。

## 目录

```
sources.csv      来源注册表：状态、公开性、锚点、权重（初猜 + 校准）、P 成分 α、测试机制
sources_bl_candidates.csv  BL 候选源（status=candidate，不进计分；mapped_models / snapshot / anchor_kind 由 `bl_compare.py --update-registry` 回填）
data/            抓取到的原始数据（按来源分目录）
  zhizhi/        致知月榜 CSV（logic / code_v3）
  shishan/       屎山挑战赛 assessment-data 快照
  vals/          Vals 逐模型 accuracy / harness
  bl/            BenchmarkList 快照（只做交叉校验，不进计分）
                 bl_rows.csv 逐模型成绩；fetch_status.json 每轮抓取结果（ok/404/failed）
  weekly/        每周留档（fetch_week.py 写）：observations.csv 一行 = (周, 源, 模型) 的原始分与比值，
                 外加 fetch_status（fresh = 本周真抓到了 / stale = 把磁盘旧数据又抄了一遍）
                 不参与拟合与定档，是给将来"发布后期降智"检测攒的多周原料
scripts/
  fetch_*.py     抓取脚本
  vals_map.py    Vals 模型名 → 统一模型名（只映射版本号一致的）
  aa_map.py      Artificial Analysis slug → 规范键（有歧义的不映射）
  bl_map.py      BenchmarkList model_id → 规范键（只映射能确认的）
  bl_compare.py  BL 交叉校验：观测比值 vs 平面预测（不参与拟合）
  pipeline.py    归一化与定档
  calibrate_weights.py  留一残差权重校准
  settle_weights.py  calibrate ↔ pipeline 交替到权重不动点（出正式基线用这个）
  check_docs.py  README / METHOD 的数字与 out/ 逐一对账，漂了就 FAIL
  sensitivity.py   λ / α 敏感性扫描（区间之外的不确定性，只读现算、不改生产产物）
  fetch_week.py    每周抓数据并按 ISO 周留档到 data/weekly/（将来测"发布后期降智"的原料）
  make_chart.py  生成自包含交互图
out/
  model_evidence.csv   逐源证据：model_key（规范键）、model_id（展示名）、source_model（源站原名）、版本、日期、原始分、基准分、比值
  model_plane.csv      最终平面：model_key、P / X、档位、标签、来源、P / X 覆盖度、fit_rmse、next_tier_gap、ratio_range、clamped、downweighted
                       表头恒含 7 列 bootstrap：P_lo / P_hi / X_lo / X_hi（5~95%）、tier_stability、tier_presence、tier_mode（没跑 --bootstrap 时留空）
  model_plane.html     交互图
  metrics.json         本次运行的链式基准（每个链式榜的 α / r_anchor / 等效基准）、守卫剔除、零点 z 与标注；注入图表脚注，也是 check_docs.py 的对账基准
  weight_calibration.csv/.json  权重校准明细、收敛过程与扰动验证
  settle.json        不动点证据：跑了几轮、最后 max|Δw|、是否收敛（由 settle_weights.py 写）
  sensitivity.json/.md  λ / α 敏感性扫描结果（只读分析，不进拟合）
  bl_crosscheck.csv/.md        BL 观测比值 vs 平面预测的残差对照（不进回归）
```

## 口径摘要

- **不硬切轴**：每个来源带一个 P 成分 α，同一个比值按 `r ≈ α·P + (1−α)·X` 同时进入两轴，用岭回归（λ=0.03）解出每个模型的 P 与 X
- **两个参照点**：1.0 = DeepSeek V4.1 Flash 1017，0.0 = MiniMax-M3。10 个源做两点归一；零点过高（z>0.75）的 6 个源只降权不修正；没有 MiniMax-M3 的 11 个源保持单点比值，且不参与决定坐标边界
- **坐标不外推**：P、X 被限制在该模型观测比值的 p10~p90 区间内（无约束解会造出榜上没出现的分数），本轮钳位 19 个点（见 `model_plane.csv` 的 `clamped`）；每个模型另有加权拟合 RMSE 可查
- **坐标带区间**：源级 bootstrap（27 个计分源有放回抽 1000 次，seed=20261026）给出 P_lo / P_hi / X_lo / X_hi（5-95%）、tier_stability、tier_presence、tier_mode；区间宽度中位 P 0.455 / X 0.497，与本轮相邻边界间距（0.653 / 0.747）同一量级，档位稳定率中位只有 0.827（分档按**点估计**档位：M0 0.885 / M1 0.964 / M2 0.682 / M3 0.682），所以档位要连着稳定率一起读。它是“换一批约 17 块榜会差多少”的组成敏感性，不是同一批数据的置信区间（METHOD §17）
- **权重与 α**：全部登记在 [sources.csv](sources.csv)，管道直接读表；权重按留一残差校准（`scripts/calibrate_weights.py`），初猜与校准值并排存着，公开源占比按上限 0.20 配平（本轮 0.20）
- **Artificial Analysis** 只取分项（HLE / LCR / CritPT / SciCode / AutomationBench），不用它的综合指数
- **版本规则**：致知按月切版本，版本内必须含基准模型，否则整版丢弃；屎山是阶梯加题，整块算一个版本，锚点为 V4.1 Flash
- **链式基准**：缺基准的榜用次新 Flash（`deepseek-v4.1-flash`）作锚点，先测出它相对基准的两个因子（本轮 P 0.8745 / X 0.7998），再按该榜成分 α 折算其余模型
- **失效守卫**：等效基准超过该榜满分、不足满分 5%、或副锚点得 0 分 → 该榜丢弃；接近满分（>0.9×满分）只标注不剔除。本轮剔除：medscribe、srebench、terminal-bench-science
- **按模型降权**：同一个模型在不同榜上剖面打架时，残差特别大的源只在该模型上降权（下限 0.25×），生效权重见 `model_evidence.csv` 的 `weight_eff`
- **档位**：取两轴较高者；**边界每轮由数据自己算**（自然断裂，档位数固定 4 但数值不写死），本轮 M0 ≥1.276、M1 ≥0.596、M2 ≥-0.135，其余 M3。**标注档位取多数派**（源级 bootstrap 里出现次数最多的那一档）：与点估计不同的本轮有 3 个（gpt5.5 M1→M2、k2horizon375ba23b M2→M1、glm5.3flash M2→M1）。点估计档位同时发布在 `tier_point` 列——两者不同时，图上颜色按多数派、另加一圈灰色虚线外圈，tooltip 与表格里两个档位都写出来
- **图上标记**：两轴覆盖度都 <35% 的模型有 24 个（其中 15 个在图上，画成虚线白心环），只标记不剔除——单一来源也是证据，只是数值靠先验撑住
- **BenchmarkList 不进计分**：BL 的逐模型成绩基本是厂商发布稿（2026-10-23 那一篇 kimi 博客就被拆成 14 个“源”），只做外部对照（`scripts/bl_compare.py` → `out/bl_crosscheck.md`），理由见 METHOD §4.1
- **同模型多档位**：致知月榜同月对同一模型给思考档与非思考档两条，取分值高的那档（与 Vals / AA 默认开启思考一致），被丢的会打印，证据行保留来源原名

完整推导见 [METHOD.md](METHOD.md)，历次设计决策见 [DECISIONS.md](DECISIONS.md)。

## 数据来源与归属

| 来源 | 链接 | 性质 |
|---|---|---|
| 致知 | https://llm2014.github.io/llm_benchmark/ | 个人维护的私有滚动题库 |
| 屎山挑战赛 | https://shishan.hellomeng.com/ | 私有题库、阶梯式赛制；锚点为 V4.1 Flash |
| Vals AI | https://www.vals.ai/benchmarks | 私有/公开测试集，第三方跑 |
| BenchmarkList | https://benchmarklist.com/ | 第三方汇总快照；多数表的原始出处是厂商发布稿，只做交叉校验、不进计分 |
| Artificial Analysis | https://artificialanalysis.ai/evaluations | 第三方跑的分项成绩；综合指数不用 |

原始数据版权归各来源所有，本仓库仅保存用于复现的分析快照。代码以 MIT 许可发布，见 [LICENSE](LICENSE)；数据快照的授权范围见 [NOTICE](NOTICE)。

## 已知限制

1. **P 轴仍偏窄**：ARC-AGI-2、FrontierMath、GAIA、OSWorld 的榜单是纯客户端渲染，静态页取不到逐模型数据。目前 P 由致知 logic、Vals 的 ProofBench / MysteryMechanism / SAGE、AA 的 HLE / CritPT 支撑。
2. **单一来源模型的位置是假设值**：13 个模型只有一个来源，落在 P=X 对角线上只是为了可见，不代表另一轴真等于该值；图上已标为虚线环。
3. **档位边界是"当轮相对量"**：边界由当次数据的自然断裂算出（§8），好处是不再拍脑袋定数，代价是分布一变（加模型、加榜）边界就移动，同一模型跨快照的档位不可直接比，必须连着 `out/metrics.json` 的当轮边界一起看。
4. **α 是先验不是测量**：α 目前靠任务结构人工判定，尚未用双因子模型反推（§16 的 ALS 未实现）；λ=0.03 同样是暂定。**这两项的量级已扫出来**（§18）：λ 取 0.01/0.03/0.1 时 P-X 相关是 0.8463 / 0.8657 / 0.9207，α 挪 ±0.15 时 54 个方向里 49 个一个档都不换、最多换 2 个。
5. **链式基准依赖次新 Flash**：次新模型自身的能力估计会随主榜更新而变，历史快照不可直接横比；等效基准接近该榜满分的源（本轮 `near_ceiling`：sage 98.48、legal_bench 96.46、shishan 94.29）对锚点估计很敏感。
6. **屎山的锚点是 V4.1 Flash**：榜单只写官方滚动别名 `DeepSeek Flash`，经核实 2026-10-19 场测试的是 DeepSeek-V4.1-Flash（不是 1017），因此按链式基准换算（本轮等效基准 94.29）。它的分数是 Rasch 映射，不是百分制，不适用 >100% 守卫。
7. **Artificial Analysis 覆盖 24 个模型**：抓取端有 28 个 slug，映射表声明 25 条、其中 24 条真的在榜上，`glm-5-3-flash` 本轮已从 AA 下架（同一份数据里没有任何替代 slug，不是改名）；另有 4 个 slug 刻意不映射（ling-3-1-flash-1019、muse-spark-open、muse-wonder、muse-wonder-full——Muse 三个变体名有歧义，Ling 3.1 Flash 1019 与平面里的 Ling-3.1-flash 是否同一份权重无法确认）。2026-10-26 起 Inkling / Beam / Nemotron / K2 Horizon、2026-10-28 起 GPT-6.1 Terra 只有 AA 五个分项的证据，按既有非填充口径处理——缺的那一轴不猜、覆盖度低、图上标虚线白心环，不另设规则（当初拦下的理由是"会挤占公开源占比上限"，那句是错的：占比约束的是来源权重，与模型数量无关）。`load_aa()` 会把"映射永不命中"和"slug 未映射"都打印进 `metrics.aa`，防止写法漂移再次静默丢证据。
8. **权重校准只看“合群 + 区分度”**：α 判错的源会被误降权；`weight_prior` 与 `weight_cal` 并排存着，可随时对比、退回。
9. **覆盖度仍不均**：平均覆盖 P 0.46 / X 0.44；已定策：不设剔除门槛，低覆盖点在图上标为虚线白心环并在 tooltip 里给出两轴覆盖度。
10. **有些模型跨榜剖面不一致**（观测比值跨度大、拟合 RMSE 高），双因子模型只能折中；这类点的两轴距离比单榜距离粗，看 tooltip 的 RMSE 判断可信度。
11. **零点只在 16 个源上成立**：其中 10 个做两点归一、6 个 z>0.75 只降权；其余 11 个源仍是单点归一（零点=原始 0），与修正过的源混在同一套坐标里是主要的近似来源；已用“不让它们决定边界 + 按 z 降权”压住，但没消除。
12. **档位边界每轮由数据算，不写死数值**：对当次 `max(P,X)` 分布做一维自然断裂聚类（METHOD §8），本轮边界 1.248 / 0.595 / -0.152，档位分布 M0 10 / M1 28 / M2 17 / M3 11。代价是档位成了**组内相对量**：分布一变（例如补进只有 AA 证据的模型），边界与所有模型的档位都会重排，所以跨快照比档位必须连着当轮边界一起看。`model_plane.csv` 的 `next_tier_gap` 给出距上一档的距离，临界模型（当前最紧的是 K2 Horizon 375B A23B 差 0.031 到 M1）应当按“临界”读，不要按“稳进”读；源级 bootstrap 给了更直接的答案：全场最低的 GLM-5.3-Flash 是 0.418（点估计 M2、多数派 M1）。
13. **BenchmarkList 只做交叉校验**：30 个候选里 28 个能凑出“含锚点 + 映射后 ≥5 个模型”的快照，可用源里 21 个来自同三个发布事件（kimi.ai 14 个、x.com 4 个、minimax.io 3 个），25 个的快照里混着厂商自报行；连 GPQA Diamond 这种全量榜，BL 的快照也只有 6 行（榜上 478 个模型），映射到 6 个。接进拟合会违反“不做厂商自报加权平均”，量化理由见 METHOD §4.1。
14. **区间的宽度大于档位带宽**：源级 bootstrap 的中位区间宽度（P 0.453 / X 0.539）比一档的宽度（0.25）还大，档位稳定率中位只有 0.736（分档：M0 0.909、M1 0.680、M2 0.696、M3 0.756）。除 M0 那批，档位应当读成“大概在这一带”，不是“定在这一档”——`tier_stability` / `tier_presence` / `tier_mode` 就在 `model_plane.csv` 里，图上 tooltip 与表格也带着（METHOD §17）。另有 15 个模型的证据在场率低于 90%（来源只有一个，或只有两三块榜），它们在约三分之一的重采样里连坐标都没有，区间宽度 0 是“没证据”而不是“很确定”。
