# Skill Normalizer 独立模块 Spec 与 MVP

## 1. 项目目标

构建一个独立的技能标准化模块：

> 输入任意技能表达或技能相关短语，将其映射到系统内部统一的标准技能概念。

例如：

```text
输入：
库存预测

输出：
库存管理
```

```text
输入：
根据销量制定补货计划

输出：
库存管理
```

```text
输入：
Excel数据分析

输出候选：
1. Excel
2. 数据分析
```

本项目暂时不依赖现有 HR 招聘系统，也不需要理解：

```text
Job
Candidate
RequirementProfile
Resume
Pipeline
```

只负责：

```text
Raw Skill Text
        ↓
Skill Normalization
        ↓
Canonical Skill
```

---

# 2. MVP 核心问题

MVP 只验证以下问题：

1. 自建 Skill Taxonomy 是否可行；
2. Alias 精确匹配是否有效；
3. BGE Embedding 能否处理未收录的新表达；
4. Top-K 结果质量如何；
5. 自动匹配阈值应该设在哪里；
6. 哪些情况需要人工 Review；
7. Taxonomy 的技能粒度是否合理。

MVP 不追求：

```text
企业级技能库
几万个技能
自动生成 Taxonomy
复杂向量数据库
和 HR 主系统集成
```

---

# 3. 输入

最简单输入：

```json
{
  "text": "库存预测"
}
```

也允许：

```json
{
  "text": "根据销量制定补货计划"
}
```

批量接口：

```json
{
  "texts": [
    "库存预测",
    "Excel数据分析",
    "跨境电商运营"
  ]
}
```

---

# 4. 输出 Schema

统一输出：

```json
{
  "raw_text": "库存预测",
  "normalized": {
    "skill_id": "inventory_management",
    "canonical_name": "库存管理"
  },
  "score": 1.0,
  "match_type": "exact",
  "needs_review": false,
  "candidates": []
}
```

语义匹配时：

```json
{
  "raw_text": "根据销量制定补货计划",
  "normalized": {
    "skill_id": "inventory_management",
    "canonical_name": "库存管理"
  },
  "score": 0.87,
  "match_type": "semantic",
  "needs_review": false,
  "candidates": [
    {
      "skill_id": "inventory_management",
      "name": "库存管理",
      "score": 0.87
    },
    {
      "skill_id": "supply_chain_management",
      "name": "供应链管理",
      "score": 0.78
    },
    {
      "skill_id": "product_operation",
      "name": "商品运营",
      "score": 0.73
    }
  ]
}
```

不确定时：

```json
{
  "raw_text": "增长打法",
  "normalized": null,
  "score": 0.68,
  "match_type": "review",
  "needs_review": true,
  "candidates": [
    ...
  ]
}
```

完全无法判断：

```json
{
  "raw_text": "神秘能力",
  "normalized": null,
  "score": 0.41,
  "match_type": "unknown",
  "needs_review": true,
  "candidates": []
}
```

---

# 5. 核心枚举

```python
MatchType = Literal[
    "exact",
    "semantic",
    "review",
    "unknown"
]
```

含义：

```text
exact
Alias 或标准名称精确命中

semantic
Embedding 高置信度匹配

review
有候选结果，但不能自动确认

unknown
当前 Taxonomy 中没有可靠结果
```

---

# 6. Taxonomy 数据格式

MVP 第一版不需要数据库。

直接：

```text
data/skills.json
```

例如：

```json
[
  {
    "id": "data_analysis",
    "name": "数据分析",
    "category": "data",
    "description": "对业务数据进行整理、统计、分析，并使用数据辅助业务判断。",
    "aliases": [
      "数据分析能力",
      "业务数据分析",
      "运营数据分析",
      "数据处理分析"
    ]
  },
  {
    "id": "inventory_management",
    "name": "库存管理",
    "category": "ecommerce",
    "description": "包括库存控制、库存预测、补货计划、库存周转和库存风险管理。",
    "aliases": [
      "库存控制",
      "库存预测",
      "补货管理",
      "库存管理能力"
    ]
  }
]
```

---

# 7. Skill 数据模型

```python
class Skill(BaseModel):
    id: str
    name: str
    category: str | None = None
    description: str = ""
    aliases: list[str] = []
```

候选结果：

```python
class SkillCandidate(BaseModel):
    skill_id: str
    name: str
    score: float
```

最终结果：

```python
class SkillNormalizationResult(BaseModel):
    raw_text: str

    skill_id: str | None
    canonical_name: str | None

    score: float | None

    match_type: Literal[
        "exact",
        "semantic",
        "review",
        "unknown"
    ]

    needs_review: bool

    candidates: list[SkillCandidate]
```

