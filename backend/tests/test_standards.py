"""限值标准版本管理: 版本维护、按监测时间匹配、历史结论保持不变."""
import copy
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Exceedance, Measurement, StandardVersion
from app.services import standard_service

FUTURE_LIMITS = {
    "PM25": {"daily": 60.0, "hourly": None},
    "PM10": {"daily": 120.0, "hourly": None},
    "SO2": {"daily": 120.0, "hourly": 400.0},
    "NO2": {"daily": 80.0, "hourly": 200.0},
    "CO": {"daily": 4.0, "hourly": 10.0},
    "O3": {"daily": 150.0, "hourly": 180.0},
}


def _future_version_payload(**overrides):
    payload = {
        "code": "GB3095-2012-L2-2027",
        "name": "GB 3095-2012 环境空气质量标准(2027 年修订)",
        "grade": "level2",
        "effective_from": "2027-01-01 00:00",
        "effective_to": None,
        "remark": "限值加严",
        "limits": copy.deepcopy(FUTURE_LIMITS),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def future_version(client):
    response = client.post("/api/standards/versions", json=_future_version_payload())
    assert response.status_code == 201
    return response.get_json()


# ---- 版本维护 ---------------------------------------------------------------


def test_default_version_is_seeded(client):
    body = client.get("/api/standards/versions").get_json()
    assert len(body["items"]) == 1
    version = body["items"][0]
    assert version["code"] == "GB3095-2012-L2"
    assert version["grade_label"] == "二级标准"
    assert version["status"] == "active"
    pm25 = next(item for item in version["limits"] if item["pollutant"] == "PM25")
    assert pm25["limits"] == {"hourly": None, "daily": 75.0}
    assert body["current_version"]["code"] == "GB3095-2012-L2"


def test_create_version_with_limits(client, future_version):
    assert future_version["status"] == "scheduled"
    pm25 = next(item for item in future_version["limits"] if item["pollutant"] == "PM25")
    assert pm25["limits"]["daily"] == 60.0

    body = client.get("/api/standards/versions").get_json()
    assert len(body["items"]) == 2
    # 现行版本仍是 2016 版, 且失效时间已自动衔接至新版本生效时间
    assert body["current_version"]["code"] == "GB3095-2012-L2"
    default = next(item for item in body["items"] if item["code"] == "GB3095-2012-L2")
    assert default["effective_to"].startswith("2027-01-01")


def test_create_version_rejects_overlapping_window(client):
    payload = _future_version_payload(
        code="GB3095-OVERLAP", effective_from="2020-01-01 00:00", effective_to="2030-01-01 00:00"
    )
    response = client.post("/api/standards/versions", json=payload)
    assert response.status_code == 409
    assert "重叠" in response.get_json()["error"]["message"]


def test_create_version_validates_payload(client):
    duplicated = client.post("/api/standards/versions", json=_future_version_payload(
        effective_from="2027-01-01 00:00",
    ))
    assert duplicated.status_code == 201
    again = client.post("/api/standards/versions", json=_future_version_payload(
        effective_from="2027-01-01 00:00",
    ))
    assert again.status_code == 409  # 版本编码唯一

    bad_limit = _future_version_payload(code="BAD-LIMIT", effective_from="2030-01-01 00:00")
    bad_limit["limits"]["PM25"]["daily"] = "abc"
    response = client.post("/api/standards/versions", json=bad_limit)
    assert response.status_code == 422

    negative = _future_version_payload(code="NEG-LIMIT", effective_from="2030-01-01 00:00")
    negative["limits"]["SO2"]["hourly"] = -1
    assert client.post("/api/standards/versions", json=negative).status_code == 422

    bad_window = _future_version_payload(
        code="BAD-WINDOW", effective_from="2030-06-01 00:00", effective_to="2030-01-01 00:00"
    )
    assert client.post("/api/standards/versions", json=bad_window).status_code == 422


def test_update_version_adjusts_window_and_limits(client, future_version):
    default = StandardVersion.query.filter_by(code="GB3095-2012-L2").one()
    response = client.put(
        "/api/standards/versions/%d" % default.id,
        json={"effective_to": "2027-01-01 00:00"},
    )
    assert response.status_code == 200
    assert response.get_json()["effective_to"].startswith("2027-01-01")

    # 修改未来版本限值
    limits = dict(FUTURE_LIMITS)
    limits["PM25"] = {"daily": 55.0, "hourly": None}
    response = client.put(
        "/api/standards/versions/%d" % future_version["id"], json={"limits": limits}
    )
    assert response.status_code == 200
    pm25 = next(
        item for item in response.get_json()["limits"] if item["pollutant"] == "PM25"
    )
    assert pm25["limits"]["daily"] == 55.0


def test_delete_unreferenced_version(client, future_version):
    response = client.delete("/api/standards/versions/%d" % future_version["id"])
    assert response.status_code == 200
    assert StandardVersion.query.filter_by(code="GB3095-2012-L2-2027").count() == 0


def test_resolve_endpoint_matches_measured_at(client, future_version):
    body = client.get("/api/standards/resolve?measured_at=2026-09-01 10:00").get_json()
    assert body["version"]["code"] == "GB3095-2012-L2"

    body = client.get("/api/standards/resolve?measured_at=2027-02-01 10:00").get_json()
    assert body["version"]["code"] == "GB3095-2012-L2-2027"

    body = client.get("/api/standards/resolve?measured_at=2010-01-01 00:00").get_json()
    assert body["version"] is None


# ---- 录入时按监测时间匹配限值 -------------------------------------------------


def test_entry_uses_version_effective_at_measured_at(client, station, future_version):
    """同一数值在不同时刻按当时有效的版本判定."""
    before = client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-12-31 23:00",
            "period": "daily",
            "entries": [{"pollutant": "PM25", "value": 70.0}],
        },
    )
    assert before.status_code == 201
    body = before.get_json()
    assert body["standard_version"]["code"] == "GB3095-2012-L2"
    assert body["summary"]["exceeded_count"] == 0  # 70 <= 75 (2016 版)

    after = client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2027-01-01 00:00",
            "period": "daily",
            "entries": [{"pollutant": "PM25", "value": 70.0}],
        },
    )
    assert after.status_code == 201
    body = after.get_json()
    assert body["standard_version"]["code"] == "GB3095-2012-L2-2027"
    assert body["summary"]["exceeded_count"] == 1  # 70 > 60 (2027 修订版)
    assert body["exceedances"][0]["level"] == "light"

    versions = {
        row.pollutant: row.standard_version.code
        for row in Measurement.query.order_by(Measurement.measured_at).all()
    }
    assert versions == {"PM25": "GB3095-2012-L2-2027"} or len(versions) == 1
    rows = Measurement.query.order_by(Measurement.measured_at).all()
    assert rows[0].standard_version.code == "GB3095-2012-L2"
    assert rows[1].standard_version.code == "GB3095-2012-L2-2027"


