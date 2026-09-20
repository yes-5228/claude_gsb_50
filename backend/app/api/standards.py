"""限值标准版本管理 API."""
from datetime import datetime

from flask import Blueprint, request

from ..domain.constants import PERIOD_LABELS, STANDARD_GRADE_LABELS, STANDARD_STATUS_LABELS
from ..errors import ValidationError
from ..services import standard_service
from ..utils.validation import Validator, parse_datetime
from .helpers import json_payload

bp = Blueprint("standards", __name__)


def _validate_version(data, partial=False):
    validator = Validator(data)
    validator.text("code", "版本编码", required=not partial, max_length=48)
    validator.text("name", "标准名称", required=not partial, max_length=120)
    validator.choice(
        "grade", "标准等级",
        choices=tuple(STANDARD_GRADE_LABELS.keys()),
        required=False,
        default="level2",
    )
    validator.datetime_field("effective_from", "生效时间", required=not partial)
    validator.text("remark", "备注", required=False, max_length=500)
    cleaned = validator.raise_if_invalid("标准版本信息不合法")

    # 失效时间可显式置空(表示现行有效); 未提交该字段时保持原值
    if "effective_to" in data:
        raw_to = data.get("effective_to")
        if raw_to in (None, ""):
            cleaned["effective_to"] = None
        else:
            try:
                cleaned["effective_to"] = parse_datetime(raw_to, "失效时间")
            except ValidationError as exc:
                raise ValidationError("标准版本信息不合法", fields={"effective_to": exc.message})
    if "limits" in data:
        cleaned["limits"] = data.get("limits")

    if partial:
        cleaned = {key: value for key, value in cleaned.items() if key in data}
    return cleaned


@bp.get("/versions")
def list_versions():
    now = datetime.now()
    items = [
        version.to_dict(include_limits=True, now=now)
        for version in standard_service.list_versions()
    ]
    current = standard_service.current_version(now=now)
    return {
        "items": items,
        "current_version": current.to_ref() if current else None,
        "grades": [
            {"value": key, "label": label} for key, label in STANDARD_GRADE_LABELS.items()
        ],
        "statuses": [
            {"value": key, "label": label} for key, label in STANDARD_STATUS_LABELS.items()
        ],
        "periods": [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()],
    }


@bp.post("/versions")
def create_version():
    payload = _validate_version(json_payload())
    if "limits" not in payload:
        raise ValidationError("限值明细不能为空", fields={"limits": "required"})
    version = standard_service.create_version(payload)
    return version.to_dict(include_limits=True), 201


@bp.get("/versions/<int:version_id>")
def get_version(version_id):
    version = standard_service.get_version(version_id)
    payload = version.to_dict(include_limits=True)
    payload["reference_count"] = standard_service.reference_count(version)
    return payload


@bp.put("/versions/<int:version_id>")
def update_version(version_id):
    version = standard_service.get_version(version_id)
    payload = _validate_version(json_payload(), partial=True)
    return standard_service.update_version(version, payload).to_dict(include_limits=True)


@bp.delete("/versions/<int:version_id>")
def delete_version(version_id):
    version = standard_service.get_version(version_id)
    standard_service.delete_version(version)
    return {"id": version_id, "deleted": True}


@bp.get("/resolve")
def resolve():
    """查询某个监测时刻适用的标准版本 (录入表单实时提示用)."""
    raw = request.args.get("measured_at")
    measured_at = parse_datetime(raw, "监测时间") if raw else datetime.now()
    version = standard_service.resolve_version(measured_at)
    return {
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "version": version.to_dict(include_limits=True) if version else None,
    }
