"""监测数据录入业务逻辑 (含超标自动判定).

判定所依据的限值标准按监测时间从版本库中解析 (standard_service.require_version),
限值与版本指针随数据一并快照, 标准版本后续调整不影响已入库数据的判定结论。
"""
from datetime import datetime

from ..domain import exceedance_rules
from ..domain.standards import get_pollutant
from ..errors import ConflictError, NotFoundError, ValidationError
from ..extensions import db
from ..models import Exceedance, Measurement, Station
from . import standard_service


def get_measurement(measurement_id):
    measurement = db.session.get(Measurement, measurement_id)
    if measurement is None:
        raise NotFoundError("监测数据不存在: id=%s" % measurement_id)
    return measurement


def _evaluate_entry(entry, period, limits):
    """Validate one entry payload and evaluate it against the resolved limits."""
    pollutant = str(entry.get("pollutant", "")).upper()
    meta = get_pollutant(pollutant)
    if meta is None:
        raise ValidationError("未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"})
    try:
        value = float(entry.get("value"))
    except (TypeError, ValueError):
        raise ValidationError(
            "%s 监测值必须为数字" % meta["label"], fields={pollutant: "invalid_number"}
        )
    evaluation = exceedance_rules.evaluate(
        pollutant, period, value, limits.get((pollutant, period))
    )
    return pollutant, meta, value, evaluation


def preview_entries(period, entries, measured_at=None):
    """Dry-run evaluation for the entry form (no database writes).

    ``measured_at`` 决定适用哪一版限值标准; 缺省时按当前时间解析。
    """
    version = standard_service.require_version(measured_at or datetime.now())
    limits = version.limit_map()
    results = []
    for entry in entries:
        pollutant, meta, value, evaluation = _evaluate_entry(entry, period, limits)
        results.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )
    return {
        "period": period,
        "results": results,
        "summary": exceedance_rules.summarize(results),
        "standard_version": version.to_ref(),
    }


def _load_station(station_id):
    station = db.session.get(Station, station_id)
    if station is None:
        raise NotFoundError("监测点不存在: id=%s" % station_id)
    return station


def record_entries(station_id, measured_at, period, entries, data_source="manual",
                   recorder=None, remark=None, overwrite=False):
    """Persist one measured_at snapshot for a station.

    Duplicate (station, pollutant, period, measured_at) rows are reported back;
    when ``overwrite`` is true the existing row is refreshed instead.
    """
    station = _load_station(station_id)
    if not entries:
        raise ValidationError("至少需要录入一条监测数据", fields={"entries": "empty"})

    # 按监测时间匹配当时有效的限值标准, 判定结果随数据快照, 不随标准调整而变化
    version = standard_service.require_version(measured_at)
    limits = version.limit_map()

    existing = {
        row.pollutant: row
        for row in Measurement.query.filter_by(
            station_id=station.id, period=period, measured_at=measured_at
        ).all()
    }

    created, updated, exceeded, duplicates, evaluated = [], [], [], [], []
    seen = set()
    for entry in entries:
        pollutant = str(entry.get("pollutant", "")).upper()
        meta = get_pollutant(pollutant)
        if meta is None:
            raise ValidationError(
                "未知监测因子: %s" % entry.get("pollutant"), fields={"pollutant": "unknown"}
            )
        if pollutant in seen:
            raise ValidationError(
                "%s 在同一时刻重复提交" % meta["label"], fields={pollutant: "duplicated_in_batch"}
            )
        seen.add(pollutant)

        _, _, value, evaluation = _evaluate_entry(entry, period, limits)
        evaluated.append(
            {
                "pollutant": pollutant,
                "pollutant_label": meta["label"],
                "value": value,
                "unit": meta["unit"],
                **evaluation,
            }
        )

        record = existing.get(pollutant)
        if record is not None and not overwrite:
            duplicates.append(
                {
                    "pollutant": pollutant,
                    "pollutant_label": meta["label"],
                    "value": value,
                    "existing_id": record.id,
                    "message": "该时刻 %s 数据已存在" % meta["label"],
                }
            )
            continue

        is_new = record is None
        if is_new:
            record = Measurement(station_id=station.id, pollutant=pollutant, period=period,
                                 measured_at=measured_at)
            db.session.add(record)

        record.value = value
        record.unit = meta["unit"]
        record.limit_value = evaluation["limit"]
        record.exceed_ratio = evaluation["ratio"]
        record.is_exceeded = evaluation["exceeded"]
        record.data_source = data_source
        record.recorder = entry.get("recorder") or recorder
        record.remark = entry.get("remark") or remark
        record.standard_version_id = version.id

        _sync_exceedance(record, meta, evaluation, version)
        db.session.flush()
        (created if is_new else updated).append(record.to_dict(include_station=True))
        if evaluation["exceeded"]:
            exceeded.append(record.exceedance.to_dict() if record.exceedance else None)

    if not created and not updated and duplicates:
        raise ConflictError(
            "所选时刻已存在相同数据, 如需覆盖请勾选\"覆盖已有数据\": %s"
            % ", ".join(item["pollutant_label"] for item in duplicates)
        )

    db.session.commit()
    return {
        "station": station.to_option(),
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "period": period,
        "created": created,
        "updated": updated,
        "exceedances": [item for item in exceeded if item],
        "duplicates": duplicates,
        "evaluations": evaluated,
        "standard_version": version.to_ref(),
        "summary": {
            "created_count": len(created),
            "updated_count": len(updated),
            "exceeded_count": len([item for item in evaluated if item["exceeded"]]),
            "duplicate_count": len(duplicates),
        },
    }


def _sync_exceedance(record, meta, evaluation, version):
    """Create / refresh / drop the exceedance row attached to a measurement."""
    if evaluation["exceeded"]:
        if record.exceedance is None:
            record.exceedance = Exceedance(
                station_id=record.station_id,
                pollutant=record.pollutant,
                period=record.period,
                measured_at=record.measured_at,
                value=record.value,
                limit_value=evaluation["limit"],
                exceed_ratio=evaluation["ratio"],
                level=evaluation["level"],
                status="pending",
                standard_version_id=version.id,
            )
        else:
            record.exceedance.value = record.value
            record.exceedance.limit_value = evaluation["limit"]
            record.exceedance.exceed_ratio = evaluation["ratio"]
            record.exceedance.level = evaluation["level"]
            record.exceedance.measured_at = record.measured_at
            record.exceedance.standard_version_id = version.id
    elif record.exceedance is not None:
        db.session.delete(record.exceedance)


def delete_measurement(measurement):
    payload = measurement.to_dict()
    db.session.delete(measurement)
    db.session.commit()
    return payload
