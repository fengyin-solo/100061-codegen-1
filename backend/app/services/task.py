"""检测任务业务规则：状态流转、字段校验与筛选口径都收在这里。

派发任务的承检人员必须通过人员资质校验：资质未登记、证书已过期或暂停承接的
一律拦下并说明原因，不允许照常派发；其余动作与既有任务记录的行为保持不变。
"""
from __future__ import annotations

from typing import Any

from app.services.qualification import qualification_service
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

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测任务可执行范围"
        notice = ""
        if action == "派发任务":
            operator = str((values or {}).get("承检人员") or "").strip()
            if not operator:
                return None, "派发任务前请先填写承检人员，并确认其资质已登记且在有效期内"
            ok, message = qualification_service.check_assignable(operator)
            if not ok:
                return None, message
            entry["承检人员"] = operator
            notice = f"（{message}）"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测任务已{action}{notice}"
