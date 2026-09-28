# Skill Normalizer｜DeepSeek + Jev 双 Provider 技术方案

## 1. 目标

当前 Skill Normalizer 保持统一业务架构：

```text
Skill Text
    │
    ▼
TextNormalizer
    │
    ▼
AliasMatcher
 ┌──┴───────────────┐
 │ exact            │ miss
 ▼                  ▼
Return Exact    SemanticMatcher
                     │
              ┌──────┴──────┐
              ▼             ▼
       DeepSeekMatcher   JevMatcher
              │             │
              └──────┬──────┘
                     ▼
               MatchResult
             /      |       \
       semantic   review   unknown
```

核心原则：

1. AliasMatcher、Taxonomy、FastAPI、Benchmark、日志完全共享。
2. DeepSeek 和 Jev 只作为 SemanticMatcher 的不同实现。
3. 不复制两套 SkillNormalizer。
4. Provider 可以通过配置切换。
5. Benchmark 可以让两种 Provider 对相同 case 分别运行。
6. 当前生产默认仍可使用 DeepSeek，Jev 作为 challenger。
7. 不做 DeepSeek → Jev 或 Jev → DeepSeek 串联。

---

# 2. 项目目录

建议调整为：

```text
skill-normalizer/
│
├─ app/
│  ├─ schemas.py
│  ├─ config.py
│  │
│  ├─ taxonomy/
│  │  ├─ repository.py
│  │  └─ validator.py
│  │
│  ├─ normalization/
│  │  ├─ text_normalizer.py
│  │  ├─ alias_matcher.py
│  │  └─ normalizer.py
│  │
│  ├─ matchers/
│  │  ├─ base.py
│  │  ├─ deepseek_matcher.py
│  │  ├─ jev_matcher.py
│  │  └─ registry.py
│  │
│  ├─ policies/
│  │  ├─ deepseek_policy.py
│  │  └─ jev_policy.py
│  │
│  └─ api/
│     └─ routes.py
│
├─ data/
│  └─ skills.json
│
├─ benchmark/
│  ├─ cases.json
│  ├─ run_benchmark.py
│  ├─ evaluator.py
│  └─ results/
│     ├─ deepseek.jsonl
│     └─ jev.jsonl
│
├─ tests/
└─ main.py
```

不需要为了两个 Provider 做复杂框架。

---

# 3. 统一业务输出

无论底层使用 DeepSeek 还是 Jev，SkillNormalizer 对外必须返回同一种结构。

```python
from typing import Literal
from pydantic import BaseModel


class SkillCandidate(BaseModel):
    skill_id: str
    name: str
    probability: float | None = None


class MatchResult(BaseModel):
    raw_text: str

    skill_id: str | None
    canonical_name: str | None

    match_type: Literal[
        "exact",
        "semantic",
        "review",
        "unknown",
    ]

    provider: Literal[
        "alias",
        "deepseek",
        "jev",
    ]

    confidence: float | None = None
    confidence_label: Literal[
        "high",
        "medium",
        "low",
    ] | None = None

    candidates: list[SkillCandidate] = []

    reason: str | None = None

    latency_ms: int | None = None

    input_tokens: int | None = None
    output_tokens: int | None = None
```

这里刻意同时保留：

```text
confidence
confidence_label
```

因为两个 Provider 的语义不同。

Jev：

```text
confidence = 原生 numeric confidence
```

DeepSeek：

```text
confidence_label = high / medium / low
```

不要人为做：

```text
DeepSeek high = 0.9
medium = 0.6
```

这种转换。

这会制造不存在的精度。

---

# 4. SemanticMatcher 接口

定义一个极薄的接口：

```python
from typing import Protocol


class SemanticMatcher(Protocol):

    @property
    def provider_name(self) -> str:
        ...

    def match(
        self,
        text: str,
        taxonomy: list,
    ) -> MatchResult:
        ...
```

然后分别实现：

```text
DeepSeekMatcher
JevMatcher
```

SkillNormalizer 不知道内部用了什么模型。

---

# 5. SkillNormalizer 主流程

