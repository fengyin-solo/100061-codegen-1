"""人员资质业务规则：培训登记、证书有效期预警、同人同证合并与岗位汇总。

资质到期判定口径（列表筛选、岗位汇总、任务派发校验全部使用这一套，写死在这里）：
- 以证书到期日与服务器当天日期比较，预警窗口 30 天：
  - 到期日 < 当天：已过期（即超过预警上限），该记录不允许保存「可承接」的承接状态；
  - 当天 ≤ 到期日 ≤ 当天 + 30 天：临期预警，可继续承接，提示尽快复训换证；
  - 到期日 > 当天 + 30 天：有效。
- 预警状态在读取时按当天日期动态计算，不落库写死，刷新页面后口径保持一致。
- 同一人同一证书（人员编号 + 证书名称）重复登记时按最近一次有效期合并：
  到期日取两次登记中更晚的，其余字段以新提交为准，台账里只保留一条。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "qualification"
REQUIRED_FIELDS = ["人员编号", "姓名", "岗位", "证书名称", "证书到期日"]
EDITABLE_FIELDS = ["人员编号", "姓名", "岗位", "证书名称", "证书编号", "培训日期", "证书到期日", "承接状态"]
WARNING_DAYS = 30
ALERT_STATUSES = ["有效", "临期预警", "已过期"]
STATUS_ACTIVE = "可承接"
STATUS_SUSPENDED = "暂停承接"


def _today() -> date:
    """当前日期单独收口，方便以后接入测试时钟。"""
    return date.today()


def _parse_date(raw: Any) -> date | None:
    try:
        return date.fromisoformat(str(raw or "").strip())
    except ValueError:
        return None


def alert_status(expiry: date, today: date) -> str:
    """按统一口径把证书到期日折算成预警状态。"""
    if expiry < today:
        return "已过期"
    if (expiry - today).days <= WARNING_DAYS:
        return "临期预警"
    return "有效"


class QualificationService:
    def _decorate(self, row: dict[str, Any], today: date) -> dict[str, Any]:
        """读取时动态计算预警状态与剩余天数；返回副本，不改台账原文。"""
        entry = dict(row)
        expiry = _parse_date(row.get("证书到期日"))
        if expiry is None:
            entry["status"] = "已过期"
            entry["预警状态"] = "已过期"
            entry["剩余天数"] = None
            entry["pending"] = True
            entry["abnormal"] = True
            return entry
        status = alert_status(expiry, today)
        entry["status"] = status
        entry["预警状态"] = status
        entry["剩余天数"] = (expiry - today).days
        entry["pending"] = status != "有效"
        entry["abnormal"] = status == "已过期"
        return entry

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        position: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        today = _today()
        rows = [self._decorate(row, today) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if any(keyword in str(row.get(field, "")) for field in ("人员编号", "姓名", "证书名称", "证书编号"))
            ]
        if position:
            rows = [row for row in rows if position in str(row.get("岗位", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        return self._decorate(row, _today())

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记培训与证书；同人同证走合并，过期证书不允许保存「可承接」。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        expiry = _parse_date(values.get("证书到期日"))
        if expiry is None:
            return None, "证书到期日格式应为 YYYY-MM-DD，请检查后重新提交"
        trained_raw = str(values.get("培训日期") or "").strip()
        if trained_raw and _parse_date(trained_raw) is None:
            return None, "培训日期格式应为 YYYY-MM-DD，请检查后重新提交"
        undertake = str(values.get("承接状态") or "").strip() or STATUS_ACTIVE
        if undertake not in (STATUS_ACTIVE, STATUS_SUSPENDED):
            return None, f"承接状态只能是「{STATUS_ACTIVE}」或「{STATUS_SUSPENDED}」"

        person = str(values.get("人员编号") or "").strip()
        cert = str(values.get("证书名称") or "").strip()
        rows = store.rows(MODULE)
        existing = next(
            (
                row
                for row in rows
                if str(row.get("人员编号", "")).strip() == person and str(row.get("证书名称", "")).strip() == cert
            ),
            None,
        )
        # 同人同证重复登记时按最近一次有效期合并：到期日取两次中更晚的
        effective_expiry = expiry
        if existing is not None:
            old_expiry = _parse_date(existing.get("证书到期日"))
            effective_expiry = max(item for item in (old_expiry, expiry) if item is not None)
        if effective_expiry < _today() and undertake == STATUS_ACTIVE:
            return None, (
                f"证书已于 {effective_expiry.isoformat()} 到期，超过 {WARNING_DAYS} 天预警上限，"
                f"不允许保存「{STATUS_ACTIVE}」状态：请先完成复训换证，或将承接状态登记为「{STATUS_SUSPENDED}」"
            )

        if existing is not None:
            for field in EDITABLE_FIELDS:
                existing[field] = str(values.get(field) or "").strip()
            existing["证书到期日"] = effective_expiry.isoformat()
            existing["承接状态"] = undertake
            return existing, (
                f"{person} 的「{cert}」已按最近一次有效期合并到原记录"
                f"（到期日 {effective_expiry.isoformat()}），台账仍只保留一条"
            )

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in EDITABLE_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["承接状态"] = undertake
        rows.append(entry)
        decorated = self._decorate(entry, _today())
        entry["status"] = decorated["status"]
        entry["pending"] = decorated["pending"]
        entry["abnormal"] = decorated["abnormal"]
        return entry, "人员资质已登记"

    def summary(self) -> dict[str, Any]:
        """按岗位汇总持证情况，并附上预警口径说明，供页面展示。"""
        today = _today()
        rows = [self._decorate(row, today) for row in store.rows(MODULE)]
        cards = [
            {"label": "台账证书", "value": len(rows)},
            {"label": "有效证书", "value": sum(1 for row in rows if row["status"] == "有效")},
            {"label": "临期预警", "value": sum(1 for row in rows if row["status"] == "临期预警")},
            {"label": "已过期", "value": sum(1 for row in rows if row["status"] == "已过期")},
        ]
        buckets: dict[str, dict[str, Any]] = {}
        for row in rows:
            position = str(row.get("岗位") or "").strip() or "未填写岗位"
            bucket = buckets.setdefault(
                position,
                {"岗位": position, "人员": set(), "证书数": 0, "有效": 0, "临期预警": 0, "已过期": 0},
            )
            bucket["人员"].add(str(row.get("人员编号") or row.get("姓名") or ""))
            bucket["证书数"] += 1
            bucket[row["status"]] += 1
        positions = [
            {
                "岗位": bucket["岗位"],
                "持证人数": len(bucket["人员"]),
                "证书数": bucket["证书数"],
                "有效": bucket["有效"],
                "临期预警": bucket["临期预警"],
                "已过期": bucket["已过期"],
            }
            for bucket in buckets.values()
        ]
        positions.sort(key=lambda item: str(item["岗位"]))
        return {
            "cards": cards,
            "positions": positions,
            "rule": (
                f"预警口径：证书到期日前 {WARNING_DAYS} 天内为临期预警，早于当天为已过期；"
                f"已过期不允许保存「{STATUS_ACTIVE}」状态；同一人同一证书重复登记按最近一次有效期合并。"
            ),
        }

    def check_assignable(self, person: str) -> tuple[bool, str]:
        """任务派发前校验：资质未登记、证书已过期或暂停承接的人员一律拦下并说明原因。"""
        name = person.strip()
        today = _today()
        rows = [
            row
            for row in store.rows(MODULE)
            if name in {str(row.get("姓名", "")).strip(), str(row.get("人员编号", "")).strip()}
        ]
        if not rows:
            return False, f"承检人员「{name}」尚未登记人员资质，不能派发：请先在人员资质台账登记培训与证书"
        decorated = [(row, self._decorate(row, today)) for row in rows]
        usable = [(row, entry) for row, entry in decorated if entry["status"] != "已过期"]
        if not usable:
            detail = "、".join(f"{row.get('证书名称')}（{row.get('证书到期日')} 到期）" for row, _ in decorated)
            return False, f"承检人员「{name}」的证书已全部过期，不能派发：{detail}，请先完成复训换证"
        if not any(str(row.get("承接状态")) == STATUS_ACTIVE for row, _ in usable):
            return False, f"承检人员「{name}」的承接状态为「{STATUS_SUSPENDED}」，不能派发"
        warning = [entry for _, entry in usable if entry["status"] == "临期预警"]
        if warning:
            return True, (
                f"资质校验通过（提醒：{warning[0].get('证书名称')} 将于 "
                f"{warning[0].get('证书到期日')} 到期，已进入 {WARNING_DAYS} 天预警）"
            )
        return True, "资质校验通过"


qualification_service = QualificationService()
