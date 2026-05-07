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
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, start_date=date(2026, 5, 1))
        assert len(result.items) > 0
        assert result.summary["已排期子任务数"] > 0

    def test_no_weekend(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, start_date=date(2026, 5, 1))
        for item in result.items:
            if item.start_date:
                assert item.start_date.weekday() < 5, f"{item.start_date} 是周末"
            if item.end_date:
                assert item.end_date.weekday() < 5, f"{item.end_date} 是周末"

    def test_no_holiday(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, start_date=date(2026, 5, 1))
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
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 1))
        for item in result.items:
            if item.start_date:
                assert item.start_date != date(2026, 5, 6)
            if item.end_date:
                assert item.end_date != date(2026, 5, 6)

    def test_dependency_order(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, start_date=date(2026, 5, 1))
        req1_items = [i for i in result.items if i.req_id == "REQ-001"]
        req2_items = [i for i in result.items if i.req_id == "REQ-002"]

        if req1_items and req2_items:
            req1_latest = max(i.end_date for i in req1_items if i.end_date)
            req2_earliest = min(i.start_date for i in req2_items if i.start_date)
            assert req2_earliest > req1_latest, "依赖任务应该在前序任务完成后开始"

    def test_deadline_first(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, strategy="deadline_first", start_date=date(2026, 5, 1))
        assert result.strategy == "deadline_first"
        assert len(result.items) > 0

    def test_workload_balance(self, sample_requirements, sample_resources, sample_holidays):
        result = schedule_requirements(sample_requirements, sample_resources, sample_holidays, strategy="workload_balance", start_date=date(2026, 5, 1))
        assert result.strategy == "workload_balance"
        assert len(result.items) > 0

    def test_dependency_not_broken_by_deadline_sort(self):
        """测试：依赖任务不会被 deadline 排序打乱"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="基础模块", frontend_days=0, backend_days=3, test_days=0,
                priority="P2", deadline=date(2026, 5, 30), dependencies=[], status="待排期"
            ),
            Requirement(
                req_id="REQ-002", name="高级模块", frontend_days=0, backend_days=1, test_days=0,
                priority="P0", deadline=date(2026, 5, 15), dependencies=["REQ-001"], status="待排期"
            ),
        ]
        resources = [
            Resource(name="李四", roles=["后端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, strategy="deadline_first", start_date=date(2026, 5, 1))

        req1_items = [i for i in result.items if i.req_id == "REQ-001"]
        req2_items = [i for i in result.items if i.req_id == "REQ-002"]

        if req1_items and req2_items:
            req1_latest = max(i.end_date for i in req1_items if i.end_date)
            req2_earliest = min(i.start_date for i in req2_items if i.start_date)
            assert req2_earliest > req1_latest, f"REQ-002 应该在 REQ-001 之后开始，但 REQ-001 结束于 {req1_latest}，REQ-002 开始于 {req2_earliest}"

    def test_weekend_not_occupied(self):
        """测试：跨周末排期不会把周末错误标记为占用"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="长任务", frontend_days=3, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 8))  # 周五开始

        item = result.items[0]
        # 从 5-8(周五) 开始，3天前端 = 6个半天
        # 5-8 上午, 5-8 下午, 5-9 上午, 5-9 下午, 跳过周末, 5-12 上午, 5-12 下午
        # 应该结束于 5-12
        assert item.end_date == date(2026, 5, 12), f"期望结束于 2026-05-12，但实际结束于 {item.end_date}"

        # 验证周末没有被占用（通过为另一个任务排期来验证）
        requirements2 = [
            Requirement(
                req_id="REQ-002", name="另一个任务", frontend_days=1, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        result2 = schedule_requirements(requirements2, resources, holidays, start_date=date(2026, 5, 8))
        item2 = result2.items[0]
        # 如果周末被错误占用了，这个任务会被排到 5-13
        # 如果周末没被占用，应该从 5-8 开始
        assert item2.start_date == date(2026, 5, 8), f"期望 REQ-002 开始于 2026-05-08，但实际开始于 {item2.start_date}"

    def test_used_slots_no_weekend(self):
        """测试：跨周末排期时，used_slots 不包含周六和周日"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="跨周末任务", frontend_days=3, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 8))  # 周五

        item = result.items[0]
        assert item.used_slots, "used_slots 不应为空"
        for slot in item.used_slots:
            slot_date = date.fromisoformat(slot["date"])
            assert slot_date.weekday() < 5, f"used_slots 中包含周末日期: {slot_date}"

    def test_used_slots_count(self):
        """测试：used_slots 数量等于 days * 2"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="2天任务", frontend_days=2, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 1))

        item = result.items[0]
        expected_slots = int(item.days * 2)
        assert len(item.used_slots) == expected_slots, f"期望 used_slots 数量为 {expected_slots}，实际为 {len(item.used_slots)}"

    def test_daily_hours_4(self):
        """测试：daily_hours=4 的资源每天最多只出现一个 used_slot"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="半天任务", frontend_days=2, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期"
            ),
        ]
        resources = [
            Resource(
                name="张三", roles=["前端"], available_start=date(2026, 5, 1),
                available_end=date(2026, 6, 30), daily_hours=4
            ),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 1))

        item = result.items[0]
        # 统计每天出现的槽位数
        date_count = {}
        for slot in item.used_slots:
            d = slot["date"]
            date_count[d] = date_count.get(d, 0) + 1

        for d, count in date_count.items():
            assert count <= 1, f"daily_hours=4 的资源在 {d} 出现了 {count} 个槽位，应最多 1 个"

    def test_assignee_filtering(self):
        """测试指定人员过滤"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="指定人员测试", frontend_days=1, backend_days=1, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期",
                frontend_assignee="张三",
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="李四", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="王五", roles=["后端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 1))

        frontend_item = next(item for item in result.items if item.subtask_type == "前端")
        backend_item = next(item for item in result.items if item.subtask_type == "后端")

        # 前端应该分配给张三
        assert frontend_item.owner == "张三"
        # 后端没有指定，可以分配给王五
        assert backend_item.owner == "王五"

    def test_assignee_not_available(self):
        """测试指定人员不具备角色"""
        requirements = [
            Requirement(
                req_id="REQ-001", name="指定人员测试", frontend_days=1, backend_days=0, test_days=0,
                priority="P0", deadline=date(2026, 5, 20), dependencies=[], status="待排期",
                frontend_assignee="王五",
            ),
        ]
        resources = [
            Resource(name="张三", roles=["前端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
            Resource(name="王五", roles=["后端"], available_start=date(2026, 5, 1), available_end=date(2026, 6, 30)),
        ]
        holidays = []
        result = schedule_requirements(requirements, resources, holidays, start_date=date(2026, 5, 1))

        # 王五不具备前端角色，应该无法排期
        assert len(result.unscheduled_items) == 1
        assert result.unscheduled_items[0].subtask_type == "前端"
        assert "王五" in result.unscheduled_items[0].reason