核心代码应该非常简单：

```python
class SkillNormalizer:

    def __init__(
        self,
        taxonomy_repository,
        alias_matcher,
        semantic_matcher,
    ):
        self.taxonomy = taxonomy_repository
        self.alias_matcher = alias_matcher
        self.semantic_matcher = semantic_matcher

    def normalize(self, text: str) -> MatchResult:

        normalized_text = normalize_text(text)

        exact = self.alias_matcher.match(normalized_text)

        if exact:
            return MatchResult(
                raw_text=text,
                skill_id=exact.skill_id,
                canonical_name=exact.name,
                match_type="exact",
                provider="alias",
            )

        return self.semantic_matcher.match(
            text=normalized_text,
            taxonomy=self.taxonomy.all(),
        )
```

整个主流程完全不出现：

```text
if provider == deepseek
elif provider == jev
```

Provider 选择在初始化时解决。

---

# 6. Provider Registry

实现一个简单 Registry：

```python
class MatcherRegistry:

    def __init__(
        self,
        deepseek_matcher,
        jev_matcher,
    ):
        self.matchers = {
            "deepseek": deepseek_matcher,
            "jev": jev_matcher,
        }

    def get(self, provider: str):
        try:
            return self.matchers[provider]
        except KeyError:
            raise ValueError(
                f"Unsupported semantic matcher: {provider}"
            )
```

配置：

```env
SKILL_MATCHER_PROVIDER=deepseek

DEEPSEEK_API_KEY=xxx
DEEPSEEK_MODEL=deepseek-flash

TYPESAFE_API_KEY=xxx
JEV_MODEL=jev-latest
```

这样正式运行时：

```text
SKILL_MATCHER_PROVIDER=deepseek
```

即可。

以后：

```text
SKILL_MATCHER_PROVIDER=jev
```

无需改业务代码。

---

# 7. JevMatcher

## 7.1 输入设计

Jev 不需要传统 LLM prompt。

核心输入：

```text
state
+
Choice Question
+
criteria
```

例如输入技能：

```text
根据商品销量和销售周期制定补货数量
```

state：

```json
{
  "skill_expression": "根据商品销量和销售周期制定补货数量"
}
```

Choice：

```text
inventory_management
inventory_forecasting
replenishment_management
...
__unknown__
```

其中每一个 canonical Skill 都应该拥有 description。

---

# 8. Jev criteria 构建

skills.json：

```json
{
  "id": "replenishment_management",
  "name": "补货管理",
  "description": "根据库存状态、销量、需求预测等信息制定或执行补货计划。",
  "aliases": [
    "补货",
    "补货计划"
  ]
}
```

生成 Jev criteria：

```python
def build_jev_criteria(skills):
    criteria = {}

    for skill in skills:
        criteria[skill.id] = {
            "name": skill.name,
            "definition": skill.description,
        }

    criteria["__unknown__"] = {
        "name": "未知技能",
        "definition": (
            "输入表达无法可靠映射到任何现有标准技能。"
            "不得因为语义相关而强行选择近似技能。"
        ),
    }

    return criteria
```

这里暂时：

**不要把 aliases 塞给 Jev。**

因为 AliasMatcher 已经先执行。

Jev 应该测试真正的 semantic mapping 能力。

---

# 9. Jev API 调用

使用 HTTP 客户端即可，没有必要引入复杂 SDK。

```python
import httpx


class JevClient:

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: float = 10.0,
    ):
        self.model = model

        self.client = httpx.Client(
            base_url="https://api.typesafe.ai",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def choice(
        self,
        state,
        criteria,
    ):
        response = self.client.post(
            "/v1/systemone",
            json={
                "state": state,
                "model": self.model,
                "questions": {
                    "skill_match": {
                        "type": "choice",
                        "instructions": (
                            "选择与输入技能表达最匹配的标准技能。"
                            "必须优先选择输入直接支持的最具体技能；"
                            "不能因为存在语义关联而推断输入未表达的能力；"
                            "若没有可靠匹配项，选择 __unknown__。"
                        ),
                        "criteria": criteria,
                    }
                },
            },
        )

        response.raise_for_status()

        return response.json()
```

