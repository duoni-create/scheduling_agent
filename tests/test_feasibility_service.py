import pytest
from datetime import date
from schedule_agent.models import ScheduleResult, ScheduleItem
from schedule_agent.feasibility_service import (
    compare_schedule_results,
    get_requirement_latest_finish,
    get_requirement_delay_status,
    item_key,
)


class TestFeasibilityService:
    def create_item(self, req_id, subtask_type, owner, start_date, end_date, delayed=False, delay_days=0, status="已排期"):
        return ScheduleItem(
            req_id=req_id,
            req_name=f"需求{req_id}",
            subtask_type=subtask_type,
            owner=owner,
            start_date=start_date,
            start_half="上午",
            end_date=end_date,
            end_half="下午",
            days=1.0,
            deadline=date(2026, 5, 20),
            delayed=delayed,
            delay_days=delay_days,
            status=status,
            used_slots=[],
        )

    def test_item_key(self):
        item = self.create_item("REQ-001", "前端", "张三", date(2026, 5, 1), date(2026, 5, 2))
        assert item_key(item) == ("REQ-001", "前端")

    def test_compare_schedule_results_no_changes(self):
        """两个完全相同的排期结果"""
        items = [
            self.create_item("REQ-001", "前端", "张三", date(2026, 5, 1), date(2026, 5, 2)),
            self.create_item("REQ-001", "后端", "李四", date(2026, 5, 3), date(2026, 5, 4)),
        ]
        baseline = ScheduleResult(items=items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")
        simulated = ScheduleResult(items=items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")

        result = compare_schedule_results(baseline, simulated)
        assert result["summary"]["总变动数"] == 0
        assert result["improved_count"] == 0
        assert result["worsened_count"] == 0

    def test_compare_schedule_results_with_changes(self):
        """有变动的排期结果"""
        baseline_items = [
            self.create_item("REQ-001", "前端", "张三", date(2026, 5, 1), date(2026, 5, 2)),
        ]
        simulated_items = [
            self.create_item("REQ-001", "前端", "李四", date(2026, 5, 3), date(2026, 5, 4)),
        ]
        baseline = ScheduleResult(items=baseline_items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")
        simulated = ScheduleResult(items=simulated_items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")

        result = compare_schedule_results(baseline, simulated)
        assert result["summary"]["总变动数"] == 1
        assert len(result["changes"]) == 1
        assert result["changes"][0]["change"] == "modified"

    def test_get_requirement_latest_finish(self):
        items = [
            self.create_item("REQ-001", "前端", "张三", date(2026, 5, 1), date(2026, 5, 2)),
            self.create_item("REQ-001", "后端", "李四", date(2026, 5, 3), date(2026, 5, 5)),
        ]
        result = ScheduleResult(items=items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")

        latest = get_requirement_latest_finish(result, "REQ-001")
        assert latest == date(2026, 5, 5)

    def test_get_requirement_delay_status_delayed(self):
        items = [
            self.create_item("REQ-001", "前端", "张三", date(2026, 5, 18), date(2026, 5, 22), delayed=True, delay_days=2),
        ]
        result = ScheduleResult(items=items, unscheduled_items=[], delayed_items=items, summary={}, strategy="deadline_first")

        status = get_requirement_delay_status(result, "REQ-001")
        assert status["exists"] is True
        assert status["is_delayed"] is True
        assert status["delay_days"] == 2
        assert status["delayed_subtasks"] == 1

    def test_get_requirement_delay_status_not_delayed(self):
        items = [
            self.create_item("REQ-001", "前端", "张三", date(2026, 5, 1), date(2026, 5, 10), delayed=False, delay_days=0),
        ]
        result = ScheduleResult(items=items, unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")

        status = get_requirement_delay_status(result, "REQ-001")
        assert status["exists"] is True
        assert status["is_delayed"] is False
        assert status["delay_days"] == 0

    def test_get_requirement_delay_status_not_found(self):
        result = ScheduleResult(items=[], unscheduled_items=[], delayed_items=[], summary={}, strategy="deadline_first")
        status = get_requirement_delay_status(result, "REQ-999")
        assert status["exists"] is False
