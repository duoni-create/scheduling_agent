from datetime import date, timedelta
from collections import defaultdict
from .models import Requirement, Resource, Holiday, ScheduleItem, ScheduleResult
from .calendar_service import is_workday, is_resource_available, next_half_day, generate_half_day_slots


def topological_sort_layers(requirements: list[Requirement]) -> list[list[Requirement]]:
    """拓扑排序，返回分层结果。每层的需求可以并行排期。"""
    req_map = {r.req_id: r for r in requirements}
    in_degree = {r.req_id: 0 for r in requirements}
    adj = defaultdict(list)

    for req in requirements:
        for dep in req.dependencies:
            if dep in req_map:
                adj[dep].append(req.req_id)
                in_degree[req.req_id] += 1

    layers = []
    remaining = set(r.req_id for r in requirements)

    while remaining:
        # 找出当前入度为 0 的所有节点
        current_layer_ids = [req_id for req_id in remaining if in_degree[req_id] == 0]
        if not current_layer_ids:
            raise ValueError("检测到循环依赖，无法排期")

        current_layer = [req_map[req_id] for req_id in current_layer_ids]
        layers.append(current_layer)
        remaining -= set(current_layer_ids)

        # 更新入度
        for req_id in current_layer_ids:
            for neighbor in adj[req_id]:
                in_degree[neighbor] -= 1

    return layers


def get_priority_weight(priority: str) -> int:
    """获取优先级权重"""
    weights = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return weights.get(priority, 4)


def sort_requirements(requirements: list[Requirement], strategy: str) -> list[Requirement]:
    """按策略排序需求"""
    if strategy == "deadline_first":
        return sorted(requirements, key=lambda r: (r.deadline, get_priority_weight(r.priority), r.req_id))
    elif strategy == "priority_first":
        return sorted(requirements, key=lambda r: (get_priority_weight(r.priority), r.deadline, r.req_id))
    else:  # workload_balance 也按 deadline + priority 排序需求
        return sorted(requirements, key=lambda r: (r.deadline, get_priority_weight(r.priority), r.req_id))


def split_subtasks(requirement: Requirement) -> list[dict]:
    """将需求拆分为子任务"""
    subtasks = []
    # 固定顺序：后端 -> 前端 -> 测试
    for task_type, days in [
        ("后端", requirement.backend_days),
        ("前端", requirement.frontend_days),
        ("测试", requirement.test_days),
    ]:
        if days > 0:
            subtasks.append({
                "req_id": requirement.req_id,
                "req_name": requirement.name,
                "type": task_type,
                "days": days,
                "deadline": requirement.deadline,
            })
    return subtasks


def get_resource_daily_halves(resource: Resource, day: date) -> list[str]:
    """获取资源某天可以工作的半天列表"""
    if resource.daily_hours == 4:
        return ["上午"]  # 4小时只上半天
    else:
        return ["上午", "下午"]  # 8小时上两个半天


def find_earliest_plan(
    subtask: dict,
    candidates: list[Resource],
    holidays: list[Holiday],
    occupied_slots: dict,
    earliest_start_date: date,
    strategy: str,
    resource_load: dict = None,
) -> tuple[date, str, date, str, str, list[tuple[date, str]]] | None:
    """找到最早的排期方案，返回 (start_date, start_half, end_date, end_half, owner, used_slots)"""
    if resource_load is None:
        resource_load = defaultdict(float)

    best_plan = None
    best_end = None

    for candidate in candidates:
        slots_needed = int(subtask["days"] * 2)  # 半天数量
        if slots_needed == 0:
            continue

        slots = generate_half_day_slots(earliest_start_date, earliest_start_date + timedelta(days=60))
        available_slots = []

        for day, half in slots:
            # 检查 daily_hours 限制
            daily_halves = get_resource_daily_halves(candidate, day)
            if half not in daily_halves:
                continue
            if is_resource_available(candidate, day, half, holidays, occupied_slots):
                available_slots.append((day, half))

        if len(available_slots) < slots_needed:
            continue

        # 取前 N 个可用半天
        used_slots = available_slots[:slots_needed]
        start_date, start_half = used_slots[0]
        end_date, end_half = used_slots[-1]

        # 计算完成时间（用于比较）
        end_score = (end_date - date(2000, 1, 1)).days * 2 + (0 if end_half == "上午" else 1)

        if best_end is None or end_score < best_end:
            best_end = end_score
            best_plan = (start_date, start_half, end_date, end_half, candidate.name, used_slots)
        elif strategy == "workload_balance" and end_score == best_end:
            # 完成时间相同时，选择负载更小的
            if resource_load[candidate.name] < resource_load[best_plan[4]]:
                best_plan = (start_date, start_half, end_date, end_half, candidate.name, used_slots)

    return best_plan