Jev 当前 OpenAPI 中，Choice 原生返回：

```text
choice
confidence
probabilities
```

其中 probabilities 是所有 choices 的概率映射。

---

# 10. Jev 原始结果

例如：

```json
{
  "choice": "replenishment_management",
  "confidence": 0.87,
  "probabilities": {
    "replenishment_management": 0.79,
    "inventory_management": 0.12,
    "inventory_forecasting": 0.06,
    "__unknown__": 0.03
  }
}
```

不要直接：

```text
choice → semantic
```

还需要 DecisionPolicy。

---

# 11. JevDecisionPolicy

第一版参数建议只作为实验起点：

```python
JEV_AUTO_CONFIDENCE = 0.80
JEV_AUTO_MARGIN = 0.15

JEV_UNKNOWN_THRESHOLD = 0.65
```

注意：

> 这些不是 Jev 官方推荐阈值，也不是固定真理，最终必须由你的 144 条 benchmark 校准。

---

## 11.1 Auto Match

例如：

```text
Top1 = 补货管理 0.82
Top2 = 库存管理 0.09

confidence = 0.91
margin = 0.73
```

满足：

```python
top1 != "__unknown__"
and confidence >= AUTO_CONFIDENCE
and margin >= AUTO_MARGIN
```

则：

```text
semantic
```

---

## 11.2 Review

例如：

```text
库存预测 0.44
补货管理 0.40
库存管理 0.12
```

虽然 Top1 有结果，但分布明显模糊。

返回：

```text
review
```

并保存 Top3：

```json
[
  {
    "skill_id": "inventory_forecasting",
    "probability": 0.44
  },
  {
    "skill_id": "replenishment_management",
    "probability": 0.40
  },
  {
    "skill_id": "inventory_management",
    "probability": 0.12
  }
]
```

---

## 11.3 Unknown

例如：

```text
__unknown__ 0.81
产品运营 0.08
用户运营 0.05
```

且：

```python
p_unknown >= UNKNOWN_THRESHOLD
```

返回：

```text
unknown
```

---

## 11.4 Unknown 不确定

如果：

```text
__unknown__ 0.39
产品运营 0.34
用户运营 0.21
```

不要直接 unknown。

返回：

```text
review
```

因为模型本身也不确定。

---

# 12. Jev Policy 代码

```python
def decide_jev(
    choice: str,
    confidence: float,
    probabilities: dict[str, float],
):

    ranked = sorted(
        probabilities.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    top1_id, top1_prob = ranked[0]

    top2_prob = (
        ranked[1][1]
        if len(ranked) > 1
        else 0.0
    )

    margin = top1_prob - top2_prob

    if top1_id == "__unknown__":
        if top1_prob >= JEV_UNKNOWN_THRESHOLD:
            return "unknown"

        return "review"

    if (
        confidence >= JEV_AUTO_CONFIDENCE
        and margin >= JEV_AUTO_MARGIN
    ):
        return "semantic"

    return "review"
```

第一版保持这么简单。

不要开始加入十几个 heuristics。

---

# 13. JevMatcher 完整职责

```text
输入文本
↓
build criteria
↓
调用 Jev
↓
解析 typed result
↓
JevDecisionPolicy
↓
构造统一 MatchResult
```

例如：

```python
class JevMatcher:

    provider_name = "jev"

    def __init__(
        self,
        client,
        policy,
    ):
        self.client = client
        self.policy = policy

    def match(self, text, taxonomy):

        criteria = build_jev_criteria(taxonomy)

        result = self.client.choice(
            state={
                "skill_expression": text
            },
            criteria=criteria,
        )

        answer = result["answers"]["skill_match"]

        status = self.policy.decide(answer)

        ranked = sorted(
            answer["probabilities"].items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return MatchResult(
            raw_text=text,
            skill_id=(
                answer["choice"]
                if status != "unknown"
                else None
            ),
            match_type=status,
            provider="jev",
            confidence=answer["confidence"],
            candidates=build_candidates(
                ranked[:3]
            ),
            input_tokens=result["usage"]["input_tokens"],
            output_tokens=result["usage"]["output_tokens"],
        )
```

