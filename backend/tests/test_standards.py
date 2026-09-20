"""限值标准版本管理测试: 版本维护 / 按监测时间匹配限值 / 历史结论不变."""
from datetime import datetime

import pytest

from app.models import Measurement, StandardVersion
from app.services import standard_service


def make_limits(**overrides):
    """默认给一套完整限值, 可用 SO2_hourly=100 形式覆盖."""
    limits = {
        ("PM25", "daily"): 75.0,
        ("PM10", "daily"): 150.0,
        ("SO2", "daily"): 150.0,
        ("SO2", "hourly"): 500.0,
        ("NO2", "daily"): 80.0,
        ("NO2", "hourly"): 200.0,
        ("CO", "daily"): 4.0,
        ("CO", "hourly"): 10.0,
        ("O3", "daily"): 160.0,
        ("O3", "hourly"): 200.0,
    }
    for key, value in overrides.items():
        pollutant, period = key.split("_")
        limits[(pollutant, period)] = value
    return [
        {"pollutant": pollutant, "period": period, "limit_value": value}
        for (pollutant, period), value in limits.items()
    ]


def create_version(client, name, effective_from, grade="grade2", limits=None, **extra):
    payload = {
        "name": name,
        "grade": grade,
        "effective_from": effective_from,
        "limits": limits if limits is not None else make_limits(),
    }
    payload.update(extra)
    return client.post("/api/standards/versions", json=payload)


@pytest.fixture
def two_versions(client):
    """v1: 2020 年起 SO2 小时限值 500; v2: 2026 年起加严到 100."""
    v1 = create_version(client, "GB 3095-2012 环境空气质量标准", "2020-01-01 00:00")
    assert v1.status_code == 201
    v2 = create_version(
        client, "GB 3095-2026 环境空气质量标准", "2026-01-01 00:00",
        limits=make_limits(SO2_hourly=100.0),
    )
    assert v2.status_code == 201
    return v1.get_json(), v2.get_json()


# ---- 版本维护 ---------------------------------------------------------

def test_create_and_list_versions(client):
    response = create_version(client, "GB 3095-2012 环境空气质量标准", "2016-01-01 00:00")
    assert response.status_code == 201
    body = response.get_json()
    assert body["grade_label"] == "二级标准"
    assert body["status"] == "current"
    assert body["limit_count"] == 10
    assert body["usage_count"] == 0
    assert body["locked"] is False

    listing = client.get("/api/standards/versions").get_json()
    assert listing["total"] == 1
    assert listing["current_id"] == body["id"]
    item = listing["items"][0]
    assert item["effective_to"] is None
    so2_hourly = next(
        row for row in item["limits"]
        if row["pollutant"] == "SO2" and row["period"] == "hourly"
    )
    assert so2_hourly["limit_value"] == 500.0
    assert so2_hourly["unit"] == "μg/m³"


def test_timeline_status_with_multiple_versions(client, two_versions):
    v1, v2 = two_versions
    listing = client.get("/api/standards/versions").get_json()
    by_id = {item["id"]: item for item in listing["items"]}
    # 当前日期 (2026-09) 落在 v2 区间: v1 已失效, v2 现行
    assert by_id[v1["id"]]["status"] == "historical"
    assert by_id[v1["id"]]["effective_to"] == "2026-01-01T00:00:00"
    assert by_id[v2["id"]]["status"] == "current"
    assert by_id[v2["id"]]["effective_to"] is None
    assert listing["current_id"] == v2["id"]


def test_future_version_is_pending(client, two_versions):
    _v1, v2 = two_versions
    response = create_version(client, "GB 3095-2030 环境空气质量标准", "2030-01-01 00:00")
    assert response.status_code == 201
    future = response.get_json()
    assert future["status"] == "pending"

    listing = client.get("/api/standards/versions").get_json()
    by_id = {item["id"]: item for item in listing["items"]}
    assert by_id[v2["id"]]["effective_to"] == "2030-01-01T00:00:00"
    assert by_id[future["id"]]["status"] == "pending"
    assert listing["current_id"] == v2["id"]


def test_duplicate_effective_from_rejected(client):
    assert create_version(client, "标准A", "2020-01-01 00:00").status_code == 201
    conflict = create_version(client, "标准B", "2020-01-01 00:00")
    assert conflict.status_code == 409
    assert "同一时刻只能有一个版本生效" in conflict.get_json()["error"]["message"]


def test_invalid_limits_rejected(client):
    unknown = create_version(
        client, "标准", "2020-01-01 00:00",
        limits=[{"pollutant": "XX", "period": "daily", "limit_value": 1}],
    )
    assert unknown.status_code == 422

    bad_period = create_version(
        client, "标准", "2020-01-01 00:00",
        limits=[{"pollutant": "SO2", "period": "weekly", "limit_value": 1}],
    )
    assert bad_period.status_code == 422

    negative = create_version(
        client, "标准", "2020-01-01 00:00",
        limits=[{"pollutant": "SO2", "period": "daily", "limit_value": -1}],
    )
    assert negative.status_code == 422

    empty = create_version(client, "标准", "2020-01-01 00:00", limits=[])
    assert empty.status_code == 422

    missing_time = client.post(
        "/api/standards/versions", json={"name": "标准", "limits": make_limits()}
    )
    assert missing_time.status_code == 422


