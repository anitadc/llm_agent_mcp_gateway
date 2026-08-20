import { Fragment } from "react";

export function DataTable({ columns, rows, rowKey = "id", emptyMessage = "No data", renderExpanded }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="rounded border border-dashed border-gray-300 p-8 text-center text-gray-400">{emptyMessage}</div>
    );
  }

  return (
    <table className="w-full overflow-hidden rounded-lg border border-gray-200 bg-white text-sm">
      <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
        <tr>
          {columns.map((col) => (
            <th key={col.key} className="px-4 py-2 font-medium">
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {rows.map((row) => (
          <Fragment key={row[rowKey]}>
            <tr className="hover:bg-gray-50">
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-2">
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
            {renderExpanded && renderExpanded(row)}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}
