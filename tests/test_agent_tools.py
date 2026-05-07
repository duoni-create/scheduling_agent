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
    check_person_vacation_feasibility,
    check_requirement_deadline_feasibility,
    check_assignment_feasibility,
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

    def test_run_schedule_invalid_strategy(self, sample_data):
        result = run_schedule_tool.invoke({"strategy": "bad_strategy"})
        assert result["success"] is False
        assert "不支持的排期策略" in result["message"]

    def test_set_baseline_empty_iteration_name(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = set_baseline_schedule_tool.invoke({"iteration_name": "", "note": ""})
        assert result["success"] is False
        assert "迭代名称不能为空" in result["message"]

    def test_simulate_change_missing_dates(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "开始日期" in result["message"] or "人员姓名" in result["message"]

    def test_simulate_change_invalid_date_format(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "2026/05/11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "日期格式错误" in result["message"]

    def test_simulate_change_end_before_start(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "2026-05-15",
            "end_date": "2026-05-11",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "早于" in result["message"]

    def test_check_feasibility_missing_task_id(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = check_feasibility_tool.invoke({
            "task_id": "",
            "target_deadline": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "task_id" in result["message"] or "不能为空" in result["message"]

    def test_check_feasibility_invalid_deadline(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = check_feasibility_tool.invoke({
            "task_id": "REQ-003",
            "target_deadline": "明天",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "日期格式错误" in result["message"]

    def test_export_schedule_invalid_format(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = export_schedule_tool.invoke({"target": "draft", "format": "pdf"})
        assert result["success"] is False
        assert "不支持的导出格式" in result["message"]

    def test_simulate_change_missing_start_date(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试", "note": ""})
        result = simulate_change_tool.invoke({
            "change_type": "person_vacation",
            "person": "张三",
            "start_date": "",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "开始日期" in result["message"] or "不能为空" in result["message"]

    def test_check_feasibility_missing_target_deadline(self, sample_data):
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        result = check_feasibility_tool.invoke({
            "task_id": "REQ-003",
            "target_deadline": "",
            "strategy": "deadline_first",
        })
        assert result["success"] is False
        assert "target_deadline" in result["message"] or "不能为空" in result["message"]

    def test_validate_schedule_data_detects_cycle(self, sample_data):
        # 修改 project_data 制造循环依赖
        from schedule_agent.project_context import project_context
        data = project_context.get_data()
        # 先备份原始依赖
        original_deps = {r.req_id: list(r.dependencies) for r in data.requirements}
        # 制造循环：REQ-001 依赖 REQ-002，REQ-002 依赖 REQ-001
        for req in data.requirements:
            if req.req_id == "REQ-001":
                req.dependencies = ["REQ-002"]
            elif req.req_id == "REQ-002":
                req.dependencies = ["REQ-001"]
        result = validate_schedule_data_tool.invoke({})
        # 恢复原始依赖
        for req in data.requirements:
            req.dependencies = original_deps.get(req.req_id, [])
        assert result["valid"] is False
        assert any("循环依赖" in e for e in result["errors"])

    def test_check_person_vacation_feasibility(self, sample_data):
        """测试人员休假可行性分析"""
        # 先设置 baseline
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试迭代"})

        result = check_person_vacation_feasibility.invoke({
            "person": "张三",
            "start_date": "2026-05-11",
            "end_date": "2026-05-15",
            "strategy": "deadline_first",
        })

        assert result["success"] is True
        assert "comparison" in result
        assert result["change_summary"] is not None

    def test_check_requirement_deadline_feasibility(self, sample_data):
        """测试需求 deadline 可行性分析"""
        result = check_requirement_deadline_feasibility.invoke({
            "req_id": "REQ-001",
            "target_deadline": "2026-05-15",
            "strategy": "deadline_first",
        })

        assert result["success"] is True
        assert "delay_status" in result
        assert result["req_id"] == "REQ-001"

    def test_check_assignment_feasibility(self, sample_data):
        """测试指定人员分配可行性分析"""
        # 先设置 baseline
        run_schedule_tool.invoke({"strategy": "deadline_first"})
        set_baseline_schedule_tool.invoke({"iteration_name": "测试迭代"})

        result = check_assignment_feasibility.invoke({
            "req_id": "REQ-001",
            "frontend_assignee": "张三",
            "strategy": "deadline_first",
        })

        assert result["success"] is True
        assert result["req_id"] == "REQ-001"
        assert result["assignment"]["frontend_assignee"] == "张三"
        assert "delay_status" in result

    def test_check_assignment_feasibility_invalid_person(self, sample_data):
        """测试指定不存在的人员"""
        result = check_assignment_feasibility.invoke({
            "req_id": "REQ-001",
            "backend_assignee": "不存在的人",
            "strategy": "deadline_first",
        })

        assert result["success"] is True  # 工具本身成功
        assert result["delay_status"]["unscheduled_subtasks"] > 0
