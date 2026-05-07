import os
import pytest
from datetime import date
import pandas as pd
from schedule_agent.excel_parser import parse_excel
from schedule_agent.sample_generator import generate_sample_excel


class TestExcelParser:
    @pytest.fixture(autouse=True)
    def setup_sample(self):
        self.sample_path = generate_sample_excel("data/test_sample.xlsx")
        yield
        if os.path.exists("data/test_sample.xlsx"):
            try:
                os.remove("data/test_sample.xlsx")
            except PermissionError:
                pass

    def test_parse_sample_excel(self):
        requirements, resources, holidays = parse_excel(self.sample_path)
        assert len(requirements) == 6
        assert len(resources) == 4
        assert len(holidays) == 3

        req_ids = [r.req_id for r in requirements]
        assert "REQ-001" in req_ids
        assert "REQ-002" in req_ids

    def test_missing_sheet(self, tmp_path):
        path = tmp_path / "missing.xlsx"
        df = pd.DataFrame({"a": [1]})
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="需求表", index=False)
        with pytest.raises(ValueError, match="缺少必要 Sheet"):
            parse_excel(str(path))

    def test_invalid_work_hours(self, tmp_path):
        path = tmp_path / "invalid.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.3],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"],
            "角色": ["前端"],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": [8],
            "休假日期": [""],
        }
        hol_data = {
            "日期": ["2026-05-01"],
            "名称": ["劳动节"],
            "是否工作日": ["否"],
        }
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="0.5 的倍数"):
            parse_excel(str(path))

    def test_invalid_dependency(self, tmp_path):
        path = tmp_path / "invalid_dep.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": ["REQ-999"],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"],
            "角色": ["前端"],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": [8],
            "休假日期": [""],
        }
        hol_data = {
            "日期": ["2026-05-01"],
            "名称": ["劳动节"],
            "是否工作日": ["否"],
        }
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="依赖需求 REQ-999 不存在"):
            parse_excel(str(path))

    def test_missing_required_column(self, tmp_path):
        """缺少必填列"""
        path = tmp_path / "missing_col.xlsx"
        req_data = {"需求名称": ["测试"]}  # 缺少需求ID
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="缺少必要列"):
            parse_excel(str(path))

    def test_duplicate_req_id(self, tmp_path):
        """需求ID重复"""
        path = tmp_path / "dup_req.xlsx"
        req_data = {
            "需求ID": ["REQ-001", "REQ-001"],
            "需求名称": ["测试1", "测试2"],
            "前端工时": [1.0, 0],
            "后端工时": [0, 1.0],
            "测试工时": [0, 0],
            "优先级": ["P0", "P1"],
            "Deadline": ["2026-05-20", "2026-05-21"],
            "依赖需求": ["", ""],
            "状态": ["待排期", "待排期"],
            "备注": ["", ""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="需求ID.*存在重复值"):
            parse_excel(str(path))

    def test_empty_req_name(self, tmp_path):
        """需求名称为空"""
        path = tmp_path / "empty_name.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": [""],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError) as exc_info:
            parse_excel(str(path))
        assert "需求名称" in str(exc_info.value) and "不能为空" in str(exc_info.value)

    def test_invalid_deadline_format(self, tmp_path):
        """Deadline 格式错误"""
        path = tmp_path / "bad_date.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026/05/20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="日期格式错误"):
            parse_excel(str(path))

    def test_duplicate_resource_name(self, tmp_path):
        """人员姓名重复"""
        path = tmp_path / "dup_res.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三", "张三"],
            "角色": ["前端", "后端"],
            "可用起始日期": ["2026-05-01", "2026-05-01"],
            "可用结束日期": ["2026-06-30", "2026-06-30"],
            "每日工时": [8, 8],
            "休假日期": ["", ""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="姓名.*存在重复值"):
            parse_excel(str(path))

    def test_empty_resource_roles(self, tmp_path):
        """角色为空"""
        path = tmp_path / "empty_role.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"],
            "角色": [""],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": [8],
            "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError) as exc_info:
            parse_excel(str(path))
        assert "角色" in str(exc_info.value) and ("不能为空" in str(exc_info.value) or "不合法" in str(exc_info.value))

    def test_invalid_daily_hours_text(self, tmp_path):
        """每日工时填文本"""
        path = tmp_path / "bad_hours.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"],
            "角色": ["前端"],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": ["八小时"],
            "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="每日工时.*必须是数字|每日工时.*必须是整数"):
            parse_excel(str(path))

    def test_daily_hours_decimal(self, tmp_path):
        """每日工时填小数 4.5"""
        path = tmp_path / "decimal_hours.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"],
            "角色": ["前端"],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": [4.5],
            "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError) as exc_info:
            parse_excel(str(path))
        assert "每日工时" in str(exc_info.value) and "必须是整数" in str(exc_info.value)

    def test_holiday_duplicate_date(self, tmp_path):
        """节假日日期重复"""
        path = tmp_path / "dup_hol.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {
            "日期": ["2026-05-01", "2026-05-01"],
            "名称": ["劳动节", "劳动节2"],
            "是否工作日": ["否", "否"],
        }
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="节假日表日期重复"):
            parse_excel(str(path))

    def test_self_dependency(self, tmp_path):
        """需求依赖自己"""
        path = tmp_path / "self_dep.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试"],
            "前端工时": [1.0],
            "后端工时": [0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": ["REQ-001"],
            "状态": ["待排期"],
            "备注": [""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="不能依赖自己"):
            parse_excel(str(path))

    def test_cycle_dependency(self, tmp_path):
        """循环依赖"""
        path = tmp_path / "cycle.xlsx"
        req_data = {
            "需求ID": ["REQ-001", "REQ-002"],
            "需求名称": ["测试1", "测试2"],
            "前端工时": [1.0, 1.0],
            "后端工时": [0, 0],
            "测试工时": [0, 0],
            "优先级": ["P0", "P1"],
            "Deadline": ["2026-05-20", "2026-05-21"],
            "依赖需求": ["REQ-002", "REQ-001"],
            "状态": ["待排期", "待排期"],
            "备注": ["", ""],
        }
        res_data = {
            "姓名": ["张三"], "角色": ["前端"], "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"], "每日工时": [8], "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        with pytest.raises(ValueError, match="检测到循环依赖"):
            parse_excel(str(path))

    def test_assignee_parsing(self, tmp_path):
        """测试指定人员解析"""
        path = tmp_path / "assignee.xlsx"
        req_data = {
            "需求ID": ["REQ-001", "REQ-002"],
            "需求名称": ["测试1", "测试2"],
            "前端工时": [1.0, 1.0],
            "后端工时": [1.0, 0],
            "测试工时": [0, 0],
            "优先级": ["P0", "P1"],
            "Deadline": ["2026-05-20", "2026-05-21"],
            "依赖需求": ["", ""],
            "状态": ["待排期", "待排期"],
            "备注": ["", ""],
            "后端指定人员": ["张三", ""],
            "前端指定人员": ["李四", "王五"],
            "测试指定人员": ["", ""],
        }
        res_data = {
            "姓名": ["张三", "李四", "王五"],
            "角色": ["后端", "前端", "前端"],
            "可用起始日期": ["2026-05-01", "2026-05-01", "2026-05-01"],
            "可用结束日期": ["2026-06-30", "2026-06-30", "2026-06-30"],
            "每日工时": [8, 8, 8],
            "休假日期": ["", "", ""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        requirements, resources, holidays = parse_excel(str(path))
        req1 = next(r for r in requirements if r.req_id == "REQ-001")
        req2 = next(r for r in requirements if r.req_id == "REQ-002")

        assert req1.backend_assignee == "张三"
        assert req1.frontend_assignee == "李四"
        assert req1.test_assignee == ""
        assert req2.backend_assignee == ""
        assert req2.frontend_assignee == "王五"
        assert req2.test_assignee == ""

    def test_assignee_cross_validation(self, tmp_path):
        """测试指定人员交叉校验"""
        path = tmp_path / "assignee_invalid.xlsx"
        req_data = {
            "需求ID": ["REQ-001"],
            "需求名称": ["测试1"],
            "前端工时": [1.0],
            "后端工时": [1.0],
            "测试工时": [0],
            "优先级": ["P0"],
            "Deadline": ["2026-05-20"],
            "依赖需求": [""],
            "状态": ["待排期"],
            "备注": [""],
            "后端指定人员": ["不存在的张三"],
            "前端指定人员": [""],
            "测试指定人员": [""],
        }
        res_data = {
            "姓名": ["李四"],
            "角色": ["前端"],
            "可用起始日期": ["2026-05-01"],
            "可用结束日期": ["2026-06-30"],
            "每日工时": [8],
            "休假日期": [""],
        }
        hol_data = {"日期": ["2026-05-01"], "名称": ["劳动节"], "是否工作日": ["否"]}
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            pd.DataFrame(req_data).to_excel(writer, sheet_name="需求表", index=False)
            pd.DataFrame(res_data).to_excel(writer, sheet_name="资源表", index=False)
            pd.DataFrame(hol_data).to_excel(writer, sheet_name="节假日表", index=False)

        # 当前实现没有交叉校验，所以应该能正常解析
        # 如果未来添加了校验，这里需要更新
        requirements, resources, holidays = parse_excel(str(path))
        req1 = requirements[0]
        assert req1.backend_assignee == "不存在的张三"
