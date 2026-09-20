"""限值标准版本管理: 版本维护、按监测时间解析适用版本.

设计约定:
- 同一时刻全局只有一个有效版本, 版本之间的生效区间不允许重叠;
- 录入监测数据时按监测时间匹配 ``effective_from <= measured_at < effective_to``
  的版本, 匹配结果与限值快照一并写入监测数据;
- 版本的修改/删除不回溯历史数据, 已被监测数据引用的版本禁止删除,
  保证历史判定结论与超标等级可追溯且保持不变。
"""
from datetime import datetime

from sqlalchemy import or_

from ..domain.standards import DEFAULT_VERSION, POLLUTANTS
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Measurement, StandardLimit, StandardVersion
from ..utils.validation import parse_datetime

PERIODS = ("hourly", "daily")


# ---- 解析 -----------------------------------------------------------------

def resolve_version(measured_at):
    """Return the version effective at ``measured_at`` (None when no match)."""
    if measured_at is None:
        return None
    return (
        StandardVersion.query.filter(StandardVersion.effective_from <= measured_at)
        .filter(
            or_(
                StandardVersion.effective_to.is_(None),
                StandardVersion.effective_to > measured_at,
            )
        )
        .order_by(StandardVersion.effective_from.desc(), StandardVersion.id.desc())
        .first()
    )


def require_version(measured_at):
    """Like :func:`resolve_version` but raises when no version covers the moment."""
    version = resolve_version(measured_at)
    if version is None:
        raise ValidationError(
            "监测时间 %s 不在任何限值标准的生效区间内, 请先在“限值标准”模块配置适用版本"
            % measured_at.strftime("%Y-%m-%d %H:%M"),
            fields={"measured_at": "no_applicable_standard"},
        )
    return version


def current_version(now=None):
    return resolve_version(now or datetime.now())


# ---- 查询 -----------------------------------------------------------------

def list_versions():
    """All versions ordered by effective window (newest first)."""
    return (
        StandardVersion.query.order_by(
            StandardVersion.effective_from.desc(), StandardVersion.id.desc()
        ).all()
    )


def get_version(version_id):
    version = db.session.get(StandardVersion, version_id)
    if version is None:
        raise NotFoundError("限值标准版本不存在: id=%s" % version_id)
    return version


def reference_count(version):
    """How many measurements were judged against this version."""
    return Measurement.query.filter_by(standard_version_id=version.id).count()


# ---- 维护 -----------------------------------------------------------------

def _validate_window(effective_from, effective_to, exclude_id=None):
    if effective_to is not None and effective_to <= effective_from:
        raise ValidationError(
            "失效时间必须晚于生效时间", fields={"effective_to": "range_invalid"}
        )
    query = StandardVersion.query
    if exclude_id is not None:
        query = query.filter(StandardVersion.id != exclude_id)
    for other in query.all():
        other_end = other.effective_to or datetime.max
        self_end = effective_to or datetime.max
        if other.effective_from < self_end and effective_from < other_end:
            raise ConflictError(
                "生效区间与已有版本「%s」(%s ~ %s)重叠, 同一时刻只能有一个有效版本"
                % (
                    other.name,
                    other.effective_from.strftime("%Y-%m-%d %H:%M"),
                    other.effective_to.strftime("%Y-%m-%d %H:%M")
                    if other.effective_to
                    else "至今",
                )
            )


def _chain_open_predecessor(effective_from, effective_to):
    """开放结尾的新版本自动衔接前序版本: 前序版本失效时间 = 新版本生效时间.

    仅处理“现行版本(无截止时间)被新的长期版本接替”的场景; 其余重叠
    (如插入临时区间) 仍按冲突处理, 由调用方显式调整。
    """
    if effective_to is not None:
        return None
    predecessor = (
        StandardVersion.query.filter(StandardVersion.effective_to.is_(None))
        .filter(StandardVersion.effective_from < effective_from)
        .order_by(StandardVersion.effective_from.desc())
        .first()
    )
    if predecessor is not None:
        predecessor.effective_to = effective_from
    return predecessor


