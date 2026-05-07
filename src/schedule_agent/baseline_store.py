import json
import os
from .models import ProjectData, ScheduleResult


def save_baseline(
    project_data: ProjectData,
    baseline_result: ScheduleResult,
    baseline_meta: dict,
    path: str = "data/baseline/current_baseline.json",
) -> str:
    """保存正式排期到本地 JSON"""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {
        "baseline_meta": baseline_meta,
        "project_data": project_data.model_dump(mode="json"),
        "baseline_result": baseline_result.model_dump(mode="json"),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


def load_baseline(
    path: str = "data/baseline/current_baseline.json",
) -> tuple[ProjectData, ScheduleResult, dict] | None:
    """从本地 JSON 加载正式排期"""
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    project_data = ProjectData.model_validate(data["project_data"])
    baseline_result = ScheduleResult.model_validate(data["baseline_result"])
    baseline_meta = data.get("baseline_meta", {})

    return project_data, baseline_result, baseline_meta


def clear_baseline(path: str = "data/baseline/current_baseline.json"):
    """删除当前 baseline 文件"""
    if os.path.exists(path):
        os.remove(path)
