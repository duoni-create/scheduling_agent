import os
from datetime import datetime
import pandas as pd
from .models import ScheduleResult


def export_schedule_to_excel(
    schedule_result: ScheduleResult,
    output_dir: str = "data/exports"
) -> str:
    """导出排期结果为 Excel"""
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"schedule_result_{timestamp}.xlsx"
    filepath = os.path.join(output_dir, filename)

    # 排期结果 Sheet
    result_data = []
    for item in schedule_result.items:
        slots_str = ""
        if item.used_slots:
            slots_str = ", ".join(
                f"{slot['date']} {slot['half']}" for slot in item.used_slots
            )
        result_data.append({
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
            "原因": item.reason,
            "实际占用槽位": slots_str,
        })

    for item in schedule_result.unscheduled_items:
        result_data.append({
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

    df_result = pd.DataFrame(result_data)

    # 延期风险 Sheet
    delayed_data = []
    for item in schedule_result.delayed_items:
        delayed_data.append({
            "需求ID": item.req_id,
            "需求名称": item.req_name,
            "子任务类型": item.subtask_type,
            "负责人": item.owner or "",
            "预计完成日期": str(item.end_date) if item.end_date else "",
            "Deadline": str(item.deadline),
            "延期天数": item.delay_days,
        })
    df_delayed = pd.DataFrame(delayed_data)

    # 汇总信息 Sheet
    summary = schedule_result.summary
    summary_data = []
    for key, value in summary.items():
        if key == "人员负载统计":
            for name, load in value.items():
                summary_data.append({"指标": f"人员负载-{name}", "数值": load})
        else:
            summary_data.append({"指标": key, "数值": str(value)})
    df_summary = pd.DataFrame(summary_data)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df_result.to_excel(writer, sheet_name="排期结果", index=False)
        df_delayed.to_excel(writer, sheet_name="延期风险", index=False)
        df_summary.to_excel(writer, sheet_name="汇总信息", index=False)

    return filepath
