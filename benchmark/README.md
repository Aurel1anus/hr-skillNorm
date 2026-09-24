# Skill Normalizer Benchmark v1

第一版 benchmark，用于暴露 Skill Normalizer 与 Skill Taxonomy 的真实问题，而不是为了跑出高分。

## 1. 产物

| 文件 | 说明 |
| --- | --- |
| `data/skills.json` | Taxonomy 草案，80 个 canonical skill，含 `domain` 与 `parent_id` |
| `benchmark/cases.json` | 144 条 benchmark case，6 领域 × 6 类型 |
| `benchmark/validate_benchmark.py` | 自检脚本，校验 10 项规则 + benchmark 泄漏 |

```bash
python benchmark/validate_benchmark.py
python benchmark/run_benchmark.py
```

`run_benchmark.py` 会加载项目内的 BGE 模型，逐条运行全部 Case，并输出 Top1 Accuracy、Top3 Recall、Auto Match Precision、Review Rate、Unknown Rate 和 Unknown Rejection。需要保存完整结果时使用：

```bash
python benchmark/run_benchmark.py --json-out benchmark/results.json
```

## 2. 统计摘要

| 指标 | 数值 |
| --- | --- |
| canonical skills | 80 |
| benchmark cases | 144 |
| 领域数 | 6（每领域 24 条） |
| case 类型数 | 6（每领域均覆盖） |
| ambiguous case | 24（16.7%） |
| unknown case | 12（8.3%） |
| 有 parent 的子技能 | 29 |

### domain 分布

| domain | skills | cases |
| --- | --- | --- |
| 跨境电商/运营 | 16 | 24 |
| 软件开发 | 15 | 24 |
| 产品 | 14 | 24 |
| HR/招聘 | 13 | 24 |
| 数据 | 12 | 24 |
| 办公软件 | 10 | 24 |

### type 分布（目标比例对照）

| type | 数量 | 占比 | 目标 |
| --- | --- | --- | --- |
| canonical | 12 | 8.3% | 10% |
| alias | 30 | 20.8% | 20% |
| semantic | 30 | 20.8% | 20% |
| context | 36 | 25.0% | 25% |
| ambiguous | 24 | 16.7% | 15% |
| unknown | 12 | 8.3% | 10% |

每个领域固定为：canonical 2 / alias 5 / semantic 5 / context 6 / ambiguous 4 / unknown 2。

### difficulty 分布

easy 54，medium 61，hard 29。

## 3. Benchmark 支持的指标

| 指标 | 计算口径 |
| --- | --- |
| Alias Exact Match | canonical + alias case 的 Top1 命中率 |
| Top1 Accuracy | 全部 case 的 Top1 命中率（含 acceptable） |
| Top3 Recall | expected 是否落在 Top-3 候选 |
| Auto Match Precision | `needs_review=false` 的结果中，命中 expected/acceptable 的比例（最关键的指标） |
| Review Rate | `match_type=review` 占比 |
| Unknown Rejection | unknown case 中返回 review/unknown（而非强行 semantic）的比例 |
| Taxonomy 粒度合理性 | 人工看 ambiguous case 的 Top-K 是否稳定出现在同一父技能簇内 |

## 4. 最容易混淆的 10 组 Skill

| # | 混淆组 | 混淆点 |
| --- | --- | --- |
| 1 | `inventory_management` / `inventory_forecasting` / `replenishment_management` / `inventory_control` | 同一父技能下 3 个子技能，句子常常同时包含预测与补货 |
| 2 | `ecommerce_operation` / `product_operation` / `campaign_operation` | 「运营策略」既可指店铺整体，也可指商品或活动 |
| 3 | `interview_scheduling` / `interview_coordination` / `candidate_communication` | 邀约、协调面试官、候选人沟通在 JD 中通常写在同一句 |
| 4 | `excel` / `spreadsheet_processing` / `pivot_table` / `vlookup` | 父技能与 3 个子功能，句子往往同时出现多个功能 |
| 5 | `excel_data_analysis` / `excel` / `data_analysis` | 「Excel + 分析」的交叉表达，无法判断应落到工具、方法还是交叉技能 |
| 6 | `sql` / `database_development` / `data_analysis` | 写 SQL 是取数、开发还是分析，取决于句型而非关键词 |
| 7 | `python` / `python_backend_development` / `backend_development` / `fastapi` | 语言、方向、框架三层同时出现在一句话里 |
| 8 | `requirements_management` / `requirements_analysis` / `requirement_prioritization` / `prd` | 需求类 4 个技能语义高度重叠 |
| 9 | `product_management` / `project_management` / `cross_functional_collaboration` | 「推动上线」可以是产品管理、项目管理或纯协调 |
| 10 | `user_research` / `user_feedback_analysis` | 主动用研 vs 被动收集反馈，文本上很难区分 |
| 补充 | `powerpoint` / `ppt_design` | 同一交付物的两个层级，几乎无法从文本区分 |
| 补充 | `report_generation` / `data_visualization` / `metric_analysis` | 报表、看板、指标监控经常混在一句话 |

