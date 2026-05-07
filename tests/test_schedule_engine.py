import pytest
from datetime import date
from schedule_agent.models import Requirement, Resource, Holiday
from schedule_agent.schedule_engine import schedule_requirements


class TestScheduleEngine:
    @pytest.fixture
    def sample_requirements(self):
        return [
            Requirement(
                req_id="REQ-001", name="首页", frontend_days=1, backend_days=1, test_days=0.5,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
            Requirement(
                req_id="REQ-002", name="用户中心", frontend_days=1, backend_days=1, test_days=0.5,
                priority="P1", deadline=date(2026, 5, 25), dependencies=["REQ-001"], status="待排期"
            ),
        ]

    @pytest.fixture
    def sample_resources(self):
        return [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="李四", roles=["后端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="王五", roles=["前端", "测试"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]

    @pytest.fixture
    def sample_holidays(self):
        return [
            Holiday(date=date(2026, 5, 1), name="劳动节", is_workday=False),
            Holiday(date=date(2026, 5, 5), name="调休", is_workday=True),
        ]

    def test_generate_schedule(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays)
        assert len(result.items) > 0
        assert result.summary["已排期子任务数"] > 0

    def test_no_weekend(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays)
        for item in result.items:
            if item.start_date:
                assert item.start_date.weekday() < 5, f"{item.start_date} 是周末"
            if item.end_date:
                assert item.end_date.weekday() < 5, f"{item.end_date} 是周末"

    def test_no_holiday(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays)
        holiday_dates = {h.date for h in sample_holidays if not h.is_workday}
        for item in result.items:
            if item.start_date:
                assert item.start_date not in holiday_dates
            if item.end_date:
                assert item.end_date not in holiday_dates

    def test_no_vacation(self):
        requirements = [
            Requirement(
                req_id="REQ-001", name="测试", frontend_days=1, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(
                name="张三", roles=["前端"], available_start=date(2026, 5, 1),
                available_end=date(2026, 6, 30), vacations=[date(2026, 5, 6)]
            ),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays)
        for item in result.items:
            if item.start_date:
                assert item.start_date != date(2026, 5, 6)
            if item.end_date:
                assert item.end_date != date(2026, 5, 6)

    def test_dependency_order(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays)
        req1_items = [i for i in result.items if i.req_id == "REQ-001"]
        req2_items = [i for i in result.items if i.req_id == "REQ-002"]

        if req1_items and req2_items:
            req1_latest = max(i.end_date for i in req1_items if i.end_date)
            req2_earliest = min(i.start_date for i in req2_items if i.start_date)
            assert req2_earliest > req1_latest, "依赖任务应该在前序任务完成后开始"

    def test_deadline_first(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, strategy="deadline_first")
        assert result.strategy == "deadline_first"
        assert len(result.items) > 0

    def test_workload_balance(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, strategy="workload_balance")
        assert result.strategy == "workload_balance"
        assert len(result.items) > 0
