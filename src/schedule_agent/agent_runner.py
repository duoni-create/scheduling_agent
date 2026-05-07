import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from .agent_tools import (
    load_project_data_tool,
    validate_schedule_data_tool,
    run_schedule_tool,
    set_baseline_schedule_tool,
    load_baseline_schedule_tool,
    simulate_change_tool,
    check_feasibility_tool,
    explain_delay_tool,
    compare_with_baseline_tool,
    export_schedule_tool,
)

load_dotenv()

SYSTEM_PROMPT = """你是一个两周迭代排期助手 Agent。

本项目不保存聊天记录，核心工作方式是：

1. 先上传 Excel 排期数据。
2. 生成临时排期 draft。
3. 用户确认后，将 draft 设置为本迭代正式排期 baseline。
4. 迭代期间所有请假、调整、可行性问题，都基于 baseline 重新模拟。
5. 模拟结果必须和 baseline 对比，不能自动把第一次排期当成正式排期。
6. 不要编造排期结果，所有结果必须来自工具调用。

术语说明：
- "正式排期"、"落地排期"、"本迭代排期"都指 baseline。
- "临时排期"指 draft。
- "模拟排期"指 simulated。

工作规范：
1. 用户说"正式排期"时，应调用 set_baseline_schedule_tool 确认。
2. 用户说"如果某人请假"时，应调用 simulate_change_tool，然后调用 compare_with_baseline_tool 对比。
3. 用户说"导出排期"时，默认导出 baseline。
4. 如果还没有 baseline，要提示用户先设为正式排期。
5. 如果工具返回失败，直接解释失败原因，不要编造替代结果。
6. 回答要简洁、清楚，用中文。"""


def create_schedule_agent():
    """创建排期助手 Agent"""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        return None

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0,
    )

    tools = [
        load_project_data_tool,
        validate_schedule_data_tool,
        run_schedule_tool,
        set_baseline_schedule_tool,
        load_baseline_schedule_tool,
        simulate_change_tool,
        check_feasibility_tool,
        explain_delay_tool,
        compare_with_baseline_tool,
        export_schedule_tool,
    ]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    return agent


def run_agent(user_text: str) -> str:
    """运行 Agent"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "当前没有配置 OPENAI_API_KEY，无法使用自然语言 Agent。你仍然可以通过页面按钮进行排期。"

    agent = create_schedule_agent()
    if not agent:
        return "创建 Agent 失败，请检查 API Key 配置。"

    try:
        result = agent.invoke({
            "messages": [HumanMessage(content=user_text)],
        })
        messages = result.get("messages", [])
        if messages:
            return messages[-1].content
        return "Agent 没有返回结果"
    except Exception as e:
        return f"Agent 运行出错: {str(e)}"
