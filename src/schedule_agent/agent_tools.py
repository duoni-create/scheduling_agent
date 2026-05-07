import copy
from datetime import datetime, date
from langchain.tools import tool
from .project_context import project_context
from .schedule_engine import schedule_requirements
from .conflict_checker import check_conflicts
from .export_service import export_schedule_to_excel
from .baseline_store import save_baseline, load_baseline
from .sqlite_store import get_db_path
from .models import Requirement, Resource, Holiday, ScheduleResult
from .feasibility_service import (
    compare_schedule_results,
    get_requirement_latest_finish,
    get_requirement_delay_status,
)
from .validation import (
    validate_strategy,
    validate_required_text,
    parse_yyyy_mm_dd,
    validate_date_range,
    validate_no_cycle,
)


@tool
def load_project_data_tool() -> dict:
    """读取当前项目数据概况"""
    if not project_context.has_data():
        return {
            "has_data": False,
            "message": "当前还没有上传排期 Excel，请先上传数据。"
        }

    data = project_context.get_data()
    baseline = project_context.get_baseline_result()
    draft = project_context.get_draft_result()
    simulated = project_context.get_simulated_result()

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
        "has_baseline": project_context.has_baseline(),
        "has_draft": draft is not None,
        "has_simulated": simulated is not None,
        "requirements_count": len(data.requirements),
        "resources_count": len(data.resources),
        "holidays_count": len(data.holidays),
        "baseline_meta": project_context.baseline_meta,
        "baseline_summary": baseline.summary if baseline else None,
        "draft_summary": draft.summary if draft else None,
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
    try:
        validate_no_cycle(data.requirements)
    except ValueError as e:
        errors.append(str(e))

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
    """执行排期，生成临时排期（draft）

    Args:
        strategy: 排期策略，可选 deadline_first, priority_first, workload_balance
    """
    is_valid, error_msg = validate_strategy(strategy)
    if not is_valid:
        return {"success": False, "message": error_msg}

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
    project_context.set_draft_result(result)

    return {
        "success": True,
        "result_type": "draft",
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
        "message": "排期已生成，当前为临时排期。确认无误后可以设为本迭代正式排期。",
    }


@tool
def set_baseline_schedule_tool(
    iteration_name: str = "",
    note: str = "",
) -> dict:
    """将当前临时排期设为本迭代正式排期

    Args:
        iteration_name: 迭代名称，例如"2026年5月第1期迭代"
        note: 备注
    """
    is_valid, error_msg = validate_required_text(iteration_name, "迭代名称")
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据。",
        }

    if not project_context.get_draft_result():
        return {
            "success": False,
            "message": "当前没有临时排期，请先生成排期。",
        }

    confirm_result = project_context.confirm_baseline(iteration_name=iteration_name, note=note)
    if not confirm_result.get("success"):
        return confirm_result

    # 保存到本地
    data = project_context.get_data()
    baseline = project_context.get_baseline_result()
    filepath = save_baseline(
        data,
        baseline,
        project_context.baseline_meta,
    )

    return {
        "success": True,
        "message": "已设为本迭代正式排期，并保存到 SQLite",
        "storage": "sqlite",
        "db_path": get_db_path(),
        "baseline_meta": project_context.baseline_meta,
        "baseline_summary": baseline.summary,
    }


@tool
def load_baseline_schedule_tool() -> dict:
    """从本地加载已保存的正式排期"""
    loaded = load_baseline()
    if not loaded:
        return {
            "success": False,
            "message": "当前没有保存过正式排期，请先设置并保存正式排期。",
        }

    project_data, baseline_result, baseline_meta = loaded
    project_context.project_data = project_data
    project_context.baseline_result = baseline_result
    project_context.baseline_meta = baseline_meta

    return {
        "success": True,
        "message": "已从 SQLite 加载正式排期",
        "storage": "sqlite",
        "db_path": get_db_path(),
        "baseline_meta": baseline_meta,
        "baseline_summary": baseline_result.summary,
    }


