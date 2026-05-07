# Schedule Agent

## 项目简介

排期助手 Agent 是一个本地 Web 版排期工具。用户通过网页上传 Excel 排期数据，系统解析需求、资源、节假日，然后由确定性的排期引擎生成排期结果。用户还可以用自然语言与 Agent 交互，完成排期、模拟变化、检查可行性、解释延期、对比方案和导出结果。

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
│   └── exports/
├── src/
│   └── schedule_agent/
│       ├── __init__.py
│       ├── app.py              # Streamlit 页面
│       ├── models.py           # Pydantic 数据模型
│       ├── project_context.py  # 项目上下文
│       ├── sample_generator.py # 示例数据生成
│       ├── excel_parser.py     # Excel 解析
│       ├── calendar_service.py # 日历服务
│       ├── schedule_engine.py  # 排期引擎
│       ├── conflict_checker.py # 冲突检测
│       ├── result_formatter.py # 结果格式化
│       ├── export_service.py   # 导出服务
│       ├── agent_tools.py      # Agent 工具
│       └── agent_runner.py     # Agent 运行器
└── tests/
    ├── test_excel_parser.py
    ├── test_schedule_engine.py
    ├── test_agent_tools.py
    └── test_agent_runner.py
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
| load_project_data_tool | 读取当前项目数据概况 |
| validate_schedule_data_tool | 校验数据是否可以排期 |
| run_schedule_tool | 执行排期 |
| simulate_change_tool | 模拟人员休假并重新排期 |
| check_feasibility_tool | 检查需求能否提前完成 |
| explain_delay_tool | 解释延期原因 |
| compare_schedule_tool | 对比两个策略的排期结果 |
| export_schedule_tool | 导出排期结果为 Excel |

## 第一版限制

1. 只支持本地单用户使用。
2. 数据暂存在内存中，不接数据库。
3. 一个子任务只分配给一个人。
4. 前后端测试顺序固定为：后端 -> 前端 -> 测试。
5. 只支持半天粒度。
6. 暂不支持多人并行完成同一个子任务。
7. simulate_change_tool 第一版只支持"人员休假"。
8. 暂不支持企业微信。
9. 暂不支持复杂审批流。
10. Agent 可以自主选择工具，但不能直接生成排期结果。

## 后续优化方向

- 支持数据库存储
- 支持多人协作
- 支持更复杂的排期策略
- 支持甘特图可视化
- 支持邮件通知
- 支持更多模拟变化类型