## 5. Taxonomy 最需要人工复核的地方

1. **`recruitment` 下 11 个子技能全部同级**，层级过于扁平，缺少「招聘执行 / 招聘策略」这类中间层。
2. **`project_management` 被放在「产品」domain**，但它是跨领域通用技能；后续应决定是独立 domain 还是跨领域共享技能。
3. **`tiktok_shop_operation` 单平台收录造成不对称**：SHEIN、Amazon 未收录，平台类技能的收录边界需要明确规则（是否「平台即技能」）。
4. **`data_analysis` 与 `metric_analysis` / `excel_data_analysis` / `traffic_analysis` 的父子关系**需要复核，「分析类」技能容易形成多个并列入口。
5. **`product_operation` 与 `ecommerce_operation` 的包含关系不清**：当前 `product_operation.parent_id = null`，但业务上商品运营通常从属于店铺运营，benchmark 中 `ecommerce_019` / `ecommerce_021` 会持续暴露这一点。
6. **办公软件 3 个 Excel 子技能是否值得独立成为 canonical**：如果招聘筛选不需要区分，应合并为 Excel 的 alias。
7. **软技能完全不在 taxonomy**（by design），所有 12 条 unknown case 都依赖这一约定；需要确认招聘系统是否真的只做专业技能。
8. **`inventory_control` 的边界**：它与 `inventory_management` 高度接近，容易退化成 alias 关系。

## 6. 发现的粒度冲突

| 冲突 | 说明 |
| --- | --- |
| `powerpoint` vs `ppt_design` | 同一交付物拆成「软件操作」和「材料制作」，embedding 几乎无法区分 |
| `excel` vs `excel_data_analysis` | 工具技能与交叉技能跨 domain 并存，导致「Excel数据分析」有三条合法出口 |
| `inventory_forecasting` vs `data_modeling` | 「销量预测」既能算库存业务技能，也能算建模技能，归属取决于 domain 视角 |
| `traffic_analysis` vs `data_analysis` | 运营场景下的数据分析，父技能与领域技能重叠 |
| `report_generation` vs `data_visualization` | 看板/报表类表达同时命中两者 |
| 招聘/产品下的子技能 | 大量子技能证据不足，实际会退化为父技能的语义近邻，threshold + margin 会频繁落到 review |

## 7. 可能缺失但值得加入的 Skill

- `influencer_marketing` 达人营销 / 红人合作（对应 unknown `ecommerce_024`）
- `listing_optimization` 商品信息优化（对应 context `ecommerce_014` 的争议答案）
- `livestream_operation` 直播运营
- 平台对称性：`amazon_operation`、`shein_operation`
- `data_engineering` 数据工程 / 数仓建模（区分于 `data_modeling`）
- `data_compliance` 数据合规与隐私（对应 unknown `data_023`）
- `kubernetes` 容器编排（对应 unknown `software_023`）
- `spring_boot`（对应 ambiguous `software_022`）
- `agile_scrum` 敏捷 / Scrum
- `employer_branding` 雇主品牌、`employee_relations` 员工关系（对应 unknown `hr_024`）
- `ui_design` UI / 视觉设计（对应 unknown `product_023`）
- `bi_tools` BI 工具（看板与指标平台的落地工具）
- 领域缺口：第一版 6 个 domain 不含**泛互联网运营**（用户运营、内容运营、增长运营）、**市场营销**、**客服**，旧版 20 技能草案中的相关技能已被移除，需要确认这是否是产品范围的预期收缩。

## 8. Benchmark 泄漏防护

- `alias` case 的输入必然是 taxonomy 中真实存在且稳定的别称，用于测试 alias 字典。
- `semantic` / `context` / `ambiguous` / `unknown` 的输入**不允许**写入 `aliases`，自检脚本会逐条比对，输入与任何 `name`/`alias` 完全相同时直接报错。
- Alias 只保留真正稳定可复用的别称（如「库存管控」「PPT」「跨境运营」），不收录完整工作句式。

## 9. 已知争议 case（有意保留）

| case | 争议点 |
| --- | --- |
| `ecommerce_014` | 商品信息优化没有独立技能，只能落到 `product_operation` |
| `ecommerce_024` | 「达人建联」与 `tiktok_shop_operation` 有语义吸引，正确答案是 unknown |
| `data_016` | 「销量预测模型」归属 `data_modeling` 还是 `inventory_forecasting` |
| `software_022` | Spring Boot 未收录，但 Java 明确，不能整体判 unknown |
| `office_019` | 「Excel数据处理与分析」同时命中工具、交叉技能和分析能力 |
| `office_022` | 一句话包含两个并列技能，expected 依赖「按输入顺序取前者」的约定 |
| `hr_020` / `hr_021` | 电话初筛既是筛选也是沟通 |
