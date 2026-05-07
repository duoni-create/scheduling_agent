from .models import ProjectData, ScheduleResult


class ProjectContext:
    def __init__(self):
        self.project_data: ProjectData | None = None
        self.baseline_result: ScheduleResult | None = None
        self.last_result: ScheduleResult | None = None

    def load_data(self, requirements, resources, holidays):
        self.project_data = ProjectData(
            requirements=requirements,
            resources=resources,
            holidays=holidays,
        )
        self.baseline_result = None
        self.last_result = None

    def get_data(self) -> ProjectData:
        return self.project_data

    def set_result(self, result: ScheduleResult):
        self.last_result = result
        if self.project_data:
            self.project_data.current_result = result
            self.project_data.current_strategy = result.strategy
        if self.baseline_result is None:
            self.baseline_result = result

    def get_result(self) -> ScheduleResult | None:
        return self.last_result

    def has_data(self) -> bool:
        return self.project_data is not None

    def reset(self):
        self.project_data = None
        self.baseline_result = None
        self.last_result = None


project_context = ProjectContext()
