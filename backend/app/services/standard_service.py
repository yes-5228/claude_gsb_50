"""限值标准版本管理: 版本时间轴解析与维护.

核心规则:
- 录入监测数据时, 按监测时间匹配当时生效的标准版本
  (effective_from <= measured_at 的最近一个版本; 早于所有版本时取最早版本);
- 判定结论(限值/超标倍数/等级)随数据快照入库, 标准调整不回溯改写历史;
- 已被监测数据引用的版本不允许删除, 也不允许调整等级/生效时间/限值,
  标准修订应新建版本并设定新的生效时间.
"""
from datetime import datetime

from ..domain.constants import STANDARD_GRADE_LABELS
from ..domain.standards import POLLUTANTS, default_limits
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Measurement, StandardLimit, StandardVersion
from ..models.base import iso

PERIODS = ("hourly", "daily")


# ---- 版本解析 ---------------------------------------------------------
def resolve_version(measured_at):
    """Return the standard version in effect at ``measured_at`` (None 表示未配置任何版本)."""
    if measured_at is None:
        measured_at = datetime.now()
    version = (
        StandardVersion.query.filter(StandardVersion.effective_from <= measured_at)
        .order_by(StandardVersion.effective_from.desc())
        .first()
    )
    if version is None:  # 监测时间早于所有版本: 沿用最早的一套标准
        version = StandardVersion.query.order_by(StandardVersion.effective_from.asc()).first()
    return version


def resolve_limits(measured_at):
    """(version, limits_map) used to evaluate data measured at the given time.

    未配置任何版本时返回 (None, None), 判定逻辑回退到内置默认限值.
    """
    version = resolve_version(measured_at)
    if version is None:
        return None, None
    return version, version.limits_map()


def _ordered_versions():
    return StandardVersion.query.order_by(
        StandardVersion.effective_from.asc(), StandardVersion.id.asc()
    ).all()


def _timeline(versions, now=None):
    """标注每个版本在时间轴上的状态与失效时间 (后一版本的生效时间)."""
    now = now or datetime.now()
    timeline = {}
    for index, version in enumerate(versions):
        effective_to = (
            versions[index + 1].effective_from if index + 1 < len(versions) else None
        )
        if version.effective_from > now:
            status = "pending"
        elif effective_to is None or effective_to > now:
            status = "current"
        else:
            status = "historical"
        timeline[version.id] = {"effective_to": effective_to, "status": status}
    return timeline


def _usage_counts(version_ids):
    if not version_ids:
        return {}
    rows = (
        db.session.query(Measurement.standard_version_id, db.func.count(Measurement.id))
        .filter(Measurement.standard_version_id.in_(version_ids))
        .group_by(Measurement.standard_version_id)
        .all()
    )
    return {version_id: int(count) for version_id, count in rows}


def _serialize(version, timeline=None, usage=None):
    payload = version.to_dict(include_limits=True)
    payload["limit_count"] = len(version.limits)
    if timeline and version.id in timeline:
        payload["effective_to"] = iso(timeline[version.id]["effective_to"])
        payload["status"] = timeline[version.id]["status"]
    else:
        payload["effective_to"] = None
        payload["status"] = "current"
    payload["usage_count"] = int((usage or {}).get(version.id, 0))
    payload["locked"] = payload["usage_count"] > 0
    return payload


def list_versions():
    """全部版本(按生效时间倒序), 含限值明细/时间轴状态/引用数据量."""
    versions = _ordered_versions()
    timeline = _timeline(versions)
    usage = _usage_counts([version.id for version in versions])
    items = [_serialize(version, timeline, usage) for version in reversed(versions)]
    current_id = next(
        (item["id"] for item in items if item["status"] == "current"), None
    )
    return {"items": items, "current_id": current_id, "total": len(items)}


def get_version(version_id):
    version = db.session.get(StandardVersion, version_id)
    if version is None:
        raise NotFoundError("标准版本不存在: id=%s" % version_id)
    return version


def version_detail(version):
    timeline = _timeline(_ordered_versions())
    usage = _usage_counts([version.id])
    return _serialize(version, timeline, usage)


def resolve_payload(measured_at):
    """供录入表单展示: 某监测时间适用的标准版本及其限值."""
    version = resolve_version(measured_at)
    if version is None:
        return {
            "version": None,
            "limits": default_limits(),
            "fallback": True,
            "message": "尚未配置标准版本, 当前按内置默认限值判定",
        }
    return {
        "version": version_detail(version),
        "limits": version.limits_map(),
        "fallback": False,
        "message": None,
    }


# ---- 版本维护 ---------------------------------------------------------
def _validate_limits(limits):
    """校验并规范化限值条目, 返回 [(pollutant, period, value, unit)]."""
    if not isinstance(limits, list) or not limits:
        raise ValidationError("至少需要配置一条限值", fields={"limits": "empty"})
    if len(limits) > len(POLLUTANTS) * len(PERIODS):
        raise ValidationError(
            "限值条目超出因子×周期组合上限", fields={"limits": "too_many"}
        )
    cleaned, seen = [], set()
    for item in limits:
        if not isinstance(item, dict):
            raise ValidationError("限值条目不合法", fields={"limits": "invalid"})
        pollutant = str(item.get("pollutant") or "").upper()
        meta = POLLUTANTS.get(pollutant)
        if meta is None:
            raise ValidationError(
                "未知监测因子: %s" % item.get("pollutant"),
                fields={"limits": "unknown_pollutant"},
            )
        period = str(item.get("period") or "")
        if period not in PERIODS:
            raise ValidationError(
                "%s 的数据周期不合法: %s" % (meta["label"], period or "空"),
                fields={"limits": "unknown_period"},
            )
        key = (pollutant, period)
        if key in seen:
            raise ValidationError(
                "%s %s 的限值重复配置" % (meta["label"], period),
                fields={"limits": "duplicated"},
            )
        seen.add(key)
        try:
            value = float(item.get("limit_value"))
        except (TypeError, ValueError):
            raise ValidationError(
                "%s 的限值必须为数字" % meta["label"], fields={"limits": "invalid_number"}
            )
        if value <= 0:
            raise ValidationError(
                "%s 的限值必须大于 0" % meta["label"], fields={"limits": "not_positive"}
            )
        cleaned.append((pollutant, period, value, meta["unit"]))
    return cleaned


