import { useCallback, useState } from 'react'
import {
  createStandardVersion,
  deleteStandardVersion,
  listStandardVersions,
  updateStandardVersion
} from '../../api/standards.js'
import { SectionCard } from '../../components/common/Card.jsx'
import ConfirmDialog from '../../components/common/ConfirmDialog.jsx'
import { Alert } from '../../components/common/Feedback.jsx'
import { useToast } from '../../components/common/ToastProvider.jsx'
import { useAsyncData } from '../../hooks/useAsyncData.js'
import { resetOptionCache } from '../../hooks/useOptions.js'
import StandardDetailModal from './components/StandardDetailModal.jsx'
import StandardFormModal from './components/StandardFormModal.jsx'
import StandardTable from './components/StandardTable.jsx'

export default function StandardsPage() {
  const toast = useToast()
  const { data, loading, error, reload } = useAsyncData(listStandardVersions)
  const [formState, setFormState] = useState({ open: false, version: null })
  const [detail, setDetail] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const items = data?.items ?? []

  const handleSubmit = useCallback(
    async (payload) => {
      if (formState.version) {
        await updateStandardVersion(formState.version.id, payload)
        toast.success(`标准版本「${payload.name}」已更新`)
      } else {
        await createStandardVersion(payload)
        toast.success(`标准版本「${payload.name}」已创建, 将按生效时间参与判定`)
      }
      setFormState({ open: false, version: null })
      resetOptionCache() // 现行版本可能变化, 刷新因子限值缓存
      reload()
    },
    [formState.version, reload, toast]
  )

  const handleDelete = useCallback(async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteStandardVersion(pendingDelete.id)
      toast.success(`标准版本「${pendingDelete.name}」已删除`)
      setPendingDelete(null)
      resetOptionCache()
      reload()
    } catch (error) {
      toast.error(error.message)
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete, reload, toast])

  return (
    <>
      {error ? <Alert tone="error">{error.message}</Alert> : null}

      <SectionCard
        title="标准版本时间轴"
        hint="每个版本自生效时间起取代上一版本; 录入数据时按监测时间匹配当时生效的版本, 历史判定结论不随标准调整而变化"
        actions={
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setFormState({ open: true, version: null })}
          >
            + 新增标准版本
          </button>
        }
      >
        <StandardTable
          rows={items}
          loading={loading}
          onView={(row) => setDetail(row)}
          onEdit={(row) => setFormState({ open: true, version: row })}
          onDelete={(row) => setPendingDelete(row)}
        />
      </SectionCard>

      <StandardFormModal
        open={formState.open}
        version={formState.version}
        onClose={() => setFormState({ open: false, version: null })}
        onSubmit={handleSubmit}
      />

      <StandardDetailModal
        version={detail}
        onClose={() => setDetail(null)}
        onEdit={(version) => {
          setDetail(null)
          setFormState({ open: true, version })
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        danger
        busy={deleting}
        title="删除标准版本"
        message={`确认删除标准版本「${pendingDelete?.name || ''}」吗?`}
        detail="仅未被监测数据引用的版本可以删除; 删除后该时间段的录入将按相邻版本判定。"
        confirmText="确认删除"
        onConfirm={handleDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}