def test_entry_before_any_version_is_rejected(client, station):
    response = client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2010-06-01 08:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 100.0}],
        },
    )
    assert response.status_code == 422
    assert "生效区间" in response.get_json()["error"]["message"]
    assert Measurement.query.count() == 0


def test_preview_uses_version_at_measured_at(client, future_version):
    payload = {"period": "daily", "entries": [{"pollutant": "PM25", "value": 70.0}]}
    body = client.post("/api/measurements/preview", json=payload).get_json()
    assert body["results"][0]["limit"] == 75.0
    assert body["standard_version"]["code"] == "GB3095-2012-L2"

    payload["measured_at"] = "2027-03-01 00:00"
    body = client.post("/api/measurements/preview", json=payload).get_json()
    assert body["results"][0]["limit"] == 60.0
    assert body["results"][0]["exceeded"] is True
    assert body["standard_version"]["code"] == "GB3095-2012-L2-2027"
    assert Measurement.query.count() == 0  # 预览不写库


# ---- 标准调整后历史数据保持不变 ------------------------------------------------


def test_historical_conclusion_survives_limit_change(client, station):
    """修改标准限值后, 历史数据的判定结论与限值快照保持不变."""
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-01 00:00",
            "period": "daily",
            "entries": [{"pollutant": "PM25", "value": 70.0}],
        },
    )
    historical = Measurement.query.one()
    assert historical.is_exceeded is False
    assert historical.limit_value == 75.0

    # 标准加严: PM2.5 日均限值 75 -> 60
    default = StandardVersion.query.filter_by(code="GB3095-2012-L2").one()
    limits = {code: dict(periods) for code, periods in
              {item["pollutant"]: item["limits"] for item in default.limits_matrix()}.items()}
    limits["PM25"]["daily"] = 60.0
    response = client.put("/api/standards/versions/%d" % default.id, json={"limits": limits})
    assert response.status_code == 200

    # 历史数据判定结论不变
    db.session.expire_all()
    historical = Measurement.query.one()
    assert historical.is_exceeded is False
    assert historical.limit_value == 75.0
    assert historical.standard_version_id == default.id

    # 新录入的数据按新限值判定
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-02 00:00",
            "period": "daily",
            "entries": [{"pollutant": "PM25", "value": 70.0}],
        },
    )
    fresh = Measurement.query.filter_by(measured_at=datetime(2026, 9, 2)).one()
    assert fresh.is_exceeded is True
    assert fresh.limit_value == 60.0


