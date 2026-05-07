import os
from datetime import date
import pandas as pd


def generate_sample_excel(output_path: str = "data/sample_schedule.xlsx") -> str:
    """生成示例排期 Excel 文件"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 需求表
    requirements_data = {
        "需求ID": ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005", "REQ-006"],
        "需求名称": ["首页改版", "用户中心", "支付模块", "消息推送", "数据分析", "权限系统"],
        "前端工时": [3.0, 2.0, 2.5, 1.5, 4.0, 2.0],
        "后端工时": [2.0, 3.0, 4.0, 1.0, 3.0, 2.5],
        "测试工时": [1.5, 1.0, 2.0, 0.5, 2.0, 1.0],
        "优先级": ["P0", "P1", "P0", "P2", "P1", "P2"],
        "Deadline": ["2026-05-20", "2026-05-25", "2026-05-18", "2026-05-30", "2026-05-22", "2026-05-28"],
        "依赖需求": ["", "REQ-001", "REQ-002", "", "REQ-003", ""],
        "状态": ["待排期", "待排期", "待排期", "待排期", "待排期", "待排期"],
        "备注": ["", "依赖首页改版完成", "", "", "", ""],
        "后端指定人员": ["", "", "", "", "", ""],
        "前端指定人员": ["张三", "", "", "", "", ""],
        "测试指定人员": ["", "", "", "", "", ""],
    }
    df_req = pd.DataFrame(requirements_data)

    # 资源表
    resources_data = {
        "姓名": ["张三", "李四", "王五", "赵六"],
        "角色": ["前端", "后端,测试", "前端,测试", "后端"],
        "可用起始日期": ["2026-05-01", "2026-05-01", "2026-05-01", "2026-05-01"],
        "可用结束日期": ["2026-06-30", "2026-06-30", "2026-06-30", "2026-06-30"],
        "每日工时": [8, 8, 8, 8],
        "休假日期": ["2026-05-12,2026-05-13", "", "", ""],
    }
    df_res = pd.DataFrame(resources_data)

    # 节假日表
    holidays_data = {
        "日期": ["2026-05-01", "2026-05-02", "2026-05-05"],
        "名称": ["劳动节", "劳动节调休", "劳动节调休上班"],
        "是否工作日": ["否", "否", "是"],
    }
    df_hol = pd.DataFrame(holidays_data)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_req.to_excel(writer, sheet_name="需求表", index=False)
        df_res.to_excel(writer, sheet_name="资源表", index=False)
        df_hol.to_excel(writer, sheet_name="节假日表", index=False)

    return output_path


if __name__ == "__main__":
    path = generate_sample_excel()
    print(f"示例 Excel 已生成: {path}")
