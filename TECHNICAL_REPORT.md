# Skill Normalizer — 完整技术报告（面向 AI 阅读）

> 本报告的事实来源：仓库源码、`data/skills.json`、`benchmark/` 产物的实际统计、`git log` 与两份设计文档。
> 所有数字均为本次实际测量结果，非估计值。测量命令见附录 A。

---

## 0. 30 秒速览（TL;DR）

| 项 | 值 |
|---|---|
| 项目名称 | Skill Normalizer（技能标准化器） |
| 核心职责 | `Raw Skill Text` → `Canonical Skill ID`（**单技能**，一进一出） |
| 技术栈 | Python 3（标准库为主）+ FastAPI/uvicorn；前端为无构建的原生 HTML/CSS/JS |
| 架构模式 | 分层单体 + Provider 策略模式（语义匹配器可插拔） |
| 匹配流水线 | `TextNormalizer` → `AliasMatcher`(精确) → 命中即返回；未命中 → `SemanticMatcher`(DeepSeek \| Jev) |
| 语义 Provider | `deepseek`（默认，文本生成模型）/ `jev`（challenger，概率决策模型） |
| Provider 关系 | **并列，不串联、不自动 fallback** |
| Taxonomy | `data/skills.json`，80 个 canonical skill，161 条 alias，29 个有 parent |
| Benchmark | 144 条 case（132 known + 12 unknown），6 领域 × 6 类型 |
| 当前实测（e2e，144 case） | DeepSeek Top1 97.73% / Auto Precision 99.17% / Review 7.64%；Jev Top1 97.73% / Auto Precision 99.13% / Review 13.19% |
| 依赖数量 | 运行时仅 3 个第三方包（fastapi、uvicorn、python-multipart） |
| 目录总数 | 5 个包（`app/`、`benchmark/`、`frontend/`、`tests/`、`data/`） |

---

## 1. 项目定位与边界

### 1.1 唯一职责

```text
Raw Skill Expression
        ↓
Skill Normalization
        ↓
Canonical Skill ID
```

### 1.2 明确不做（by design）

以下概念在代码中**完全不出现**，任何涉及它们的改动都超出本项目边界：

```text
Job / Candidate / RequirementProfile / Resume / Pipeline
多技能抽取（multi-skill extraction）
自动生成或自动扩充 Taxonomy
向量数据库
与 HR 主系统集成
DeepSeek ↔ Jev 串联或自动 fallback
Ensemble / 多模型投票 / 动态 routing
```

### 1.3 硬约束（违反即为架构破坏）

1. **单技能**：一次 `normalize()` 最多返回一个 `skill_id`。多技能输入应落为 `review`。
2. **共享单例**：`Taxonomy`、`AliasMatcher`、`SkillNormalizer`、`MatchResult Schema`、FastAPI、Benchmark、Evaluation 在 Provider 之间**完全共享**，不允许复制两套。
3. **主流程零 Provider 分支**：`SkillNormalizer.normalize()` 内部不得出现 `if provider == "deepseek" / elif provider == "jev"`。Provider 选择只在初始化时解决（Registry）。
4. **不做精度伪造**：不得将 DeepSeek 的 `high/medium/low` 映射为 `0.9/0.6/0.3`，也不得为 DeepSeek 伪造 probability 分布。
5. **不吞掉 Provider 错误**：Provider 失败时禁止静默切换到另一个 Provider（否则 benchmark 失真、成本/延迟不可预测）。

---

## 2. 仓库结构与文件清单

```
resume_reader/
├── app/                          # 核心领域层（9 个 .py，无第三方依赖）
│   ├── __init__.py               # 仅 re-export：DeepSeekMatcher, Skill, SkillCandidate,
│   │                             #   SkillNormalizationResult, SkillNormalizer
│   ├── schemas.py                # 数据模型（唯一真源）
│   ├── taxonomy.py               # skills.json 加载 + id 唯一性校验
│   ├── text_normalizer.py        # 文本归一化（3 行）
│   ├── alias_matcher.py          # 精确/别名匹配 + 冲突检测
│   ├── normalizer.py             # 编排器（SkillNormalizer）+ Matcher Protocol
│   ├── matchers.py               # SemanticMatcher Protocol + MatcherRegistry
│   ├── deepseek_matcher.py       # Provider A
│   └── jev_matcher.py            # Provider B（含 JevClient + JevPolicy 内联）
├── api_server.py                 # FastAPI HTTP 桥接层（唯一 Web 入口）
├── main.py                       # CLI 入口
├── requirements.txt              # 仅 3 个运行时依赖
├── README.md
├── .env.example                  # 环境变量模板（.env 已 gitignore）
├── .gitignore
├── data/
│   └── skills.json               # Taxonomy（80 条）
├── benchmark/
│   ├── cases.json                # 144 条评测 case（ground truth，禁止改）
│   ├── inputs.json               # 从 cases.json 抽取的 {id, input} 精简输入集
│   ├── evaluation.py             # 共享指标计算器（唯一评测口径）
│   ├── validate_benchmark.py     # 数据自检 + benchmark 泄漏检查
│   ├── run_provider_benchmark.py # 双 Provider 共用 runner（e2e / semantic-only）
│   ├── run_deepseek_baseline.py  # DeepSeek-only baseline（无 alias/无检索）
│   ├── test_run_deepseek_baseline.py
│   ├── README.md                 # benchmark 规格与已知争议说明
│   ├── deepseek_results.json     # baseline 完整产物（含 traces）
│   ├── results.json / results_1..5.json   # ⚠️ BGE 时代遗留产物
│   └── results/
│       ├── deepseek-e2e.jsonl    # ⚠️ 未纳入 git（untracked）
│       ├── jev-e2e.jsonl
│       ├── jev-e2e_1.jsonl
│       └── jev-smoke.jsonl
├── frontend/                     # 无构建 SPA
│   ├── index.html                # 3 个 Tab：单条 / 批量 / Taxonomy
│   ├── app.js                    # 原生 JS，fetch 调 API，手写 HTML escape
│   └── style.css
├── tests/
│   ├── test_normalizer.py
│   └── test_deepseek_matcher.py
├── models/bge-small-zh-v1.5/     # ⚠️ 遗留物，已 gitignore（见 §3）
└── *.md                          # 两份设计文档（见 §14）
```

**值得注意的遗留物/不一致点：**

| 项 | 状态 | 说明 |
|---|---|---|
| `models/bge-small-zh-v1.5/` | 死代码/死资产 | 被 `.gitignore` 排除。BGE 时代残留，无任何 `.py` 引用它 |
| `benchmark/results.json`, `results_1..5.json` | 历史产物 | BGE 时代的指标输出（`review_rate≈0.278`、`unknown_rate≈0.403`），与当前架构不可比 |
| `benchmark/results/deepseek-e2e.jsonl` | untracked | `git status` 显示为新增未提交文件 |
| `Skill` 模型的 `category` 字段 | 未被数据使用 | `skills.json` 中无 `category` 键；`api_server` 用 `skill.category or skill.domain` 兜底 |

---

## 3. 演进历史（git log，时间正序）

| commit | 说明 | 架构含义 |
|---|---|---|
| `bf3dff7` | 第一次 | 初始骨架 |
| `4158f6c` | benchmark | 建立 144-case 评测体系 |
| `fa66371` | BGE模型最终版本，之后改为LLM判断 | **分水岭**：embedding 方案终结 |
| `97397ff` | refactor: use exact matching with DeepSeek fallback | 确立「Alias 精确 + LLM 兜底」主流水线 |
| `58377c0` | feat: load DeepSeek settings from env file | 引入自研 `load_env()`（不依赖 python-dotenv） |
| `c4a22c4` | jev+deepseek双架构 | 引入 `SemanticMatcher` 抽象 + `MatcherRegistry` |