def test_exceedance_level_survives_standard_change(client, station):
    """标准调整后, 历史超标记录的等级与限值快照保持不变."""
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-01 10:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 900.0}],
        },
    )
    exceedance = Exceedance.query.one()
    assert exceedance.level == "moderate"  # 900 / 500 = 1.8
    assert exceedance.limit_value == 500.0

    # 标准加严: SO2 小时限值 500 -> 300
    default = StandardVersion.query.filter_by(code="GB3095-2012-L2").one()
    limits = {item["pollutant"]: dict(item["limits"]) for item in default.limits_matrix()}
    limits["SO2"]["hourly"] = 300.0
    client.put("/api/standards/versions/%d" % default.id, json={"limits": limits})

    db.session.expire_all()
    exceedance = Exceedance.query.one()
    assert exceedance.level == "moderate"  # 等级保持
    assert exceedance.limit_value == 500.0  # 限值快照保持
    assert exceedance.standard_version_id == default.id

    # 新数据按新限值重新分级: 900 / 300 = 3.0 -> 重度
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-02 10:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 900.0}],
        },
    )
    levels = [row.level for row in Exceedance.query.order_by(Exceedance.measured_at).all()]
    assert levels == ["moderate", "severe"]


def test_new_version_does_not_rewrite_history(client, station, future_version):
    """发布未来生效的新版本后, 历史数据及其超标记录保持原判定."""
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-01 00:00",
            "period": "daily",
            "entries": [{"pollutant": "PM25", "value": 70.0}],
        },
    )
    row = Measurement.query.one()
    assert row.is_exceeded is False

    # 编辑未来版本(触发一次“标准调整”)后历史数据仍不变
    client.put(
        "/api/standards/versions/%d" % future_version["id"],
        json={"remark": "调整说明"},
    )
    db.session.expire_all()
    row = Measurement.query.one()
    assert row.is_exceeded is False
    assert row.limit_value == 75.0
    assert row.standard_version.code == "GB3095-2012-L2"


def test_delete_referenced_version_is_rejected(client, station):
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-01 10:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 100.0}],
        },
    )
    default = StandardVersion.query.filter_by(code="GB3095-2012-L2").one()
    response = client.delete("/api/standards/versions/%d" % default.id)
    assert response.status_code == 409
    assert "不允许删除" in response.get_json()["error"]["message"]
    assert StandardVersion.query.count() == 1


def test_backfill_restores_version_pointer(client, station):
    """历史遗留数据(版本指针为空)可按监测时间回填, 判定结论不受影响."""
    client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2026-09-01 10:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 900.0}],
        },
    )
    row = Measurement.query.one()
    row.standard_version_id = None
    row.exceedance.standard_version_id = None
    db.session.commit()

    updated = standard_service.backfill_measurement_versions()
    assert updated == 1
    db.session.expire_all()
    row = Measurement.query.one()
    assert row.standard_version.code == "GB3095-2012-L2"
    assert row.exceedance.standard_version_id == row.standard_version_id
    assert row.is_exceeded is True  # 判定结论未被重算
    assert row.exceedance.level == "moderate"


def test_meta_pollutants_reflect_current_version(client, future_version):
    body = client.get("/api/meta/pollutants").get_json()
    pm25 = next(item for item in body["items"] if item["code"] == "PM25")
    assert pm25["limits"]["daily"] == 75.0  # 当前仍执行 2016 版
    assert body["current_version"]["code"] == "GB3095-2012-L2"
