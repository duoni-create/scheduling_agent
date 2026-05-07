import os
import pytest
from datetime import date
from schedule_agent.models import Requirement, Resource, Holiday, ScheduleResult, ScheduleItem
from schedule_agent.project_context import ProjectContext, project_context
from schedule_agent.agent_tools import (
    load_project_data_tool,
    validate_schedule_data_tool,
    run_schedule_tool,
    set_baseline_schedule_tool,
    load_baseline_schedule_tool,
    simulate_change_tool,
    check_feasibility_tool,
    explain_delay_tool,
    compare_with_baseline_tool,
    export_schedule_tool,
)
from schedule_agent.sample_generator import generate_sample_excel
from schedule_agent.excel_parser import parse_excel


class TestAgentTools:
    @pytest.fixture(autouse=True)
    def reset_context(self):
        project_context.reset()
        yield
        project_context.reset()

    @pytest.fixture
    def sample_data(self):
        path = generate_sample_excel("data/test_tools.xlsx")
        requirements, resources, holidays = parse_excel(path)
        project_context.load_data(requirements, resources, holidays)
        yield
        if os.path.exists("data/test_tools.xlsx"):
            try:
                os.remove("data/test_tools.xlsx")
            except PermissionError:
                pass

    def test_load_project_data_no_data(self):
        result = load_project_data_tool.invoke({})
        assert result["has_data"] is False

    def test_validate_schedule_data_valid(self, sample_data):
        result = validate_schedule_data_tool.invoke({})
        assert result["valid"] is True

    def test_run_schedule_tool_only_sets_draft(self, sample_data):
        result = run_schedule_tool.invoke({"strategy": "deadline_first"})
        assert result["success"] is True
        assert result["result_type"] == "draft"
        assert project_context.get_draft_result() is not None
        assert project_context.get_baseline_result() is None

    def test_set_baseline_schedule_tool(self, sample_data):
        # 先 run_schedule_tool
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        # 再 set_baseline_schedule_tool
        result = set_baseline_schedule_tool.invoke({
            "iteration_name": "2026年5月第1期",
            "note": "测试",
        })
        assert result["success"] is True
        assert project_context.get_baseline_result() is not None
        assert project_context.baseline_meta["iteration_name"] == "2026年5月第1期"

    def test_simulate_change_invalid_type(self, sample_data):
        result = simulate_change_tool.invoke({
            "change_type": "invalid_type",
            "person": "张三",
            "start_date": "2026-05-11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "只支持人员休假模拟" in result["message"]

    def test_simulate_change_requires_baseline(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        # 不设置 baseline，直接 simulate
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "2026-05-11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "还没有正式排期" in result["message"]

    def test_simulate_change_compare_with_baseline(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试迭代", "note": ""})
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "2026-05-11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is True
        assert result["base"] == "baseline"
        assert "affected_items" in result
        assert project_context.get_simulated_result() is not None

    def test_check_feasibility_tool(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = check_feasibility_tool.invoke({
            "task_id": "REQ-003",
            "target_deadline": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is True
        assert "feasible" in result

    def test_explain_delay_no_result(self):
        result = explain_delay_tool.invoke({"task_id": "REQ-003"})
        assert result["success"] is False
        assert "先运行排期" in result["message"]

    def test_compare_with_baseline_tool(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "2026-05-11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        result = compare_with_baseline_tool.invoke({"compare_target": "simulated"})
        assert result["success"] is True
        assert "baseline_summary" in result
        assert "target_summary" in result

    def test_export_baseline_schedule_tool(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        result = export_schedule_tool.invoke({"target": "baseline", "format": "excel"})
        assert result["success"] is True
        assert os.path.exists(result["file_path"])
        if os.path.exists(result["file_path"]):
            os.remove(result["file_path"])
