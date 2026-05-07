# Schedule Agent

## 项目简介

排期助手 Agent 是一个面向**两周版本迭代**的本地 Web 版排期工具。

**核心工作方式**：

1. 每个迭代周期上传 Excel 排期数据。
2. 生成**临时排期 draft**。
3. 用户确认后，将 draft 设为**本迭代正式排期 baseline**。
4. 迭代期间所有请假、调整、可行性问题，都基于 baseline 重新模拟。
5. 模拟结果必须和 baseline 对比。

**项目特点**：

- 不保存用户聊天记录，只保存一版正式排期 baseline。
- 使用 SQLite 持久化当前 baseline 的输入数据和排期结果。
- 排期计算由确定性引擎完成，Agent 只负责理解意图和选择工具。

## 技术栈

- Python 3.9+
- uv (包管理)
- Streamlit (Web 页面)
- pandas + openpyxl (Excel 解析和导出)
- pydantic (数据模型)
- python-dotenv (环境变量)
- LangChain + LangChain OpenAI (Agent)
- pytest (测试)

## 项目结构

```
schedule-agent/
├── pyproject.toml
├── README.md
├── .env.example
├── .gitignore
├── data/
│   ├── sample_schedule.xlsx
│   ├── scheduling_agent.db
│   └── exports/
├── src/
│   └── schedule_agent/
│       ├── __init__.py
│       ├── app.py              # Streamlit 页面
│       ├── models.py           # Pydantic 数据模型
│       ├── project_context.py  # 项目上下文（baseline/draft/simulated 状态管理）
│       ├── sqlite_store.py     # SQLite 持久化实现
│       ├── baseline_store.py   # baseline 持久化兼容层，底层使用 SQLite
│       ├── sample_generator.py # 示例数据生成
│       ├── excel_parser.py     # Excel 解析
│       ├── calendar_service.py # 日历服务
│       ├── schedule_engine.py  # 确定性排期引擎
│       ├── conflict_checker.py # 冲突检测
│       ├── result_formatter.py # 结果格式化
│       ├── export_service.py   # 导出服务
│       ├── agent_tools.py      # Agent 工具
│       └── agent_runner.py     # Agent 运行器
└── tests/
    ├── test_excel_parser.py
    ├── test_schedule_engine.py
    ├── test_agent_tools.py
    ├── test_agent_runner.py
    ├── test_baseline_store.py
    └── test_sqlite_store.py
```

## 安装依赖

```bash
uv sync
```

## 配置环境变量

复制 `.env.example` 为 `.env`，并填写你的 OpenAI API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

如果 `OPENAI_API_KEY` 为空，Web 页面仍然可以手动排期，但自然语言 Agent 功能会提示用户配置 API Key。

## 生成示例 Excel

```bash
uv run python -m schedule_agent.sample_generator
```

## 启动 Web 页面

```bash
uv run streamlit run src/schedule_agent/app.py
```

## 运行测试

```bash
uv run pytest
```

## Agent 工具说明

| 工具名 | 功能 |
|--------|------|
| load_project_data_tool | 读取当前项目数据概况（含 baseline/draft/simulated 状态） |
| validate_schedule_data_tool | 校验数据是否可以排期 |
| run_schedule_tool | 生成临时排期 draft |
| set_baseline_schedule_tool | 将当前 draft 确认为本迭代正式排期 baseline |
| load_baseline_schedule_tool | 从本地加载已保存的正式排期 |
| simulate_change_tool | 模拟人员休假并和 baseline 对比 |
| check_feasibility_tool | 检查需求能否提前完成 |
| explain_delay_tool | 解释延期原因（优先解释 baseline） |
| compare_with_baseline_tool | 对比 simulated/draft 与 baseline |
| export_schedule_tool | 导出排期结果为 Excel（默认导出 baseline） |

## 核心工作流

### 1. 上传排期数据

通过页面上传 Excel 或使用示例数据。

### 2. 生成临时排期

点击"开始排期"生成 draft_result。

### 3. 确认正式排期

确认 draft 无误后，点击"设为本迭代正式排期"：

- 将 draft 提升为 baseline。
- 保存到 SQLite（`data/scheduling_agent.db`）。
- 记录迭代名称和确认时间。

### 4. 迭代期间模拟

迭代期间如果有人请假或需求调整：

- 使用 Agent 或页面模拟变化。
- 生成 simulated_result。
- 自动与 baseline 对比，展示影响。

### 5. 导出排期

默认导出 baseline，也支持导出 draft 和 simulated。

## 第一版限制

1. 只支持本地单用户使用。
2. 数据暂存在内存中，仅 baseline 持久化到 SQLite。
3. 只保存一版 current_baseline，不支持多迭代历史版本。
4. 不保存用户会话记录和聊天记录。
5. 不支持多人同时在线编辑。
6. 一个子任务只分配给一个人。
7. 前后端测试顺序固定为：后端 -> 前端 -> 测试。
8. 只支持半天粒度。
9. 暂不支持多人并行完成同一个子任务。
10. simulate_change_tool 第一版只支持"人员休假"。
11. 暂不支持企业微信。
12. 暂不支持复杂审批流。
13. Agent 可以自主选择工具，但不能直接生成排期结果。

## SQLite 数据落地说明

SQLite 中保存：
- iterations（迭代元信息）
- requirements（需求数据）
- resources（人员资源）
- holidays（节假日/调休）
- schedule_runs（排期结果头）
- schedule_items（排期明细，含 used_slots）

SQLite 中不保存：
- 用户会话记录
- Agent 聊天记录
- 临时 draft 排期
- 模拟 simulated 排期

## 后续优化方向

- 支持多迭代历史版本管理
- 支持多人协作
- 支持多人协作
- 支持甘特图可视化
- 支持更多模拟变化类型