---

# 14. DeepSeekMatcher 保持独立

DeepSeek 不要为了“统一 Jev”被迫改成概率模型。

它仍然做：

```text
Skill Expression
+
Taxonomy
+
Prompt
↓
DeepSeek
↓
JSON
```

输出：

```json
{
  "decision": "auto_match",
  "skill_id": "replenishment_management",
  "confidence": "high",
  "reason": "..."
}
```

然后映射：

```text
auto_match → semantic
review     → review
unknown    → unknown
```

但后端仍然必须：

```text
验证 skill_id 是否存在于 taxonomy
```

如果：

```text
skill_id 不存在
```

则不得接受。

返回：

```text
review / provider_error
```

或者直接标记调用失败。

---

# 15. 为什么不要强行让两者输出完全相同的内部结构

因为：

```text
DeepSeek
→ 文本生成模型
→ decision + reason + confidence label

Jev
→ decision model
→ choice + probability distribution + confidence
```

它们能力不同。

所以：

```text
Provider Raw Result
↓
Provider-specific policy
↓
统一 MatchResult
```

才合理。

不要：

```text
Jev模拟DeepSeek
```

也不要：

```text
DeepSeek伪造probability
```

---

# 16. FastAPI 设计

正式业务 API：

```http
POST /api/v1/normalize
```

请求：

```json
{
  "text": "根据商品销量制定补货数量"
}
```

默认使用：

```env
SKILL_MATCHER_PROVIDER
```

---

开发阶段增加：

```http
POST /api/v1/normalize/debug
```

请求：

```json
{
  "text": "根据商品销量制定补货数量",
  "provider": "jev"
}
```

或者：

```json
{
  "text": "...",
  "provider": "deepseek"
}
```

---

再增加专门实验接口：

```http
POST /api/v1/normalize/compare
```

返回：

```json
{
  "alias_match": null,

  "deepseek": {
    "skill_id": "replenishment_management",
    "match_type": "semantic",
    "confidence_label": "high",
    "latency_ms": 1832
  },

  "jev": {
    "skill_id": "replenishment_management",
    "match_type": "semantic",
    "confidence": 0.89,
    "latency_ms": 212,
    "candidates": [
      {
        "skill_id": "replenishment_management",
        "probability": 0.81
      },
      {
        "skill_id": "inventory_management",
        "probability": 0.11
      }
    ]
  }
}
```

这个接口：

> 只用于开发 / Benchmark / Debug。

生产业务代码不要依赖 compare。

---

# 17. Shadow Mode

以后真正接到招聘系统时，可以加入：

```env
SKILL_MATCHER_PROVIDER=deepseek
SKILL_MATCHER_SHADOW_PROVIDER=jev
```

流程：

```text
用户请求
↓
Alias miss
↓
DeepSeek
↓
正式结果
```

同时：

```text
          └────→ Jev
                 ↓
              只记录
```

Jev 的结果：

```text
不影响用户结果
不推进流程
不写业务状态
```

只进入日志。

这样可以在真实流量中比较：

```text
DeepSeek / Jev agreement rate
Latency
Confidence
Review rate
```

不过你现在不需要立刻做 Shadow Mode。

Benchmark 先跑够。

---

# 18. Benchmark 架构

现有：

```text
benchmark/cases.json
```

完全不要改 ground truth。

执行：

```bash
python benchmark/run_benchmark.py --provider deepseek

python benchmark/run_benchmark.py --provider jev
```

输出：

```text
results/deepseek.jsonl
results/jev.jsonl
```

---

# 19. 两层 Benchmark

一定同时做：

## A. End-to-End

```text
Alias
+
SemanticMatcher
```

评价整个系统。

---

## B. Semantic-only

只选：

```text
AliasMatcher 没有命中的 cases
```

然后：

```text
DeepSeekMatcher
vs
JevMatcher
```

这是判断模型能力最重要的一组。

