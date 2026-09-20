"""污染物监测因子元数据与默认限值标准模板.

限值不再硬编码在因子定义中: 判定以数据库 ``standard_versions`` / ``standard_limits``
表中按监测时间匹配到的版本为准 (见 services/standard_service.py)。本模块仅保留
因子元数据, 以及首次初始化时写入的默认标准版本模板 (GB 3095-2012 二级)。
"""

# period 取值: hourly = 1 小时平均, daily = 24 小时平均
POLLUTANTS = {
    "PM25": {
        "code": "PM25",
        "label": "PM2.5",
        "name": "细颗粒物",
        "unit": "μg/m³",
        "precision": 1,
    },
    "PM10": {
        "code": "PM10",
        "label": "PM10",
        "name": "可吸入颗粒物",
        "unit": "μg/m³",
        "precision": 1,
    },
    "SO2": {
        "code": "SO2",
        "label": "SO₂",
        "name": "二氧化硫",
        "unit": "μg/m³",
        "precision": 1,
    },
    "NO2": {
        "code": "NO2",
        "label": "NO₂",
        "name": "二氧化氮",
        "unit": "μg/m³",
        "precision": 1,
    },
    "CO": {
        "code": "CO",
        "label": "CO",
        "name": "一氧化碳",
        "unit": "mg/m³",
        "precision": 2,
    },
    "O3": {
        "code": "O3",
        "label": "O₃",
        "name": "臭氧",
        "unit": "μg/m³",
        "precision": 1,
    },
}

POLLUTANT_CODES = tuple(POLLUTANTS.keys())

# 默认标准版本模板: 系统首次初始化时写入数据库, 保证开箱即可判定。
# limits 中 None 表示该因子在该周期不设限值(仅记录, 不参与判定)。
DEFAULT_VERSION = {
    "code": "GB3095-2012-L2",
    "name": "GB 3095-2012 环境空气质量标准",
    "grade": "level2",
    "effective_from": "2016-01-01 00:00",  # GB 3095-2012 全国实施日期
    "effective_to": None,
    "remark": "系统初始化的默认限值标准, 可在“限值标准”模块中维护新版本。",
    "limits": {
        "PM25": {"daily": 75.0, "hourly": None},
        "PM10": {"daily": 150.0, "hourly": None},
        "SO2": {"daily": 150.0, "hourly": 500.0},
        "NO2": {"daily": 80.0, "hourly": 200.0},
        "CO": {"daily": 4.0, "hourly": 10.0},
        "O3": {"daily": 160.0, "hourly": 200.0},
    },
}


def get_pollutant(code):
    """Return the pollutant definition or None when unknown."""
    return POLLUTANTS.get(str(code or "").upper())


def pollutant_options():
    """Serialisable list used by the frontend dropdowns."""
    return [dict(item) for item in POLLUTANTS.values()]
