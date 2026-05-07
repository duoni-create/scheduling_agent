from datetime import datetime
from .models import ProjectData, ScheduleResult


class ProjectContext:
    def __init__(self):
        self.project_data: ProjectData | None = None
        self.baseline_result: ScheduleResult | None = None
        self.draft_result: ScheduleResult | None = None
        self.simulated_result: ScheduleResult | None = None
        self.baseline_meta: dict = {}

    def load_data(self, requirements, resources, holidays):
        self.project_data = ProjectData(
            requirements=requirements,
            resources=resources,
            holidays=holidays,
        )
        self.draft_result = None
        self.simulated_result = None
        # 新上传 Excel 代表新迭代，默认清空 baseline
        self.baseline_result = None
        self.baseline_meta = {}

    def get_data(self) -> ProjectData:
        return self.project_data

    def set_draft_result(self, result: ScheduleResult):
        self.draft_result = result
        if self.project_data:
            self.project_data.current_result = result
            self.project_data.current_strategy = result.strategy

    def get_draft_result(self) -> ScheduleResult | None:
        return self.draft_result

    def confirm_baseline(self, iteration_name: str = "", note: str = "") -> dict:
        if not self.draft_result:
            return {
                "success": False,
                "message": "当前没有临时排期，请先生成排期。",
            }
        self.baseline_result = self.draft_result
        self.baseline_meta = {
            "iteration_name": iteration_name,
            "note": note,
            "confirmed_at": datetime.now().isoformat(),
            "strategy": self.draft_result.strategy,
        }
        return {
            "success": True,
            "message": "已设为本迭代正式排期",
            "baseline_meta": self.baseline_meta,
        }

    def set_baseline_result(self, result: ScheduleResult, iteration_name: str = "", note: str = ""):
        self.baseline_result = result
        self.baseline_meta = {
            "iteration_name": iteration_name,
            "note": note,
            "confirmed_at": datetime.now().isoformat(),
            "strategy": result.strategy,
        }

    def get_baseline_result(self) -> ScheduleResult | None:
        return self.baseline_result

    def has_baseline(self) -> bool:
        return self.baseline_result is not None

    def set_simulated_result(self, result: ScheduleResult):
        self.simulated_result = result

    def get_simulated_result(self) -> ScheduleResult | None:
        return self.simulated_result

    def get_result(self) -> ScheduleResult | None:
        """兼容旧代码，优先返回 draft，其次 baseline"""
        return self.draft_result or self.baseline_result

    def has_data(self) -> bool:
        return self.project_data is not None

    def reset(self):
        self.project_data = None
        self.baseline_result = None
        self.draft_result = None
        self.simulated_result = None
        self.baseline_meta = {}


project_context = ProjectContext()