**结论**：当前架构是「**BGE 向量检索 → LLM 语义判定**」这一技术路线切换后的产物。所有 BGE 相关资产均已废弃，但物理文件未清理。

---

## 4. 架构分层与依赖方向

```text
┌─────────────────────────── 表现层 ──────────────────────────┐
│ frontend/  (index.html + app.js + style.css)                │
│   单条标准化 / 批量标准化 / Taxonomy 浏览与搜索              │
│   由 FastAPI StaticFiles 挂载于 /static，页面由 SPA fallback │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP + JSON (CORS allow_origins=["*"])
┌─────────────────────────── 接口层 ──────────────────────────┐
│ api_server.py  (FastAPI app, title="Skill Normalizer")      │
│   GET  /api/skills                                          │
│   POST /api/normalize          ← 默认 Provider               │
│   POST /api/normalize-many     ← 批量                        │
│   POST /api/normalize/debug    ← 指定 Provider               │
│   POST /api/normalize/compare  ← 双 Provider 并排            │
│   GET  /static/*               ← 静态资源                    │
│   GET  /{full_path:path}       ← SPA fallback → index.html   │
└────────────────────────────┬────────────────────────────────┘
                             │ 进程内单例（模块级初始化）
┌────────────────────── 核心领域层 app/ ──────────────────────┐
│                                                             │
│  SkillNormalizer (normalizer.py)                            │
│     ├── AliasMatcher (alias_matcher.py)                     │
│     │      └── normalize_text (text_normalizer.py)          │
│     └── SemanticMatcher  ← Protocol，运行时注入             │
│            ├── DeepSeekMatcher  (deepseek_matcher.py)       │
│            └── JevMatcher       (jev_matcher.py)            │
│                                                             │
│  MatcherRegistry (matchers.py)   ← provider 名 → 实例        │
│  schemas.py                      ← Skill / SkillCandidate /  │
│                                    SkillNormalizationResult  │
│  taxonomy.py                     ← load_skills()             │
└────────────────────────────┬────────────────────────────────┘
                             │
┌─────────────────────────── 数据层 ──────────────────────────┐
│ data/skills.json   （进程启动时一次性载入内存，无数据库）   │
└─────────────────────────────────────────────────────────────┘

旁路（并行复用核心层）：
  main.py                         CLI
  tests/                          unittest（离线，无网络）
  benchmark/run_provider_benchmark.py   双 Provider 评测
  benchmark/run_deepseek_baseline.py    DeepSeek-only 消融
```

### 4.1 依赖方向规则

- `app/schemas.py` 是**叶子节点**，不被任何 `app/` 内模块反向依赖（零内部依赖）。
- `app/normalizer.py` 只依赖 `alias_matcher` + `schemas`（**不 import 任何 Provider**）。
- 两个 Provider 只依赖 `schemas`，互不依赖。
- `matchers.py` 只依赖 `schemas`，提供 Protocol 与 Registry。
- 依赖注入点：`SkillNormalizer(skills, semantic_matcher=...)`；`api_server` 与 `main.py` 是**唯一的组装点**。

### 4.2 模块级初始化（进程启动时执行一次）

`api_server.py` 顶层代码在 import 时执行：

```python
_skills   = load_skills(SKILLS_PATH)                                  # 读 80 条 taxonomy
_registry = MatcherRegistry([DeepSeekMatcher(_skills), JevMatcher(_skills)])
_default_provider = os.getenv("SKILL_MATCHER_PROVIDER", "deepseek")
_normalizer = SkillNormalizer(_skills, semantic_matcher=_registry.get(_default_provider))
```

**关键性质：启动时不会发起任何网络调用。** `DeepSeekMatcher.__init__` / `JevMatcher.__init__` 仅构造 prompt/criteria 字符串，API Key 缺失也不报错——错误只在 `match()` 被调用且 alias 未命中时才以 `RuntimeError` 抛出。

⚠️ 注意：`_registry.get(_default_provider)` 在**模块 import 期**执行，若 `SKILL_MATCHER_PROVIDER` 填了非法值，会直接抛 `ValueError` 导致服务无法启动（启动期 fail-fast）。

---

## 5. 核心数据流（精确时序）

```text
normalize(text)
  │
  ├─ [1] normalize_text(text)              # strip() → lower() → replace(" ","")
  │
  ├─ [2] AliasMatcher.match(normalized)
  │        alias_map.get(key) → Skill | None
  │
  ├─ 命中 ──► SkillNormalizationResult(
  │              raw_text      = 原始 text（注意：不是归一化后的）
  │              skill_id      = exact.id
  │              canonical_name= exact.name
  │              score         = 1.0
  │              match_type    = "exact"
  │              needs_review  = False
  │              candidates    = []          ← 空列表，不是 [自身]
  │              provider      = "alias"     ← 默认值
  │              confidence_label / latency_ms / tokens / reason = None
  │           )
  │
  └─ 未命中 ──► self._fallback_matcher(raw_text)
                  │
                  ├─ 若为 None（SkillNormalizer(_skills) 无 matcher）
                  │     → SkillNormalizationResult(match_type="unknown", needs_review=True)
                  │
                  └─ Provider.match() → SkillNormalizationResult
                        └─ 若 result.raw_text != raw_text：
                             dataclasses.replace(result, raw_text=raw_text)   # 强制回填原始文本

normalize_many(texts) = [normalize(t) for t in texts]   # 纯串行，无并发
```

### 5.1 三个必须遵守的行为不变量

| # | 不变量 | 代码位置 |
|---|---|---|
| I1 | `raw_text` 永远是**调用方传入的原始字符串**（Provider 若改动会被 `replace` 回填） | `normalizer.py:38-40` |
| I2 | `exact` 分支的 `candidates` 恒为 `[]`（`evaluation.py` 的 `_top_ids` 对 exact 特判为 `[skill_id]`） | `normalizer.py:31-33` + `evaluation.py:8-11` |
| I3 | `AliasMatcher` 构造期即校验 alias 冲突，冲突直接抛 `ValueError`（fail-fast，不在查询期） | `alias_matcher.py:12-14` |

---

## 6. 数据契约（字段级，唯一真源 = `app/schemas.py`）

### 6.1 `Skill`（frozen dataclass）

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `id` | `str` | 必填 | 主键，全局唯一 |
| `name` | `str` | 必填 | canonical 名称，**同时作为隐式 alias** |
| `domain` | `str \| None` | `None` | `skills.json` 实际必填，6 个枚举值 |
| `category` | `str \| None` | `None` | **数据中未使用**，仅 schema 保留 |
| `description` | `str` | `""` | 供 LLM prompt / Jev criteria 使用 |
| `aliases` | `list[str]` | `[]` | 别名列表 |
| `parent_id` | `str \| None` | `None` | 父技能引用，允许为 null |

### 6.2 `SkillCandidate`（frozen dataclass）

| 字段 | 类型 | 说明 |
|---|---|---|
| `skill_id` | `str` | |
| `name` | `str` | |
| `score` | `float` | DeepSeek: `confidence - index*0.01`；Jev: **真实概率** |

### 6.3 `SkillNormalizationResult`（frozen dataclass）— 对外统一输出

