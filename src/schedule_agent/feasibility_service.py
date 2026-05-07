from datetime import date
from .models import ScheduleResult, ScheduleItem


def compare_schedule_results(
    baseline: ScheduleResult,
    simulated: ScheduleResult,
    req_id: str | None = None,
) -> dict:
    """对比 baseline 和 simulated 的排期结果，返回差异分析"""
    # 构建索引
    baseline_items = {item_key(item): item for item in baseline.items + baseline.unscheduled_items}
    simulated_items = {item_key(item): item for item in simulated.items + simulated.unscheduled_items}

    all_keys = set(baseline_items.keys()) | set(simulated_items.keys())

    changes = []
    improved = []
    worsened = []

    for key in all_keys:
        base_item = baseline_items.get(key)
        sim_item = simulated_items.get(key)

        # 如果只存在于 baseline
        if sim_item is None:
            changes.append({
                "req_id": key[0],
                "subtask_type": key[1],
                "change": "removed",
                "baseline": _item_summary(base_item),
                "simulated": None,
            })
            worsened.append(key)
            continue

        # 如果只存在于 simulated
        if base_item is None:
            changes.append({
                "req_id": key[0],
                "subtask_type": key[1],
                "change": "added",
                "baseline": None,
                "simulated": _item_summary(sim_item),
            })
            improved.append(key)
            continue

        # 对比 owner
        owner_changed = base_item.owner != sim_item.owner
        # 对比 start_date
        start_changed = base_item.start_date != sim_item.start_date
        # 对比 end_date
        end_changed = base_item.end_date != sim_item.end_date
        # 对比 delayed
        delay_changed = base_item.delayed != sim_item.delayed

        if owner_changed or start_changed or end_changed or delay_changed:
            change_info = {
                "req_id": key[0],
                "subtask_type": key[1],
                "change": "modified",
                "baseline": _item_summary(base_item),
                "simulated": _item_summary(sim_item),
            }
            changes.append(change_info)

            # 判断是改善还是恶化
            if sim_item.delayed and not base_item.delayed:
                worsened.append(key)
            elif not sim_item.delayed and base_item.delayed:
                improved.append(key)
            elif base_item.end_date and sim_item.end_date and sim_item.end_date < base_item.end_date:
                improved.append(key)
            elif base_item.end_date and sim_item.end_date and sim_item.end_date > base_item.end_date:
                worsened.append(key)

    # 汇总统计
    baseline_scheduled = len(baseline.items)
    simulated_scheduled = len(simulated.items)
    baseline_delayed = len(baseline.delayed_items)
    simulated_delayed = len(simulated.delayed_items)

    summary = {
        "已排期任务数变化": simulated_scheduled - baseline_scheduled,
        "延期任务数变化": simulated_delayed - baseline_delayed,
        "改善的任务数": len(improved),
        "恶化的任务数": len(worsened),
        "总变动数": len(changes),
    }

    # 如果指定了需求ID，只返回该需求相关的变动
    if req_id:
        req_changes = [c for c in changes if c["req_id"] == req_id]
        return {
            "summary": summary,
            "changes": req_changes,
            "improved_count": len([k for k in improved if k[0] == req_id]),
            "worsened_count": len([k for k in worsened if k[0] == req_id]),
        }

    return {
        "summary": summary,
        "changes": changes,
        "improved_count": len(improved),
        "worsened_count": len(worsened),
    }


def item_key(item: ScheduleItem) -> tuple:
    """生成 item 的唯一键"""
    return (item.req_id, item.subtask_type)


def _item_summary(item: ScheduleItem | None) -> dict:
    """生成 item 的摘要信息"""
    if item is None:
        return None
    return {
        "owner": item.owner,
        "start_date": str(item.start_date) if item.start_date else None,
        "end_date": str(item.end_date) if item.end_date else None,
        "status": item.status,
        "delayed": item.delayed,
        "delay_days": item.delay_days,
        "reason": item.reason,
    }


def get_requirement_latest_finish(result: ScheduleResult, req_id: str) -> date | None:
    """获取某个需求在所有子任务中的最晚完成日期"""
    req_items = [
        item for item in result.items
        if item.req_id == req_id and item.end_date is not None
    ]
    if not req_items:
        return None
    return max(item.end_date for item in req_items)


def get_requirement_delay_status(result: ScheduleResult, req_id: str) -> dict:
    """获取某个需求的延期状态"""
    req_items = [item for item in result.items + result.unscheduled_items if item.req_id == req_id]

    if not req_items:
        return {"exists": False, "message": f"需求 {req_id} 不存在"}

    unscheduled = [item for item in req_items if item.status == "无法排期"]
    delayed = [item for item in req_items if item.delayed]

    latest_finish = get_requirement_latest_finish(result, req_id)

    # 获取该需求的 deadline（所有子任务 deadline 应该相同）
    deadline = req_items[0].deadline if req_items else None

    is_delayed = bool(delayed) or bool(unscheduled)
    delay_days = 0
    if latest_finish and deadline and latest_finish > deadline:
        delay_days = (latest_finish - deadline).days

    return {
        "exists": True,
        "req_id": req_id,
        "deadline": str(deadline) if deadline else None,
        "latest_finish": str(latest_finish) if latest_finish else None,
        "is_delayed": is_delayed,
        "delay_days": delay_days,
        "delayed_subtasks": len(delayed),
        "unscheduled_subtasks": len(unscheduled),
        "total_subtasks": len(req_items),
    }
