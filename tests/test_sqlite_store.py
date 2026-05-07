import os
import sqlite3
import pytest
from datetime import date
from schedule_agent.models import Requirement, Resource, Holiday, ScheduleResult, ScheduleItem, ProjectData
from schedule_agent.sqlite_store import (
    init_db,
    save_baseline_to_db,
    load_current_baseline_from_db,
    clear_current_baseline,
    has_current_baseline,
    list_baselines,
    get_db_path,
)


class TestSqliteStore:
    @pytest.fixture
    def sample_project_data(self):
        requirements = [
            Requirement(
                req_id="REQ-001", name="首页", frontend_days=1, backend_days=1, test_days=0.5,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
            Requirement(
                req_id="REQ-002", name="用户中心", frontend_days=1, backend_days=1, test_days=0.5,
                priority="P1", deadline=date(2026, 5, 25), dependencies=["REQ-001"], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="李四", roles=["后端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = [
            Holiday(date=date(2026, 5, 1), name="劳动节", is_workday=False),
        ]
        return ProjectData(requirements=requirements, resources=resources, holidays=holidays)

    @pytest.fixture
    def sample_baseline_result(self):
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
            used_slots=[
                {"date": "2026-05-06", "half": "上午"},
                {"date": "2026-05-06", "half": "下午"},
            ],
        )
        return ScheduleResult(
            items=[schedule_item],
            unscheduled_items=[],
            delayed_items=[],
            summary={"总需求数": 1, "已排期子任务数": 1},
            strategy="deadline_first",
        )

    @pytest.fixture
    def sample_baseline_meta(self):
        return {
            "iteration_name": "2026年5月第1期",
            "note": "测试",
            "confirmed_at": "2026-05-01T00:00:00",
            "strategy": "deadline_first",
        }

    def test_init_db_creates_tables(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        tables = [
            "iterations", "requirements", "resources", "holidays",
            "schedule_runs", "schedule_items",
        ]
        for table in tables:
            cursor.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            assert cursor.fetchone() is not None, f"表 {table} 不存在"

        conn.close()

    def test_save_and_load_baseline_from_db(self, tmp_path, sample_project_data, sample_baseline_result, sample_baseline_meta):
        db_path = str(tmp_path / "test.db")
        iteration_id = save_baseline_to_db(
            sample_project_data,
            sample_baseline_result,
            sample_baseline_meta,
            db_path,
        )
        assert iteration_id > 0

        loaded = load_current_baseline_from_db(db_path)
        assert loaded is not None

        loaded_project_data, loaded_baseline_result, loaded_meta = loaded
        assert loaded_meta["iteration_name"] == "2026年5月第1期"
        assert len(loaded_project_data.requirements) == 2
        assert len(loaded_project_data.resources) == 2
        assert len(loaded_project_data.holidays) == 1
        assert len(loaded_baseline_result.items) == 1

        # 验证 used_slots 能正确还原
        item = loaded_baseline_result.items[0]
        assert len(item.used_slots) == 2
        assert item.used_slots[0]["date"] == "2026-05-06"
        assert item.used_slots[0]["half"] == "上午"

    def test_clear_current_baseline(self, tmp_path, sample_project_data, sample_baseline_result, sample_baseline_meta):
        db_path = str(tmp_path / "test.db")
        save_baseline_to_db(
            sample_project_data,
            sample_baseline_result,
            sample_baseline_meta,
            db_path,
        )
        assert has_current_baseline(db_path)

        clear_current_baseline(db_path)
        assert not has_current_baseline(db_path)
        assert load_current_baseline_from_db(db_path) is None

    def test_save_baseline_overwrites_old_current(self, tmp_path, sample_project_data, sample_baseline_result, sample_baseline_meta):
        db_path = str(tmp_path / "test.db")

        # 第一次保存
        meta1 = {**sample_baseline_meta, "iteration_name": "第一次"}
        save_baseline_to_db(sample_project_data, sample_baseline_result, meta1, db_path)

        # 第二次保存
        meta2 = {**sample_baseline_meta, "iteration_name": "第二次"}
        iteration_id2 = save_baseline_to_db(sample_project_data, sample_baseline_result, meta2, db_path)

        # 加载后应该得到第二次的
        loaded = load_current_baseline_from_db(db_path)
        assert loaded is not None
        _, _, loaded_meta = loaded
        assert loaded_meta["iteration_name"] == "第二次"

        # 检查 list_baselines 中只有当前的一条
        baselines = list_baselines(db_path)
        assert len(baselines) >= 1
        assert any(b["iteration_name"] == "第二次" for b in baselines)

    def test_load_nonexistent_baseline(self, tmp_path):
        db_path = str(tmp_path / "nonexistent.db")
        loaded = load_current_baseline_from_db(db_path)
        assert loaded is None