def schedule_requirements(
    requirements: list[Requirement],
    resources: list[Resource],
    holidays: list[Holiday],
    strategy: str = "deadline_first",
    start_date: date = None,
) -> ScheduleResult:
    """主排期函数"""
    if start_date is None:
        start_date = date.today()

    # 拓扑分层
    layers = topological_sort_layers(requirements)

    # 每层内部按策略排序
    sorted_layers = []
    for layer in layers:
        sorted_layers.append(sort_requirements(layer, strategy))

    occupied_slots = {}  # (name, day, half) -> bool
    req_end_dates = {}  # req_id -> 最晚完成日期
    resource_load = defaultdict(float)
    items = []
    unscheduled_items = []
    delayed_items = []

    for layer in sorted_layers:
        for req in layer:
            subtasks = split_subtasks(req)
            req_earliest_start = start_date

            # 考虑依赖
            for dep in req.dependencies:
                if dep in req_end_dates:
                    dep_end = req_end_dates[dep]
                    if dep_end > req_earliest_start:
                        req_earliest_start = dep_end + timedelta(days=1)

            req_latest_end = None

            for subtask in subtasks:
                task_type = subtask["type"]
                candidates = [r for r in resources if task_type in r.roles]

                if not candidates:
                    item = ScheduleItem(
                        req_id=req.req_id,
                        req_name=req.name,
                        subtask_type=task_type,
                        owner=None,
                        start_date=None,
                        start_half=None,
                        end_date=None,
                        end_half=None,
                        days=subtask["days"],
                        deadline=req.deadline,
                        status="无法排期",
                        reason=f"没有具备'{task_type}'角色的可用人员",
                    )
                    unscheduled_items.append(item)
                    continue

                plan = find_earliest_plan(
                    subtask, candidates, holidays, occupied_slots,
                    req_earliest_start, strategy, resource_load
                )

                if plan is None:
                    item = ScheduleItem(
                        req_id=req.req_id,
                        req_name=req.name,
                        subtask_type=task_type,
                        owner=None,
                        start_date=None,
                        start_half=None,
                        end_date=None,
                        end_half=None,
                        days=subtask["days"],
                        deadline=req.deadline,
                        status="无法排期",
                        reason="可用时间不足",
                    )
                    unscheduled_items.append(item)
                    continue

                start_date_val, start_half_val, end_date_val, end_half_val, owner, used_slots = plan

                # 标记占用 - 使用实际使用的 used_slots
                for slot_day, slot_half in used_slots:
                    occupied_slots[(owner, slot_day, slot_half)] = True

                resource_load[owner] += subtask["days"]

                delayed = end_date_val > req.deadline
                delay_days = (end_date_val - req.deadline).days if delayed else 0

                item = ScheduleItem(
                    req_id=req.req_id,
                    req_name=req.name,
                    subtask_type=task_type,
                    owner=owner,
                    start_date=start_date_val,
                    start_half=start_half_val,
                    end_date=end_date_val,
                    end_half=end_half_val,
                    days=subtask["days"],
                    deadline=req.deadline,
                    delayed=delayed,
                    delay_days=delay_days,
                    status="已排期",
                )
                items.append(item)

                if delayed:
                    delayed_items.append(item)

                if req_latest_end is None or end_date_val > req_latest_end:
                    req_latest_end = end_date_val

                # 下一个子任务最早开始时间为当前子任务完成后的下一天
                req_earliest_start = end_date_val + timedelta(days=1)

            if req_latest_end:
                req_end_dates[req.req_id] = req_latest_end

    # 计算汇总
    all_items = items + unscheduled_items
    total_reqs = len(set(item.req_id for item in all_items))
    total_subtasks = len(all_items)
    scheduled_count = len(items)
    unscheduled_count = len(unscheduled_items)
    delayed_count = len(delayed_items)

    earliest_start = min((item.start_date for item in items if item.start_date), default=None)
    latest_finish = max((item.end_date for item in items if item.end_date), default=None)

    summary = {
        "总需求数": total_reqs,
        "总子任务数": total_subtasks,
        "已排期子任务数": scheduled_count,
        "无法排期子任务数": unscheduled_count,
        "延期子任务数": delayed_count,
        "使用策略": strategy,
        "最早开始日期": str(earliest_start) if earliest_start else None,
        "最晚完成日期": str(latest_finish) if latest_finish else None,
        "人员负载统计": dict(resource_load),
    }

    return ScheduleResult(
        items=items,
        unscheduled_items=unscheduled_items,
        delayed_items=delayed_items,
        summary=summary,
        strategy=strategy,
    )
