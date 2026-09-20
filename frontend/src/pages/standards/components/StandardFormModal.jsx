import { useEffect, useMemo, useState } from 'react'
import Modal from '../../../components/common/Modal.jsx'
import { Field, Input, Select, Textarea } from '../../../components/common/FormField.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'
import { STANDARD_GRADE_LABELS } from '../../../constants/index.js'
import { usePollutantMeta } from '../../../hooks/useOptions.js'
import { toDateTimeInput } from '../../../utils/format.js'

const GRADE_OPTIONS = Object.entries(STANDARD_GRADE_LABELS).map(([value, label]) => ({
  value,
  label
}))

function emptyLimits(pollutants) {
  const map = {}
  pollutants.forEach((item) => {
    map[item.code] = { hourly: '', daily: '' }
  })
  return map
}

function limitsFromVersion(version, pollutants) {
  const map = emptyLimits(pollutants)
  ;(version?.limits || []).forEach((item) => {
    if (map[item.pollutant]) map[item.pollutant][item.period] = String(item.limit_value)
  })
  return map
}

export default function StandardFormModal({ open, version, onClose, onSubmit }) {
  const { data: pollutantData } = usePollutantMeta()
  const pollutants = useMemo(() => pollutantData?.items ?? [], [pollutantData])

  const [form, setForm] = useState({ name: '', grade: 'grade2', effective_from: '', remark: '' })
  const [limits, setLimits] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const locked = Boolean(version?.locked)

  useEffect(() => {
    if (!open) return
    setErrors({})
    setMessage(null)
    if (version) {
      setForm({
        name: version.name ?? '',
        grade: version.grade ?? 'grade2',
        effective_from: version.effective_from ? version.effective_from.slice(0, 16) : '',
        remark: version.remark ?? ''
      })
      setLimits(limitsFromVersion(version, pollutants))
    } else {
      setForm({ name: '', grade: 'grade2', effective_from: toDateTimeInput(), remark: '' })
      setLimits(emptyLimits(pollutants))
    }
  }, [open, version, pollutants])

  const set = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const setLimit = (code, period) => (event) => {
    const raw = event.target.value
    setLimits((prev) => ({ ...prev, [code]: { ...prev[code], [period]: raw } }))
    setErrors((prev) => ({ ...prev, limits: undefined }))
  }

  const submit = async (event) => {
    event.preventDefault()
    const next = {}
    if (!form.name.trim()) next.name = '标准名称不能为空'
    if (!form.effective_from) next.effective_from = '生效时间不能为空'
    const limitItems = []
    pollutants.forEach((item) => {
      ;['hourly', 'daily'].forEach((period) => {
        const raw = limits[item.code]?.[period]
        if (raw === '' || raw === null || raw === undefined) return
        const value = Number(raw)
        if (Number.isNaN(value) || value <= 0) {
          next.limits = `${item.label} 的限值必须是大于 0 的数字`
          return
        }
        limitItems.push({ pollutant: item.code, period, limit_value: value })
      })
    })
    if (!next.limits && limitItems.length === 0) next.limits = '至少填写一条限值'
    setErrors(next)
    if (Object.keys(next).length) {
      setMessage('请先修正表单中标红的问题')
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      await onSubmit({
        name: form.name.trim(),
        grade: form.grade,
        effective_from: form.effective_from,
        remark: form.remark.trim() || null,
        limits: limitItems
      })
    } catch (error) {
      setErrors(error.fields || {})
      setMessage(error.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      wide
      title={version ? `编辑标准版本 · ${version.name}` : '新增标准版本'}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="submit" form="standard-form" className="btn btn-primary" disabled={busy}>
            {busy ? '保存中...' : '保存'}
          </button>
        </>
      }
    >
      <form id="standard-form" className="stack" onSubmit={submit}>
        {message ? <Alert tone="error">{message}</Alert> : null}
        {locked ? (
          <Alert tone="warning">
            该版本已用于 {version.usage_count} 条监测数据的判定, 等级、生效时间与限值已锁定,
            仅可修改名称与备注; 如需修订标准请新建版本。
          </Alert>
        ) : null}
        <div className="form-grid">
          <Field label="标准名称" required error={errors.name} className="span-2">
            <Input
              value={form.name}
              onChange={set('name')}
              invalid={Boolean(errors.name)}
              placeholder="如: GB 3095-2012 环境空气质量标准"
            />
          </Field>
          <Field label="标准等级" required hint={locked ? '已被数据引用, 不可调整' : undefined}>
            <Select
              value={form.grade}
              onChange={set('grade')}
              options={GRADE_OPTIONS}
              disabled={locked}
            />
          </Field>
          <Field
            label="生效时间"
            required
            error={errors.effective_from}
            hint={locked ? '已被数据引用, 不可调整' : '自该时刻起按本版本限值判定'}
          >
            <Input
              type="datetime-local"
              value={form.effective_from}
              onChange={set('effective_from')}
              invalid={Boolean(errors.effective_from)}
              disabled={locked}
            />
          </Field>
          <Field label="备注" error={errors.remark} className="span-2">
            <Textarea
              value={form.remark}
              onChange={set('remark')}
              placeholder="标准来源、适用范围等说明"
            />
          </Field>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>浓度限值</h3>
            <span className="hint">留空表示该因子在此周期不设限值, 仅记录数值</span>
          </div>
          <div className="card-body">
            {errors.limits ? <Alert tone="error">{errors.limits}</Alert> : null}
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>监测因子</th>
                    <th style={{ width: 180 }}>小时均值限值</th>
                    <th style={{ width: 180 }}>日均值限值</th>
                    <th style={{ width: 90 }}>单位</th>
                  </tr>
                </thead>
                <tbody>
                  {pollutants.map((item) => (
                    <tr key={item.code}>
                      <td>
                        {item.label}
                        <span className="muted small"> {item.name}</span>
                      </td>
                      <td>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={limits[item.code]?.hourly ?? ''}
                          onChange={setLimit(item.code, 'hourly')}
                          placeholder="--"
                          disabled={locked}
                        />
                      </td>
                      <td>
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          value={limits[item.code]?.daily ?? ''}
                          onChange={setLimit(item.code, 'daily')}
                          placeholder="--"
                          disabled={locked}
                        />
                      </td>
                      <td className="muted">{item.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  )
}