| 字段 | 类型 | 默认 | DeepSeek 填充 | Jev 填充 | alias 路径 |
|---|---|---|---|---|---|
| `raw_text` | `str` | 必填 | ✓ | ✓ | ✓ |
| `skill_id` | `str \| None` | 必填 | ✓ | ✓ | ✓ |
| `canonical_name` | `str \| None` | 必填 | ✓ | ✓ | ✓ |
| `score` | `float \| None` | 必填 | ✓（0–1，来自 LLM `confidence` 数值） | ✓（`answer.confidence` 或回退 `top_prob`） | `1.0` |
| `match_type` | `Literal["exact","semantic","review","unknown"]` | 必填 | ✓ | ✓ | `"exact"` |
| `needs_review` | `bool` | 必填 | `decision != "auto_match"` | `match_type != "semantic"` | `False` |
| `candidates` | `list[SkillCandidate]` | `[]` | ✓（≤3） | ✓（≤3，剔除 `__unknown__`） | `[]` |
| `provider` | `str` | `"alias"` | `"deepseek"` | `"jev"` | `"alias"` |
| `confidence_label` | `str \| None` | `None` | `high/medium/low` 或 `None` | **恒 None** | `None` |
| `latency_ms` | `int \| None` | `None` | ✓ | ✓ | `None` |
| `input_tokens` | `int \| None` | `None` | ✓ | ✓ | `None` |
| `output_tokens` | `int \| None` | `None` | ✓ | ✓ | `None` |
| `reason` | `str \| None` | `None` | ✓（LLM 理由） | **恒 None** | `None` |

**派生属性/方法：**

```python
@property
def normalized(self) -> dict[str, str] | None:
    if self.skill_id is None or self.canonical_name is None:
        return None
    return {"skill_id": self.skill_id, "canonical_name": self.canonical_name}

def to_dict(self) -> dict:
    value = asdict(self)          # 注意：不含 normalized
    value["normalized"] = self.normalized
    return value
```

**JSON 输出键顺序（实测，`to_dict()` 的 `asdict` 字段序 + 追加 `normalized`）：**

```json
{"raw_text","skill_id","canonical_name","score","match_type","needs_review",
 "candidates","provider","confidence_label","latency_ms","input_tokens",
 "output_tokens","reason","normalized"}
```

> ⚠️ 两份设计文档中写的是 pydantic `BaseModel` 且字段名为 `confidence`；**实际实现是 frozen dataclass 且字段名为 `score`**。以代码为准。

---

## 7. 模块级 API 规格

### 7.1 `app/text_normalizer.py`

```python
def normalize_text(text: str) -> str:
    return text.strip().lower().replace(" ", "")
```

- 只做三项：去首尾空白、小写、删除**半角空格**。
- **不做**：全角/半角转换、中英文标点归一、其他空白符（`\t`、`\n`、全角空格 `\u3000`）处理。
- 已知局限：`"库存\t预测"` 归一化后**不等于** `"库存预测"`。

### 7.2 `app/taxonomy.py`

```python
def load_skills(path: str | Path) -> list[Skill]:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    skills = [Skill(**record) for record in records]
    ids = [skill.id for skill in skills]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy contains duplicate skill ids")
    return skills
```

- 加载失败/字段不匹配 → 原生异常（`JSONDecodeError` / `TypeError`）。
- 只校验 **id 唯一性**。parent 存在性、alias 冲突、环检测**均不在此处**（由 `AliasMatcher` 与 `validate_benchmark.py` 分别承担）。

### 7.3 `app/alias_matcher.py`

```python
class AliasMatcher:
    def __init__(self, skills: list[Skill]):
        self._skills = {skill.id: skill for skill in skills}
        self._aliases: dict[str, str] = {}
        for skill in skills:
            for alias in [skill.name, *skill.aliases]:     # name 也进表
                key = normalize_text(alias)
                previous = self._aliases.get(key)
                if previous and previous != skill.id:
                    raise ValueError(f"alias maps to multiple skills: {alias}")
                self._aliases[key] = skill.id

    def match(self, text: str) -> Skill | None:
        skill_id = self._aliases.get(normalize_text(text))
        return self._skills.get(skill_id)
```

- 映射表 = `name` ∪ `aliases`，键经 `normalize_text`。
- 内部构建的是 `normalized_key → skill_id` 的**扁平字典**，无前缀/模糊/大小写模糊匹配。
- 冲突（含 `name` 与他 skill 的 `alias` 冲突）在**构造期**抛 `ValueError`。
- 复杂度 O(1) 查询。

### 7.4 `app/normalizer.py`

```python
FallbackMatcher = Callable[[str], SkillNormalizationResult]

class Matcher(Protocol):
    provider_name: str
    def match(self, text: str) -> SkillNormalizationResult: ...

class SkillNormalizer:
    def __init__(self, skills: list[Skill],
                 fallback_matcher: FallbackMatcher | None = None,
                 semantic_matcher: Matcher | None = None):
        self._alias_matcher = AliasMatcher(skills)
        self._fallback_matcher = semantic_matcher.match if semantic_matcher else fallback_matcher

    def normalize(self, text: str) -> SkillNormalizationResult: ...
    def normalize_many(self, texts: list[str]) -> list[SkillNormalizationResult]: ...
```

- **双注入通道**：`semantic_matcher`（Protocol 对象，优先）与 `fallback_matcher`（裸函数，兼容旧测试）。两者同时传入时 `semantic_matcher` 胜出。
- `normalize_many` 是纯列表推导，**无并发、无批处理 API 调用**（N 条输入 = N 次串行 Provider 请求）。

### 7.5 `app/matchers.py`

```python
class SemanticMatcher(Protocol):
    provider_name: str
    def match(self, text: str) -> SkillNormalizationResult: ...

class MatcherRegistry:
    def __init__(self, matchers: Sequence[SemanticMatcher]):
        self._matchers = {matcher.provider_name: matcher for matcher in matchers}
    def get(self, provider: str) -> SemanticMatcher:      # KeyError → ValueError
    def providers(self) -> list[str]:                     # 返回 list(dict keys)
```

> 注意：`SemanticMatcher` Protocol 与 `normalizer.Matcher` Protocol **结构相同但定义了两份**（重复定义）。

### 7.6 `app/deepseek_matcher.py`（Provider A）

**模块级副作用：**

```python
def load_env(path: Path) -> None:   # 自研 .env 解析器
    # 跳过空行 / '#' 注释 / 无 '=' 行
    # strip 引号；支持 'export ' 前缀
    # 使用 os.environ.setdefault → 已存在的 shell 环境变量优先

load_env(Path(__file__).resolve().parents[1] / ".env")   # ← import 即执行
```

**关键行为：**

| 项 | 值 |
|---|---|
| `provider_name` | `"deepseek"` |
| 端点 | `{DEEPSEEK_BASE_URL}/chat/completions`，默认 `https://api.deepseek.com` |
| 模型 | `DEEPSEEK_MODEL`，默认 `deepseek-chat` |
| Key | `DEEPSEEK_API_KEY`（缺失时 `match()` 抛 `RuntimeError`） |
| 请求体 | `temperature=0`, `max_tokens=256`, `response_format={"type":"json_object"}` |
| 超时 | 60s（硬编码） |
| HTTP 客户端 | 标准库 `urllib.request.urlopen`，**无重试** |
| Prompt 内容 | 角色 + 5 条规则 + JSON 格式说明 + **完整 taxonomy JSON**（id/name/domain/description/aliases/parent_id） |

**期望的模型输出格式：**

```json
{"skill_id":"string 或 null","decision":"auto_match | review | unknown",
 "confidence":0.0,"top3_skill_ids":["最多 3 个 Taxonomy skill_id"]}
```