否则大量 exact alias case 会把结果差异稀释。

---

# 20. 统一指标

至少输出：

```text
Cases

Exact Accuracy
Acceptable Accuracy

Auto Match Precision
Auto Match Count
Auto Match Coverage

Review Rate
Unknown Rate
Unknown Rejection

Average Latency
P50 Latency
P95 Latency

Input Tokens
Output Tokens
Estimated Cost
```

Jev额外输出：

```text
Mean Confidence

Mean Correct Confidence
Mean Incorrect Confidence

Mean Margin

Calibration by Confidence Bucket
```

---

# 21. Jev Calibration 实验

这是 Jev 最值得额外测试的一项。

分桶：

```text
0.0–0.5
0.5–0.6
0.6–0.7
0.7–0.8
0.8–0.9
0.9–1.0
```

统计：

```text
bucket
cases
accuracy
```

例如：

```text
confidence    cases    accuracy

0.50–0.60       12       58%
0.60–0.70       19       68%
0.70–0.80       25       80%
0.80–0.90       33       91%
0.90–1.00       31       97%
```

如果大致呈现：

```text
confidence 越高
→ accuracy 越高
```

说明 confidence 对你这套中文 HR Taxonomy 确实有使用价值。

如果完全不相关：

```text
就不要直接依赖它作为自动确认阈值。
```

TypeSafe 把 Jev 的概率与 confidence 作为自动化决策核心能力，但你自己的中文招聘数据仍应自行校准。

---

# 22. Jev Confusion Matrix

Jev 的完整概率分布还可以帮助维护 taxonomy。

重点找：

```text
真实 Skill A

但概率经常：
A = 0.45
B = 0.42
```

例如：

```text
库存管理
vs
补货管理

招聘管理
vs
招聘流程管理

数据分析
vs
数据统计

需求管理
vs
产品管理
```

这种 pair 应该输出：

```text
Top Confusing Skill Pairs
```

用于检查：

```text
description 是否不清晰
taxonomy 粒度是否冲突
parent-child 是否过近
```

这是 Jev 相对 DeepSeek 一个挺有价值的额外诊断能力。

---

# 23. 日志

每次 Semantic Match 统一记录：

```json
{
  "run_id": "uuid",
  "text": "...",

  "provider": "jev",
  "model": "jev-latest",

  "skill_id": "replenishment_management",
  "match_type": "semantic",

  "confidence": 0.88,

  "top_candidates": [
    ["replenishment_management", 0.82],
    ["inventory_management", 0.11],
    ["inventory_forecasting", 0.05]
  ],

  "latency_ms": 236,

  "input_tokens": 1320,
  "output_tokens": 0,

  "error": null
}
```

DeepSeek同样使用这个 audit envelope。

Provider-specific 字段可以放：

```json
{
  "provider_metadata": {}
}
```

不用为了统一日志把所有差异抹掉。

---

# 24. 错误策略

## Alias

不会发生远程错误。

---

## DeepSeek API Error

```text
timeout
rate_limit
provider_error
invalid_json
schema_error
```

不要偷偷切换 Jev。

---

## Jev API Error

```text
timeout
429
5xx
invalid_response
unknown_model
```

同样：

> 默认不要自动 fallback 到 DeepSeek。

否则 Benchmark 和生产问题会变得很难定位。

第一版：

```text
Provider失败
→ normalization failed
```

或者：

```text
→ review
```

根据调用场景决定。

但一定记录：

```text
error_stage
provider
```

---

# 25. 为什么暂时不要自动 Provider Fallback

不要现在做：

```text
Jev失败
→ DeepSeek

DeepSeek失败
→ Jev
```

虽然看起来“高可用”，但会导致：

```text
结果来源难追踪
benchmark失真
延迟不可预测
成本不可预测
错误被掩盖
```

当前实验阶段：

```text
Provider A 就只跑 A
Provider B 就只跑 B
```

最干净。

以后生产化再决定是否需要 fallback。

---

# 26. 模型配置

Jev 模型名不要永远写死。

官方 API 提供：

```http
GET /v1/models
```

