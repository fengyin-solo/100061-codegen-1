"""人员资质接口：维护人员资质台账，覆盖登记证书、暂停承接、恢复承接等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.personnel import QUALIFICATION_STATUSES, UNDERTAKE_STATUSES, PersonnelService

router = APIRouter(prefix="/api/personnel", tags=["人员资质"])

service = PersonnelService()

LIST_FIELDS = ["人员编号", "姓名", "岗位", "证书名称", "证书编号", "发证日期", "有效期至", "承接状态"]


@router.get("/summary")
def summary() -> dict[str, Any]:
    """按岗位汇总持证情况，并返回资质到期判定口径原文。"""
    return service.summary()


@router.get("/options")
def dispatchable_options() -> dict[str, Any]:
    """派发检测任务时可选的承检人员清单：承接状态可承接且证书未过期。"""
    return {"items": service.dispatchable_options()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出人员资质清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "personnel", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按人员编号、姓名、证书名称检索"),
    position: str | None = Query(default=None, description="按岗位过滤"),
    warning: str | None = Query(default=None, description="正常、预警、已过期"),
    undertake: str | None = Query(default=None, description="可承接、暂停承接"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字、岗位、预警状态与承接状态过滤人员资质列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if warning and warning not in QUALIFICATION_STATUSES:
        raise HTTPException(status_code=400, detail=f"预警状态只能是：{'、'.join(QUALIFICATION_STATUSES)}")
    if undertake and undertake not in UNDERTAKE_STATUSES:
        raise HTTPException(status_code=400, detail=f"承接状态只能是：{'、'.join(UNDERTAKE_STATUSES)}")
    items, total = service.list_entries(keyword=keyword, position=position, warning=warning, undertake=undertake, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条人员资质明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"人员资质 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条人员资质；同人同证按最近一次有效期合并，过期证书不允许保存可承接状态。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条人员资质执行暂停承接、恢复承接；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
