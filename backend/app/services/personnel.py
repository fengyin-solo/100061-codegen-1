"""人员资质业务规则：培训持证台账、到期判定口径与派发前资质核查都收在这里。

资质到期判定口径（对外公示，接口 /api/personnel/summary 会原样返回）：
1. 以证书「有效期至」为判定基准，按自然日比较，到期日当天仍视为有效。
2. 有效期至 早于 今天：已过期。
3. 有效期至 距今天不超过 30 天（含第 30 天）：预警（临期）。
4. 其余：正常。
5. 预警上限即到期日当天：超过预警上限（已过期）的证书，不允许保存「可承接」
   承接状态——登记、重复合并、恢复承接三个入口一律拦截并说明原因。
6. 同一人员编号 + 同一证书名称重复登记时，按最近一次（最晚）有效期合并为一
   条，台账里不允许出现两条同人同证的记录。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "personnel"
REQUIRED_FIELDS = ["人员编号", "姓名", "岗位", "证书名称", "有效期至"]
ALL_FIELDS = ["人员编号", "姓名", "岗位", "证书名称", "证书编号", "发证日期", "有效期至", "承接状态"]
WARNING_DAYS = 30
QUALIFICATION_STATUSES = ["正常", "预警", "已过期"]
UNDERTAKE_STATUSES = ["可承接", "暂停承接"]

RULE_TEXT = (
    "资质到期判定口径：以证书「有效期至」为基准按自然日比较，到期日当天仍有效；"
    f"有效期至早于今天为「已过期」；距今天 {WARNING_DAYS} 天内（含第 {WARNING_DAYS} 天）为「预警」；其余为「正常」。"
    "预警上限即到期日当天，超过预警上限（已过期）的证书不允许保存「可承接」承接状态；"
    "同一人员同一证书重复登记时按最近一次（最晚）有效期合并，只保留一条。"
)


def _parse_date(value: Any) -> date | None:
    """把 YYYY-MM-DD 字符串解析成日期；解析不了返回 None，由调用方决定怎么提示。"""
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _qualification_status(row: dict[str, Any], today: date) -> str:
    expiry = _parse_date(row.get("有效期至"))
    if expiry is None:
        return "已过期"
    if expiry < today:
        return "已过期"
    if (expiry - today).days <= WARNING_DAYS:
        return "预警"
    return "正常"


def _refresh(row: dict[str, Any], today: date) -> dict[str, Any]:
    """按当天日期重算派生字段并回写，保证筛选、概览与详情口径一致。"""
    expiry = _parse_date(row.get("有效期至"))
    status = _qualification_status(row, today)
    row["status"] = status
    row["资质状态"] = status
    row["剩余天数"] = (expiry - today).days if expiry is not None else ""
    row["pending"] = status != "正常"
    row["abnormal"] = status == "已过期"
    return row


def _refreshed_rows() -> list[dict[str, Any]]:
    today = date.today()
    return [_refresh(row, today) for row in store.rows(MODULE)]


def check_assignee(name: str) -> tuple[bool, str]:
    """派发检测任务前的资质核查：未登记、暂停承接、证书全部过期都要拦下并说明原因。"""
    person = str(name or "").strip()
    if not person:
        return False, "派发前请先指定承检人员"
    rows = [
        row for row in _refreshed_rows()
        if person in {str(row.get("姓名", "")).strip(), str(row.get("人员编号", "")).strip()}
    ]
    if not rows:
        return False, f"承检人员「{person}」尚未登记人员资质，不能派发，请先在人员资质台账登记"
    usable = [row for row in rows if row.get("承接状态") == "可承接"]
    if not usable:
        return False, f"承检人员「{person}」承接状态为暂停承接，不能派发"
    valid = [row for row in usable if row.get("资质状态") != "已过期"]
    if not valid:
        latest = max(str(row.get("有效期至", "")) for row in usable)
        return False, f"承检人员「{person}」的证书均已过期（最晚有效期至 {latest}），不能派发，请完成换证登记"
    expiring = [row for row in valid if row.get("资质状态") == "预警"]
    if expiring:
        notes = "、".join(f"《{row.get('证书名称')}》{row.get('有效期至')}到期" for row in expiring)
        return True, f"注意：「{person}」{notes}，请尽快安排续证"
    return True, ""


class PersonnelService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        position: str | None = None,
        warning: str | None = None,
        undertake: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = _refreshed_rows()
        if keyword:
            rows = [
                row for row in rows
                if any(keyword in str(row.get(field, "")) for field in ("人员编号", "姓名", "证书名称", "证书编号"))
            ]
        if position:
            rows = [row for row in rows if row.get("岗位") == position]
        if warning:
            rows = [row for row in rows if row.get("资质状态") == warning]
        if undertake:
            rows = [row for row in rows if row.get("承接状态") == undertake]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return _refresh(row, date.today())

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记证书资质；同人同证按最近一次有效期合并，过期证书不允许保存可承接状态。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        expiry = _parse_date(values.get("有效期至"))
        if expiry is None:
            return None, "有效期至 格式应为 YYYY-MM-DD"
        issue = str(values.get("发证日期") or "").strip()
        if issue and _parse_date(issue) is None:
            return None, "发证日期 格式应为 YYYY-MM-DD"
        undertake = str(values.get("承接状态") or "可承接").strip()
        if undertake not in UNDERTAKE_STATUSES:
            return None, f"承接状态 只能是：{'、'.join(UNDERTAKE_STATUSES)}"

        rows = store.rows(MODULE)
        person = str(values.get("人员编号")).strip()
        cert = str(values.get("证书名称")).strip()
        existing = next(
            (row for row in rows if str(row.get("人员编号", "")).strip() == person and str(row.get("证书名称", "")).strip() == cert),
            None,
        )
        if existing is not None:
            # 同人同证重复登记：按最近一次（最晚）有效期合并，只保留一条。
            snapshot = dict(existing)
            old_expiry = _parse_date(existing.get("有效期至"))
            if old_expiry is None or expiry >= old_expiry:
                for field in ALL_FIELDS:
                    if field in values and str(values.get(field) or "").strip():
                        existing[field] = str(values.get(field)).strip()
                # 承接状态只有显式提交时才覆盖，避免合并把暂停承接静默重置。
                if str(values.get("承接状态") or "").strip():
                    existing["承接状态"] = undertake
            message = f"同一人同一证书已存在，已按最近一次有效期合并为一条（有效期至 {existing.get('有效期至')}）"
            entry = existing
        else:
            snapshot = None
            entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            for field in ALL_FIELDS:
                entry[field] = str(values.get(field) or "").strip()
            entry["承接状态"] = undertake
            rows.append(entry)
            message = "人员资质已登记"

        today = date.today()
        _refresh(entry, today)
        if entry["资质状态"] == "已过期" and entry.get("承接状态") == "可承接":
            # 超过预警上限（已过期）不允许保存可承接状态：整笔登记拒绝，台账恢复原状。
            rejected_expiry = entry.get("有效期至")
            if snapshot is not None:
                existing.clear()
                existing.update(snapshot)
                _refresh(existing, today)
            else:
                rows.remove(entry)
            return None, f"证书有效期至 {rejected_expiry} 已过期（超过预警上限），不允许保存「可承接」承接状态"
        return entry, message

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"人员资质 {entry_id} 不存在或已归档"
        _refresh(entry, date.today())
        if action == "暂停承接":
            entry["承接状态"] = "暂停承接"
            return entry, f"人员资质 {entry_id} 已暂停承接"
        if action == "恢复承接":
            if entry["资质状态"] == "已过期":
                return None, f"证书有效期至 {entry.get('有效期至')} 已过期（超过预警上限），不允许恢复「可承接」承接状态"
            entry["承接状态"] = "可承接"
            return entry, f"人员资质 {entry_id} 已恢复承接"
        return None, f"动作「{action}」不属于人员资质可执行范围"

    def summary(self) -> dict[str, Any]:
        """按岗位汇总持证情况，并附上判定口径，口径写死在服务端保证各端一致。"""
        rows = _refreshed_rows()
        positions: dict[str, dict[str, Any]] = {}
        for row in rows:
            position = str(row.get("岗位") or "未设置")
            bucket = positions.setdefault(position, {
                "岗位": position, "人数": 0, "证书数": 0,
                "正常": 0, "预警": 0, "已过期": 0, "可承接": 0,
                "_people": set(),
            })
            bucket["_people"].add(str(row.get("人员编号", "")))
            bucket["证书数"] += 1
            bucket[str(row.get("资质状态"))] += 1
            if row.get("承接状态") == "可承接":
                bucket["可承接"] += 1
        position_rows = []
        for bucket in positions.values():
            bucket["人数"] = len(bucket.pop("_people"))
            position_rows.append(bucket)
        position_rows.sort(key=lambda item: str(item["岗位"]))
        total = {
            "证书数": len(rows),
            "正常": sum(1 for row in rows if row.get("资质状态") == "正常"),
            "预警": sum(1 for row in rows if row.get("资质状态") == "预警"),
            "已过期": sum(1 for row in rows if row.get("资质状态") == "已过期"),
            "可承接人员": len({str(row.get("人员编号")) for row in rows if row.get("承接状态") == "可承接" and row.get("资质状态") != "已过期"}),
        }
        return {"rule": RULE_TEXT, "warning_days": WARNING_DAYS, "total": total, "positions": position_rows}

    def dispatchable_options(self) -> list[dict[str, Any]]:
        """派发任务时可选的承检人员：承接状态可承接且证书未过期。"""
        options = []
        for row in _refreshed_rows():
            if row.get("承接状态") == "可承接" and row.get("资质状态") != "已过期":
                options.append({
                    "人员编号": row.get("人员编号"),
                    "姓名": row.get("姓名"),
                    "岗位": row.get("岗位"),
                    "证书名称": row.get("证书名称"),
                    "有效期至": row.get("有效期至"),
                    "资质状态": row.get("资质状态"),
                })
        return options