def _check_effective_from(effective_from, exclude_id=None):
    query = StandardVersion.query.filter(StandardVersion.effective_from == effective_from)
    if exclude_id is not None:
        query = query.filter(StandardVersion.id != exclude_id)
    if query.first() is not None:
        raise ConflictError(
            "生效时间 %s 已被其他版本占用, 同一时刻只能有一个版本生效"
            % iso(effective_from)
        )


def _apply_limits(version, cleaned_limits):
    # 先显式删除旧条目并 flush, 避免唯一约束 (version, pollutant, period) 冲突
    for item in list(version.limits):
        db.session.delete(item)
    if version.limits:
        db.session.flush()
    version.limits = [
        StandardLimit(pollutant=pollutant, period=period, limit_value=value, unit=unit)
        for pollutant, period, value, unit in cleaned_limits
    ]


def create_version(data):
    """新建标准版本(含限值明细)."""
    name = (data.get("name") or "").strip()
    grade = data.get("grade") or "grade2"
    effective_from = data.get("effective_from")
    if not name:
        raise ValidationError("标准名称不能为空", fields={"name": "required"})
    if grade not in STANDARD_GRADE_LABELS:
        raise ValidationError(
            "标准等级取值不合法, 可选: %s" % ", ".join(STANDARD_GRADE_LABELS),
            fields={"grade": "unknown"},
        )
    if effective_from is None:
        raise ValidationError("生效时间不能为空", fields={"effective_from": "required"})
    _check_effective_from(effective_from)
    cleaned_limits = _validate_limits(data.get("limits"))

    version = StandardVersion(
        name=name,
        grade=grade,
        effective_from=effective_from,
        remark=(data.get("remark") or "").strip() or None,
    )
    _apply_limits(version, cleaned_limits)
    db.session.add(version)
    db.session.commit()
    return version


def _limits_changed(version, cleaned_limits):
    """对比提交的限值与版本现有限值是否一致."""
    current = {
        (item.pollutant, item.period): round(item.limit_value, 6) for item in version.limits
    }
    submitted = {
        (pollutant, period): round(value, 6)
        for pollutant, period, value, _unit in cleaned_limits
    }
    return current != submitted


def update_version(version, data):
    """更新版本. 已被数据引用的版本仅允许修改名称与备注."""
    locked = (
        db.session.query(Measurement.id)
        .filter(Measurement.standard_version_id == version.id)
        .first()
        is not None
    )

    name = (data.get("name") or "").strip()
    if not name:
        raise ValidationError("标准名称不能为空", fields={"name": "required"})

    wants_grade = data.get("grade")
    wants_effective = data.get("effective_from")
    cleaned_limits = _validate_limits(data["limits"]) if "limits" in data else None
    structural_change = (
        (wants_grade is not None and wants_grade != version.grade)
        or (wants_effective is not None and wants_effective != version.effective_from)
        or (cleaned_limits is not None and _limits_changed(version, cleaned_limits))
    )
    if locked and structural_change:
        raise ConflictError(
            "该版本已被监测数据引用, 为保证历史判定结论可追溯, 不允许调整等级、"
            "生效时间或限值; 如需修订标准请新建版本"
        )

    version.name = name
    version.remark = (data.get("remark") or "").strip() or None
    if wants_grade is not None:
        if wants_grade not in STANDARD_GRADE_LABELS:
            raise ValidationError(
                "标准等级取值不合法, 可选: %s" % ", ".join(STANDARD_GRADE_LABELS),
                fields={"grade": "unknown"},
            )
        version.grade = wants_grade
    if wants_effective is not None:
        _check_effective_from(wants_effective, exclude_id=version.id)
        version.effective_from = wants_effective
    if cleaned_limits is not None:
        _apply_limits(version, cleaned_limits)

    db.session.commit()
    return version


def delete_version(version):
    """删除未被数据引用的版本."""
    usage = (
        db.session.query(db.func.count(Measurement.id))
        .filter(Measurement.standard_version_id == version.id)
        .scalar()
    )
    if usage:
        raise ConflictError(
            "该版本已用于 %d 条监测数据的判定, 删除会破坏历史结论的可追溯性, 不允许删除"
            % int(usage)
        )
    payload = version.to_dict()
    db.session.delete(version)
    db.session.commit()
    return payload


# ---- 引导 -------------------------------------------------------------
def ensure_default_versions():
    """首次启动时把内置默认限值落库为一个标准版本 (幂等)."""
    if StandardVersion.query.first() is not None:
        return None
    version = StandardVersion(
        name="GB 3095-2012 环境空气质量标准",
        grade="grade2",
        effective_from=datetime(2016, 1, 1, 0, 0),
        remark="系统初始化默认版本, 限值取自 GB 3095-2012 二级浓度限值",
    )
    _apply_limits(
        version,
        [
            (code, period, value, meta["unit"])
            for code, meta in POLLUTANTS.items()
            for period, value in meta["limits"].items()
            if value is not None
        ],
    )
    db.session.add(version)
    db.session.commit()
    return version
