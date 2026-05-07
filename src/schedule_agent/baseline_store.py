from .sqlite_store import (
    save_baseline_to_db,
    load_current_baseline_from_db,
    clear_current_baseline,
    get_db_path,
)


def save_baseline(project_data, baseline_result, baseline_meta, path=None):
    """保存 baseline（兼容层，底层使用 SQLite）"""
    iteration_id = save_baseline_to_db(project_data, baseline_result, baseline_meta)
    db_path = get_db_path()
    return f"sqlite://{db_path}#iteration_id={iteration_id}"


def load_baseline(path=None):
    """加载 baseline（兼容层，底层使用 SQLite）"""
    return load_current_baseline_from_db()


def clear_baseline(path=None):
    """清空 baseline（兼容层，底层使用 SQLite）"""
    clear_current_baseline()
