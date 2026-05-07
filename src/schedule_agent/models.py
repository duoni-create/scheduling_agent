from datetime import date
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class Requirement(BaseModel):
    req_id: str = Field(..., min_length=1)
    name: str
    frontend_days: float = Field(default=0, ge=0)
    backend_days: float = Field(default=0, ge=0)
    test_days: float = Field(default=0, ge=0)
    priority: str
    deadline: date
    dependencies: list[str] = []
    status: str
    memo: str = ""

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v not in ("P0", "P1", "P2", "P3"):
            raise ValueError(f"优先级必须是 P0/P1/P2/P3，当前值: {v}")
        return v

    @field_validator("frontend_days", "backend_days", "test_days")
    @classmethod
    def validate_days(cls, v):
        if v < 0:
            raise ValueError("工时必须大于等于 0")
        if v % 0.5 != 0:
            raise ValueError("工时必须是 0.5 的倍数")
        return v

    @field_validator("req_id")
    @classmethod
    def validate_req_id(cls, v):
        if not v or not v.strip():
            raise ValueError("需求ID不能为空")
        return v


class Resource(BaseModel):
    name: str
    roles: list[str]
    available_start: date
    available_end: date
    daily_hours: int = Field(default=8)
    vacations: list[date] = []

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v):
        valid_roles = {"前端", "后端", "测试"}
        for role in v:
            if role not in valid_roles:
                raise ValueError(f"角色必须是 前端/后端/测试，当前值: {role}")
        return v

    @field_validator("daily_hours")
    @classmethod
    def validate_daily_hours(cls, v):
        if v not in (4, 8):
            raise ValueError("每日工时暂时只支持 4 或 8")
        return v

    @field_validator("available_end")
    @classmethod
    def validate_dates(cls, v, info):
        if "available_start" in info.data and v < info.data["available_start"]:
            raise ValueError("可用结束日期不能早于可用起始日期")
        return v


class Holiday(BaseModel):
    date: date
    name: str
    is_workday: bool


class ScheduleItem(BaseModel):
    req_id: str
    req_name: str
    subtask_type: str
    owner: Optional[str] = None
    start_date: Optional[date] = None
    start_half: Optional[str] = None
    end_date: Optional[date] = None
    end_half: Optional[str] = None
    days: float
    deadline: date
    delayed: bool = False
    delay_days: int = 0
    status: str
    reason: str = ""
    used_slots: list[dict] = []


class ScheduleResult(BaseModel):
    items: list[ScheduleItem]
    unscheduled_items: list[ScheduleItem]
    delayed_items: list[ScheduleItem]
    summary: dict
    strategy: str


class ProjectData(BaseModel):
    requirements: list[Requirement]
    resources: list[Resource]
    holidays: list[Holiday]
    current_result: Optional[ScheduleResult] = None
    current_strategy: Optional[str] = None


class AgentResponse(BaseModel):
    message: str
    tool_name: Optional[str] = None
    data: Optional[dict] = None