**决策映射（`_parse`）：**

| LLM `decision` | 附加条件 | → `match_type` | `needs_review` | `skill_id` |
|---|---|---|---|---|
| `"auto_match"` | `skill_id` 是 str 且 ∈ taxonomy | `"semantic"` | `False` | 该 skill |
| `"auto_match"` | `skill_id` 非法/缺失 | `"review"`（落到最后的 fallback return） | `True` | `None` |
| `"unknown"` | — | `"unknown"` | `True` | `None` |
| 其他/缺失/JSON 解析失败 | — | `"review"` | `True` | `None` |

**健壮性细节：**
- `confidence` 非数值 → `0.0`；数值则 clamp 到 `[0,1]`。
- `confidence_label` 仅当 LLM 原样返回 `"high"/"medium"/"low"` 字符串时才赋值（**注意该字符串同时被 `float()` 失败后置为 score=0.0**）。
- `top3_skill_ids`：过滤非 str 与不在 taxonomy 的 id → 去重（`dict.fromkeys`）→ 截断 3 条。`auto_match` 时把命中的 `skill_id` **提到首位**。
- `candidates[].score` = `max(0.0, confidence - index*0.01)`（人造递减，**第 2、3 名并非真实置信度**）。
- 解析失败（`json.JSONDecodeError`）静默降级为 `review`，不抛异常。

### 7.7 `app/jev_matcher.py`（Provider B）

**`JevClient`：**

| 项 | 值 |
|---|---|
| Key | `TYPESAFE_API_KEY`（缺失时 `choice()` 抛 `RuntimeError`） |
| 模型 | `JEV_MODEL`，默认 `jev-latest` |
| 端点 | 硬编码 `https://api.typesafe.ai/v1/systemone`（**不可通过 env 配置**） |
| 超时 | 默认 10s（构造参数，**比 DeepSeek 短 6 倍**） |
| 请求体 | `{state, model, questions: {skill_match: {type:"choice", instructions, criteria}}}` |
| HTTP 客户端 | `urllib.request.urlopen`，无重试 |

**`JevMatcher`：**

| 项 | 值 |
|---|---|
| `provider_name` | `"jev"` |
| criteria 构建 | `{skill.id: {"name", "definition": description}}`，**不含 aliases**（因为 AliasMatcher 已前置） |
| 额外 criteria | `__unknown__`：`{"name":"未知技能","definition":"...不得因语义相关而强行选择近似技能。"}` |
| 决策常量（类属性） | `AUTO_CONFIDENCE = 0.80`、`AUTO_MARGIN = 0.15`、`UNKNOWN_THRESHOLD = 0.65`、`UNKNOWN_ID = "__unknown__"` |

**期望的 API 响应结构：**

```json
{"answers":{"skill_match":{"choice":"...","confidence":0.87,
  "probabilities":{"skill_id":0.79,"__unknown__":0.03}}},
 "usage":{"input_tokens":6040,"output_tokens":772}}
```

**决策策略（`match` 内联，未拆成独立 policy 类）：**

```text
ranked = sorted(probabilities, desc)
top_id, top_prob = ranked[0]
confidence = answer.confidence（数值）否则 top_prob
margin = top_prob - (ranked[1].prob 或 0.0)

if top_id == "__unknown__":
      match_type = "unknown" if top_prob >= 0.65 else "review";  skill_id = None
elif confidence >= 0.80 and margin >= 0.15:
      match_type = "semantic";  skill_id = top_id
else:
      match_type = "review";    skill_id = None
```

**响应校验（任一失败 → `RuntimeError`，不返回结果）：**

- `answers.skill_match` 缺失或非 dict
- `probabilities` 缺失/空/非 dict
- 过滤后（键必须在 criteria 内且值为数值）无有效概率

**candidates**：`ranked` 剔除 `__unknown__` 后取前 3，`score` = **真实概率**（非人造递减）。

---

## 8. Provider 对比矩阵（最终结论）

| 维度 | DeepSeek | Jev |
|---|---|---|
| 模型类型 | 文本生成模型 | 决策模型（choice） |
| 交互方式 | system prompt + 完整 taxonomy JSON | `state` + choice question + criteria |
| taxonomy 传入形式 | 完整 JSON（含 aliases、parent_id） | `{id: {name, definition}}`（**无 aliases**） |
| 原生输出 | `decision` + `skill_id` + `confidence`(数值或标签) + `top3_skill_ids` + `reason` | `choice` + `confidence` + `probabilities` 分布 |
| 是否输出概率分布 | ❌（candidates 的 score 是 `confidence - index*0.01` 人造值） | ✅ 真实分布 |
| `confidence_label` | 可能填充 | 恒 `null` |
| `reason` | 可能填充 | 恒 `null` |
| `score` 语义 | LLM 自报置信度 | 原生 confidence / top_prob |
| 阈值策略 | 无（信任 LLM 的 `decision`） | 三重阈值：confidence 0.80 / margin 0.15 / unknown 0.65 |
| 超时 | 60s | 10s |
| 端点可配置 | ✅ `DEEPSEEK_BASE_URL` | ❌ 硬编码 |
| 是否可对比 | ✅ `/api/normalize/compare` 并排 | ✅ 同 |
| 是否自动 fallback | ❌ | ❌ |

**输出格式结论（回答"两者格式是否一样"）：**
JSON **键名、顺序、嵌套结构完全一致**（同一 `SkillNormalizationResult`），消费方若只读 `skill_id` / `match_type` / `needs_review` / `candidates` 可完全互换；但 `confidence_label` 与 `reason` 在 Jev 路径恒为 `null`，`score` 与 `candidates[].score` 的语义不同。这是**刻意设计**，不是缺陷。

---

## 9. HTTP API 契约

### 9.1 端点一览

| Method | Path | 请求体 | 响应 | 说明 |
|---|---|---|---|---|
| GET | `/api/skills` | — | `[{id, name, category, domain, description, aliases}]` | `category = skill.category or skill.domain` |
| POST | `/api/normalize` | `{"text": str}` | `SkillNormalizationResult.to_dict()` | 使用 `SKILL_MATCHER_PROVIDER` |
| POST | `/api/normalize-many` | `{"texts": [str]}` | `[Result.to_dict()]` | 串行 |
| POST | `/api/normalize/debug` | `{"text": str, "provider": str}` | `Result.to_dict()` | 每次**新建** Provider 实例 |
| POST | `/api/normalize/compare` | `{"text": str}` | 见下 | 双 Provider 并排 |
| GET | `/static/*` | — | 静态文件 | `StaticFiles(directory=frontend/)` |
| GET | `/{full_path:path}` | — | `index.html` | SPA fallback |

### 9.2 `/api/normalize/compare` 响应形状

```jsonc
// alias 命中时（短路，不调任何 Provider）
{"alias_match": {...exact result...}, "deepseek": null, "jev": null}

// alias 未命中时
{
  "alias_match": null,
  "deepseek": {...result...} | {"error":"...", "provider":"deepseek"},
  "jev":      {...result...} | {"error":"...", "provider":"jev"}
}
```

### 9.3 错误码

| 场景 | 状态码 | 触发点 |
|---|---|---|
| 非法 `provider` | 400 | `registry.get()` 抛 `ValueError` |
| Provider 运行时失败（缺 Key / HTTP / 超时 / 响应结构非法） | 503 | `RuntimeError` 统一捕获 |

