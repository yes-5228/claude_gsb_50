import DataTable from '../../../components/common/DataTable.jsx'
import Tag from '../../../components/common/Tag.jsx'
import {
  STANDARD_GRADE_TONE,
  STANDARD_STATUS_LABELS,
  STANDARD_STATUS_TONE
} from '../../../constants/index.js'
import { formatDateTime } from '../../../utils/format.js'

export default function StandardTable({ rows, loading, onView, onEdit, onDelete }) {
  const columns = [
    {
      key: 'name',
      title: '标准版本',
      render: (row) => (
        <div>
          <div>{row.name}</div>
          {row.remark ? <div className="small muted">{row.remark}</div> : null}
        </div>
      )
    },
    {
      key: 'grade_label',
      title: '等级',
      render: (row) => <Tag tone={STANDARD_GRADE_TONE[row.grade]}>{row.grade_label}</Tag>
    },
    {
      key: 'effective_from',
      title: '生效时间',
      className: 'cell-nowrap',
      render: (row) => formatDateTime(row.effective_from)
    },
    {
      key: 'effective_to',
      title: '失效时间',
      className: 'cell-nowrap',
      render: (row) => (row.effective_to ? formatDateTime(row.effective_to) : <span className="muted">至今</span>)
    },
    {
      key: 'status',
      title: '状态',
      render: (row) => (
        <Tag tone={STANDARD_STATUS_TONE[row.status]}>
          {STANDARD_STATUS_LABELS[row.status] || row.status}
        </Tag>
      )
    },
    { key: 'limit_count', title: '限值条目', align: 'right' },
    {
      key: 'usage_count',
      title: '引用数据量',
      align: 'right',
      render: (row) =>
        row.usage_count > 0 ? (
          <span title="按本版本判定的监测数据条数, 判定结论已快照, 不受后续标准调整影响">
            {row.usage_count} 条
          </span>
        ) : (
          <span className="muted">0</span>
        )
    },
    {
      key: 'actions',
      title: '操作',
      align: 'right',
      className: 'cell-nowrap',
      render: (row) => (
        <div className="inline" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-sm" onClick={() => onView(row)}>
            查看
          </button>
          <button type="button" className="btn btn-sm" onClick={() => onEdit(row)}>
            编辑
          </button>
          <button
            type="button"
            className="btn btn-sm btn-danger"
            onClick={() => onDelete(row)}
            disabled={row.locked}
            title={row.locked ? '已被监测数据引用, 不允许删除' : undefined}
          >
            删除
          </button>
        </div>
      )
    }
  ]

  return (
    <DataTable
      columns={columns}
      rows={rows}
      loading={loading}
      emptyText="尚未配置标准版本, 请新增"
      emptyIcon="📏"
      caption="录入监测数据时按监测时间匹配当时生效的版本; 判定结论随数据快照保存, 标准调整不影响历史记录"
    />
  )
}
