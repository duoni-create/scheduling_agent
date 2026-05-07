from datetime import date
from typing import Optional


VALID_STRATEGIES = {"deadline_first", "priority_first", "workload_balance"}


def validate_required_columns(df, required_columns: list[str], sheet_name: str) -> None:
    """校验 DataFrame 是否包含所有必填列"""
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Excel 的【{sheet_name}】缺少必要列：{', '.join(missing)}")


def parse_date_safe(value, field_name: str, row_index: Optional[int] = None) -> Optional[date]:
    """安全解析日期，返回 date 对象或 None"""
    if value is None or (isinstance(value, float) and str(value) == 'nan') or str(value).strip() == "":
        return None

    try:
        from datetime import datetime
        # 先判断 datetime，再判断 date（因为 datetime 是 date 的子类）
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        # 处理 pandas Timestamp
        if hasattr(value, "date"):
            return value.date()
        value_str = str(value).strip()
        return datetime.strptime(value_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        row_info = f"第 {row_index} 行" if row_index is not None else ""
        raise ValueError(
            f"{row_info}字段【{field_name}】日期格式错误，请使用 YYYY-MM-DD，例如 2026-05-20"
        )


def parse_date_list_safe(value, field_name: str, row_index: Optional[int] = None) -> list[date]:
    """安全解析逗号分隔的日期列表"""
    if value is None or (isinstance(value, float) and str(value) == 'nan') or str(value).strip() == "":
        return []

    dates = []
    for d in str(value).split(","):
        d = d.strip()
        if d:
            try:
                from datetime import datetime
                dates.append(datetime.strptime(d, "%Y-%m-%d").date())
            except (ValueError, TypeError):
                row_info = f"第 {row_index} 行" if row_index is not None else ""
                raise ValueError(
                    f"{row_info}字段【{field_name}】中包含日期格式错误：'{d}'，请使用 YYYY-MM-DD"
                )
    return dates


def parse_yyyy_mm_dd(value: str, field_name: str) -> date:
    """专门解析工具入参日期，必须为 YYYY-MM-DD"""
    if not value or not str(value).strip():
        raise ValueError(f"字段 {field_name} 不能为空，格式必须是 YYYY-MM-DD。")
    try:
        from datetime import datetime
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError(f"字段 {field_name} 日期格式错误：'{value}'，格式必须是 YYYY-MM-DD。")


def validate_unique_values(values, field_name: str) -> None:
    """校验列表中是否有重复值（忽略空字符串）"""
    seen = set()
    duplicates = set()
    for v in values:
        if v and str(v).strip():
            v_str = str(v).strip()
            if v_str in seen:
                duplicates.add(v_str)
            seen.add(v_str)
    if duplicates:
        raise ValueError(f"字段【{field_name}】存在重复值：{', '.join(sorted(duplicates))}")


def validate_no_cycle(requirements) -> None:
    """检查需求依赖是否有循环"""
    req_map = {r.req_id: r for r in requirements}

    def dfs(req_id, visiting, path):
        if req_id in visiting:
            cycle_path = " -> ".join(path[path.index(req_id):] + [req_id])
            raise ValueError(f"检测到循环依赖：{cycle_path}")
        if req_id not in req_map:
            return
        visiting.add(req_id)
        path.append(req_id)
        for dep in req_map[req_id].dependencies:
            if dep:  # 忽略空依赖
                dfs(dep, visiting, path)
        path.pop()
        visiting.remove(req_id)

    visited = set()
    for req in requirements:
        if req.req_id not in visited:
            dfs(req.req_id, set(), [])
            visited.add(req.req_id)


def validate_strategy(strategy: str) -> tuple[bool, str]:
    """校验排期策略是否合法"""
    if strategy not in VALID_STRATEGIES:
        return False, f"不支持的排期策略：{strategy}，可选值：{', '.join(sorted(VALID_STRATEGIES))}"
    return True, ""


def validate_required_text(value: str, field_name: str) -> tuple[bool, str]:
    """校验文本字段不能为空"""
    if not value or not str(value).strip():
        return False, f"{field_name}不能为空"
    return True, ""


def validate_date_range(start_date: date, end_date: date, field_name: str = "结束日期") -> None:
    """校验日期范围"""
    if end_date < start_date:
        raise ValueError(f"{field_name}不能早于开始日期。")