---

# 8. MVP 总体流程

```text
输入 Raw Text
      │
      ▼
Text Normalization
      │
      ▼
Exact Match
      │
 ┌────┴────┐
 │         │
命中       未命中
 │         │
 ▼         ▼
返回      Embedding
           │
           ▼
         Top-K
           │
           ▼
    Threshold Decision
           │
    ┌──────┼──────┐
    ▼      ▼      ▼
 Semantic Review Unknown
```

---

# 9. Text Normalization

先做轻量文本标准化：

```python
def normalize_text(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(" ", "")
    )
```

后续可以扩展：

```text
全角半角
中英文标点
大小写
常见符号
```

但 MVP 不要做复杂 NLP 清洗。

---

# 10. Exact Matcher

构建：

```python
alias_map: dict[str, str]
```

例如：

```python
{
    "数据分析": "data_analysis",
    "数据分析能力": "data_analysis",
    "运营数据分析": "data_analysis",
    "库存预测": "inventory_management"
}
```

匹配：

```python
skill_id = alias_map.get(normalized_text)
```

如果成功：

```json
{
  "match_type": "exact",
  "score": 1.0,
  "needs_review": false
}
```

---

# 11. Embedding Matcher

模型：

```text
BAAI/bge-small-zh-v1.5
```

使用：

```python
SentenceTransformer
```

MVP 不需要向量数据库。

技能数量：

```text
100～300
```

全部 Embedding 常驻内存即可。

---

# 12. Skill Document 构造

不要只 Embedding：

```text
库存管理
```

建议：

```text
库存管理。
包括库存控制、库存预测、补货计划、
库存周转和库存风险管理。
相关表达：库存预测、库存控制、补货管理。
```

函数：

```python
def build_skill_document(skill: Skill) -> str:
    aliases = "、".join(skill.aliases)

    return (
        f"{skill.name}。"
        f"{skill.description}。"
        f"相关表达：{aliases}"
    )
```

---

# 13. Embedding 初始化

程序启动：

```python
skill_docs = [
    build_skill_document(skill)
    for skill in skills
]

skill_embeddings = model.encode(
    skill_docs,
    normalize_embeddings=True
)
```

只计算一次。

---

# 14. Semantic Search

输入：

```text
根据销量制定补货计划
```

生成 query embedding：

```python
query_embedding = model.encode(
    [text],
    normalize_embeddings=True
)
```

搜索 Top 5：

```python
hits = semantic_search(
    query_embedding,
    skill_embeddings,
    top_k=5,
)
```

输出：

```text
库存管理        0.87
供应链管理      0.79
商品运营        0.72
数据分析        0.65
采购管理        0.58
```

---

# 15. Threshold 策略

MVP 初始建议：

```text
Top1 >= 0.82
AND
Top1 - Top2 >= 0.05

→ semantic
```

如果：

```text
Top1 >= 0.70
```

但：

```text
Top1 < 0.82
```

或者：

```text
Top1 - Top2 < 0.05
```

则：

```text
review
```

如果：

```text
Top1 < 0.70
```

则：

```text
unknown
```

注意：

这些数字只是初始参数。

必须通过 Benchmark 调整。

---

# 16. 为什么需要 Margin

例如：

```text
商品运营 0.84
电商运营 0.83
```

虽然 Top1：

```text
0.84
```

很高。

但两者几乎一样。

因此：

```text
0.84 - 0.83 = 0.01
```

不能自动判断。

应该：

```text
review
```

而：

```text
库存管理 0.88
供应链管理 0.72
```

差距：

```text
0.16
```

更适合自动匹配。

---

# 17. SkillNormalizer 核心接口

```python
class SkillNormalizer:

    def normalize(
        self,
        text: str
    ) -> SkillNormalizationResult:
        ...
```

批量：

```python
def normalize_many(
    self,
    texts: list[str]
) -> list[SkillNormalizationResult]:
    ...
```

---

# 18. 推荐代码结构

```text
skill-normalizer/

├── app/
│   ├── __init__.py
│   │
│   ├── schemas.py
│   │
│   ├── taxonomy.py
│   │
│   ├── text_normalizer.py
│   │
│   ├── alias_matcher.py
│   │
│   ├── embedding_matcher.py
│   │
│   ├── normalizer.py
│   │
│   └── config.py
│
├── data/
│   └── skills.json
│
├── benchmark/
│   ├── cases.json
│   └── run_benchmark.py
│
├── tests/
│   ├── test_alias_matcher.py
│   ├── test_embedding_matcher.py
│   └── test_normalizer.py
│
├── scripts/
│   └── inspect_skill.py
│
├── main.py
├── requirements.txt
└── README.md
```

