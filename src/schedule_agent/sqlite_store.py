import json
import sqlite3
import os
from datetime import date, datetime
from .models import ProjectData, ScheduleResult, Requirement, Resource, Holiday, ScheduleItem


def get_db_path() -> str:
    """获取 SQLite 数据库路径"""
    from dotenv import load_dotenv
    load_dotenv()
    env_path = os.getenv("SCHEDULE_DB_PATH", "")
    if env_path:
        return env_path
    return "data/scheduling_agent.db"


def get_connection(db_path: str | None = None):
    """获取数据库连接"""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | None = None):
    """初始化数据库表"""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS iterations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_name TEXT,
                note TEXT,
                strategy TEXT,
                status TEXT NOT NULL DEFAULT 'current',
                confirmed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_id INTEGER NOT NULL,
                req_id TEXT NOT NULL,
                req_name TEXT NOT NULL,
                frontend_days REAL NOT NULL DEFAULT 0,
                backend_days REAL NOT NULL DEFAULT 0,
                test_days REAL NOT NULL DEFAULT 0,
                priority TEXT NOT NULL,
                deadline TEXT NOT NULL,
                dependencies_json TEXT,
                status TEXT,
                memo TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(iteration_id) REFERENCES iterations(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_id INTEGER NOT NULL,
                resource_name TEXT NOT NULL,
                roles_json TEXT NOT NULL,
                available_start TEXT NOT NULL,
                available_end TEXT NOT NULL,
                daily_hours INTEGER NOT NULL DEFAULT 8,
                vacations_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(iteration_id) REFERENCES iterations(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holidays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                name TEXT,
                is_workday INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(iteration_id) REFERENCES iterations(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                iteration_id INTEGER NOT NULL,
                schedule_type TEXT NOT NULL DEFAULT 'baseline',
                strategy TEXT NOT NULL,
                summary_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(iteration_id) REFERENCES iterations(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_run_id INTEGER NOT NULL,
                req_id TEXT NOT NULL,
                req_name TEXT NOT NULL,
                subtask_type TEXT NOT NULL,
                owner TEXT,
                start_date TEXT,
                start_half TEXT,
                end_date TEXT,
                end_half TEXT,
                days REAL NOT NULL,
                deadline TEXT NOT NULL,
                delayed INTEGER NOT NULL DEFAULT 0,
                delay_days INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                reason TEXT,
                used_slots_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(schedule_run_id) REFERENCES schedule_runs(id)
            )
        """)

        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now().isoformat()


def save_baseline_to_db(
    project_data: ProjectData,
    baseline_result: ScheduleResult,
    baseline_meta: dict,
    db_path: str | None = None,
) -> int:
    """保存 baseline 到 SQLite，返回 iteration_id"""
    init_db(db_path)
    conn = get_connection(db_path)
    now = _now_iso()

    try:
        cursor = conn.cursor()

        # 清空旧 current baseline
        cursor.execute("DELETE FROM schedule_items")
        cursor.execute("DELETE FROM schedule_runs")
        cursor.execute("DELETE FROM holidays")
        cursor.execute("DELETE FROM resources")
        cursor.execute("DELETE FROM requirements")
        cursor.execute("DELETE FROM iterations WHERE status = 'current'")

        # 插入 iteration
        cursor.execute("""
            INSERT INTO iterations
            (iteration_name, note, strategy, status, confirmed_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            baseline_meta.get("iteration_name", ""),
            baseline_meta.get("note", ""),
            baseline_meta.get("strategy", ""),
            "current",
            baseline_meta.get("confirmed_at", None),
            now,
            now,
        ))
        iteration_id = cursor.lastrowid

        # 插入 requirements
        for req in project_data.requirements:
            cursor.execute("""
                INSERT INTO requirements
                (iteration_id, req_id, req_name, frontend_days, backend_days, test_days,
                 priority, deadline, dependencies_json, status, memo, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                iteration_id,
                req.req_id,
                req.name,
                req.frontend_days,
                req.backend_days,
                req.test_days,
                req.priority,
                req.deadline.isoformat(),
                json.dumps(req.dependencies, ensure_ascii=False) if req.dependencies else None,
                req.status,
                req.memo,
                now,
                now,
            ))

        # 插入 resources
        for res in project_data.resources:
            cursor.execute("""
                INSERT INTO resources
                (iteration_id, resource_name, roles_json, available_start, available_end,
                 daily_hours, vacations_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                iteration_id,
                res.name,
                json.dumps(res.roles, ensure_ascii=False),
                res.available_start.isoformat(),
                res.available_end.isoformat(),
                res.daily_hours,
                json.dumps([d.isoformat() for d in res.vacations], ensure_ascii=False) if res.vacations else None,
                now,
                now,
            ))

        # 插入 holidays
        for hol in project_data.holidays:
            cursor.execute("""
                INSERT INTO holidays
                (iteration_id, date, name, is_workday, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                iteration_id,
                hol.date.isoformat(),
                hol.name,
                1 if hol.is_workday else 0,
                now,
                now,
            ))

        # 插入 schedule_run
        cursor.execute("""
            INSERT INTO schedule_runs
            (iteration_id, schedule_type, strategy, summary_json, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            iteration_id,
            "baseline",
            baseline_result.strategy,
            json.dumps(baseline_result.summary, ensure_ascii=False) if baseline_result.summary else None,
            now,
        ))
        schedule_run_id = cursor.lastrowid

        # 插入 schedule_items
        all_items = baseline_result.items + baseline_result.unscheduled_items
        for item in all_items:
            cursor.execute("""
                INSERT INTO schedule_items
                (schedule_run_id, req_id, req_name, subtask_type, owner,
                 start_date, start_half, end_date, end_half, days,
                 deadline, delayed, delay_days, status, reason,
                 used_slots_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                schedule_run_id,
                item.req_id,
                item.req_name,
                item.subtask_type,
                item.owner,
                item.start_date.isoformat() if item.start_date else None,
                item.start_half,
                item.end_date.isoformat() if item.end_date else None,
                item.end_half,
                item.days,
                item.deadline.isoformat(),
                1 if item.delayed else 0,
                item.delay_days,
                item.status,
                item.reason or None,
                json.dumps(item.used_slots, ensure_ascii=False) if item.used_slots else None,
                now,
            ))

        conn.commit()
        return iteration_id
    finally:
        conn.close()


def load_current_baseline_from_db(
    db_path: str | None = None,
) -> tuple[ProjectData, ScheduleResult, dict] | None:
    """从 SQLite 加载 current baseline"""
    init_db(db_path)
    conn = get_connection(db_path)

    try:
        cursor = conn.cursor()

        # 查询 current iteration
        cursor.execute("SELECT * FROM iterations WHERE status = 'current' LIMIT 1")
        iteration_row = cursor.fetchone()
        if not iteration_row:
            return None

        iteration_id = iteration_row["id"]

        # 还原 baseline_meta
        baseline_meta = {
            "iteration_name": iteration_row["iteration_name"] or "",
            "note": iteration_row["note"] or "",
            "strategy": iteration_row["strategy"] or "",
            "confirmed_at": iteration_row["confirmed_at"],
        }

        # 还原 requirements
        cursor.execute("SELECT * FROM requirements WHERE iteration_id = ?", (iteration_id,))
        req_rows = cursor.fetchall()
        requirements = []
        for row in req_rows:
            deps = json.loads(row["dependencies_json"]) if row["dependencies_json"] else []
            requirements.append(Requirement(
                req_id=row["req_id"],
                name=row["req_name"],
                frontend_days=row["frontend_days"],
                backend_days=row["backend_days"],
                test_days=row["test_days"],
                priority=row["priority"],
                deadline=date.fromisoformat(row["deadline"]),
                dependencies=deps,
                status=row["status"] or "待排期",
                memo=row["memo"] or "",
            ))

        # 还原 resources
        cursor.execute("SELECT * FROM resources WHERE iteration_id = ?", (iteration_id,))
        res_rows = cursor.fetchall()
        resources = []
        for row in res_rows:
            roles = json.loads(row["roles_json"]) if row["roles_json"] else []
            vacations = [date.fromisoformat(d) for d in json.loads(row["vacations_json"])] if row["vacations_json"] else []
            resources.append(Resource(
                name=row["resource_name"],
                roles=roles,
                available_start=date.fromisoformat(row["available_start"]),
                available_end=date.fromisoformat(row["available_end"]),
                daily_hours=row["daily_hours"],
                vacations=vacations,
            ))

        # 还原 holidays
        cursor.execute("SELECT * FROM holidays WHERE iteration_id = ?", (iteration_id,))
        hol_rows = cursor.fetchall()
        holidays = []
        for row in hol_rows:
            holidays.append(Holiday(
                date=date.fromisoformat(row["date"]),
                name=row["name"] or "",
                is_workday=bool(row["is_workday"]),
            ))

        # 还原 schedule_run
        cursor.execute("SELECT * FROM schedule_runs WHERE iteration_id = ? AND schedule_type = 'baseline' LIMIT 1", (iteration_id,))
        run_row = cursor.fetchone()
        if not run_row:
            return None

        schedule_run_id = run_row["id"]
        strategy = run_row["strategy"]
        summary = json.loads(run_row["summary_json"]) if run_row["summary_json"] else {}

        # 还原 schedule_items
        cursor.execute("SELECT * FROM schedule_items WHERE schedule_run_id = ?", (schedule_run_id,))
        item_rows = cursor.fetchall()

        items = []
        unscheduled_items = []
        delayed_items = []
        for row in item_rows:
            used_slots = json.loads(row["used_slots_json"]) if row["used_slots_json"] else []
            item = ScheduleItem(
                req_id=row["req_id"],
                req_name=row["req_name"],
                subtask_type=row["subtask_type"],
                owner=row["owner"],
                start_date=date.fromisoformat(row["start_date"]) if row["start_date"] else None,
                start_half=row["start_half"],
                end_date=date.fromisoformat(row["end_date"]) if row["end_date"] else None,
                end_half=row["end_half"],
                days=row["days"],
                deadline=date.fromisoformat(row["deadline"]),
                delayed=bool(row["delayed"]),
                delay_days=row["delay_days"],
                status=row["status"],
                reason=row["reason"] or "",
                used_slots=used_slots,
            )

            if item.status == "无法排期":
                unscheduled_items.append(item)
            else:
                items.append(item)
                if item.delayed:
                    delayed_items.append(item)

        project_data = ProjectData(
            requirements=requirements,
            resources=resources,
            holidays=holidays,
        )

        baseline_result = ScheduleResult(
            items=items,
            unscheduled_items=unscheduled_items,
            delayed_items=delayed_items,
            summary=summary,
            strategy=strategy,
        )

        return project_data, baseline_result, baseline_meta
    finally:
        conn.close()


def clear_current_baseline(db_path: str | None = None):
    """清空 current baseline"""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schedule_items")
        cursor.execute("DELETE FROM schedule_runs")
        cursor.execute("DELETE FROM holidays")
        cursor.execute("DELETE FROM resources")
        cursor.execute("DELETE FROM requirements")
        cursor.execute("DELETE FROM iterations WHERE status = 'current'")
        conn.commit()
    finally:
        conn.close()


def has_current_baseline(db_path: str | None = None) -> bool:
    """检查是否有 current baseline"""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM iterations WHERE status = 'current'")
        return cursor.fetchone()[0] > 0
    finally:
        conn.close()


def list_baselines(db_path: str | None = None) -> list[dict]:
    """列出所有 baseline"""
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, iteration_name, note, strategy, status, confirmed_at, created_at
            FROM iterations
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "iteration_name": row["iteration_name"],
                "note": row["note"],
                "strategy": row["strategy"],
                "status": row["status"],
                "confirmed_at": row["confirmed_at"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]
    finally:
        conn.close()
