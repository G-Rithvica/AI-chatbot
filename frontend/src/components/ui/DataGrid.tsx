type DataGridAlignment = 'left' | 'center' | 'right'

type DataGridProps = {
  columns: string[]
  rows: string[][]
  alignments?: DataGridAlignment[]
  dense?: boolean
}

export function DataGrid({ columns, rows, alignments = [], dense = false }: DataGridProps) {
  const cellClass = dense ? 'px-2 py-1.5 text-xs' : 'px-3 py-2 text-sm'

  return (
    <div className="ui-chat-table-wrap rounded-lg border border-slate-700/70" role="region" aria-label="Data table">
      <table className="ui-chat-table border-collapse">
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th
                key={index}
                className={`ui-chat-table-th ${cellClass}`}
                scope="col"
                style={{ textAlign: alignments[index] ?? 'left' }}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="ui-chat-table-row">
              {row.map((cell, cellIndex) => (
                <td
                  key={`${rowIndex}-${cellIndex}`}
                  className={`ui-chat-table-td ${cellClass}`}
                  style={{ textAlign: alignments[cellIndex] ?? 'left' }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
