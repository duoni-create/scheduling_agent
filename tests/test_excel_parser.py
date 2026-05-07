import os
import pytest
from datetime import date
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
        import pandas as pd
        path = tmp_path / "missing.xlsx"
        df = pd.DataFrame({"a": [1]})
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="需求表", index=False)
        with pytest.raises(ValueError, match="缺少必要 Sheet"):
            parse_excel(str(path))

    def test_invalid_work_hours(self, tmp_path):
        import pandas as pd
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
        import pandas as pd
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
