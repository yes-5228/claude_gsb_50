"""元数据与健康检查 API."""
from datetime import date, datetime, timedelta

from flask import Blueprint, current_app

from ..domain.constants import (
    DATA_SOURCE_LABELS,
    EXCEEDANCE_LEVEL_LABELS,
    EXCEEDANCE_STATUS_LABELS,
    PERIOD_LABELS,
    STATION_STATUS_LABELS,
    STATION_TYPE_LABELS,
    options_payload,
)
from ..domain.standards import POLLUTANTS
from ..extensions import db
from ..services import exceedance_service, query_service, standard_service, station_service

bp = Blueprint("meta", __name__)


def _current_policy(now=None):
    """Display name of the currently effective standard version."""
    version = standard_service.current_version(now=now)
    if version is None:
        return current_app.config["LIMIT_POLICY"]
    return "%s(%s)" % (version.name, version.to_ref()["grade_label"])


@bp.get("/health")
def health():
    database = "ok"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive
        database = "error: %s" % exc
    current = standard_service.current_version()
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "time": datetime.now().isoformat(timespec="seconds"),
        "timezone": current_app.config["TIMEZONE"],
        "limit_policy": _current_policy(),
        "current_standard": current.to_ref() if current else None,
    }


@bp.get("/pollutants")
def pollutants():
    """监测因子清单; limits 取自当前有效的标准版本, 供录入表单默认提示."""
    current = standard_service.current_version()
    limit_map = current.limit_map() if current else {}
    items = []
    for item in POLLUTANTS.values():
        row = dict(item)
        row["limits"] = {
            period: limit_map.get((item["code"], period)) for period in PERIOD_LABELS
        }
        items.append(row)
    return {
        "items": items,
        "policy": _current_policy(),
        "current_version": current.to_ref() if current else None,
        "periods": [{"value": key, "label": label} for key, label in PERIOD_LABELS.items()],
    }


@bp.get("/options")
def options():
    payload = options_payload()
    payload["stations"] = station_service.option_list()
    payload["areas"] = station_service.area_list()
    return payload


@bp.get("/overview")
def overview():
    """首页概览: 台账规模 / 数据量 / 超标待办 / 近 7 日趋势."""
    today = date.today()
    trend_args = {
        "group_by": "day",
        "metric": "count",
        "date_from": (today - timedelta(days=6)).isoformat(),
    }
    trend = query_service.statistics(trend_args)
    filters = query_service.parse_filters({})

    pending_args = {"status": "pending"}
    pending_records = (
        exceedance_service.exceedance_query({**pending_args, "order": "desc"})
        .limit(5)
        .all()
    )
    return {
        "stations": station_service.metadata_summary(),
        "measurements": query_service.summary(filters),
        "exceedances": exceedance_service.summary({}),
        "pending_exceedances": [record.to_dict() for record in pending_records],
        "trend": trend,
        "labels": {
            "station_status": STATION_STATUS_LABELS,
            "station_type": STATION_TYPE_LABELS,
            "exceedance_status": EXCEEDANCE_STATUS_LABELS,
            "exceedance_level": EXCEEDANCE_LEVEL_LABELS,
            "data_source": DATA_SOURCE_LABELS,
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