---

# 19. MVP 暂时不要 FastAPI

第一阶段甚至不需要 API。

直接做：

```bash
python main.py "库存预测"
```

输出：

```text
Input:
库存预测

Match:
库存管理

Type:
exact

Score:
1.0
```

再比如：

```bash
python main.py "根据销量制定补货计划"
```

输出：

```text
Input:
根据销量制定补货计划

Result:
库存管理

Type:
semantic

Score:
0.87

Top candidates:
库存管理       0.87
供应链管理     0.78
商品运营       0.73
```

这样调试效率最高。

等效果稳定以后再加：

```text
FastAPI
```

---

# 20. Benchmark 是整个项目最重要的部分

不要只凭：

```text
“感觉结果挺准”
```

建立：

```text
benchmark/cases.json
```

例如：

```json
[
  {
    "input": "库存预测",
    "expected": "inventory_management"
  },
  {
    "input": "根据销量制定补货计划",
    "expected": "inventory_management"
  },
  {
    "input": "Excel数据分析",
    "expected": "excel"
  },
  {
    "input": "分析点击率和转化率",
    "expected": "data_analysis"
  }
]
```

---

# 21. Benchmark 要包含三种数据

## A. 简单 Alias

例如：

```text
库存预测
→ 库存管理
```

---

## B. 隐式语义

例如：

```text
根据商品销量制定补货数量
→ 库存管理
```

---

## C. 容易混淆

例如：

```text
根据销售数据调整商品策略
```

可能：

```text
数据分析
商品运营
电商运营
```

这种测试最有价值。

---

# 22. 第一版 Benchmark 数量

先：

```text
50 条
```

很快扩到：

```text
100～200 条
```

不需要一开始造几千条。

---

# 23. Benchmark 指标

至少统计：

```text
Top1 Accuracy

Top3 Recall

Auto Match Accuracy

Review Rate

Unknown Rate
```

---

# 24. Top1 Accuracy

例如：

```text
100 个测试

Top1正确：
83

Top1 Accuracy：
83%
```

---

# 25. Top3 Recall

如果正确答案出现在：

```text
Top 3
```

就算召回成功。

例如：

```text
Top1：
商品运营

Top2：
数据分析

Expected：
数据分析
```

Top1 错。

但：

```text
Top3 Recall = success
```

说明：

> Embedding 能找到正确概念，只是排序需要优化。

---

# 26. Auto Match Accuracy

最重要。

因为真正危险的是：

```text
系统高置信度自动匹配错了
```

例如：

```text
match_type = semantic
needs_review = false
```

这种结果正确率最好非常高。

理想目标：

```text
>95%
```

哪怕因此 Review 多一点也没关系。

---

# 27. Review Rate

例如：

```text
100条

semantic自动匹配：
60

review：
30

unknown：
10
```

那么：

```text
Review Rate = 30%
```

后面可以逐渐降低。

---

# 28. Unknown 的意义

Unknown 不是失败。

它意味着：

> 当前 Taxonomy 无法可靠表达这个技能。

例如：

```text
TikTok Shop测款
```

如果库里没有：

```text
TikTok运营
```

返回：

```text
unknown
```

比硬映射到：

```text
商品运营
```

更安全。

---

# 29. Error Analysis

Benchmark 跑完之后，不要只看 Accuracy。

把错误分成：

```text
Taxonomy 缺失

Alias 缺失

Embedding误匹配

技能粒度冲突

一句话包含多个技能

Threshold问题
```

例如：

```text
“分析点击率并调整活动价格”

Expected:
数据分析 + 活动运营
```

但当前模型只能返回一个技能。

这不是 BGE 错了。

而是：

> 输入本身是 Multi-skill。

这种要单独分类。

---

# 30. MVP 第一版只允许 Single Skill

建议第一版明确：

> 一个输入最多标准化到一个主技能。

例如：

```text
Excel数据处理
```

→ Excel

而：

```text
分析销售数据并制定库存补货计划
```

这种 Multi-skill 输入：

```text
needs_review = true
```

后面再支持：

```text
normalize_to_multiple()
```

不要第一版同时解决所有问题。

---

# 31. Taxonomy 初始范围

不要做全行业。

第一版围绕你当前比较容易拿到测试案例的领域。

建议：

```text
基础办公
数据
软件开发
互联网运营
电商
跨境电商
HR
产品
```

先做：

```text
100～150 skills
```

就够。

---

# 32. Taxonomy 粒度原则

例如：

```text
Python
FastAPI
React
SQL
```

可以作为独立技能。

但是：

```text
良好的Python编码能力
Python开发能力
Python编程
```

应该：

```text
→ Python
```

再比如：

