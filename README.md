# Skill Normalizer

独立的单技能标准化模块：将原始技能表达映射为 Taxonomy 中的标准技能。

## 当前 MVP

- `data/skills.json`：可人工维护的 Taxonomy
- 标准名称和 Alias 精确匹配
- 稳定的输出 Schema、Top-K 候选和审核决策
- 批量 `normalize_many()` 接口
- DeepSeek 语义判定
- CLI 和单元测试

架构：标准名称或 Alias 本地精确命中时立即返回；未命中时，把完整 Taxonomy 和输入交给 DeepSeek 判定为自动匹配、待审核或未知技能。

## 运行

```bash
pip install -r requirements.txt
# PowerShell: $env:DEEPSEEK_API_KEY="your-api-key"
# Bash: export DEEPSEEK_API_KEY="your-api-key"
python main.py "库存预测"
python main.py "根据销量制定补货计划"
python -m unittest discover -s tests -v
```

标准名称和 Alias 查询不需要 API Key；只有未命中时才调用 DeepSeek。可用 `DEEPSEEK_MODEL` 与 `DEEPSEEK_BASE_URL` 覆盖默认配置。

## 前端页面

项目新增了 `frontend/` 前端页面与 `api_server.py` 桥接层。
桥接层复用 `SkillNormalizer`，并和 CLI 使用同一套本地精确匹配与 DeepSeek fallback 流程。

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

启动后访问 http://127.0.0.1:8000/ 即可使用：

- 单条技能标准化
- 批量技能标准化
- Taxonomy 浏览与搜索

API 进程启动时不会调用 DeepSeek；只有未命中名称或 Alias 的请求才会发起 API 调用。