用于查看当前账号可使用的模型名称。

所以配置：

```env
JEV_MODEL=jev-latest
```

应用启动时可以选择：

```text
开发环境：
直接使用配置

CI / Benchmark：
记录实际响应返回的 resolved model

生产：
启动健康检查时验证模型存在
```

日志必须记录 API 最终返回的：

```text
model
```

因为 alias 将来可能指向新版本。

---

# 27. 测试

至少覆盖：

### Alias

```text
标准名命中
alias命中
大小写
空格
中文标点
```

### Jev Policy

人工构造概率：

```text
高 confidence + 大 margin
→ semantic

低 margin
→ review

unknown 高概率
→ unknown

unknown 低概率
→ review
```

### Jev response parser

```text
正常response
缺answer
缺probabilities
不存在skill_id
HTTP 401
HTTP 429
HTTP 500
timeout
```

### DeepSeek

继续保留现有：

```text
JSON parse
Schema validation
Skill ID validation
```

---

# 28. 开发顺序

不要一次全部实现。

## Step 1

抽象现有：

```text
DeepSeekMatcher
```

让当前系统仍然正常工作。

目标：

```text
重构前后 benchmark 结果完全一致。
```

---

## Step 2

定义：

```text
SemanticMatcher
MatchResult
MatcherRegistry
```

---

## Step 3

写：

```text
JevClient
```

先用一个：

```text
3 Skill + unknown
```

的小实验测试 API。

---

## Step 4

接完整 80 Skill Taxonomy。

---

## Step 5

实现：

```text
JevDecisionPolicy
```

初始阈值先固定。

---

## Step 6

跑：

```text
144-case benchmark
```

暂时不要调参数。

得到第一版 baseline。

---

## Step 7

做：

```text
Jev confidence / margin distribution
```

再调：

```text
AUTO_CONFIDENCE
AUTO_MARGIN
UNKNOWN_THRESHOLD
```

---

## Step 8

生成正式对比：

```text
Alias + DeepSeek
vs
Alias + Jev
```

再决定主 Provider。

---

# 29. 当前暂时不要做

以下全部先不做：

```text
DeepSeek → Jev
Jev → DeepSeek
BGE → Jev
Jev + BGE ensemble
自动provider fallback
动态routing
多模型投票
数据库保存所有probabilities
Agent调用
Resume Screening接入
```

先把：

```text
DeepSeekMatcher
vs
JevMatcher
```

比较清楚。

---

# 30. 最终当前架构

```text
                      SkillNormalizer
                            │
                     TextNormalizer
                            │
                       AliasMatcher
                   ┌────────┴─────────┐
                   │                  │
                 exact               miss
                   │                  │
                   ▼                  ▼
              MatchResult       MatcherRegistry
                                      │
                        ┌─────────────┴─────────────┐
                        │                           │
                        ▼                           ▼
                DeepSeekMatcher                JevMatcher
                        │                           │
             Prompt + JSON                  Choice Question
                        │                           │
             Provider Decision             Probability Dist.
                        │                           │
             DeepSeekPolicy                  JevPolicy
                        │                           │
                        └─────────────┬─────────────┘
                                      ▼
                                MatchResult
                          semantic/review/unknown
```

这就是当前最合适的双架构。

---

# 31. 技术决策

当前不要决定：

> “Jev 替代 DeepSeek。”

当前技术决策应该是：

> SkillNormalizer 的语义标准化能力抽象为 SemanticMatcher，并并行实现 DeepSeekMatcher 与 JevMatcher。两者共享 AliasMatcher、Skill Taxonomy、API Schema、Benchmark 与 Evaluation，通过同一套 144-case Benchmark 比较准确率、Unknown 拒绝能力、自动确认精确率、Review Rate、延迟、成本以及稳定性；在数据足够前不进行模型级串联或自动 fallback。

这样即使最终 Jev 实验失败，这次改造也不会浪费。

因为你得到的：

```text
SemanticMatcher abstraction
+
统一 Benchmark
+
Provider 可替换能力
```

本身就是正确的工程结构。