⚠️ `/api/normalize/debug` 与 `/api/normalize/compare` 捕获了 `ValueError` 与 `RuntimeError`；`/api/normalize` / `/api/normalize-many` 通过 `normalize_text()` 辅助函数只捕获 `RuntimeError` 并转 503。

### 9.4 CORS

```python
allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
```

本地开发用，**生产前必须收紧**。

### 9.5 路由顺序陷阱

`/{full_path:path}` 是**兜底路由**，在 FastAPI 中按注册顺序匹配，因此它必须在所有 `/api/*` 之后注册——当前实现正确（API 定义在前，mount 与 fallback 在后）。修改时不要调整顺序。

---

## 10. CLI 契约

```bash
python main.py "技能表达"
```

行为：
1. 参数个数必须为 1，否则 `SystemExit("用法: python main.py \"技能表达\"")`。
2. `load_skills(.../data/skills.json)` → `MatcherRegistry` → `SkillNormalizer`。
3. **无论输入是否命中 alias，都会构造 Provider 实例**（但只有 miss 时才发网络请求）。
4. 输出 `json.dumps(result.to_dict(), ensure_ascii=False, indent=2)` 到 stdout。
5. Provider 选择：`SKILL_MATCHER_PROVIDER`，默认 `deepseek`。

---

## 11. Taxonomy 规范（`data/skills.json`）

### 11.1 实测规模

| 指标 | 值 |
|---|---|
| canonical skills | **80** |
| 总 alias 数 | **161** |
| 有 parent 的子技能 | **29** |
| 无 parent 的根技能 | **51** |
| 字段集 | `id`, `name`, `domain`, `description`, `aliases`, `parent_id`（**无 `category`**） |

### 11.2 domain 分布

| domain | skills |
|---|---|
| 跨境电商/运营 | 16 |
| 软件开发 | 15 |
| 产品 | 14 |
| HR/招聘 | 13 |
| 数据 | 12 |
| 办公软件 | 10 |

### 11.3 数据条目示例

```json
{
  "id": "product_listing",
  "name": "商品上新",
  "domain": "跨境电商/运营",
  "description": "完成新品资料准备、上架发布与类目属性维护，强调商品进入销售前的发布动作，不包含选品决策。",
  "aliases": ["商品上架", "新品上架"],
  "parent_id": "product_operation"
}
```

`description` 承担**双重职责**：既是给 LLM/Jev 的判别依据，也承担"区分于相邻技能"的负向定义（如 "不包含选品决策"）。这是 taxonomy 质量的关键人工资产。

### 11.4 运行时强制的约束（违反则崩溃）

1. `id` 全局唯一（`taxonomy.load_skills`）。
2. 任意两个 skill 的 `name`/`aliases` 归一化后**不得碰撞**（`AliasMatcher.__init__`），否则构造期抛 `ValueError`。

### 11.5 仅由 `validate_benchmark.py` 离线校验的约束

- `parent_id` 必须存在且非自身
- parent 链**无环**
- 单个 skill 的 `aliases` 内部不重复

---

## 12. Benchmark 体系

### 12.1 数据集

| 项 | 值 |
|---|---|
| `benchmark/cases.json` | **144** 条，6 领域 × 24 条 |
| case 字段 | `id`, `domain`, `input`, `type`, `expected_skill`, `acceptable_skills`, `difficulty`, `notes` |
| known cases | 132（`expected_skill != null`） |
| unknown cases | 12（`expected_skill == null` 且 `acceptable_skills == []`） |
| 领域 | 跨境电商/运营、HR/招聘、数据、办公软件、软件开发、产品 |
| type | `canonical` / `alias` / `semantic` / `context` / `ambiguous` / `unknown` |
| difficulty | easy 54 / medium 61 / hard 29 |
| `benchmark/inputs.json` | 144 条 `{id, input}` 精简视图 |

**type 目标比例**（`validate_benchmark.py` 中的 `TARGET_TYPE_RATIO`）：
`canonical 10% / alias 20% / semantic 20% / context 25% / ambiguous 15% / unknown 10%`
实际每领域固定配比：`canonical 2 / alias 5 / semantic 5 / context 6 / ambiguous 4 / unknown 2`。

### 12.2 自检规则（`validate_benchmark.py`，10 项 + 泄漏检查）

| # | 规则 |
|---|---|
| 1 | skill id 与 case id 均唯一 |
| 2 | `expected_skill` 必须存在于 taxonomy |
| 3 | `acceptable_skills` 必须存在，且不得与 `expected_skill` 重复 |
| 4 | `parent_id` 必须存在 |
| 5 | `parent_id` 不得自指；parent 链不得成环 |
| 6 | 单个 skill 的 `aliases` 内部不得重复 |
| 7 | 同一 name/alias 不得归属多个 skill |
| 8 | case `input` 不得完全重复 |
| 9 | `type` / `domain` 枚举合法；`unknown` case 不得有 expected/acceptable |
| 10 | `difficulty` 枚举合法 |
| 泄漏 | `semantic` / `context` / `ambiguous` / `unknown` 的 input 归一化后**不得等于任何 name/alias** |

退出码：`0` 通过，`1` 失败。运行：`python benchmark/validate_benchmark.py`

### 12.3 指标口径（`evaluation.py`，唯一实现）

| 指标 | 计算口径 |
|---|---|
| `top1_accuracy` | known cases 中，Top1 ∈ {expected} ∪ acceptable 的占比 |
| `top3_recall` | known cases 中，`candidates[:3]` 任一 ∈ 可接受集合的占比 |
| `auto_match_precision` | `needs_review == False` 的结果中命中可接受集合的占比（**最关键指标**） |
| `auto_match_count` | `needs_review == False` 的样本数 |
| `review_rate` | `match_type == "review"` / 全部 case |
| `unknown_rate` | `match_type == "unknown"` / 全部 case |
| `unknown_rejection` | unknown cases 中返回 `review`/`unknown` 的占比 |

**`_top_ids()` 的关键语义**：

```python
def _top_ids(result):
    if result["match_type"] == "exact" and result["skill_id"]:
        return [result["skill_id"]]      # exact 用 skill_id 自身
    return [c["skill_id"] for c in result["candidates"]]   # 其余用 candidates 序列
```

⇒ **`semantic` 结果的 Top1 取自 `candidates[0]`，而非 `skill_id`。** 若某 Provider 返回了 `skill_id` 但 `candidates[0]` 与之不一致，指标会与直觉不符。两个 Provider 都保证了 `candidates[0] == skill_id`（DeepSeek 显式提位，Jev 显式取 `ranked[0]`），因此当前无实际风险，但属于隐式契约。

`errors` 列表结构：`{id, input, expected, actual_top1, match_type, score, top3}`。

### 12.4 三个 runner

| 脚本 | 用途 | 是否走 alias | 输出 |
|---|---|---|---|
| `run_provider_benchmark.py --provider {deepseek\|jev}` | 端到端（Alias + Semantic） | ✅ | `results/{provider}.jsonl` |
| `run_provider_benchmark.py --provider X --semantic-only` | 只跑 alias 未命中的 case（**判断模型能力最重要的一组**） | ❌（先过滤） | 同上 |
| `run_deepseek_baseline.py` | DeepSeek-only baseline，无 alias/检索兜底，支持 `--without-aliases` 消融 | ❌（完全不用 alias） | `deepseek_results.json`（含 `metrics`/`results`/`traces`） |

`run_provider_benchmark.py` 的 JSONL trace 结构：

```json
{"case_id":"ecommerce_008","latency_ms":1033,"result":{...完整 SkillNormalizationResult.to_dict()...}}
```

`run_deepseek_baseline.py` 的实验元数据（**可复现性设计**）：

