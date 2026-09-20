import { useCallback, useState } from 'react'
import {
  createStandardVersion,
  deleteStandardVersion,
  listStandardVersions,
  updateStandardVersion
} from '../../api/standards.js'
import ConfirmDialog from '../../components/common/ConfirmDialog.jsx'
import { Alert, EmptyState, Loading } from '../../components/common/Feedback.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useAsyncData } from '../../hooks/useAsyncData.js'
import ResolvePanel from './components/ResolvePanel.jsx'
import StandardFormModal from './components/StandardFormModal.jsx'
import StandardVersionCard from './components/StandardVersionCard.jsx'

export default function StandardsPage() {
  const toast = useToast()
  const loader = useCallback(() => listStandardVersions(), [])
  const { data, loading, error, reload } = useAsyncData(loader)
  const [formState, setFormState] = useState({ open: false, version: null })
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const handleSubmit = useCallback(
    async (payload) => {
      if (formState.version) {
        await updateStandardVersion(formState.version.id, payload)
        toast.success(`标准版本 ${payload.code} 已更新, 历史数据判定结论保持不变`)
      } else {
        await createStandardVersion(payload)
        toast.success(`标准版本 ${payload.code} 已创建`)
      }
      setFormState({ open: false, version: null })
      reload()
    },
    [formState.version, reload, toast]
  )

  const handleDelete = useCallback(async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteStandardVersion(pendingDelete.id)
      toast.success(`标准版本 ${pendingDelete.code} 已删除`)
      setPendingDelete(null)
      reload()
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete, reload, toast])

  const versions = data?.items ?? []

  return (
    <>
      <ResolvePanel />

      {error ? <Alert tone="error">{error.message}</Alert> : null}

      <div className="card">
        <div className="card-header">
          <div>
            <h3>标准版本时间线</h3>
            <div className="hint">
              同一时刻只有一个有效版本; 录入数据时按监测时间匹配适用版本并快照限值,
              标准调整后历史数据的判定结论与超标等级保持不变
            </div>
          </div>
          <div className="inline">
            <button type="button" className="btn" onClick={reload} disabled={loading}>
              刷新
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setFormState({ open: true, version: null })}
            >
              + 新建标准版本
            </button>
          </div>
        </div>
      </div>

      {loading && versions.length === 0 ? <Loading text="正在加载标准版本..." /> : null}
      {!loading && versions.length === 0 ? (
        <EmptyState text="尚未配置任何限值标准版本" icon="📏" />
      ) : null}

      {versions.map((version) => (
        <StandardVersionCard
          key={version.id}
          version={version}
          onEdit={(row) => setFormState({ open: true, version: row })}
          onDelete={(row) => setPendingDelete(row)}
        />
      ))}

      <StandardFormModal
        open={formState.open}
        version={formState.version}
        onClose={() => setFormState({ open: false, version: null })}
        onSubmit={handleSubmit}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        danger
        busy={deleting}
        title="删除标准版本"
        message={`确认删除标准版本「${pendingDelete?.name || ''}」吗?`}
        detail="已被监测数据引用的版本不允许删除; 删除未引用的版本不会影响任何历史数据的判定结论。"
        confirmText="确认删除"
        onConfirm={handleDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}
