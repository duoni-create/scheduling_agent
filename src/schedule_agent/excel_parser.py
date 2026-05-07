import pandas as pd
from datetime import datetime, date
from .models import Requirement, Resource, Holiday
from .validation import (
    validate_required_columns,
    parse_date_safe,
    parse_date_list_safe,
    validate_unique_values,
    validate_no_cycle,
)


def parse_dependencies(dep_str):
    """解析依赖需求"""
    if dep_str is None or (isinstance(dep_str, float) and str(dep_str) == 'nan') or str(dep_str).strip() == "":
        return []
    return [d.strip() for d in str(dep_str).split(",") if d.strip()]


def _safe_float(value, row_info, field_name):
    """安全解析 float"""
    if value is None or (isinstance(value, float) and str(value) == 'nan'):
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{row_info}【{field_name}】必须是数字。")


def _safe_int(value, row_info, field_name):
    """安全解析 int"""
    if value is None or (isinstance(value, float) and str(value) == 'nan'):
        raise ValueError(f"{row_info}【{field_name}】不能为空，必须是整数。")
    try:
        float_value = float(value)
        if not float_value.is_integer():
            raise ValueError(f"{row_info}【{field_name}】必须是整数。")
        return int(float_value)
    except (ValueError, TypeError):
        raise ValueError(f"{row_info}【{field_name}】必须是整数。")