```json
{"experiment":{"name":"deepseek_only_full_taxonomy_v1","model":"deepseek-chat","temperature":0,
  "taxonomy_sha256":"...","prompt_sha256":"...","run_at":"...ISO8601..."},
 "metrics":{...},"results":[...],"traces":[{case_id, latency_ms, usage, raw_response, api_error}]}
```

⚠️ README 明确警告：**不要提交含 API 原始响应的结果文件**（`traces.raw_response`）。

### 12.5 实测结果（本次复算，144 case，e2e）

| 指标 | DeepSeek (`results/deepseek-e2e.jsonl`) | Jev (`results/jev-e2e.jsonl`) | Jev 第二次 (`jev-e2e_1.jsonl`) |
|---|---|---|---|
| Top1 Accuracy | **0.9773** | **0.9773** | 0.9773 |
| Top3 Recall | 0.9924 | **1.0000** | 1.0000 |
| Auto Match Precision | **0.9917** | 0.9913 | 0.9913 |
| Auto Match Count | 121 | 115 | 115 |
| Review Rate | **0.0764** | 0.1319 | 0.1319 |
| Unknown Rate | 0.0833 | 0.0694 | 0.0694 |
| Unknown Rejection | **1.0000** | 0.9167 | 0.9167 |

**路径分布（144 条）：**

| | DeepSeek | Jev |
|---|---|---|
| `alias`/`exact` | 42 | 42 |
| Provider 调用 | 102 | 102 |
| `semantic` | 79 | 73 |
| `review` | 11 | 19 |
| `unknown` | 12 | 10 |

**性能与成本：**

| 项 | DeepSeek | Jev |
|---|---|---|
| 延迟 mean / p50 / p95 / max | 737 / 700 / 1108 / 2273 ms | 1070 / 964 / 1745 / 2712 ms |
| 平均 input tokens | 5,034 | 6,038 |
| 平均 output tokens | 39 | 770 |
| 102 次调用总 tokens | in 513,453 / out 3,983 | in 615,849 / out 78,578 |

**解读要点：**

1. 两者 **Top1 Accuracy 完全相同（0.9773）**，差异集中在**行为倾向**而非准确率。
2. DeepSeek 更激进（auto 121 条、review 仅 7.6%）；Jev 更保守（auto 115 条、review 13.2%）。
3. **Jev 的 Top3 Recall 达 100%**，说明其概率分布排序能力强；但 **Unknown Rejection 仅 91.67%**（12 条 unknown 中有 1 条被强行判为 semantic），而 DeepSeek 为 100%。这是 Jev 当前唯一的实质短板。
4. Jev 延迟约为 DeepSeek 的 1.45 倍（p50 964 vs 700 ms），output tokens 约 20 倍（770 vs 39）——因为 Jev 返回完整概率分布。
5. `jev-e2e.jsonl` 与 `jev-e2e_1.jsonl` 指标完全一致（仅 p95 延迟不同：1745 vs 1027 ms），可视为**结果稳定性良好**。

### 12.6 Legacy 结果（BGE 时代，仅供参考，已不可比）

`benchmark/results.json`：Top1 0.9242 / Top3 0.9697 / Auto Precision 1.0 / Auto Count 46 / **Review Rate 0.2778** / **Unknown Rate 0.4028** / Unknown Rejection 1.0

⇒ BGE 方案的问题一目了然：**40% 的输入被判为 unknown**，覆盖率严重不足。这是技术路线切换的直接动因。

### 12.7 已知的 Taxonomy 冲突（来自 `benchmark/README.md`，人工分析）

**Top 混淆组（节选）：**

1. `inventory_management` / `inventory_forecasting` / `replenishment_management` / `inventory_control` — 同父 3 子技能
2. `ecommerce_operation` / `product_operation` / `campaign_operation` — "运营策略"三义
3. `interview_scheduling` / `interview_coordination` / `candidate_communication`
4. `excel` / `spreadsheet_processing` / `pivot_table` / `vlookup` — 工具 vs 功能
5. `excel_data_analysis` / `excel` / `data_analysis` — 交叉技能三出口
6. `sql` / `database_development` / `data_analysis`
7. `python` / `python_backend_development` / `backend_development` / `fastapi` — 语言/方向/框架三层同现
8. `requirements_management` / `requirements_analysis` / `requirement_prioritization` / `prd`
9. `product_management` / `project_management` / `cross_functional_collaboration`
10. `user_research` / `user_feedback_analysis`
11. `powerpoint` / `ppt_design`（同一交付物两级粒度）
12. `report_generation` / `data_visualization` / `metric_analysis`

**需要人工复核的 taxonomy 决策（8 条，节选）：**

- `recruitment` 下 11 个子技能全部同级，层级过于扁平
- `project_management` 被放在「产品」domain，实际是跨领域通用技能
- `tiktok_shop_operation` 单平台收录，Amazon/SHEIN 缺失 ⇒ 平台收录规则不明
- `data_analysis` 与 `metric_analysis` / `excel_data_analysis` / `traffic_analysis` 父子关系需复核
- `product_operation.parent_id = null`，但业务上通常从属于店铺运营
- 办公软件 3 个 Excel 子技能是否值得独立
- **软技能完全不在 taxonomy（by design）** — 12 条 unknown case 全部依赖此约定
- `inventory_control` 边界接近 `inventory_management`，易退化为 alias

**有意保留的争议 case：** `ecommerce_014`、`ecommerce_024`、`data_016`、`software_022`、`office_019`、`office_022`、`hr_020` / `hr_021`

---

## 13. 测试覆盖

| 测试文件 | 用例 | 覆盖内容 |
|---|---|---|
| `tests/test_normalizer.py` | 3 | ① name/alias 精确命中（含前后空格）② 无 matcher 时安全返回 unknown ③ `fallback_matcher` 裸函数通道 |
| `tests/test_deepseek_matcher.py` | 3 | ① `_parse` 的 auto_match 与候选提位 ② 非法 skill_id → review ③ `load_env` 不覆盖已有 shell 环境变量 |
| `benchmark/test_run_deepseek_baseline.py` | 2 | `adapt_response` 的 auto_match 提位与非法 skill_id 降级 |

运行：`python -m unittest discover -s tests -v`

**测试缺口（重要）：**

- ❌ 无 `JevMatcher` 任何测试（策略阈值、响应解析、错误分支全部未覆盖）
- ❌ 无 `AliasMatcher` 冲突检测测试
- ❌ 无 `api_server.py` / FastAPI 端点测试
- ❌ 无 `taxonomy.load_skills` 的重复 id 测试
- ❌ 所有测试均**离线**，无任何真实网络调用（设计上合理，但意味着 Provider 契约无集成验证）
- ❌ `benchmark/test_run_deepseek_baseline.py` 位于 `benchmark/` 内，`unittest discover -s tests` **不会发现它**

---

## 14. 配置与环境变量

`.env.example` 内容：

```env
SKILL_MATCHER_PROVIDER=deepseek    # deepseek | jev
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
TYPESAFE_API_KEY=
JEV_MODEL=jev-latest
```

| 变量 | 默认值 | 读取位置 | 备注 |
|---|---|---|---|
| `SKILL_MATCHER_PROVIDER` | `"deepseek"` | `api_server` / `main.py` | 非法值 → 启动期 `ValueError` |
| `DEEPSEEK_API_KEY` | 无 | `DeepSeekMatcher.__init__` | 缺失时仅 miss 场景抛 `RuntimeError` |
| `DEEPSEEK_MODEL` | `"deepseek-chat"` | 同上 | 文档示例里出现过 `deepseek-flash`（文档与 `.env.example` 不一致） |
| `DEEPSEEK_BASE_URL` | `"https://api.deepseek.com"` | 同上 | |
| `TYPESAFE_API_KEY` | 无 | `JevClient.__init__` | |
| `JEV_MODEL` | `"jev-latest"` | 同上 | |

