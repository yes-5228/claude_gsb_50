"""限值标准版本与限值明细.

同一时刻全局只有一个有效版本: 录入监测数据时按监测时间匹配
``effective_from <= measured_at < effective_to`` 的版本进行超标判定,
判定所依据的版本与限值会快照到监测数据上, 标准后续调整不影响历史结论。
"""
from datetime import datetime

from ..domain.constants import (
    PERIOD_LABELS,
    STANDARD_GRADE_LABELS,
    STANDARD_STATUS_LABELS,
    label_of,
)
from ..domain.standards import POLLUTANTS
from ..extensions import db
from .base import TimestampMixin, iso


class StandardVersion(TimestampMixin, db.Model):
    __tablename__ = "standard_versions"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(48), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    grade = db.Column(db.String(16), nullable=False, default="level2")
    effective_from = db.Column(db.DateTime, nullable=False, index=True)
    effective_to = db.Column(db.DateTime)  # 空 = 现行有效, 无截止
    remark = db.Column(db.Text)

    limits = db.relationship(
        "StandardLimit",
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StandardLimit.id",
    )

    def status(self, now=None):
        """Derive the lifecycle status from the effective window."""
        now = now or datetime.now()
        if self.effective_from and now < self.effective_from:
            return "scheduled"
        if self.effective_to and now >= self.effective_to:
            return "retired"
        return "active"

    def limit_map(self):
        """{(pollutant, period): limit_value} — None 值表示该周期不设限值."""
        return {(item.pollutant, item.period): item.limit_value for item in self.limits}

    def limit_for(self, pollutant, period):
        return self.limit_map().get((pollutant, period))

    def limits_matrix(self):
        """按因子组织的限值明细, 供前端矩阵展示与编辑."""
        matrix = {
            code: {"hourly": None, "daily": None} for code in POLLUTANTS
        }
        for item in self.limits:
            matrix.setdefault(item.pollutant, {"hourly": None, "daily": None})[
                item.period
            ] = item.limit_value
        return [
            {
                "pollutant": code,
                "pollutant_label": POLLUTANTS[code]["label"] if code in POLLUTANTS else code,
                "unit": POLLUTANTS[code]["unit"] if code in POLLUTANTS else None,
                "limits": limits,
            }
            for code, limits in matrix.items()
        ]

    def to_dict(self, include_limits=False, now=None):
        status = self.status(now)
        payload = {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "grade": self.grade,
            "grade_label": label_of(STANDARD_GRADE_LABELS, self.grade),
            "status": status,
            "status_label": label_of(STANDARD_STATUS_LABELS, status),
            "effective_from": iso(self.effective_from),
            "effective_to": iso(self.effective_to),
            "remark": self.remark,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }
        if include_limits:
            payload["limits"] = self.limits_matrix()
        return payload

    def to_ref(self):
        """Compact reference embedded in measurement / exceedance payloads."""
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "grade": self.grade,
            "grade_label": label_of(STANDARD_GRADE_LABELS, self.grade),
        }

    def __repr__(self):
        return "<StandardVersion %s %s>" % (self.code, self.effective_from)


class StandardLimit(db.Model):
    __tablename__ = "standard_limits"
    __table_args__ = (
        db.UniqueConstraint("version_id", "pollutant", "period", name="uq_standard_limit"),
    )

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(
        db.Integer,
        db.ForeignKey("standard_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pollutant = db.Column(db.String(16), nullable=False)
    period = db.Column(db.String(16), nullable=False)
    limit_value = db.Column(db.Float)  # NULL = 该周期不设限值

    version = db.relationship("StandardVersion", back_populates="limits")

    def to_dict(self):
        return {
            "id": self.id,
            "pollutant": self.pollutant,
            "period": self.period,
            "period_label": label_of(PERIOD_LABELS, self.period),
            "limit_value": self.limit_value,
        }

    def __repr__(self):
        return "<StandardLimit %s %s %s=%s>" % (
            self.version_id,
            self.pollutant,
            self.period,
            self.limit_value,
        )