def parse_excel(file_path: str):
    """解析 Excel 文件，返回需求、资源、节假日列表"""
    try:
        xls = pd.ExcelFile(file_path)
    except Exception as e:
        raise ValueError(f"无法读取 Excel 文件: {e}")

    required_sheets = ["需求表", "资源表", "节假日表"]
    for sheet in required_sheets:
        if sheet not in xls.sheet_names:
            raise ValueError(f"Excel 缺少必要 Sheet: {sheet}")

    # ===== 需求表 =====
    df_req = pd.read_excel(file_path, sheet_name="需求表")
    validate_required_columns(df_req, [
        "需求ID", "需求名称", "前端工时", "后端工时", "测试工时",
        "优先级", "Deadline", "依赖需求", "状态", "备注",
        "后端指定人员", "前端指定人员", "测试指定人员"
    ], "需求表")

    requirements = []
    req_ids = []
    req_names = []
    for idx, row in df_req.iterrows():
        req_id = str(row["需求ID"]).strip() if pd.notna(row["需求ID"]) else ""
        req_name = str(row["需求名称"]).strip() if pd.notna(row["需求名称"]) else ""
        status = str(row.get("状态", "")).strip() if pd.notna(row.get("状态", "")) else ""

        row_info = f"第 {idx + 2} 行需求 {req_id} " if req_id else f"第 {idx + 2} 行"

        # 跳过非待排期
        if status != "待排期":
            continue

        # 基本非空校验
        if not req_id:
            raise ValueError(f"{row_info}【需求ID】不能为空")
        if not req_name:
            raise ValueError(f"{row_info}【需求名称】不能为空")
        if not status:
            raise ValueError(f"{row_info}【状态】不能为空")

        req_ids.append(req_id)
        req_names.append(req_name)

        # 工时解析和校验
        frontend_days = _safe_float(row.get("前端工时", 0), row_info, "前端工时")
        backend_days = _safe_float(row.get("后端工时", 0), row_info, "后端工时")
        test_days = _safe_float(row.get("测试工时", 0), row_info, "测试工时")

        if frontend_days == 0 and backend_days == 0 and test_days == 0:
            raise ValueError(f"{row_info}所有工时都为 0")

        for days, name in [(frontend_days, "前端工时"), (backend_days, "后端工时"), (test_days, "测试工时")]:
            if days < 0:
                raise ValueError(f"{row_info}【{name}】不能为负数")
            if days % 0.5 != 0:
                raise ValueError(f"{row_info}【{name}】必须是 0.5 的倍数")

        # Deadline
        deadline = parse_date_safe(row.get("Deadline"), "Deadline", idx + 2)
        if deadline is None:
            raise ValueError(f"{row_info}【Deadline】不能为空")

        # 优先级
        priority = str(row.get("优先级", "")).strip()
        if priority not in ("P0", "P1", "P2", "P3"):
            raise ValueError(f"{row_info}【优先级】必须是 P0/P1/P2/P3")

        # 依赖
        dependencies = parse_dependencies(row.get("依赖需求", ""))

        # 自检依赖
        for dep in dependencies:
            if dep == req_id:
                raise ValueError(f"需求 {req_id} 不能依赖自己")

        # 解析指定人员（允许为空）
        backend_assignee = str(row.get("后端指定人员", "")).strip() if pd.notna(row.get("后端指定人员", "")) else ""
        frontend_assignee = str(row.get("前端指定人员", "")).strip() if pd.notna(row.get("前端指定人员", "")) else ""
        test_assignee = str(row.get("测试指定人员", "")).strip() if pd.notna(row.get("测试指定人员", "")) else ""

        req = Requirement(
            req_id=req_id,
            name=req_name,
            frontend_days=frontend_days,
            backend_days=backend_days,
            test_days=test_days,
            priority=priority,
            deadline=deadline,
            dependencies=dependencies,
            status=status,
            memo=str(row.get("备注", "")).strip() if pd.notna(row.get("备注", "")) else "",
            backend_assignee=backend_assignee,
            frontend_assignee=frontend_assignee,
            test_assignee=test_assignee,
        )
        requirements.append(req)

    # 需求ID重复校验
    validate_unique_values(req_ids, "需求ID")

    # ===== 资源表 =====
    df_res = pd.read_excel(file_path, sheet_name="资源表")
    validate_required_columns(df_res, [
        "姓名", "角色", "可用起始日期", "可用结束日期", "每日工时", "休假日期"
    ], "资源表")

    resources = []
    resource_names = []
    for idx, row in df_res.iterrows():
        name = str(row["姓名"]).strip() if pd.notna(row["姓名"]) else ""
        row_info = f"第 {idx + 2} 行"

        if not name:
            raise ValueError(f"{row_info}资源表【姓名】不能为空")

        resource_names.append(name)

        role_value = row.get("角色", "")
        if role_value is None or (isinstance(role_value, float) and str(role_value) == 'nan'):
            role_value = ""
        roles = [r.strip() for r in str(role_value).split(",") if r.strip()]
        if not roles:
            raise ValueError(f"{row_info}人员 {name} 的【角色】不能为空")

        valid_roles = {"前端", "后端", "测试"}
        for role in roles:
            if role not in valid_roles:
                raise ValueError(f"{row_info}人员 {name} 的角色 {role} 不合法")

        available_start = parse_date_safe(row.get("可用起始日期"), "可用起始日期", idx + 2)
        available_end = parse_date_safe(row.get("可用结束日期"), "可用结束日期", idx + 2)

        if available_start is None:
            raise ValueError(f"{row_info}人员 {name} 的【可用起始日期】不能为空")
        if available_end is None:
            raise ValueError(f"{row_info}人员 {name} 的【可用结束日期】不能为空")
        if available_end < available_start:
            raise ValueError(f"{row_info}人员 {name} 的可用结束日期不能早于可用起始日期")

        daily_hours = _safe_int(row.get("每日工时", 8), row_info, "每日工时")
        if daily_hours not in (4, 8):
            raise ValueError(f"{row_info}人员 {name} 的每日工时必须是 4 或 8")

        vacations = parse_date_list_safe(row.get("休假日期", ""), "休假日期", idx + 2)

        # 校验休假日期是否在可用范围内
        for vac in vacations:
            if vac < available_start or vac > available_end:
                raise ValueError(
                    f"{row_info}人员 {name} 的休假日期 {vac} 不在可用日期范围"
                    f"（{available_start} ~ {available_end}）内"
                )

        res = Resource(
            name=name,
            roles=roles,
            available_start=available_start,
            available_end=available_end,
            daily_hours=daily_hours,
            vacations=vacations,
        )
        resources.append(res)

    # 人员姓名重复校验
    validate_unique_values(resource_names, "姓名")

    # ===== 节假日表 =====
    df_hol = pd.read_excel(file_path, sheet_name="节假日表")
    validate_required_columns(df_hol, [
        "日期", "名称", "是否工作日"
    ], "节假日表")

    holidays = []
    holiday_dates = []
    for idx, row in df_hol.iterrows():
        hol_date = parse_date_safe(row.get("日期"), "日期", idx + 2)
        if hol_date is None:
            continue

        if hol_date in holiday_dates:
            raise ValueError(f"节假日表日期重复：{hol_date}")
        holiday_dates.append(hol_date)

        is_workday_str = str(row.get("是否工作日", "")).strip()
        if is_workday_str not in ("是", "否"):
            raise ValueError(
                f"第 {idx + 2} 行节假日【是否工作日】必须是'是'或'否'，当前值：{is_workday_str}"
            )
        is_workday = is_workday_str == "是"

        hol = Holiday(
            date=hol_date,
            name=str(row.get("名称", "")).strip() if pd.notna(row.get("名称", "")) else "",
            is_workday=is_workday,
        )
        holidays.append(hol)

    # ===== 跨表校验 =====

    # 校验依赖需求是否存在
    req_id_set = set(req_ids)
    for req in requirements:
        for dep in req.dependencies:
            if dep not in req_id_set:
                raise ValueError(f"需求 {req.req_id} 的依赖需求 {dep} 不存在")

    # 校验需求所需角色是否有可用资源
    for req in requirements:
        needed_roles = set()
        if req.frontend_days > 0:
            needed_roles.add("前端")
        if req.backend_days > 0:
            needed_roles.add("后端")
        if req.test_days > 0:
            needed_roles.add("测试")

        for role in needed_roles:
            has_resource = any(role in res.roles for res in resources)
            if not has_resource:
                raise ValueError(f"需求 {req.req_id} 需要 {role} 角色，但没有可用资源")

    # 校验循环依赖
    validate_no_cycle(requirements)

    return requirements, resources, holidays