```text
库存预测
库存控制
补货管理
```

是否都是：

```text
库存管理
```

要根据你未来招聘筛选是否需要区分决定。

核心原则：

> Taxonomy 的粒度应该服务于招聘判断，而不是追求知识分类上的绝对正确。

---

# 33. MVP 不做自动 Taxonomy 扩充

遇到 Unknown：

```text
不要：
自动新增 Skill
```

第一版只输出：

```json
{
  "match_type": "unknown",
  "needs_review": true
}
```

然后你人工决定：

```text
新增 Skill

或

新增 Alias
```

---

# 34. 可选的小型 Review 工具

MVP 后期可以做一个非常简单的：

```text
python scripts/inspect_skill.py
```

输入：

```text
TikTok Shop测款
```

显示：

```text
Top candidates

TikTok运营       0.78
跨境电商运营     0.76
商品运营         0.72

Decision:
REVIEW
```

然后手动：

```text
1 → 添加为 TikTok运营 alias
2 → 创建新 skill
3 → ignore
```

这对构建 Taxonomy 很有用。

---

# 35. 第一阶段开发顺序

## Sprint 1

项目骨架：

```text
schemas
taxonomy loader
skills.json
```

先写：

```text
20～30个Skill
```

验证结构。

---

## Sprint 2

Alias Matcher：

```text
Text normalize
↓
Exact alias
↓
Skill
```

先保证确定性部分完全正确。

---

## Sprint 3

BGE Matcher：

```text
加载模型
↓
build skill docs
↓
embedding
↓
Top-K
```

---

## Sprint 4

Decision Logic：

```text
threshold
+
margin
↓
semantic / review / unknown
```

---

## Sprint 5

Benchmark：

准备：

```text
50～100 test cases
```

跑：

```text
Top1 Accuracy
Top3 Recall
Auto Accuracy
Review Rate
```

---

## Sprint 6

Error Analysis：

人工分析：

```text
哪些错了
为什么错
```

再调整：

```text
Taxonomy
Aliases
Description
Threshold
```

---

# 36. MVP 完成标准

以下流程必须稳定：

```text
输入技能短语
↓
Exact Alias Match
↓
如果未命中
↓
BGE Semantic Search
↓
Top5
↓
Threshold + Margin
↓
Exact / Semantic / Review / Unknown
```

并达到：

```text
Benchmark >= 100条

Auto Match Accuracy 足够高

所有结果可以查看 Top-K

Unknown 不会被强制错误映射
```

---

# 37. MVP Demo

例如：

```text
$ python main.py "库存预测"

库存管理
exact
1.00
```

---

```text
$ python main.py "根据销量制定补货计划"

库存管理
semantic
0.87

Candidates:
库存管理       0.87
供应链管理     0.78
商品运营       0.72
```

---

```text
$ python main.py "运营增长打法"

Result:
REVIEW

Candidates:
用户运营       0.76
增长运营       0.75
产品运营       0.72
```

---

```text
$ python main.py "量子招聘能力"

Result:
UNKNOWN
```

这个 Demo 跑通，MVP 就已经完成。

---

# 38. 未来和 HR 系统的对接

当前不要做。

但输出 Schema 保持稳定。

以后只需要：

```text
RequirementProfile.skills
        ↓
Adapter
        ↓
SkillNormalizer.normalize_many()
```

例如：

```json
{
  "skills": [
    "数据分析能力",
    "库存预测"
  ]
}
```

经过 Normalizer：

```json
[
  {
    "skill_id": "data_analysis",
    "name": "数据分析"
  },
  {
    "skill_id": "inventory_management",
    "name": "库存管理"
  }
]
```

主系统只依赖：

```text
SkillNormalizer API / Python Interface
```

不用知道内部是：

```text
Alias
BGE
Threshold
```

---

# 39. 后续版本路线

MVP v1：

```text
Alias
+
BGE
+
Top-K
+
Threshold
+
Benchmark
```

v2：

```text
Multi-skill extraction

人工Review UI

Taxonomy编辑

Alias学习
```

v3：

```text
LLM fallback

Context-aware normalization

中英文统一

自动发现新技能
```

v4：

```text
接入招聘画像

接入Resume Skill Extraction

Requirement ↔ Resume Skill Matching
```

---

# 40. 最终模块定位

这个项目最终不是一个：

> “BGE Demo”

而应该是一个：

> **可测试、可扩展、可人工维护的 Skill Normalization Engine。**

其核心职责永远保持简单：

```text
Raw Skill Expression
        ↓
Canonical Skill ID
```

至于这个 Skill 来自：

```text
JD
Resume
RequirementProfile
Chat
```

都不是 SkillNormalizer 需要关心的问题。