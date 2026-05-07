import os
import pytest
from datetime import date
from schedule_agent.models import Requirement, Resource, Holiday, ScheduleResult, ScheduleItem, ProjectData
from schedule_agent.baseline_store import save_baseline, load_baseline, clear_baseline
from schedule_agent.sqlite_store import get_db_path


class TestBaselineStore:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        yield
        db_path = get_db_path()
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass

    def test_save_and_load_baseline(self):
        requirements = [
            Requirement(
                req_id="REQ-001", name="首页", frontend_days=1, backend_days=1, test_days=0.5,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = [
            Holiday(date=date(2026, 5, 1), name="劳动节", is_workday=False),
        ]

        project_data = ProjectData(
            requirements=requirements,
            resources=resources,
            holidays=holidays,
        )

        schedule_item = ScheduleItem(
            req_id="REQ-001",
            req_name="首页",
            subtask_type="前端",
            owner="张三",
            start_date=date(2026, 5, 6),
            start_half="上午",
            end_date=date(2026, 5, 6),
            end_half="下午",
            days=1.0,
            deadline=date(2026, 5, 20),
            status="已排期",
            used_slots=[{"date": "2026-05-06", "half": "上午"}, {"date": "2026-05-06", "half": "下午"}],
        )

        baseline_result = ScheduleResult(
            items=[schedule_item],
            unscheduled_items=[],
            delayed_items=[],
            summary={"总需求数": 1, "已排期子任务数": 1},
            strategy="deadline_first",
        )

        baseline_meta = {
            "iteration_name": "2026年5月第1期",
            "note": "测试",
            "confirmed_at": "2026-05-01T00:00:00",
            "strategy": "deadline_first",
        }

        path = save_baseline(project_data, baseline_result, baseline_meta)
        assert "sqlite://" in path

        loaded = load_baseline()
        assert loaded is not None

        loaded_project_data, loaded_baseline_result, loaded_meta = loaded
        assert loaded_meta["iteration_name"] == "2026年5月第1期"
        assert len(loaded_project_data.requirements) == 1
        assert len(loaded_baseline_result.items) == 1
        assert loaded_baseline_result.items[0].req_id == "REQ-001"

    def test_load_nonexistent_baseline(self):
        # 先确保没有 baseline
        clear_baseline()
        loaded = load_baseline()
        assert loaded is None

    def test_clear_baseline(self):
        requirements = [
            Requirement(
                req_id="REQ-001", name="首页", frontend_days=1, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []

        project_data = ProjectData(
            requirements=requirements,
            resources=resources,
            holidays=holidays,
        )

        baseline_result = ScheduleResult(
            items=[],
            unscheduled_items=[],
            delayed_items=[],
            summary={},
            strategy="deadline_first",
        )

        save_baseline(project_data, baseline_result, {})
        db_path = get_db_path()
        assert os.path.exists(db_path)

        clear_baseline()
        # SQLite clear 删除表内数据，不删除文件本身
        loaded = load_baseline()
        assert loaded is None