@tool
def check_person_vacation_feasibility(
    person: str = "",
    start_date: str = "",
    end_date: str = "",
    strategy: str = "deadline_first",
) -> dict:
    """检查人员休假对排期的影响，与 baseline 对比

    Args:
        person: 人员姓名
        start_date: 休假开始日期，格式 YYYY-MM-DD
        end_date: 休假结束日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    is_valid, error_msg = validate_required_text(person, "人员姓名")
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not start_date or not str(start_date).strip():
        return {"success": False, "message": "需要提供请假开始日期。"}

    if not end_date or not str(end_date).strip():
        return {"success": False, "message": "需要提供请假结束日期。"}

    is_valid, error_msg = validate_strategy(strategy)
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据，请先上传 Excel。"
        }

    if not project_context.has_baseline():
        return {
            "success": False,
            "message": "当前还没有正式排期，请先生成排期并设为本迭代正式排期。",
        }

    data = project_context.get_data()
    baseline_result = project_context.get_baseline_result()

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

    try:
        start = parse_yyyy_mm_dd(start_date, "start_date")
        end = parse_yyyy_mm_dd(end_date, "end_date")
        validate_date_range(start, end, "end_date")
    except ValueError as e:
        return {"success": False, "message": str(e)}

    current = start
    while current <= end:
        if current not in target_resource.vacations:
            target_resource.vacations.append(current)
        current += __import__("datetime").timedelta(days=1)

    new_data = copy.deepcopy(data)
    new_data.resources = new_resources

    simulated_result = schedule_requirements(
        new_data.requirements,
        new_data.resources,
        new_data.holidays,
        strategy=strategy,
    )
    project_context.set_simulated_result(simulated_result)

    comparison = compare_schedule_results(baseline_result, simulated_result)

    return {
        "success": True,
        "base": "baseline",
        "change_summary": f"模拟 {person} 从 {start_date} 到 {end_date} 休假",
        "baseline_summary": baseline_result.summary,
        "simulated_summary": simulated_result.summary,
        "comparison": comparison,
        "message": "模拟完成，已和正式排期进行对比。",
    }


@tool
def check_requirement_deadline_feasibility(
    req_id: str = "",
    target_deadline: str = "",
    strategy: str = "deadline_first",
) -> dict:
    """检查某个需求能否提前到指定日期前完成

    Args:
        req_id: 需求ID
        target_deadline: 目标日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    is_valid, error_msg = validate_required_text(req_id, "req_id")
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not target_deadline or not str(target_deadline).strip():
        return {"success": False, "message": "目标日期 target_deadline 不能为空。"}

    is_valid, error_msg = validate_strategy(strategy)
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据。"
        }

    if not project_context.has_baseline():
        return {
            "success": False,
            "message": "当前还没有正式排期，请先生成排期并设为本迭代正式排期。",
        }

    data = project_context.get_data()
    baseline_result = project_context.get_baseline_result()

    try:
        target = parse_yyyy_mm_dd(target_deadline, "target_deadline")
    except ValueError as e:
        return {"success": False, "message": str(e)}

    new_requirements = copy.deepcopy(data.requirements)
    found = False
    for req in new_requirements:
        if req.req_id == req_id:
            req.deadline = target
            found = True
            break

    if not found:
        return {
            "success": False,
            "message": f"找不到需求 {req_id}",
        }

    simulated_result = schedule_requirements(
        new_requirements,
        copy.deepcopy(data.resources),
        copy.deepcopy(data.holidays),
        strategy=strategy,
    )
    project_context.set_simulated_result(simulated_result)

    comparison = compare_schedule_results(baseline_result, simulated_result, req_id)

    delay_status = get_requirement_delay_status(simulated_result, req_id)
    baseline_delay = get_requirement_delay_status(baseline_result, req_id)

    feasible = not delay_status.get("is_delayed", True)

    # 计算预期完成日期
    req_items = [item for item in simulated_result.items if item.req_id == req_id]
    expected_finish = max((item.end_date for item in req_items if item.end_date), default=None)
    baseline_items = [item for item in baseline_result.items if item.req_id == req_id]
    baseline_finish = max((item.end_date for item in baseline_items if item.end_date), default=None)

    # has_impact 判断
    has_impact = comparison.get("worsened_count", 0) > 0 or comparison.get("improved_count", 0) > 0

    message = "需求提前可行性分析完成。"
    if feasible and has_impact:
        message += "可行但可能影响其他需求。"
    elif not feasible:
        message += "不可行，目标需求无法在指定日期前完成。"

    return {
        "success": True,
        "req_id": req_id,
        "target_deadline": target_deadline,
        "feasible": feasible,
        "has_impact": has_impact,
        "baseline_summary": baseline_result.summary,
        "simulated_summary": simulated_result.summary,
        "comparison": comparison,
        "baseline_finish_date": str(baseline_finish) if baseline_finish else None,
        "expected_finish_date": str(expected_finish) if expected_finish else None,
        "delay_status": delay_status,
        "baseline_delay_status": baseline_delay,
        "message": message,
    }


