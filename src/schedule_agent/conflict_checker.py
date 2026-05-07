from datetime import timedelta
from .models import ScheduleResult, Requirement, Resource, Holiday
from .calendar_service import is_workday


def check_conflicts(
    schedule_result: ScheduleResult,
    requirements: list[Requirement],
    resources: list[Resource],
    holidays: list[Holiday],
) -> list[str]:
    """检测排期结果中的冲突"""
    conflicts = []

    # 1. 检测同一个人同一个半天是否被安排多个任务
    occupied = {}
    for item in schedule_result.items:
        if item.owner and item.used_slots:
            for slot in item.used_slots:
                slot_date = slot.get("date")
                slot_half = slot.get("half")
                key = (item.owner, slot_date, slot_half)
                if key in occupied:
                    conflicts.append(
                        f"冲突: {item.owner} 在 {slot_date} {slot_half} 被安排了多个任务"
                    )
                occupied[key] = item.req_id

    # 2. 检测 used_slots 里的日期是否为工作日
    for item in schedule_result.items:
        if item.used_slots:
            for slot in item.used_slots:
                slot_date_str = slot.get("date")
                if slot_date_str:
                    from datetime import datetime
                    slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
                    if not is_workday(slot_date, holidays):
                        conflicts.append(
                            f"冲突: {item.req_id} 的 {item.subtask_type} 任务占用日期 {slot_date} 不是工作日"
                        )

    # 3. 检测 used_slots 里的日期是否为员工休假日
    resource_map = {r.name: r for r in resources}
    for item in schedule_result.items:
        if item.owner and item.used_slots:
            res = resource_map.get(item.owner)
            if res and res.vacations:
                for slot in item.used_slots:
                    slot_date_str = slot.get("date")
                    if slot_date_str:
                        from datetime import datetime
                        slot_date = datetime.strptime(slot_date_str, "%Y-%m-%d").date()
                        if slot_date in res.vacations:
                            conflicts.append(
                                f"冲突: {item.owner} 在 {slot_date} 休假，但安排了 {item.req_id} 的 {item.subtask_type} 任务"
                            )

    # 4. 检测依赖是否被破坏
    req_map = {r.req_id: r for r in requirements}
    req_end_dates = {}
    for item in schedule_result.items:
        if item.req_id not in req_end_dates:
            req_end_dates[item.req_id] = item.end_date
        elif item.end_date and item.end_date > req_end_dates[item.req_id]:
            req_end_dates[item.req_id] = item.end_date

    for item in schedule_result.items:
        req = req_map.get(item.req_id)
        if req:
            for dep in req.dependencies:
                dep_end = req_end_dates.get(dep)
                if dep_end and item.start_date and item.start_date <= dep_end:
                    conflicts.append(
                        f"冲突: {item.req_id} 的 {item.subtask_type} 任务开始于 {item.start_date}，"
                        f"但依赖任务 {dep} 完成于 {dep_end}"
                    )

    # 5. 检测没有负责人但状态为已排期的任务
    for item in schedule_result.items:
        if item.status == "已排期" and not item.owner:
            conflicts.append(
                f"冲突: {item.req_id} 的 {item.subtask_type} 任务状态为已排期但没有负责人"
            )

    return conflicts
