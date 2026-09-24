# Skill Normalizer

独立的单技能标准化模块：将原始技能表达映射为 Taxonomy 中的标准技能。

## 当前 MVP

- `data/skills.json`：可人工维护的 Taxonomy
- 标准名称和 Alias 精确匹配
- 稳定的输出 Schema、Top-K 候选和 threshold/margin 决策逻辑
- 批量 `normalize_many()` 接口
- BGE Embedding 语义匹配
- CLI 和不下载模型的单元测试

Embedding Matcher 从项目内的 `models/bge-small-zh-v1.5` 加载 BGE 模型，并将 Taxonomy 文档 Embedding 一次后常驻内存。`SkillNormalizer` 仍支持注入 Matcher，因此单元测试不需要加载模型。

## 运行

```bash
pip install -r requirements.txt
python main.py "库存预测"
python main.py "根据销量制定补货计划"
python -m unittest discover -s tests -v
```

复制项目时需要保留 `models/bge-small-zh-v1.5` 目录。目标电脑安装依赖后即可离线加载模型，不再访问 Hugging Face。

## 前端页面

项目新增了 `frontend/` 前端页面与 `api_server.py` 桥接层。
桥接层仅导入现有 `app/` 模块，未修改任何后端代码。

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

启动后访问 http://127.0.0.1:8000/ 即可使用：

- 单条技能标准化
- 批量技能标准化
- Taxonomy 浏览与搜索

注意：当前语义模型尚未接入，因此只有精确匹配（标准名称或 Alias）会返回 `exact` 结果；其余表达会按现有逻辑返回 `review` 或 `unknown`。