@tool
def check_assignment_feasibility(
    task_id: str = "",
    role: str = "",
    person: str = "",
    strategy: str = "deadline_first",
) -> dict:
    """检查指定人员分配对排期的影响

    Args:
        task_id: 需求ID
        role: 角色，只能是 前端 / 后端 / 测试
        person: 指定人员姓名
        strategy: 排期策略
    """
    is_valid, error_msg = validate_required_text(task_id, "task_id")
    if not is_valid:
        return {"success": False, "message": error_msg}

    is_valid, error_msg = validate_required_text(role, "role")
    if not is_valid:
        return {"success": False, "message": "角色 role 不能为空"}

    if role not in ("前端", "后端", "测试"):
        return {"success": False, "message": f"角色 role 必须是 前端/后端/测试，当前值: {role}"}

    is_valid, error_msg = validate_required_text(person, "person")
    if not is_valid:
        return {"success": False, "message": "人员姓名 person 不能为空"}

    is_valid, error_msg = validate_strategy(strategy)
    if not is_valid:
        return {"success": False, "message": error_msg}

    if not project_context.has_data():
        return {
            "success": False,
            "message": "当前没有项目数据，请先上传 Excel。"
        }

    if not project_context.has_baseline():
        return {
            "success": False,
            "message": "当前还没有正式排期，请先生成排期并设为本迭代正式排期。",
        }

    data = project_context.get_data()
    baseline_result = project_context.get_baseline_result()

    # 校验 task_id 对应需求存在
    target_req = None
    for req in data.requirements:
        if req.req_id == task_id:
            target_req = req
            break

    if not target_req:
        return {
            "success": False,
            "message": f"找不到需求 {task_id}",
        }

    # 校验该需求对应 role 的工时 > 0
    role_days_map = {
        "后端": target_req.backend_days,
        "前端": target_req.frontend_days,
        "测试": target_req.test_days,
    }
    if role_days_map[role] <= 0:
        return {
            "success": False,
            "message": f"需求 {task_id} 的 {role} 工时为 0，无法指定 {role} 人员",
        }

    # 校验 person 在资源表中存在
    resource_map = {res.name: res for res in data.resources}
    if person not in resource_map:
        return {
            "success": False,
            "message": f"人员 {person} 不在资源表中",
        }

    # 校验 person 具备对应 role
    if role not in resource_map[person].roles:
        return {
            "success": False,
            "message": f"人员 {person} 不具备 {role} 角色",
        }

    new_requirements = copy.deepcopy(data.requirements)
    for req in new_requirements:
        if req.req_id == task_id:
            if role == "后端":
                req.backend_assignee = person
            elif role == "前端":
                req.frontend_assignee = person
            elif role == "测试":
                req.test_assignee = person
            break

    simulated_result = schedule_requirements(
        new_requirements,
        copy.deepcopy(data.resources),
        copy.deepcopy(data.holidays),
        strategy=strategy,
    )
    project_context.set_simulated_result(simulated_result)

    comparison = compare_schedule_results(baseline_result, simulated_result, task_id)

    # feasible 判断：如果目标需求出现无法排期，则 false
    req_items = [item for item in simulated_result.items + simulated_result.unscheduled_items if item.req_id == task_id]
    has_unscheduled = any(item.status == "无法排期" for item in req_items)
    feasible = not has_unscheduled

    # has_impact 判断：如果有变动，则为 true
    has_impact = comparison.get("worsened_count", 0) > 0 or comparison.get("improved_count", 0) > 0

    message = "指定人员可行性分析完成。"
    if feasible and has_impact:
        message += "可行但存在延期风险。"
    elif not feasible:
        message += "不可行，目标需求出现无法排期。"

    return {
        "success": True,
        "analysis_type": "assignment",
        "task_id": task_id,
        "role": role,
        "person": person,
        "feasible": feasible,
        "has_impact": has_impact,
        "baseline_summary": baseline_result.summary,
        "simulated_summary": simulated_result.summary,
        "comparison": comparison,
        "message": message,
    }


