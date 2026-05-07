import copy
from datetime import datetime, date
from langchain.tools import tool
from .project_context import project_context
from .schedule_engine import schedule_requirements
from .conflict_checker import check_conflicts
from .export_service import export_schedule_to_excel
from .models import Requirement, Resource, Holiday, ScheduleResult


@tool
def load_project_data_tool() -> dict:
    """读取当前项目数据概况"""
    if not project_context.has_data():
        return {
            "has_data": False,
            "message": "当前还没有上传排期 Excel，请先上传数据。"
        }

    data = project_context.get_data()
    result = project_context.get_result()

    preview = []
    for req in data.requirements[:5]:
        preview.append({
            "req_id": req.req_id,
            "name": req.name,
            "priority": req.priority,
            "deadline": str(req.deadline),
        })

    return {
        "has_data": True,
        "requirements_count": len(data.requirements),
        "resources_count": len(data.resources),
        "holidays_count": len(data.holidays),
        "has_schedule_result": result is not None,
        "current_strategy": data.current_strategy,
        "requirements_preview": preview,
    }


@tool
def validate_schedule_data_tool() -> dict:
    """校验当前项目数据是否可以排期"""
    if not project_context.has_data():
        return {
            "valid": False,
            "errors": ["还没有上传数据"],
            "warnings": [],
        }

    data = project_context.get_data()
    errors = []
    warnings = []

    if not data.requirements:
        errors.append("没有需求数据")

    if not data.resources:
        errors.append("没有资源数据")

    # 检查循环依赖
    req_map = {r.req_id: r for r in data.requirements}
    for req in data.requirements:
        for dep in req.dependencies:
            if dep not in req_map:
                errors.append(f"需求 {req.req_id} 的依赖 {dep} 不存在")

    # 检查工时
    for req in data.requirements:
        if req.frontend_days == 0 and req.backend_days == 0 and req.test_days == 0:
            errors.append(f"需求 {req.req_id} 所有工时都为 0")

    # 检查角色资源
    for req in data.requirements:
        needed = set()
        if req.frontend_days > 0:
            needed.add("前端")
        if req.backend_days > 0:
            needed.add("后端")
        if req.test_days > 0:
            needed.add("测试")
        for role in needed:
            if not any(role in r.roles for r in data.resources):
                errors.append(f"需求 {req.req_id} 需要 {role} 角色但没有可用资源")

    # 检查 deadline
    for req in data.requirements:
        if req.deadline is None:
            errors.append(f"需求 {req.req_id} 的 Deadline 为空")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


@tool
def run_schedule_tool(strategy: str = "deadline_first") -> dict:
    """执行排期

    Args:
        strategy: 排期策略，可选 deadline_first, priority_first, workload_balance
    """
    validation = validate_schedule_data_tool.invoke({})
    if not validation.get("valid"):
        return {
            "success": False,
            "message": f"数据校验失败: {', '.join(validation['errors'])}",
        }

    data = project_context.get_data()
    result = schedule_requirements(
        data.requirements,
        data.resources,
        data.holidays,
        strategy=strategy,
    )
    project_context.set_result(result)

    return {
        "success": True,
        "strategy": strategy,
        "summary": result.summary,
        "delayed_items": [
            {
                "req_id": item.req_id,
                "req_name": item.req_name,
                "subtask_type": item.subtask_type,
                "delay_days": item.delay_days,
            }
            for item in result.delayed_items
        ],
        "unscheduled_items": [
            {
                "req_id": item.req_id,
                "req_name": item.req_name,
                "subtask_type": item.subtask_type,
                "reason": item.reason,
            }
            for item in result.unscheduled_items
        ],
        "message": "排期完成",
    }