def _validate_limits(limits):
    """Normalise the limits payload into {(pollutant, period): value|None}."""
    if not isinstance(limits, dict) or not limits:
        raise ValidationError("限值明细不能为空", fields={"limits": "empty"})
    normalised = {}
    errors = {}
    for code in POLLUTANTS:
        raw = limits.get(code)
        if raw is None:
            raw = {}
        if not isinstance(raw, dict):
            errors[code] = "限值格式不合法"
            continue
        for period in PERIODS:
            value = raw.get(period)
            if value in (None, ""):
                normalised[(code, period)] = None  # 不设限值
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                errors["%s.%s" % (code, period)] = "限值必须是数字"
                continue
            if number <= 0:
                errors["%s.%s" % (code, period)] = "限值必须大于 0"
                continue
            normalised[(code, period)] = number
    unknown = [key for key in limits if str(key).upper() not in POLLUTANTS]
    if unknown:
        errors["limits"] = "未知监测因子: %s" % ", ".join(sorted(unknown))
    if errors:
        raise ValidationError("限值明细不合法", fields=errors)
    if not any(value is not None for value in normalised.values()):
        raise ValidationError("至少需要为一个因子设置限值", fields={"limits": "empty"})
    return normalised


def _apply_limits(version, normalised):
    version.limits = [
        StandardLimit(pollutant=code, period=period, limit_value=value)
        for (code, period), value in sorted(normalised.items())
    ]


def create_version(payload):
    """Create a standard version together with its limit rows."""
    code = (payload.get("code") or "").strip()
    if StandardVersion.query.filter_by(code=code).first():
        raise ConflictError("版本编码已存在: %s" % code)
    _chain_open_predecessor(payload["effective_from"], payload.get("effective_to"))
    _validate_window(payload["effective_from"], payload.get("effective_to"))
    normalised = _validate_limits(payload.get("limits"))

    version = StandardVersion(
        code=code,
        name=payload["name"],
        grade=payload.get("grade") or "level2",
        effective_from=payload["effective_from"],
        effective_to=payload.get("effective_to"),
        remark=payload.get("remark"),
    )
    _apply_limits(version, normalised)
    db.session.add(version)
    db.session.commit()
    return version


def update_version(version, payload):
    """Update a version. 历史监测数据已快照判定结果, 此处修改只影响之后的录入。"""
    if "code" in payload and payload["code"] != version.code:
        existing = StandardVersion.query.filter_by(code=payload["code"]).first()
        if existing is not None and existing.id != version.id:
            raise ConflictError("版本编码已存在: %s" % payload["code"])

    effective_from = payload.get("effective_from", version.effective_from)
    effective_to = payload.get("effective_to", version.effective_to)
    _validate_window(effective_from, effective_to, exclude_id=version.id)

    for field in ("code", "name", "grade", "remark"):
        if field in payload:
            setattr(version, field, payload[field])
    version.effective_from = effective_from
    version.effective_to = effective_to

    if "limits" in payload:
        normalised = _validate_limits(payload.get("limits"))
        version.limits.clear()
        db.session.flush()
        _apply_limits(version, normalised)

    db.session.commit()
    return version


def delete_version(version):
    """Delete a version; versions referenced by measurements are protected."""
    references = Measurement.query.filter_by(standard_version_id=version.id).count()
    if references:
        raise ConflictError(
            "该版本已被 %d 条监测数据引用, 删除会破坏历史判定结论的追溯, 不允许删除" % references
        )
    db.session.delete(version)
    db.session.commit()


# ---- 初始化与迁移 -----------------------------------------------------------

def ensure_default_versions():
    """Insert the built-in GB 3095-2012 二级 version when the table is empty."""
    if db.session.query(StandardVersion.id).first() is not None:
        return None
    version = StandardVersion(
        code=DEFAULT_VERSION["code"],
        name=DEFAULT_VERSION["name"],
        grade=DEFAULT_VERSION["grade"],
        effective_from=parse_datetime(DEFAULT_VERSION["effective_from"]),
        effective_to=None,
        remark=DEFAULT_VERSION["remark"],
    )
    normalised = {
        (code, period): value
        for code, periods in DEFAULT_VERSION["limits"].items()
        for period, value in periods.items()
    }
    _apply_limits(version, normalised)
    db.session.add(version)
    db.session.commit()
    return version


def backfill_measurement_versions():
    """Fill ``standard_version_id`` for legacy rows that predate versioning.

    只补齐版本指针, 不重算判定结论 — 历史记录的限值快照与超标等级保持不变。
    """
    versions = list_versions()
    if not versions:
        return 0
    updated = 0
    pending = Measurement.query.filter(Measurement.standard_version_id.is_(None)).all()
    for row in pending:
        version = resolve_version(row.measured_at)
        if version is not None:
            row.standard_version_id = version.id
            if row.exceedance is not None:
                row.exceedance.standard_version_id = version.id
            updated += 1
    if updated:
        db.session.commit()
    return updated
