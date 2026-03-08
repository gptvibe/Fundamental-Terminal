"use client";

import { useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, RowClickedEvent } from "ag-grid-community";

interface DenseGridProps<RowData extends object> {
  rowData: RowData[];
  columnDefs: ColDef<RowData>[];
  height?: number;
  onRowClicked?: (event: RowClickedEvent<RowData>) => void;
}

export function DenseGrid<RowData extends object>({
  rowData,
  columnDefs,
  height = 420,
  onRowClicked
}: DenseGridProps<RowData>) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const defaultColDef = useMemo<ColDef<RowData>>(
    () => ({
      sortable: true,
      resizable: true,
      filter: true,
      flex: 1,
      minWidth: 110
    }),
    []
  );

  if (!mounted) {
    return (
      <div
        className="panel"
        style={{
          minHeight: height,
          display: "grid",
          placeItems: "center",
          color: "var(--text-muted)"
        }}
      >
        Initializing grid…
      </div>
    );
  }

  return (
    <div className="ag-theme-quartz" style={{ height, width: "100%" }}>
      <AgGridReact<RowData>
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        animateRows
        suppressCellFocus
        rowSelection="single"
        onRowClicked={onRowClicked}
      />
    </div>
  );
}
