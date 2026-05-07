import pandas as pd
from datetime import datetime, date
from .models import Requirement, Resource, Holiday


def parse_date(date_value):
    """解析日期字段"""
    if pd.isna(date_value) or date_value == "":
        return None
    if isinstance(date_value, date):
        return date_value
    if isinstance(date_value, str):
        return datetime.strptime(date_value.strip(), "%Y-%m-%d").date()
    if isinstance(date_value, datetime):
        return date_value.date()
    return None


def parse_date_list(date_str):
    """解析逗号分隔的日期列表"""
    if pd.isna(date_str) or str(date_str).strip() == "":
        return []
    dates = []
    for d in str(date_str).split(","):
        d = d.strip()
        if d:
            dates.append(datetime.strptime(d, "%Y-%m-%d").date())
    return dates


def parse_dependencies(dep_str):
    """解析依赖需求"""
    if pd.isna(dep_str) or str(dep_str).strip() == "":
        return []
    return [d.strip() for d in str(dep_str).split(",") if d.strip()]


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

    # 解析需求表
    df_req = pd.read_excel(file_path, sheet_name="需求表")
    requirements = []
    req_ids = set()
    for idx, row in df_req.iterrows():
        req_id = str(row["需求ID"]).strip()
        status = str(row.get("状态", "")).strip()
        if status != "待排期":
            continue
        req_ids.add(req_id)
        frontend_days = float(row.get("前端工时", 0) or 0)
        backend_days = float(row.get("后端工时", 0) or 0)
        test_days = float(row.get("测试工时", 0) or 0)

        if frontend_days == 0 and backend_days == 0 and test_days == 0:
            raise ValueError(f"需求 {req_id} 的所有工时都为 0")

        for days, name in [(frontend_days, "前端"), (backend_days, "后端"), (test_days, "测试")]:
            if days < 0:
                raise ValueError(f"需求 {req_id} 的{name}工时不能为负数")
            if days % 0.5 != 0:
                raise ValueError(f"需求 {req_id} 的{name}工时必须是 0.5 的倍数")

        deadline = parse_date(row.get("Deadline"))
        if deadline is None:
            raise ValueError(f"需求 {req_id} 的 Deadline 不能为空")

        priority = str(row.get("优先级", "")).strip()
        if priority not in ("P0", "P1", "P2", "P3"):
            raise ValueError(f"需求 {req_id} 的优先级必须是 P0/P1/P2/P3")

        req = Requirement(
            req_id=req_id,
            name=str(row.get("需求名称", "")).strip(),
            frontend_days=frontend_days,
            backend_days=backend_days,
            test_days=test_days,
            priority=priority,
            deadline=deadline,
            dependencies=parse_dependencies(row.get("依赖需求", "")),
            status=status,
            memo=str(row.get("备注", "")).strip(),
        )
        requirements.append(req)

    # 解析资源表
    df_res = pd.read_excel(file_path, sheet_name="资源表")
    resources = []
    resource_names = set()
    for idx, row in df_res.iterrows():
        name = str(row["姓名"]).strip()
        resource_names.add(name)
        roles = [r.strip() for r in str(row.get("角色", "")).split(",") if r.strip()]
        valid_roles = {"前端", "后端", "测试"}
        for role in roles:
            if role not in valid_roles:
                raise ValueError(f"人员 {name} 的角色 {role} 不合法")

        available_start = parse_date(row.get("可用起始日期"))
        available_end = parse_date(row.get("可用结束日期"))
        daily_hours = int(row.get("每日工时", 8))
        vacations = parse_date_list(row.get("休假日期", ""))

        if available_start is None or available_end is None:
            raise ValueError(f"人员 {name} 的可用日期不能为空")

        if available_end < available_start:
            raise ValueError(f"人员 {name} 的可用结束日期不能早于可用起始日期")

        if daily_hours not in (4, 8):
            raise ValueError(f"人员 {name} 的每日工时必须是 4 或 8")

        res = Resource(
            name=name,
            roles=roles,
            available_start=available_start,
            available_end=available_end,
            daily_hours=daily_hours,
            vacations=vacations,
        )
        resources.append(res)

    # 解析节假日表
    df_hol = pd.read_excel(file_path, sheet_name="节假日表")
    holidays = []
    for idx, row in df_hol.iterrows():
        hol_date = parse_date(row.get("日期"))
        if hol_date is None:
            continue
        is_workday = str(row.get("是否工作日", "")).strip() == "是"
        hol = Holiday(
            date=hol_date,
            name=str(row.get("名称", "")).strip(),
            is_workday=is_workday,
        )
        holidays.append(hol)

    # 校验依赖需求是否存在
    for req in requirements:
        for dep in req.dependencies:
            if dep not in req_ids:
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

    return requirements, resources, holidays
