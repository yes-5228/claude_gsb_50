"""超标判定规则: 依据给定限值计算超标倍数并分级.

判定所需的限值由调用方按监测时间从适用标准版本中解析
(services/standard_service.resolve_version), 本模块保持纯函数, 不访问数据库。
"""
from .standards import get_pollutant

# 超标倍数 -> 等级
LEVEL_THRESHOLDS = ((2.0, "severe"), (1.5, "moderate"), (1.0, "light"))

LEVEL_ORDER = {"light": 1, "moderate": 2, "severe": 3}


def grade_ratio(ratio):
    """Map an exceedance ratio (value / limit) to a level code."""
    for threshold, level in LEVEL_THRESHOLDS:
        if ratio >= threshold:
            return level
    return "light"


def evaluate(pollutant_code, period, value, limit):
    """Evaluate a single reading against ``limit``.

    ``limit`` 必须显式给出; 传 None 表示该因子在该周期不设限值
    (如 PM2.5 无 1 小时限值), 此时仅记录数值, 不参与超标判定。

    Returns a dict: {"applicable", "exceeded", "limit", "ratio", "level", "unit", "message"}.
    """
    pollutant = get_pollutant(pollutant_code)
    if pollutant is None:
        raise ValueError("未知监测因子: %s" % pollutant_code)
    if period not in ("hourly", "daily"):
        raise ValueError("未知数据周期: %s" % period)
    if value is None:
        raise ValueError("监测数值不能为空")

    if limit is None:
        return {
            "applicable": False,
            "exceeded": False,
            "limit": None,
            "ratio": None,
            "level": None,
            "unit": pollutant["unit"],
            "message": "%s 未设定%s限值, 仅记录数值"
            % (pollutant["label"], "小时均值" if period == "hourly" else "日均值"),
        }

    ratio = round(float(value) / float(limit), 3)
    exceeded = float(value) > float(limit)
    return {
        "applicable": True,
        "exceeded": exceeded,
        "limit": float(limit),
        "ratio": ratio,
        "level": grade_ratio(ratio) if exceeded else None,
        "unit": pollutant["unit"],
        "message": None,
    }


def summarize(results):
    """Aggregate evaluation results for the batch entry form."""
    exceeded = [item for item in results if item["exceeded"]]
    return {
        "total": len(results),
        "exceeded_count": len(exceeded),
        "exceeded_pollutants": [item["pollutant"] for item in exceeded],
    }
