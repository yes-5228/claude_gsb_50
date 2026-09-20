import Tag from '../../../components/common/Tag.jsx'
import { STANDARD_GRADE_TONE, STANDARD_STATUS_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber } from '../../../utils/format.js'

/** 单个标准版本卡片: 生效区间、状态与限值矩阵. */
export default function StandardVersionCard({ version, onEdit, onDelete }) {
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h3>
            {version.name}{' '}
            <Tag tone={STANDARD_GRADE_TONE[version.grade]}>{version.grade_label}</Tag>{' '}
            <Tag tone={STANDARD_STATUS_TONE[version.status]}>{version.status_label}</Tag>
          </h3>
          <div className="hint">
            {version.code} · 生效区间 {formatDateTime(version.effective_from)} ~{' '}
            {version.effective_to ? formatDateTime(version.effective_to) : '至今'}
          </div>
        </div>
        <div className="inline">
          <button type="button" className="btn btn-sm" onClick={() => onEdit(version)}>
            编辑
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => onDelete(version)}>
            删除
          </button>
        </div>
      </div>
      <div className="card-body tight">
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>监测因子</th>
                <th className="text-right">1 小时平均</th>
                <th className="text-right">24 小时平均</th>
                <th>单位</th>
              </tr>
            </thead>
            <tbody>
              {version.limits.map((row) => (
                <tr key={row.pollutant}>
                  <td>{row.pollutant_label}</td>
                  <td className="text-right">
                    {row.limits.hourly === null ? (
                      <span className="muted small">不设限值</span>
                    ) : (
                      formatNumber(row.limits.hourly)
                    )}
                  </td>
                  <td className="text-right">
                    {row.limits.daily === null ? (
                      <span className="muted small">不设限值</span>
                    ) : (
                      formatNumber(row.limits.daily)
                    )}
                  </td>
                  <td className="muted small">{row.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {version.remark ? <div className="table-caption">备注: {version.remark}</div> : null}
      </div>
    </div>
  )
}
