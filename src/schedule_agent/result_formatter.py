import pandas as pd
from .models import ScheduleResult


def format_schedule_result_for_table(schedule_result: ScheduleResult) -> pd.DataFrame:
    """格式化排期结果为 DataFrame"""
    data = []
    for item in schedule_result.items:
        slots_str = ""
        if item.used_slots:
            slots_str = ", ".join(
                f"{slot['date']} {slot['half']}" for slot in item.used_slots
            )
        data.append({
            "需求ID": item.req_id,
            "需求名称": item.req_name,
            "子任务类型": item.subtask_type,
            "负责人": item.owner or "",
            "开始日期": str(item.start_date) if item.start_date else "",
            "开始半天": item.start_half or "",
            "结束日期": str(item.end_date) if item.end_date else "",
            "结束半天": item.end_half or "",
            "工时天数": item.days,
            "Deadline": str(item.deadline),
            "是否延期": "是" if item.delayed else "否",
            "延期天数": item.delay_days,
            "状态": item.status,
            "实际占用槽位": slots_str,
        })

    for item in schedule_result.unscheduled_items:
        data.append({
            "需求ID": item.req_id,
            "需求名称": item.req_name,
            "子任务类型": item.subtask_type,
            "负责人": "",
            "开始日期": "",
            "开始半天": "",
            "结束日期": "",
            "结束半天": "",
            "工时天数": item.days,
            "Deadline": str(item.deadline),
            "是否延期": "否",
            "延期天数": 0,
            "状态": item.status,
            "原因": item.reason,
        })

    return pd.DataFrame(data)


def format_summary_text(schedule_result: ScheduleResult) -> str:
    """格式化汇总信息为文本"""
    summary = schedule_result.summary
    lines = [
        f"总需求数: {summary.get('总需求数', 0)}",
        f"总子任务数: {summary.get('总子任务数', 0)}",
        f"已排期子任务数: {summary.get('已排期子任务数', 0)}",
        f"无法排期子任务数: {summary.get('无法排期子任务数', 0)}",
        f"延期子任务数: {summary.get('延期子任务数', 0)}",
        f"使用策略: {summary.get('使用策略', '')}",
        f"最早开始日期: {summary.get('最早开始日期', '')}",
        f"最晚完成日期: {summary.get('最晚完成日期', '')}",
    ]

    load_stats = summary.get("人员负载统计", {})
    if load_stats:
        lines.append("人员负载统计:")
        for name, load in load_stats.items():
            lines.append(f"  {name}: {load} 天")

    return "\n".join(lines)


def format_delayed_items(schedule_result: ScheduleResult) -> pd.DataFrame:
    """格式化延期项为 DataFrame"""
    data = []
    for item in schedule_result.delayed_items:
        data.append({
            "需求ID": item.req_id,
            "需求名称": item.req_name,
            "子任务类型": item.subtask_type,
            "负责人": item.owner or "",
            "预计完成日期": str(item.end_date) if item.end_date else "",
            "Deadline": str(item.deadline),
            "延期天数": item.delay_days,
        })
    return pd.DataFrame(data)


def format_unscheduled_items(schedule_result: ScheduleResult) -> pd.DataFrame:
    """格式化无法排期项为 DataFrame"""
    data = []
    for item in schedule_result.unscheduled_items:
        data.append({
            "需求ID": item.req_id,
            "需求名称": item.req_name,
            "子任务类型": item.subtask_type,
            "工时天数": item.days,
            "Deadline": str(item.deadline),
            "原因": item.reason,
        })
    return pd.DataFrame(data)


def format_conflicts(conflicts: list[str]) -> str:
    """格式化冲突信息"""
    if not conflicts:
        return "未检测到冲突"
    return "\n".join(f"• {c}" for c in conflicts)
