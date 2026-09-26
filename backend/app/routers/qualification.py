"""人员资质接口：维护培训与持证台账，覆盖登记、预警筛选、岗位汇总与导出。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.qualification import QualificationService

router = APIRouter(prefix="/api/qualification", tags=["人员资质"])

service = QualificationService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按姓名、人员编号或证书名称检索"),
    status: str | None = Query(default=None, description="有效、临期预警、已过期"),
    position: str | None = Query(default=None, description="按岗位过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字、岗位与预警状态过滤人员资质列表；预警状态按当天日期动态计算。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, position=position, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary() -> dict[str, Any]:
    """按岗位汇总持证情况，并返回预警口径说明，供页面展示。"""
    return service.summary()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出人员资质清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "qualification", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条人员资质明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"人员资质 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记培训与证书；同人同证自动合并，过期证书保存「可承接」会被拦下并说明原因。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