**`.env` 加载机制**：仅 `app/deepseek_matcher.py` 在 **import 期**调用 `load_env(<repo>/.env)`，使用 `os.environ.setdefault` ⇒ **已存在的进程环境变量优先于 `.env`**。

⚠️ **副作用耦合**：Jev 的 Key 依赖 DeepSeek 模块被 import 时才加载 `.env`。若单独使用 `JevMatcher` 而不 import `deepseek_matcher`，`.env` 不会被加载。（当前 `api_server.py` / `main.py` 都同时 import 两者，故实际无影响。）

⚠️ 不使用 `python-dotenv`，`load_env` 自研，不支持多行值、变量插值、`\n` 转义。

---

## 15. 运行方式

```bash
pip install -r requirements.txt

# CLI
python main.py "库存预测"
python main.py "根据销量制定补货计划"

# 单元测试
python -m unittest discover -s tests -v

# Benchmark 自检
python benchmark/validate_benchmark.py

# Benchmark（需 API Key）
python benchmark/run_provider_benchmark.py --provider deepseek --semantic-only
python benchmark/run_provider_benchmark.py --provider jev
python benchmark/run_deepseek_baseline.py --json-out benchmark/deepseek_results.json

# HTTP 服务（同时托管前端）
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
# → http://127.0.0.1:8000/
```

**Windows/PowerShell 提示**：`.env.example` → `.env` 使用 `Copy-Item .env.example .env`。

---

## 16. 代码与文档的不一致清单（供后续修正）

| # | 文档描述 | 实际代码 | 影响 |
|---|---|---|---|
| 1 | `MatchResult.confidence: float` | `SkillNormalizationResult.score: float` | 对接方字段名需以代码为准 |
| 2 | pydantic `BaseModel` | `@dataclass(frozen=True)` | 无 pydantic 校验；`Skill(**record)` 遇多余键会 `TypeError` |
| 3 | 目录结构含 `app/config.py`、`app/taxonomy/repository.py`、`app/matchers/base.py`、`app/policies/*.py`、`app/api/routes.py` | 全部为**扁平单层** `app/*.py`，无 `config.py`、无 `policies` 拆分 | 实际结构比设计更简单；Jev 策略内联在 `jev_matcher.py` |
| 4 | `SkillCandidate.probability` | 字段名为 `score` | |
| 5 | API 路径 `/api/v1/normalize` | 实际为 `/api/normalize`（**无 `/v1`**） | |
| 6 | `SemanticMatcher.match(text, taxonomy)` | 实际 `match(text)`，taxonomy 在构造期注入 | 签名更简单 |
| 7 | 文档称 `DEEPSEEK_MODEL=deepseek-flash` | `.env.example` 与代码默认为 `deepseek-chat` | |
| 8 | 文档规划 BGE `embedding_matcher.py` | 已删除，仅剩 `models/` 目录残留 | |
| 9 | `Skill.category` | 数据中无此键，`api_server` 用 `domain` 兜底 | `/api/skills` 的 `category` 恒等于 `domain` |

---

## 17. 已知问题、风险与技术债

按严重度排序：

| 级别 | 问题 | 位置 | 影响 |
|---|---|---|---|
| 高 | `JevMatcher` 零测试覆盖 | `tests/` | 阈值策略、响应解析、错误分支无回归保护 |
| 高 | Jev `Unknown Rejection` 仅 91.67%（1/12 条被强行 semantic） | 策略阈值 | 违背"宁 review 不硬映射"的核心安全原则 |
| 高 | Provider 失败无重试、无降级，直接 503 | 两个 Matcher | 真实流量下可用性依赖单次调用 |
| 中 | `candidates[].score` 对 DeepSeek 是人造递减值 | `deepseek_matcher.py:_candidates` | 前端展示第 2/3 名分数具有误导性 |
| 中 | `normalize_many` 纯串行，无并发/批量 | `normalizer.py` | 144 条评测需 ~2 分钟；生产批量场景延迟线性增长 |
| 中 | 超时不一致（DeepSeek 60s vs Jev 10s） | 两个 Matcher | 评测公平性受影响；DeepSeek 卡死时会拖长整体 |
| 中 | Jev 端点硬编码，不可通过 env 配置 | `jev_matcher.py:32` | 无法指向代理/测试环境 |
| 中 | CORS `allow_origins=["*"]` | `api_server.py` | 上线前必须收紧 |
| 中 | `/api/normalize/debug` 与 `/compare` 无鉴权、无开关 | `api_server.py` | 可被用于消耗 API 额度；文档称其"仅用于开发"，但无代码级限制 |
| 中 | `normalize_text` 只删半角空格 | `text_normalizer.py` | `\t`/`\n`/全角空格/中英标点会导致 alias 漏匹配 |
| 低 | 两处重复定义 Protocol（`normalizer.Matcher` / `matchers.SemanticMatcher`） | — | 维护冗余 |
| 低 | `models/bge-small-zh-v1.5/`（含 `model.safetensors`）残留 | 仓库磁盘 | 死资产，占空间 |
| 低 | `benchmark/results.json` / `results_1..5.json` 遗留 | `benchmark/` | 易被误当作当前结果 |
| 低 | `benchmark/test_run_deepseek_baseline.py` 不在 `tests/` | — | `unittest discover -s tests` 不会执行 |
| 低 | `deepseek_results.json` 含 `traces.raw_response`（完整 API 原始响应） | `benchmark/` | 泄漏风险，README 已警告 |
| 低 | 无 `.env` 时 Jev Key 加载依赖 DeepSeek 模块 import | `deepseek_matcher.py:27` | 模块耦合副作用 |
| 低 | `deepseek-e2e.jsonl` 未纳入 git | `benchmark/results/` | 结果可复现性弱 |

### 17.1 报告未验证的缺口（Benchmark 层面）

- §20 设计文档要求的 **平均/P50/P95 延迟、token 成本、Jev Calibration 分桶、Confusion Matrix** 指标，`evaluation.py` **均未实现**（仅有 accuracy 类指标）。
- 设计文档要求的 **semantic-only 双 Provider 对比结果** 未在仓库中留存产物。
- Jev 的 `confidence` 校准（confidence 分桶 vs accuracy）**尚未做过**——这是判断"能否把 Jev confidence 直接当自动确认阈值"的前置实验。

---

## 18. 扩展指南（How-to）

### 18.1 新增一个 Skill

1. 编辑 `data/skills.json`，追加记录：`{id, name, domain, description, aliases, parent_id}`。
2. **关键**：`description` 必须写清与相邻技能的边界（"不包含 X"），因为它是两个 Provider 的唯一判别依据。
3. `name` 与所有 `aliases` 归一化后不得与现有任何 name/alias 冲突（否则 `AliasMatcher` 构造期崩溃）。
4. 如有 parent，`parent_id` 必须已存在且不成环。
5. 跑 `python benchmark/validate_benchmark.py` 自检。
6. 若新增 skill 是既有 case 的正确答案，需同步更新 `cases.json` 的 `expected_skill`。

### 18.2 新增一个 Provider

1. 在 `app/` 下新建 `xxx_matcher.py`，实现：

