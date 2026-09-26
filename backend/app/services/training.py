"""培训记录业务规则：登记培训、考核结论流转与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "人员编号", "姓名", "培训项目", "培训日期"]
ALL_FIELDS = ["培训编号", "人员编号", "姓名", "培训项目", "培训日期", "培训学时", "考核结果", "培训状态"]
STATUS_ORDER = ["已登记", "已合格", "未合格"]
ACTION_RULES = {"考核合格": "已合格", "考核不合格": "未合格"}
NEGATIVE_ACTIONS = ["考核不合格"]


class TrainingService:
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
            rows = [
                row for row in rows
                if any(keyword in str(row.get(field, "")) for field in ("培训编号", "人员编号", "姓名", "培训项目"))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        trained_on = str(values.get("培训日期") or "").strip()
        try:
            datetime.strptime(trained_on, "%Y-%m-%d")
        except ValueError:
            return None, "培训日期 格式应为 YYYY-MM-DD"
        rows = store.rows(MODULE)
        if any(str(row.get("培训编号", "")).strip() == str(values.get("培训编号")).strip() for row in rows):
            return None, f"培训编号 {values.get('培训编号')} 已存在，培训记录不允许重复登记"
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, ""

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于培训记录可执行范围"
        target = ACTION_RULES[action]
        entry["status"] = target
        entry["考核结果"] = "合格" if target == "已合格" else "不合格"
        entry["培训状态"] = target
        entry["pending"] = target == STATUS_ORDER[0]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"
