import copy
from datetime import datetime, date
from langchain.tools import tool
from .project_context import project_context
from .schedule_engine import schedule_requirements
from .conflict_checker import check_conflicts
from .export_service import export_schedule_to_excel
from .baseline_store import save_baseline, load_baseline
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
        "message": "已设为本迭代正式排期",
        "file_path": filepath,
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
        "message": "已加载正式排期",
        "baseline_meta": baseline_meta,
        "baseline_summary": baseline_result.summary,
    }


@tool
def simulate_change_tool(
    change_type: str,
    person: str,
    start_date: str,
    end_date: str,
    strategy: str = "deadline_first",
) -> dict:
    """模拟变化并重新排期，与正式排期对比

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
            "message": f"当前只支持人员休假模拟 (person_vacation)，不支持的 change_type: {change_type}",
        }

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
    project_context.set_simulated_result(after_result)

    # 对比受影响项（和 baseline 对比）
    before_map = {}
    for item in baseline_result.items:
        key = (item.req_id, item.subtask_type)
        before_map[key] = item

    affected = []
    for item in after_result.items:
        key = (item.req_id, item.subtask_type)
        before_item = before_map.get(key)
        if before_item:
            changes = []
            if before_item.owner != item.owner:
                changes.append(f"负责人从 {before_item.owner} 变为 {item.owner}")
            if before_item.start_date != item.start_date:
                changes.append(f"开始日期从 {before_item.start_date} 变为 {item.start_date}")
            if before_item.start_half != item.start_half:
                changes.append(f"开始半天从 {before_item.start_half} 变为 {item.start_half}")
            if before_item.end_date != item.end_date:
                changes.append(f"结束日期从 {before_item.end_date} 变为 {item.end_date}")
            if before_item.end_half != item.end_half:
                changes.append(f"结束半天从 {before_item.end_half} 变为 {item.end_half}")
            if before_item.delayed != item.delayed:
                changes.append(f"延期状态从 {before_item.delayed} 变为 {item.delayed}")
            if before_item.delay_days != item.delay_days:
                changes.append(f"延期天数从 {before_item.delay_days} 变为 {item.delay_days}")

            if changes:
                affected.append({
                    "req_id": item.req_id,
                    "req_name": item.req_name,
                    "subtask_type": item.subtask_type,
                    "changes": changes,
                })

    return {
        "success": True,
        "base": "baseline",
        "change_summary": f"模拟 {person} 从 {start_date} 到 {end_date} 休假",
        "baseline_summary": baseline_result.summary,
        "simulated_summary": after_result.summary,
        "affected_items": affected,
        "message": "模拟完成，已和正式排期进行对比。",
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

    # 获取 baseline 中的完成时间
    baseline_finish = None
    baseline = project_context.get_baseline_result()
    if baseline:
        baseline_items = [i for i in baseline.items if i.req_id == task_id]
        if baseline_items:
            baseline_finish = max(i.end_date for i in baseline_items if i.end_date)

    return {
        "success": True,
        "task_id": task_id,
        "target_deadline": target_deadline,
        "feasible": feasible,
        "expected_finish_date": str(latest_end),
        "baseline_finish_date": str(baseline_finish) if baseline_finish else None,
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
    baseline_unscheduled = {(i.req_id, i.subtask_type) for i in baseline.unscheduled_items}
    target_unscheduled = {(i.req_id, i.subtask_type) for i in target.unscheduled_items}
    newly_unscheduled = target_unscheduled - baseline_unscheduled

    return {
        "success": True,
        "baseline_summary": baseline.summary,
        "target_summary": target.summary,
        "target_name": target_name,
        "affected_items": affected,
        "newly_unscheduled": list(newly_unscheduled),
        "message": f"已完成 {target_name} 与正式排期的对比。",
    }


@tool
def export_schedule_tool(target: str = "baseline", format: str = "excel") -> dict:
    """导出排期结果为 Excel

    Args:
        target: 导出目标，可选 baseline/draft/simulated，默认 baseline
        format: 导出格式，目前只支持 excel
    """
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