@tool
def simulate_change_tool(
    change_type: str,
    person: str,
    start_date: str,
    end_date: str,
    strategy: str = "deadline_first",
) -> dict:
    """模拟变化并重新排期

    Args:
        change_type: 变化类型，目前只支持 person_vacation
        person: 人员姓名
        start_date: 休假开始日期，格式 YYYY-MM-DD
        end_date: 休假结束日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据，请先上传 Excel。"
        }

    data = project_context.get_data()

    # 如果没有 baseline，先跑一次
    if project_context.baseline_result is None:
        baseline = schedule_requirements(
            data.requirements, data.resources, data.holidays, strategy
        )
        project_context.baseline_result = baseline

    before_result = project_context.baseline_result

    # 深拷贝并修改
    new_resources = copy.deepcopy(data.resources)
    target_resource = None
    for r in new_resources:
        if r.name == person:
            target_resource = r
            break

    if not target_resource:
        return {
            "success": False,
            "message": f"找不到人员 {person}",
        }

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    current = start
    while current <= end:
        if current not in target_resource.vacations:
            target_resource.vacations.append(current)
        current += __import__("datetime").timedelta(days=1)

    new_data = copy.deepcopy(data)
    new_data.resources = new_resources

    after_result = schedule_requirements(
        new_data.requirements,
        new_data.resources,
        new_data.holidays,
        strategy=strategy,
    )

    # 对比受影响项
    before_map = {}
    for item in before_result.items:
        key = (item.req_id, item.subtask_type)
        before_map[key] = item

    affected = []
    for item in after_result.items:
        key = (item.req_id, item.subtask_type)
        before_item = before_map.get(key)
        if before_item:
            if (before_item.owner != item.owner or
                before_item.start_date != item.start_date or
                before_item.end_date != item.end_date or
                before_item.delayed != item.delayed):
                affected.append({
                    "req_id": item.req_id,
                    "req_name": item.req_name,
                    "subtask_type": item.subtask_type,
                    "before_owner": before_item.owner,
                    "after_owner": item.owner,
                    "before_start": str(before_item.start_date) if before_item.start_date else None,
                    "after_start": str(item.start_date) if item.start_date else None,
                    "before_end": str(before_item.end_date) if before_item.end_date else None,
                    "after_end": str(item.end_date) if item.end_date else None,
                    "before_delayed": before_item.delayed,
                    "after_delayed": item.delayed,
                })

    return {
        "success": True,
        "change_summary": f"模拟 {person} 从 {start_date} 到 {end_date} 休假",
        "before_summary": before_result.summary,
        "after_summary": after_result.summary,
        "affected_items": affected,
        "message": "模拟完成",
    }


@tool
def check_feasibility_tool(task_id: str, target_deadline: str, strategy: str = "deadline_first") -> dict:
    """检查某个需求能否提前到指定日期前完成

    Args:
        task_id: 需求ID
        target_deadline: 目标日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据。"
        }

    data = project_context.get_data()
    target = datetime.strptime(target_deadline, "%Y-%m-%d").date()

    # 深拷贝并修改 deadline
    new_requirements = copy.deepcopy(data.requirements)
    found = False
    for req in new_requirements:
        if req.req_id == task_id:
            req.deadline = target
            found = True
            break

    if not found:
        return {
            "success": False,
            "message": f"找不到需求 {task_id}",
        }

    result = schedule_requirements(
        new_requirements,
        copy.deepcopy(data.resources),
        copy.deepcopy(data.holidays),
        strategy=strategy,
    )

    # 找到该需求的最晚完成时间
    req_items = [item for item in result.items if item.req_id == task_id]
    if not req_items:
        return {
            "success": True,
            "task_id": task_id,
            "target_deadline": target_deadline,
            "feasible": False,
            "expected_finish_date": None,
            "reason": "该需求无法排期",
            "related_items": [],
        }

    latest_end = max(item.end_date for item in req_items if item.end_date)
    feasible = latest_end <= target

    reasons = []
    if not feasible:
        reasons.append(f"任务预计完成日期 {latest_end} 晚于目标日期 {target}")
        # 检查是否受依赖影响
        req = next((r for r in data.requirements if r.req_id == task_id), None)
        if req and req.dependencies:
            dep_items = [item for item in result.items if item.req_id in req.dependencies]
            if dep_items:
                dep_latest = max(item.end_date for item in dep_items if item.end_date)
                if dep_latest and dep_latest >= target:
                    reasons.append(f"依赖任务最晚完成于 {dep_latest}，影响当前需求")

    return {
        "success": True,
        "task_id": task_id,
        "target_deadline": target_deadline,
        "feasible": feasible,
        "expected_finish_date": str(latest_end),
        "reason": "；".join(reasons) if reasons else "可以按目标日期完成",
        "related_items": [
            {
                "subtask_type": item.subtask_type,
                "owner": item.owner,
                "end_date": str(item.end_date) if item.end_date else None,
            }
            for item in req_items
        ],
    }


