"""限值标准版本管理 API."""
from flask import Blueprint, request

from ..domain.constants import STANDARD_GRADE_LABELS
from ..services import standard_service
from ..utils.validation import Validator
from .helpers import json_payload

bp = Blueprint("standards", __name__)


def _validate_version(data, partial=False):
    """校验版本基础字段; 限值明细在 service 层校验."""
    validator = Validator(data)
    validator.text("name", "标准名称", required=True, max_length=120)
    validator.choice(
        "grade", "标准等级",
        choices=tuple(STANDARD_GRADE_LABELS.keys()),
        required=False,
        default=None,
    )
    validator.datetime_field("effective_from", "生效时间", required=not partial)
    validator.text("remark", "备注", required=False, max_length=500)
    cleaned = validator.raise_if_invalid("标准版本信息不合法")
    if not data.get("grade"):
        cleaned.pop("grade", None)
    if "effective_from" not in data:
        cleaned.pop("effective_from", None)
    return cleaned


@bp.get("/versions", strict_slashes=False)
def list_versions():
    return standard_service.list_versions()


@bp.post("/versions", strict_slashes=False)
def create_version():
    data = json_payload()
    cleaned = _validate_version(data)
    version = standard_service.create_version({**cleaned, "limits": data.get("limits")})
    return standard_service.version_detail(version), 201


@bp.get("/versions/<int:version_id>")
def get_version(version_id):
    return standard_service.version_detail(standard_service.get_version(version_id))


@bp.put("/versions/<int:version_id>")
def update_version(version_id):
    version = standard_service.get_version(version_id)
    data = json_payload()
    cleaned = _validate_version(data, partial=True)
    payload = {**cleaned}
    if "limits" in data:
        payload["limits"] = data.get("limits")
    return standard_service.version_detail(standard_service.update_version(version, payload))


@bp.delete("/versions/<int:version_id>")
def delete_version(version_id):
    version = standard_service.get_version(version_id)
    removed = standard_service.delete_version(version)
    return {"id": removed["id"], "deleted": True}


@bp.get("/resolve")
def resolve():
    """查询某个监测时间适用的标准版本与限值 (录入表单实时提示用)."""
    validator = Validator(request.args)
    measured_at = validator.datetime_field("measured_at", "监测时间", required=False)
    validator.raise_if_invalid()
    return standard_service.resolve_payload(measured_at)
