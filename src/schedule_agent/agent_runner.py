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
    check_person_vacation_feasibility,
    check_requirement_deadline_feasibility,
    check_assignment_feasibility,
)

load_dotenv(override=True)


def _get_openai_config():
    # Reload .env on each call so Streamlit reflects updated local config
    # without requiring a full process restart.
    load_dotenv(override=True)
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")
    base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip().strip('"').strip("'")
    model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip().strip('"').strip("'")
    return api_key, base_url, model


def _format_agent_error(error: Exception, base_url: str, model: str) -> str:
    message = str(error)

    if "401" in message and "Invalid Authentication" in message:
        return (
            "Agent 鉴权失败：当前 OPENAI_API_KEY 无效，或与 OPENAI_BASE_URL 不匹配。"
            f" 当前 base_url={base_url}。"
        )

    if "404" in message and "resource_not_found_error" in message:
        return (
            "Agent 接口地址或模型配置不正确：服务端返回 404。"
            f" 当前 base_url={base_url}，model={model}。"
            " 请优先检查 base_url 是否为兼容 OpenAI 的 /v1 接口地址。"
        )

    return f"Agent 运行出错: {message}"

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
2. 用户说"如果某人请假"时，应调用 check_person_vacation_feasibility。
3. 用户说"检查某需求能否提前"时，应调用 check_requirement_deadline_feasibility。
4. 用户说"指定某人做某需求"时，应调用 check_assignment_feasibility。
5. 用户说"导出排期"时，默认导出 baseline。
6. 如果还没有 baseline，要提示用户先设为正式排期。
7. 如果工具返回失败，直接解释失败原因，不要编造替代结果。
8. 回答要简洁、清楚，用中文。

参数完整性规范：
- 当用户要求模拟人员请假时，必须同时具备：人员姓名、请假开始日期、请假结束日期。
  如果用户没有提供具体日期范围，不要调用 simulate_change_tool，应先追问用户补充具体请假时间。
  不要自行猜测"下周""过几天"等模糊日期。
- 当用户要求检查某需求能否提前完成时，必须同时具备：需求ID、目标日期。
  如果缺少任一信息，应先追问。
- 当用户要求导出时，如果未指定格式，默认使用 excel。"""


def create_schedule_agent():
    """创建排期助手 Agent"""
    api_key, base_url, model = _get_openai_config()

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
        check_person_vacation_feasibility,
        check_requirement_deadline_feasibility,
        check_assignment_feasibility,
    ]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    return agent


def run_agent(user_text: str) -> str:
    """运行 Agent"""
    api_key, base_url, model = _get_openai_config()
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
        return _format_agent_error(e, base_url, model)