```python
class XxxMatcher:
    provider_name = "xxx"                       # 唯一，Registry 的键
    def __init__(self, skills: Sequence[Skill]): ...
    def match(self, text: str) -> SkillNormalizationResult: ...
```

2. **必须**遵守：返回统一的 `SkillNormalizationResult`；`provider` 字段填 `"xxx"`；Provider 失败抛 `RuntimeError`（让 HTTP 层转 503）；非语义明确时返回 `review` 或 `unknown`，不得硬映射。
3. 注册进三处组装点：
   - `api_server.py:35` `MatcherRegistry([...])`
   - `main.py:18` `MatcherRegistry([...])`
   - `benchmark/run_provider_benchmark.py:29` + `--provider` 的 `choices`
4. 若要参与 `/api/normalize/compare`，需同步 `api_server.py:97` 的 `for provider in (...)` 元组。
5. 新增 `tests/test_xxx_matcher.py`（至少覆盖：正常响应解析、字段缺失、非法 skill_id、HTTP 错误）。

### 18.3 调整 Jev 阈值

直接修改 `JevMatcher` 的类属性：

```python
AUTO_CONFIDENCE    = 0.80    # 提高 → auto 更少、更保守
AUTO_MARGIN        = 0.15    # 提高 → 对模糊分布更敏感
UNKNOWN_THRESHOLD  = 0.65    # 提高 → unknown 更难被判为 unknown
```

正确的调参顺序（见设计文档 §28 Step 6-7）：先跑 baseline 不动参数 → 再做 confidence/margin 分布分析 → 最后调阈值。**未知当前阈值是否为最优**（未做校准实验）。

### 18.4 实现 Shadow Mode（设计已规划，未实现）

```env
SKILL_MATCHER_PROVIDER=deepseek
SKILL_MATCHER_SHADOW_PROVIDER=jev
```

语义：主 Provider 结果返回给用户；Shadow Provider 结果**只进日志**，不影响业务状态。当前代码**无任何 shadow 实现**。

---

## 19. 关键事实速查表（AI 检索用）

```text
# 入口
FastAPI app          : api_server.py::app
CLI                  : main.py::main()
核心编排             : app/normalizer.py::SkillNormalizer.normalize()
唯一评测口径         : benchmark/evaluation.py::evaluate()

# 数据真源
Taxonomy             : data/skills.json (80 条)
Benchmark GT         : benchmark/cases.json (144 条, 禁止修改)
输出 Schema          : app/schemas.py::SkillNormalizationResult
Provider 注册表      : app/matchers.py::MatcherRegistry

# 关键常量
默认 Provider        : "deepseek" (env SKILL_MATCHER_PROVIDER)
DeepSeek 端点        : https://api.deepseek.com/chat/completions
DeepSeek 超时        : 60s
Jev 端点             : https://api.typesafe.ai/v1/systemone (硬编码)
Jev 超时             : 10s
Jev AUTO_CONFIDENCE  : 0.80
Jev AUTO_MARGIN      : 0.15
Jev UNKNOWN_THRESHOLD: 0.65
Jev UNKNOWN_ID       : "__unknown__"
文本归一化           : strip -> lower -> remove(" ")
exact 的 score       : 1.0
exact 的 candidates  : []

# match_type 语义
exact    : AliasMatcher 命中，provider="alias"
semantic : Provider 高置信度接受，needs_review=False
review   : 有候选但不自动确认，needs_review=True
unknown  : taxonomy 无可靠结果，needs_review=True

# 错误码
400 : provider 名非法
503 : Provider 运行时失败（缺 Key / HTTP / 超时 / 响应非法）

# 当前指标（144 case e2e）
DeepSeek: Top1 .9773 | Top3 .9924 | AutoP .9917 | AutoN 121 | Review .0764 | UnkRej 1.000
Jev     : Top1 .9773 | Top3 1.000 | AutoP .9913 | AutoN 115 | Review .1319 | UnkRej .9167

# 延迟（Provider 调用，ms）
DeepSeek: mean 737 | p50 700 | p95 1108 | max 2273
Jev     : mean 1070 | p50 964 | p95 1745 | max 2712
```

---

## 20. 架构一句话总结

> **Skill Normalizer 是一个「静态 Taxonomy + 本地 Alias 精确优先 + 可插拔 LLM 语义兜底」的 Python 分层单体。**
> 核心设计是把"语义判定"抽象成极薄的 `SemanticMatcher` Protocol，用 `MatcherRegistry` 在初始化期完成 Provider 注入，使 `SkillNormalizer` 主流程保持零 Provider 分支；DeepSeek 与 Jev 作为两个并列实现共享同一套 Taxonomy、输出 Schema、HTTP 层与 Benchmark，通过同一个 `evaluate()` 口径对比，**互不串联、互不 fallback**。
> 当前实测两者 Top1 准确率持平（97.73%），差异体现在行为倾向（DeepSeek 更激进、Jev 更保守且 Top3 召回达 100%），Jev 唯一实质短板是 Unknown Rejection（91.67%）。

---

## 附录 A：本报告数据的测量命令

```bash
# 仓库规模与隐藏文件
Get-ChildItem -Force -Name

# Taxonomy / Benchmark 统计
python -c "import json;from collections import Counter;s=json.load(open('data/skills.json',encoding='utf-8'));print(len(s));print(Counter(x['domain'] for x in s));print(sum(1 for x in s if x['parent_id']))"

# 指标复算（用官方 evaluator）
python -c "
import json,sys;sys.path.insert(0,'.')
from pathlib import Path
from benchmark.evaluation import evaluate
cases=json.loads(Path('benchmark/cases.json').read_text(encoding='utf-8'))
for n in ['benchmark/results/deepseek-e2e.jsonl','benchmark/results/jev-e2e.jsonl']:
    rows=[json.loads(l) for l in Path(n).read_text(encoding='utf-8').splitlines() if l.strip()]
    print(n, evaluate(cases,[r['result'] for r in rows]))
"

# 延迟 / token 统计
python -c "
import json,statistics
from pathlib import Path
rows=[json.loads(l) for l in Path('benchmark/results/jev-e2e.jsonl').read_text(encoding='utf-8').splitlines()]
lat=[r['result']['latency_ms'] for r in rows if r['result']['latency_ms']]
print(statistics.mean(lat), statistics.median(lat), sorted(lat)[int(len(lat)*.95)-1], max(lat))
"

# 演进历史
git --no-pager log --oneline
```

## 附录 B：关键代码片段索引

| 关注点 | 位置 |
|---|---|
| 流水线主循环 | `app/normalizer.py:27-41` |
| raw_text 回填 | `app/normalizer.py:38-40` |
| alias 冲突 fail-fast | `app/alias_matcher.py:11-15` |
| Provider 注册表 | `app/matchers.py:15-26` |
| DeepSeek 决策映射 | `app/deepseek_matcher.py:98-115` |
| DeepSeek 人造候选分 | `app/deepseek_matcher.py:117-121` |
| DeepSeek Prompt 模板 | `app/deepseek_matcher.py:136-143` |
| Jev 阈值策略 | `app/jev_matcher.py:85-91` |
| Jev criteria 构建（含 __unknown__） | `app/jev_matcher.py:56-63` |
| 进程级单例组装 | `api_server.py:34-37` |
| exact 短路（compare 接口） | `api_server.py:93-95` |
| 评测 Top1 取值规则 | `benchmark/evaluation.py:8-11` |
| 自检 10 项规则 | `benchmark/validate_benchmark.py:45-124` |
| benchmark 泄漏检查 | `benchmark/validate_benchmark.py:118-122` |