@tool
def simulate_change_tool(
    change_type: str = "",
    person: str = "",
    start_date: str = "",
    end_date: str = "",
    strategy: str = "deadline_first",
) -> dict:
    """模拟变化并重新排期，与正式排期对比（兼容旧接口）

    Args:
        change_type: 变化类型，目前只支持 person_vacation
        person: 人员姓名
        start_date: 休假开始日期，格式 YYYY-MM-DD
        end_date: 休假结束日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    if change_type != "person_vacation":
        return {
            "success": False,
            "message": f"当前只支持人员休假模拟 person_vacation，不支持 {change_type}"
        }

    return check_person_vacation_feasibility.invoke({
        "person": person,
        "start_date": start_date,
        "end_date": end_date,
        "strategy": strategy,
    })


@tool
def check_feasibility_tool(task_id: str = "", target_deadline: str = "", strategy: str = "deadline_first") -> dict:
    """检查某个需求能否提前到指定日期前完成（兼容旧接口）

    Args:
        task_id: 需求ID
        target_deadline: 目标日期，格式 YYYY-MM-DD
        strategy: 排期策略
    """
    return check_requirement_deadline_feasibility.invoke({
        "req_id": task_id,
        "target_deadline": target_deadline,
        "strategy": strategy,
    })


@tool
def explain_delay_tool(task_id: str = "", scope: str = "baseline") -> dict:
    """解释延期原因

    Args:
        task_id: 需求ID，为空则解释所有延期需求
        scope: 范围，可选 baseline/draft/simulated，默认 baseline
    """
    # 确定要解释的结果
    if scope == "baseline":
        result = project_context.get_baseline_result()
        scope_name = "正式排期"
    elif scope == "draft":
        result = project_context.get_draft_result()
        scope_name = "临时排期"
    elif scope == "simulated":
        result = project_context.get_simulated_result()
        scope_name = "模拟排期"
    else:
        return {
            "success": False,
            "message": f"不支持的 scope: {scope}",
        }

    if not result:
        if scope == "baseline" and project_context.get_draft_result():
            # fallback to draft
            result = project_context.get_draft_result()
            scope_name = "临时排期"
            fallback_note = "（当前解释的是临时排期，不是正式排期）"
        else:
            return {
                "success": False,
                "message": "当前还没有排期结果，请先运行排期。"
            }
    else:
        fallback_note = ""

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
                    if item.start_date in res.vacations:
                        reasons.append(f"负责人 {item.owner} 在 {item.start_date} 休假")

        # 检查 deadline
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

    message = f"{scope_name}延期原因解释"
    if fallback_note:
        message += fallback_note

    return {
        "success": True,
        "scope": scope,
        "message": message,
        "explanations": explanations,
    }


@tool
def compare_with_baseline_tool(compare_target: str = "simulated") -> dict:
    """对比当前 simulated_result 或 draft_result 与 baseline_result

    Args:
        compare_target: 对比对象，可选 simulated/draft，默认 simulated
    """
    if not project_context.has_baseline():
        return {
            "success": False,
            "message": "当前还没有正式排期，请先生成排期并设为本迭代正式排期。",
        }

    baseline = project_context.get_baseline_result()

    if compare_target == "simulated":
        target = project_context.get_simulated_result()
        target_name = "模拟排期"
        if not target:
            return {
                "success": False,
                "message": "当前没有模拟排期，请先做 what-if 模拟。",
            }
    elif compare_target == "draft":
        target = project_context.get_draft_result()
        target_name = "临时排期"
        if not target:
            return {
                "success": False,
                "message": "当前没有临时排期，请先生成排期。",
            }
    else:
        return {
            "success": False,
            "message": f"不支持的 compare_target: {compare_target}",
        }

    # 构建 baseline 映射
    baseline_map = {}
    for item in baseline.items:
        key = (item.req_id, item.subtask_type)
        baseline_map[key] = item

    affected = []
    for item in target.items:
        key = (item.req_id, item.subtask_type)
        base_item = baseline_map.get(key)
        if not base_item:
            continue

        changes = []
        if base_item.owner != item.owner:
            changes.append(f"负责人从 {base_item.owner} 变为 {item.owner}")
        if base_item.start_date != item.start_date:
            changes.append(f"开始日期从 {base_item.start_date} 变为 {item.start_date}")
        if base_item.end_date != item.end_date:
            changes.append(f"结束日期从 {base_item.end_date} 变为 {item.end_date}")
        if base_item.delayed != item.delayed:
            if not base_item.delayed and item.delayed:
                changes.append("新增延期")
            elif base_item.delayed and not item.delayed:
                changes.append("延期消除")
        if base_item.delay_days != item.delay_days:
            changes.append(f"延期天数从 {base_item.delay_days} 变为 {item.delay_days}")

        if changes:
            affected.append({
                "req_id": item.req_id,
                "req_name": item.req_name,
                "subtask_type": item.subtask_type,
                "changes": changes,
            })

    # 新增无法排期任务
    baseline_unscheduled_ids = {(i.req_id, i.subtask_type) for i in baseline.unscheduled_items}
    target_unscheduled = [(i.req_id, i.subtask_type) for i in target.unscheduled_items]
    newly_unscheduled = []
    for req_id, subtask_type in target_unscheduled:
        if (req_id, subtask_type) not in baseline_unscheduled_ids:
            newly_unscheduled.append({
                "req_id": req_id,
                "subtask_type": subtask_type,
            })

    return {
        "success": True,
        "baseline_summary": baseline.summary,
        "target_summary": target.summary,
        "target_name": target_name,
        "affected_items": affected,
        "newly_unscheduled": newly_unscheduled,
        "message": f"已完成 {target_name} 与正式排期的对比。",
    }


@tool
def export_schedule_tool(target: str = "baseline", format: str = "excel") -> dict:
    """导出排期结果为 Excel

    Args:
        target: 导出目标，可选 baseline/draft/simulated，默认 baseline
        format: 导出格式，目前只支持 excel
    """
    if format != "excel":
        return {
            "success": False,
            "message": f"不支持的导出格式：{format}，当前只支持 excel。",
        }

    if target == "baseline":
        result = project_context.get_baseline_result()
        name = "正式排期"
    elif target == "draft":
        result = project_context.get_draft_result()
        name = "临时排期"
    elif target == "simulated":
        result = project_context.get_simulated_result()
        name = "模拟排期"
    else:
        return {
            "success": False,
            "message": f"不支持的 target: {target}",
        }

    if not result:
        return {
            "success": False,
            "message": f"当前没有 {name}，请先生成或设置。",
        }

    filepath = export_schedule_to_excel(result)
    return {
        "success": True,
        "file_path": filepath,
        "message": f"{name}已导出",
    }
