import Modal from '../../../components/common/Modal.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { STANDARD_STATUS_LABELS, STANDARD_STATUS_TONE } from '../../../constants/index.js'
import { formatDateTime, formatNumber } from '../../../utils/format.js'

export default function StandardDetailModal({ version, onClose, onEdit }) {
  if (!version) return null
  const limits = version.limits ?? []
  return (
    <Modal
      open={Boolean(version)}
      wide
      title={`标准版本详情 · ${version.name}`}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            关闭
          </button>
          <button type="button" className="btn btn-primary" onClick={() => onEdit?.(version)}>
            编辑
          </button>
        </>
      }
    >
      <div className="stack">
        <dl className="kv">
          <dt>标准等级</dt>
          <dd>{version.grade_label}</dd>
          <dt>生效时间</dt>
          <dd>{formatDateTime(version.effective_from)}</dd>
          <dt>失效时间</dt>
          <dd>{version.effective_to ? formatDateTime(version.effective_to) : '至今'}</dd>
          <dt>时间轴状态</dt>
          <dd>
            <Tag tone={STANDARD_STATUS_TONE[version.status]}>
              {STANDARD_STATUS_LABELS[version.status] || version.status}
            </Tag>
          </dd>
          <dt>引用数据量</dt>
          <dd>{version.usage_count} 条监测数据按本版本判定</dd>
          {version.remark ? (
            <>
              <dt>备注</dt>
              <dd>{version.remark}</dd>
            </>
          ) : null}
        </dl>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>监测因子</th>
                <th>数据周期</th>
                <th className="text-right">限值</th>
                <th>单位</th>
              </tr>
            </thead>
            <tbody>
              {limits.map((item) => (
                <tr key={`${item.pollutant}-${item.period}`}>
                  <td>{item.pollutant_label}</td>
                  <td>{item.period_label}</td>
                  <td className="text-right">{formatNumber(item.limit_value)}</td>
                  <td className="muted">{item.unit}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  )
}
