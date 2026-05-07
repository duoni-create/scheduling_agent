from datetime import date, timedelta
from .models import Resource, Holiday


def is_workday(day: date, holidays: list[Holiday]) -> bool:
    """判断某天是否为工作日"""
    holiday_map = {h.date: h for h in holidays}
    if day in holiday_map:
        return holiday_map[day].is_workday
    return day.weekday() < 5  # 周一到周五为工作日


def is_resource_available(
    resource: Resource,
    day: date,
    half: str,
    holidays: list[Holiday],
    occupied_slots: dict,
) -> bool:
    """判断资源某天某半天是否可用"""
    if day < resource.available_start or day > resource.available_end:
        return False
    if day in resource.vacations:
        return False
    if not is_workday(day, holidays):
        return False
    key = (resource.name, day, half)
    if key in occupied_slots and occupied_slots[key]:
        return False
    return True


def next_half_day(day: date, half: str) -> tuple[date, str]:
    """获取下一个半天"""
    if half == "上午":
        return day, "下午"
    else:
        return day + timedelta(days=1), "上午"


def generate_half_day_slots(start_date: date, end_date: date) -> list[tuple[date, str]]:
    """生成日期范围内的半天槽位"""
    slots = []
    current_date = start_date
    while current_date <= end_date:
        slots.append((current_date, "上午"))
        slots.append((current_date, "下午"))
        current_date += timedelta(days=1)
    return slots
