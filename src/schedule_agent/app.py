import os
import streamlit as st
from .excel_parser import parse_excel
from .sample_generator import generate_sample_excel
from .schedule_engine import schedule_requirements
from .conflict_checker import check_conflicts
from .project_context import project_context
from .export_service import export_schedule_to_excel
from .agent_runner import run_agent
from .result_formatter import (
    format_schedule_result_for_table,
    format_summary_text,
    format_delayed_items,
    format_unscheduled_items,
    format_conflicts,
)

st.set_page_config(page_title="排期助手 Agent", layout="wide")

st.title("排期助手 Agent")

# 侧边栏
with st.sidebar:
    st.header("操作")
    if st.button("使用示例数据"):
        path = generate_sample_excel()
        requirements, resources, holidays = parse_excel(path)
        project_context.load_data(requirements, resources, holidays)
        st.success("示例数据已加载")
        st.rerun()

    if st.button("重置数据"):
        project_context.reset()
        st.success("数据已重置")
        st.rerun()

# 数据区
st.header("1. 数据上传")
uploaded_file = st.file_uploader("上传排期 Excel", type=["xlsx"])

if uploaded_file:
    temp_path = "data/temp_upload.xlsx"
    with open(temp_path, "wb") as f:
        f.write(uploaded_file.getvalue())
    try:
        requirements, resources, holidays = parse_excel(temp_path)
        project_context.load_data(requirements, resources, holidays)
        st.success("Excel 解析成功")
    except Exception as e:
        st.error(f"解析失败: {e}")

if project_context.has_data():
    data = project_context.get_data()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("需求表")
        req_df = pd.DataFrame([
            {
                "需求ID": r.req_id,
                "需求名称": r.name,
                "前端": r.frontend_days,
                "后端": r.backend_days,
                "测试": r.test_days,
                "优先级": r.priority,
                "Deadline": str(r.deadline),
                "依赖": ",".join(r.dependencies) if r.dependencies else "",
            }
            for r in data.requirements
        ])
        st.dataframe(req_df, use_container_width=True)

    with col2:
        st.subheader("资源表")
        res_df = pd.DataFrame([
            {
                "姓名": r.name,
                "角色": ",".join(r.roles),
                "可用起始": str(r.available_start),
                "可用结束": str(r.available_end),
                "每日工时": r.daily_hours,
                "休假": ",".join(str(d) for d in r.vacations) if r.vacations else "",
            }
            for r in data.resources
        ])
        st.dataframe(res_df, use_container_width=True)

    with col3:
        st.subheader("节假日表")
        hol_df = pd.DataFrame([
            {
                "日期": str(h.date),
                "名称": h.name,
                "是否工作日": "是" if h.is_workday else "否",
            }
            for h in data.holidays
        ])
        st.dataframe(hol_df, use_container_width=True)

# 手动排期区
st.header("2. 手动排期")
if project_context.has_data():
    strategy = st.selectbox(
        "选择排期策略",
        options=["deadline_first", "priority_first", "workload_balance"],
        format_func=lambda x: {
            "deadline_first": "Deadline 优先",
            "priority_first": "优先级优先",
            "workload_balance": "负载均衡",
        }.get(x, x),
    )

    if st.button("开始排期", type="primary"):
        with st.spinner("排期中..."):
            data = project_context.get_data()
            result = schedule_requirements(
                data.requirements,
                data.resources,
                data.holidays,
                strategy=strategy,
            )
            project_context.set_result(result)
            st.success("排期完成")
            st.rerun()

# 显示排期结果
if project_context.get_result():
    result = project_context.get_result()

    st.header("3. 排期结果")

    st.subheader("汇总信息")
    st.text(format_summary_text(result))

    st.subheader("排期明细")
    result_df = format_schedule_result_for_table(result)
    st.dataframe(result_df, use_container_width=True)

    if result.delayed_items:
        st.subheader("延期风险")
        delayed_df = format_delayed_items(result)
        st.dataframe(delayed_df, use_container_width=True)

    if result.unscheduled_items:
        st.subheader("无法排期任务")
        unscheduled_df = format_unscheduled_items(result)
        st.dataframe(unscheduled_df, use_container_width=True)

    # 冲突检测
    st.subheader("冲突检测")
    data = project_context.get_data()
    conflicts = check_conflicts(result, data.requirements, data.resources, data.holidays)
    st.text(format_conflicts(conflicts))

    # 导出区
    st.header("4. 导出")
    if st.button("导出当前排期结果为 Excel"):
        filepath = export_schedule_to_excel(result)
        st.success(f"已导出: {filepath}")
        with open(filepath, "rb") as f:
            st.download_button(
                label="下载 Excel",
                data=f,
                file_name=os.path.basename(filepath),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

# Agent 对话区
st.header("5. Agent 对话")
st.markdown("""
你可以尝试以下问题：
- 帮我按 deadline 优先排一下
- 如果张三 2026-05-11 到 2026-05-15 休假，会影响哪些需求？
- REQ-003 能不能提前到 2026-05-15 前完成？
- 为什么 REQ-003 延期了？
- 对比 deadline 优先和 workload_balance
- 导出当前排期结果
""")

user_input = st.text_input("输入你的问题")
if st.button("发送给 Agent") and user_input:
    with st.spinner("Agent 思考中..."):
        response = run_agent(user_input)
        st.markdown(f"**Agent:** {response}")

import pandas as pd
