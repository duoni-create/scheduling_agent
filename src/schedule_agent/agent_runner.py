import os
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from .agent_tools import (
    load_project_data_tool,
    validate_schedule_data_tool,
    run_schedule_tool,
    simulate_change_tool,
    check_feasibility_tool,
    explain_delay_tool,
    compare_schedule_tool,
    export_schedule_tool,
)

load_dotenv()

SYSTEM_PROMPT = """你是一个排期助手 Agent，负责帮助用户完成项目排期、模拟变化、检查可行性、解释延期、对比方案和导出结果。

你可以自主选择工具，但必须遵守：

1. 不要直接编造排期结果。
2. 所有排期结果必须来自 run_schedule_tool、simulate_change_tool、check_feasibility_tool 或 compare_schedule_tool。
3. 如果用户还没有上传数据，先调用 load_project_data_tool 检查状态，并提示用户上传 Excel。
4. 如果用户要求排期，先确认数据有效，再调用 run_schedule_tool。
5. 如果用户要求模拟休假，调用 simulate_change_tool。
6. 如果用户要求检查某需求能否提前完成，调用 check_feasibility_tool。
7. 如果用户问为什么延期，调用 explain_delay_tool。
8. 如果用户要求对比方案，调用 compare_schedule_tool。
9. 如果用户要求导出结果，调用 export_schedule_tool。
10. 回答要简洁、清楚，用中文。
11. 如果工具返回失败，直接解释失败原因，不要编造替代结果。"""


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
        simulate_change_tool,
        check_feasibility_tool,
        explain_delay_tool,
        compare_schedule_tool,
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