@tool
def explain_delay_tool(task_id: str = "") -> dict:
    """解释延期原因

    Args:
        task_id: 需求ID，为空则解释所有延期需求
    """
    result = project_context.get_result()
    if not result:
        return {
            "success": False,
            "message": "当前还没有排期结果，请先运行排期。"
        }

    explanations = []
    items_to_explain = result.delayed_items
    if task_id:
        items_to_explain = [item for item in result.delayed_items if item.req_id == task_id]

    data = project_context.get_data()
    req_map = {r.req_id: r for r in data.requirements}
    resource_map = {r.name: r for r in data.resources}

    # 按需求分组
    grouped = {}
    for item in items_to_explain:
        if item.req_id not in grouped:
            grouped[item.req_id] = []
        grouped[item.req_id].append(item)

    for req_id, items in grouped.items():
        req = req_map.get(req_id)
        reasons = []

        # 检查依赖
        if req and req.dependencies:
            dep_items = [i for i in result.items if i.req_id in req.dependencies]
            if dep_items:
                dep_latest = max(i.end_date for i in dep_items if i.end_date)
                if dep_latest and dep_latest >= min(i.start_date for i in items if i.start_date):
                    reasons.append(f"依赖任务完成较晚，最晚完成于 {dep_latest}")

        # 检查资源
        for item in items:
            if item.owner:
                res = resource_map.get(item.owner)
                if res and item.start_date:
                    # 检查是否因休假导致
                    if item.start_date in res.vacations:
                        reasons.append(f"负责人 {item.owner} 在 {item.start_date} 休假")

        # 检查 deadline 是否太近
        if req:
            max_delay = max(item.delay_days for item in items)
            if max_delay > 0:
                reasons.append(f"Deadline {req.deadline} 较近，资源不足导致延期 {max_delay} 天")

        if not reasons:
            reasons.append("资源在目标周期内占用较高")

        explanations.append({
            "task_id": req_id,
            "delayed": True,
            "delay_days": max(item.delay_days for item in items),
            "reasons": reasons,
        })

    return {
        "success": True,
        "explanations": explanations,
    }


@tool
def compare_schedule_tool(strategy_a: str, strategy_b: str) -> dict:
    """对比两个策略的排期结果

    Args:
        strategy_a: 策略A
        strategy_b: 策略B
    """
    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据。"
        }

    data = project_context.get_data()
    result_a = schedule_requirements(
        copy.deepcopy(data.requirements),
        copy.deepcopy(data.resources),
        copy.deepcopy(data.holidays),
        strategy=strategy_a,
    )
    result_b = schedule_requirements(
        copy.deepcopy(data.requirements),
        copy.deepcopy(data.resources),
        copy.deepcopy(data.holidays),
        strategy=strategy_b,
    )

    # 比较维度
    delayed_diff = len(result_a.delayed_items) - len(result_b.delayed_items)
    unscheduled_diff = len(result_a.unscheduled_items) - len(result_b.unscheduled_items)

    # 最晚完成时间
    latest_a = max((item.end_date for item in result_a.items if item.end_date), default=None)
    latest_b = max((item.end_date for item in result_b.items if item.end_date), default=None)

    # P0/P1 延期数量
    p0p1_delayed_a = sum(1 for item in result_a.delayed_items
                         if any(r.req_id == item.req_id and r.priority in ("P0", "P1")
                                for r in data.requirements))
    p0p1_delayed_b = sum(1 for item in result_b.delayed_items
                         if any(r.req_id == item.req_id and r.priority in ("P0", "P1")
                                for r in data.requirements))

    # 负载均衡程度（标准差）
    def calc_load_std(result):
        loads = list(result.summary.get("人员负载统计", {}).values())
        if not loads:
            return 0
        avg = sum(loads) / len(loads)
        variance = sum((x - avg) ** 2 for x in loads) / len(loads)
        return variance ** 0.5

    std_a = calc_load_std(result_a)
    std_b = calc_load_std(result_b)

    # 推荐策略
    score_a = 0
    score_b = 0

    if len(result_a.delayed_items) < len(result_b.delayed_items):
        score_a += 3
    elif len(result_b.delayed_items) < len(result_a.delayed_items):
        score_b += 3

    if p0p1_delayed_a < p0p1_delayed_b:
        score_a += 2
    elif p0p1_delayed_b < p0p1_delayed_a:
        score_b += 2

    if std_a < std_b:
        score_a += 1
    elif std_b < std_a:
        score_b += 1

    if score_a > score_b:
        better = strategy_a
        reason = f"{strategy_a} 在延期控制或负载均衡方面更优"
    elif score_b > score_a:
        better = strategy_b
        reason = f"{strategy_b} 在延期控制或负载均衡方面更优"
    else:
        better = strategy_a
        reason = "两个策略表现相当"

    return {
        "success": True,
        "strategy_a_summary": result_a.summary,
        "strategy_b_summary": result_b.summary,
        "better_strategy": better,
        "comparison": {
            "delayed_count_diff": delayed_diff,
            "unscheduled_count_diff": unscheduled_diff,
            "latest_finish_diff": f"{latest_a} vs {latest_b}",
            "p0p1_delayed_diff": p0p1_delayed_a - p0p1_delayed_b,
            "load_std_diff": round(std_a - std_b, 2),
        },
        "message": reason,
    }


@tool
def export_schedule_tool(format: str = "excel") -> dict:
    """导出当前排期结果为 Excel

    Args:
        format: 导出格式，目前只支持 excel
    """
    result = project_context.get_result()
    if not result:
        return {
            "success": False,
            "message": "当前没有排期结果，请先运行排期。"
        }

    filepath = export_schedule_to_excel(result)
    return {
        "success": True,
        "file_path": filepath,
        "message": "排期结果已导出",
    }