def test_update_unused_version(client):
    version = create_version(client, "标准", "2020-01-01 00:00").get_json()
    response = client.put(
        "/api/standards/versions/%d" % version["id"],
        json={
            "name": "标准(修订)",
            "grade": "grade1",
            "effective_from": "2021-06-01 00:00",
            "remark": "加严",
            "limits": make_limits(SO2_hourly=150.0),
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["name"] == "标准(修订)"
    assert body["grade"] == "grade1"
    assert body["effective_from"] == "2021-06-01T00:00:00"
    so2 = next(
        row for row in body["limits"]
        if row["pollutant"] == "SO2" and row["period"] == "hourly"
    )
    assert so2["limit_value"] == 150.0


def test_delete_unused_version(client):
    version = create_version(client, "标准", "2020-01-01 00:00").get_json()
    response = client.delete("/api/standards/versions/%d" % version["id"])
    assert response.status_code == 200
    assert StandardVersion.query.count() == 0


def test_missing_version_returns_404(client):
    assert client.get("/api/standards/versions/999").status_code == 404
    assert client.put("/api/standards/versions/999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/standards/versions/999").status_code == 404


# ---- 版本解析 ---------------------------------------------------------

def test_resolve_matches_version_effective_at_measured_time(client, two_versions):
    v1, v2 = two_versions
    early = client.get("/api/standards/resolve?measured_at=2021-06-01 10:00").get_json()
    assert early["version"]["id"] == v1["id"]
    assert early["limits"]["SO2"]["hourly"] == 500.0

    late = client.get("/api/standards/resolve?measured_at=2026-06-01 10:00").get_json()
    assert late["version"]["id"] == v2["id"]
    assert late["limits"]["SO2"]["hourly"] == 100.0

    boundary = client.get("/api/standards/resolve?measured_at=2026-01-01 00:00").get_json()
    assert boundary["version"]["id"] == v2["id"]


def test_resolve_before_all_versions_uses_earliest(client, two_versions):
    v1, _v2 = two_versions
    body = client.get("/api/standards/resolve?measured_at=1999-01-01 00:00").get_json()
    assert body["version"]["id"] == v1["id"]


def test_resolve_without_versions_falls_back_to_defaults(client):
    body = client.get("/api/standards/resolve?measured_at=2026-06-01 10:00").get_json()
    assert body["version"] is None
    assert body["fallback"] is True
    assert body["limits"]["SO2"]["hourly"] == 500.0


# ---- 录入按监测时间匹配限值 --------------------------------------------

def test_entry_uses_limit_effective_at_measured_time(client, station, two_versions):
    v1, v2 = two_versions
    base = {
        "station_id": station.id,
        "period": "hourly",
        "entries": [{"pollutant": "SO2", "value": 300.0}],
    }
    old = client.post(
        "/api/measurements/entries", json={**base, "measured_at": "2021-06-01 10:00"}
    )
    assert old.status_code == 201
    old_body = old.get_json()
    assert old_body["standard"]["id"] == v1["id"]
    assert old_body["evaluations"][0]["limit"] == 500.0
    assert old_body["evaluations"][0]["exceeded"] is False

    new = client.post(
        "/api/measurements/entries", json={**base, "measured_at": "2026-06-01 10:00"}
    )
    assert new.status_code == 201
    new_body = new.get_json()
    assert new_body["standard"]["id"] == v2["id"]
    assert new_body["evaluations"][0]["limit"] == 100.0
    assert new_body["evaluations"][0]["exceeded"] is True
    assert new_body["summary"]["exceeded_count"] == 1

    old_record = Measurement.query.filter_by(measured_at=datetime(2021, 6, 1, 10, 0)).one()
    assert old_record.standard_version_id == v1["id"]
    assert old_record.limit_value == 500.0
    assert old_record.is_exceeded is False
    new_record = Measurement.query.filter_by(measured_at=datetime(2026, 6, 1, 10, 0)).one()
    assert new_record.standard_version_id == v2["id"]
    assert new_record.limit_value == 100.0
    assert new_record.is_exceeded is True


def test_historical_conclusion_survives_standard_adjustment(client, station):
    """标准调整前录入的数据, 判定结论与超标等级保持不变."""
    create_version(client, "GB 3095-2012 环境空气质量标准", "2020-01-01 00:00")
    entry = client.post(
        "/api/measurements/entries",
        json={
            "station_id": station.id,
            "measured_at": "2025-06-01 10:00",
            "period": "hourly",
            "entries": [{"pollutant": "SO2", "value": 300.0}],
        },
    )
    assert entry.status_code == 201
    measurement_id = entry.get_json()["created"][0]["id"]

    # 标准调整: 新版本 2026 年起 SO2 小时限值加严到 100
    create_version(
        client, "GB 3095-2026 环境空气质量标准", "2026-01-01 00:00",
        limits=make_limits(SO2_hourly=100.0),
    )

    stored = Measurement.query.filter_by(id=measurement_id).one()
    assert stored.limit_value == 500.0
    assert stored.is_exceeded is False
    assert stored.exceed_ratio == 0.6

    detail = client.get("/api/measurements/%d" % measurement_id).get_json()
    assert detail["limit_value"] == 500.0
    assert detail["is_exceeded"] is False
    assert detail["standard"]["name"] == "GB 3095-2012 环境空气质量标准"

    listing = client.get("/api/measurements?is_exceeded=false").get_json()
    assert listing["total"] == 1
    assert listing["items"][0]["standard"]["display_name"].endswith("(二级标准)")


def test_overwrite_revalidates_against_historical_version(client, station, two_versions):
    """覆盖历史数据时仍按监测时间对应的标准版本重新判定, 而不是用现行版本."""
    v1, _v2 = two_versions
    payload = {
        "station_id": station.id,
        "measured_at": "2021-06-01 10:00",
        "period": "hourly",
        "entries": [{"pollutant": "SO2", "value": 120.0}],
    }
    assert client.post("/api/measurements/entries", json=payload).status_code == 201
    again = client.post(
        "/api/measurements/entries",
        json={**payload, "overwrite": True, "entries": [{"pollutant": "SO2", "value": 300.0}]},
    )
    assert again.status_code == 201
    body = again.get_json()
    assert body["standard"]["id"] == v1["id"]
    assert body["evaluations"][0]["limit"] == 500.0
    assert body["evaluations"][0]["exceeded"] is False


def test_preview_uses_measured_at_version(client, station, two_versions):
    payload = {"period": "hourly", "entries": [{"pollutant": "SO2", "value": 300.0}]}
    old = client.post(
        "/api/measurements/preview", json={**payload, "measured_at": "2021-06-01 10:00"}
    ).get_json()
    assert old["results"][0]["limit"] == 500.0
    assert old["results"][0]["exceeded"] is False

    new = client.post(
        "/api/measurements/preview", json={**payload, "measured_at": "2026-06-01 10:00"}
    ).get_json()
    assert new["results"][0]["limit"] == 100.0
    assert new["results"][0]["exceeded"] is True
    assert new["standard"]["name"] == "GB 3095-2026 环境空气质量标准"


# ---- 版本锁定: 保护历史判定可追溯 --------------------------------------

def test_used_version_cannot_be_deleted(client, station, entry_payload):
    version = create_version(client, "标准", "2020-01-01 00:00").get_json()
    client.post("/api/measurements/entries", json=entry_payload(station.id))

    response = client.delete("/api/standards/versions/%d" % version["id"])
    assert response.status_code == 409
    assert "不允许删除" in response.get_json()["error"]["message"]
    assert StandardVersion.query.count() == 1


def test_used_version_limits_are_locked(client, station, entry_payload):
    version = create_version(client, "标准", "2020-01-01 00:00").get_json()
    client.post("/api/measurements/entries", json=entry_payload(station.id))

    tightened = client.put(
        "/api/standards/versions/%d" % version["id"],
        json={"name": "标准", "limits": make_limits(SO2_hourly=100.0)},
    )
    assert tightened.status_code == 409
    assert "新建版本" in tightened.get_json()["error"]["message"]

    retime = client.put(
        "/api/standards/versions/%d" % version["id"],
        json={"name": "标准", "effective_from": "2022-01-01 00:00"},
    )
    assert retime.status_code == 409

    # 名称/备注仍可修改; 原样提交相同限值不算变更
    rename = client.put(
        "/api/standards/versions/%d" % version["id"],
        json={"name": "标准(更名)", "remark": "仅修订描述", "limits": make_limits()},
    )
    assert rename.status_code == 200
    assert rename.get_json()["name"] == "标准(更名)"


def test_version_usage_count_grows_with_entries(client, station, entry_payload):
    version = create_version(client, "标准", "2020-01-01 00:00").get_json()
    client.post("/api/measurements/entries", json=entry_payload(station.id))

    detail = client.get("/api/standards/versions/%d" % version["id"]).get_json()
    assert detail["usage_count"] == 3
    assert detail["locked"] is True


def test_service_resolve_version_without_rows(app):
    with app.app_context():
        assert standard_service.resolve_version(datetime(2026, 1, 1)) is None
        version, limits = standard_service.resolve_limits(datetime(2026, 1, 1))
        assert version is None
        assert limits is None
