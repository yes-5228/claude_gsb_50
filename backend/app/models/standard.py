"""限值标准版本: 标准版本(名称/等级/生效时间) + 因子限值条目."""
from ..domain.constants import PERIOD_LABELS, STANDARD_GRADE_LABELS, label_of
from ..domain.standards import get_pollutant
from ..extensions import db
from .base import TimestampMixin, iso


class StandardVersion(TimestampMixin, db.Model):
    """一套在某一时刻起生效的限值标准.

    版本之间按 effective_from 构成时间轴: 某时刻适用的版本为
    effective_from <= 该时刻的最近一个版本. 历史监测数据在录入时已快照
    判定结论, 版本调整不会回溯改写.
    """

    __tablename__ = "standard_versions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    grade = db.Column(db.String(16), nullable=False, default="grade2")
    effective_from = db.Column(db.DateTime, nullable=False, unique=True, index=True)
    remark = db.Column(db.Text)

    limits = db.relationship(
        "StandardLimit",
        back_populates="version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StandardLimit.pollutant, StandardLimit.period",
    )
    measurements = db.relationship("Measurement", back_populates="standard_version")

    def grade_label(self):
        return label_of(STANDARD_GRADE_LABELS, self.grade)

    def display_name(self):
        return "%s(%s)" % (self.name, self.grade_label())

    def limits_map(self):
        """嵌套字典: {pollutant: {period: limit_value}}."""
        result = {}
        for item in self.limits:
            result.setdefault(item.pollutant, {})[item.period] = item.limit_value
        return result

    def to_dict(self, include_limits=False):
        payload = {
            "id": self.id,
            "name": self.name,
            "grade": self.grade,
            "grade_label": self.grade_label(),
            "display_name": self.display_name(),
            "effective_from": iso(self.effective_from),
            "remark": self.remark,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }
        if include_limits:
            payload["limits"] = [item.to_dict() for item in self.limits]
        return payload

    def __repr__(self):
        return "<StandardVersion %s %s>" % (self.name, iso(self.effective_from))


class StandardLimit(db.Model):
    """单个监测因子在某一数据周期下的浓度限值 (缺行表示该周期不设限值)."""

    __tablename__ = "standard_limits"
    __table_args__ = (
        db.UniqueConstraint("version_id", "pollutant", "period", name="uq_standard_limit_item"),
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
    limit_value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(16), nullable=False)

    version = db.relationship("StandardVersion", back_populates="limits")

    def to_dict(self):
        meta = get_pollutant(self.pollutant)
        return {
            "id": self.id,
            "version_id": self.version_id,
            "pollutant": self.pollutant,
            "pollutant_label": meta["label"] if meta else self.pollutant,
            "period": self.period,
            "period_label": label_of(PERIOD_LABELS, self.period),
            "limit_value": self.limit_value,
            "unit": self.unit,
        }

    def __repr__(self):
        return "<StandardLimit v%s %s %s=%s>" % (
            self.version_id,
            self.pollutant,
            self.period,
            self.limit_value,
        )
