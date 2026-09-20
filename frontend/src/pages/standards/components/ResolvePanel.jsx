import { useState } from 'react'
import { resolveStandard } from '../../../api/standards.js'
import { SectionCard } from '../../../components/common/Card.jsx'
import { Field, Input } from '../../../components/common/FormField.jsx'
import Tag from '../../../components/common/Tag.jsx'
import { STANDARD_GRADE_TONE, STANDARD_STATUS_TONE } from '../../../constants/index.js'
import { formatDateTime, toDateTimeInput } from '../../../utils/format.js'

/** 试算某个监测时刻适用的标准版本, 与录入判定口径一致. */
export default function ResolvePanel() {
  const [measuredAt, setMeasuredAt] = useState(toDateTimeInput())
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await resolveStandard(measuredAt))
    } catch (err) {
      setError(err.message)
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const version = result?.version

  return (
    <SectionCard
      title="适用标准试算"
      hint="录入监测数据时, 系统按监测时间自动匹配当时有效的标准版本"
      actions={
        <button type="button" className="btn btn-sm btn-primary" onClick={run} disabled={busy || !measuredAt}>
          {busy ? '查询中...' : '查询适用标准'}
        </button>
      }
    >
      <div className="filter-bar" style={{ marginBottom: 12 }}>
        <Field label="监测时间">
          <Input
            type="datetime-local"
            value={measuredAt}
            onChange={(event) => setMeasuredAt(event.target.value)}
          />
        </Field>
      </div>
      {error ? <div className="alert alert-error"><span>{error}</span></div> : null}
      {result ? (
        version ? (
          <div className="inline">
            <Tag tone={STANDARD_STATUS_TONE[version.status]}>{version.status_label}</Tag>
            <Tag tone={STANDARD_GRADE_TONE[version.grade]}>{version.grade_label}</Tag>
            <span className="strong">{version.name}</span>
            <span className="muted small">
              ({formatDateTime(version.effective_from)} ~{' '}
              {version.effective_to ? formatDateTime(version.effective_to) : '至今'})
            </span>
          </div>
        ) : (
          <div className="alert alert-warning">
            <span>该时刻不在任何标准版本的生效区间内, 录入前需要先配置适用版本。</span>
          </div>
        )
      ) : null}
    </SectionCard>
  )
}
