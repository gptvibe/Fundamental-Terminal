"use client";

import { useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, RowClickedEvent } from "ag-grid-community";

interface DenseGridProps<RowData extends object> {
  rowData: RowData[];
  columnDefs: ColDef<RowData>[];
  height?: number;
  density?: "compact" | "normal";
  onRowClicked?: (event: RowClickedEvent<RowData>) => void;
}

export function DenseGrid<RowData extends object>({
  rowData,
  columnDefs,
  height = 420,
  density = "compact",
  onRowClicked
}: DenseGridProps<RowData>) {
  const [mounted, setMounted] = useState(false);
  const rowHeight = density === "compact" ? 30 : 38;
  const headerHeight = density === "compact" ? 32 : 40;

  useEffect(() => {
    setMounted(true);
  }, []);

  const defaultColDef = useMemo<ColDef<RowData>>(
    () => ({
      sortable: true,
      resizable: true,
      filter: true,
      flex: 1,
      minWidth: 110,
      headerClass: "dense-grid-header-cell",
      cellClass: "dense-grid-body-cell"
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
    <div className={`ag-theme-quartz dense-grid dense-grid-${density}`} style={{ height, width: "100%" }}>
      <AgGridReact<RowData>
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        animateRows={false}
        suppressMovableColumns
        suppressCellFocus
        rowHeight={rowHeight}
        headerHeight={headerHeight}
        rowSelection="single"
        onRowClicked={onRowClicked}
      />
    </div>
  );
}
