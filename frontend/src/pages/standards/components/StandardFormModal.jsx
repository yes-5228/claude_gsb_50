import { useEffect, useMemo, useState } from 'react'
import Modal from '../../../components/common/Modal.jsx'
import { Field, Input, Select } from '../../../components/common/FormField.jsx'
import { Alert } from '../../../components/common/Feedback.jsx'
import { usePollutantMeta } from '../../../hooks/useOptions.js'
import { toDateTimeInput } from '../../../utils/format.js'

const GRADE_OPTIONS = [
  { value: 'level1', label: '一级标准' },
  { value: 'level2', label: '二级标准' }
]

function emptyLimits(pollutants) {
  const limits = {}
  pollutants.forEach((item) => {
    limits[item.code] = { hourly: '', daily: '' }
  })
  return limits
}

/** 新建 / 编辑标准版本: 基本信息 + 因子 × 周期限值矩阵. */
export default function StandardFormModal({ open, version, onClose, onSubmit }) {
  const { data: pollutantData } = usePollutantMeta()
  const pollutants = useMemo(() => pollutantData?.items ?? [], [pollutantData])

  const [form, setForm] = useState({
    code: '',
    name: '',
    grade: 'level2',
    effective_from: '',
    effective_to: '',
    remark: ''
  })
  const [limits, setLimits] = useState({})
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setErrors({})
    setMessage(null)
    if (version) {
      setForm({
        code: version.code,
        name: version.name,
        grade: version.grade,
        effective_from: toDateTimeInput(new Date(version.effective_from)),
        effective_to: version.effective_to ? toDateTimeInput(new Date(version.effective_to)) : '',
        remark: version.remark || ''
      })
      const next = emptyLimits(pollutants)
      ;(version.limits || []).forEach((row) => {
        next[row.pollutant] = {
          hourly: row.limits.hourly === null ? '' : String(row.limits.hourly),
          daily: row.limits.daily === null ? '' : String(row.limits.daily)
        }
      })
      setLimits(next)
    } else {
      setForm({
        code: '',
        name: '',
        grade: 'level2',
        effective_from: '',
        effective_to: '',
        remark: ''
      })
      setLimits(emptyLimits(pollutants))
    }
  }, [open, version, pollutants])

  const setField = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const setLimit = (code, period) => (event) => {
    const raw = event.target.value
    setLimits((prev) => ({ ...prev, [code]: { ...prev[code], [period]: raw } }))
    setErrors((prev) => ({ ...prev, [`${code}.${period}`]: undefined }))
  }

  const payload = useMemo(() => {
    const parsed = {}
    pollutants.forEach((item) => {
      const row = limits[item.code] || {}
      parsed[item.code] = {
        hourly: row.hourly === '' || row.hourly === undefined ? null : Number(row.hourly),
        daily: row.daily === '' || row.daily === undefined ? null : Number(row.daily)
      }
    })
    return {
      code: form.code.trim(),
      name: form.name.trim(),
      grade: form.grade,
      effective_from: form.effective_from,
      effective_to: form.effective_to || null,
      remark: form.remark.trim() || null,
      limits: parsed
    }
  }, [form, limits, pollutants])

  const validate = () => {
    const next = {}
    if (!payload.code) next.code = '请填写版本编码'
    if (!payload.name) next.name = '请填写标准名称'
    if (!form.effective_from) next.effective_from = '请选择生效时间'
    if (form.effective_to && form.effective_from && form.effective_to <= form.effective_from) {
      next.effective_to = '失效时间必须晚于生效时间'
    }
    let hasLimit = false
    pollutants.forEach((item) => {
      ;['hourly', 'daily'].forEach((period) => {
        const raw = (limits[item.code] || {})[period]
        if (raw === '' || raw === undefined) return
        const number = Number(raw)
        if (Number.isNaN(number)) next[`${item.code}.${period}`] = '限值必须是数字'
        else if (number <= 0) next[`${item.code}.${period}`] = '限值必须大于 0'
        else hasLimit = true
      })
    })
    if (!hasLimit) next.limits = '至少需要为一个因子设置限值, 留空表示该周期不设限值'
    setErrors(next)
    if (Object.keys(next).length) {
      setMessage('请先修正表单中标红的问题')
      return false
    }
    setMessage(null)
    return true
  }

  const submit = async () => {
    if (!validate()) return
    setBusy(true)
    try {
      await onSubmit(payload)
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
      title={version ? `编辑标准版本 · ${version.code}` : '新建标准版本'}
      onClose={onClose}
      width="wide"
      footer={
        <>
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? '保存中...' : '保存版本'}
          </button>
        </>
      }
    >
      <div className="stack">
        {message ? <Alert tone="error">{message}</Alert> : null}
        <Alert tone="info">
          保存后仅影响之后录入的数据; 已入库数据的判定结论与超标等级保持原值不变。
          若新版本不设失效时间, 现行版本的失效时间将自动衔接为新版本生效时间。
        </Alert>

        <div className="form-grid">
          <Field label="版本编码" required error={errors.code} hint="唯一标识, 如 GB3095-2012-L2">
            <Input
              value={form.code}
              onChange={setField('code')}
              invalid={Boolean(errors.code)}
              placeholder="GB3095-2012-L2"
            />
          </Field>
          <Field label="标准名称" required error={errors.name}>
            <Input
              value={form.name}
              onChange={setField('name')}
              invalid={Boolean(errors.name)}
              placeholder="GB 3095-2012 环境空气质量标准"
            />
          </Field>
          <Field label="标准等级" required>
            <Select value={form.grade} onChange={setField('grade')} options={GRADE_OPTIONS} />
          </Field>
          <Field label="生效时间" required error={errors.effective_from}>
            <Input
              type="datetime-local"
              value={form.effective_from}
              onChange={setField('effective_from')}
              invalid={Boolean(errors.effective_from)}
            />
          </Field>
          <Field
            label="失效时间"
            error={errors.effective_to}
            hint="留空表示长期有效, 直至被下一版本接替"
          >
            <Input
              type="datetime-local"
              value={form.effective_to}
              onChange={setField('effective_to')}
              invalid={Boolean(errors.effective_to)}
            />
          </Field>
          <Field label="备注">
            <Input value={form.remark} onChange={setField('remark')} placeholder="选填" />
          </Field>
        </div>

        <div className="card" style={{ boxShadow: 'none' }}>
          <div className="card-header">
            <h3>浓度限值</h3>
            <span className="hint">留空表示该因子在该周期不设限值(仅记录, 不参与判定)</span>
          </div>
          <div className="card-body tight">
            {errors.limits ? <Alert tone="error">{errors.limits}</Alert> : null}
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>监测因子</th>
                    <th style={{ width: 180 }}>1 小时平均</th>
                    <th style={{ width: 180 }}>24 小时平均</th>
                    <th>单位</th>
                  </tr>
                </thead>
                <tbody>
                  {pollutants.map((item) => (
                    <tr key={item.code}>
                      <td>{item.label}</td>
                      {['hourly', 'daily'].map((period) => (
                        <td key={period}>
                          <Input
                            type="number"
                            step="0.01"
                            min="0"
                            value={(limits[item.code] || {})[period] ?? ''}
                            onChange={setLimit(item.code, period)}
                            invalid={Boolean(errors[`${item.code}.${period}`])}
                            placeholder="不设限值"
                          />
                          {errors[`${item.code}.${period}`] ? (
                            <span className="field-error">{errors[`${item.code}.${period}`]}</span>
                          ) : null}
                        </td>
                      ))}
                      <td className="muted small">{item.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
