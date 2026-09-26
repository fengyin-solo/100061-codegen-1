"""检测任务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.personnel import check_assignee
from app.store import store

MODULE = "task"
REQUIRED_FIELDS = ["任务编号", "关联样品", "检测项目"]
STATUS_ORDER = ["待派发", "检测中", "待复核", "已完成"]
ACTION_RULES = {"派发任务": "检测中", "提交复核": "待复核", "确认完成": "已完成"}
NEGATIVE_ACTIONS = []


class TaskService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测任务可执行范围"
        note = ""
        if action == "派发任务":
            # 派发前核查承检人员资质：未登记、已过期、暂停承接一律拦下并说明原因。
            assignee = str((values or {}).get("承检人员") or entry.get("承检人员") or "").strip()
            allowed, note = check_assignee(assignee)
            if not allowed:
                return None, note
            entry["承检人员"] = assignee
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"检测任务已{action}"
        if note:
            message = f"{message}（{note}）"
        return entry, message
