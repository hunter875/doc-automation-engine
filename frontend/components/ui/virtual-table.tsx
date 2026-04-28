"use client";

import { useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableCaption } from "@/components/ui/table";
import { cn } from "@/lib/utils";

interface VirtualTableColumn<T> {
  key: string;
  header: string;
  width?: string;
  renderCell: (item: T) => React.ReactNode;
}

interface VirtualTableProps<T> {
  data: T[];
  columns: VirtualTableColumn<T>[];
  rowHeight?: number;
  overscan?: number;
  className?: string;
  containerHeight?: string | number;
  getRowClassName?: (item: T, index: number) => string;
  onRowClick?: (item: T, index: number) => void;
  caption?: string;
}

export function VirtualTable<T>({
  data,
  columns,
  rowHeight = 40,
  overscan = 5,
  className,
  containerHeight = "400px",
  getRowClassName,
  onRowClick,
  caption,
}: VirtualTableProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);

  const rowVirtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan,
  });

  const items = rowVirtualizer.getVirtualItems();
  const totalHeight = rowVirtualizer.getTotalSize();

  return (
    <div ref={parentRef} className={cn("overflow-auto", className)} style={{ height: containerHeight }}>
      <Table style={{ tableLayout: "fixed" }}>
        {caption && <TableCaption className="sr-only">{caption}</TableCaption>}
        <TableHeader>
          <TableRow>
            {columns.map((col) => (
              <TableHead key={col.key} style={{ width: col.width, minWidth: col.width }}>
                {col.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody style={{ height: `${totalHeight}px`, position: "relative" }}>
          {items.map((virtualRow) => {
            const item = data[virtualRow.index];
            const rowClass = getRowClassName ? getRowClassName(item, virtualRow.index) : undefined;
            return (
              <TableRow
                key={virtualRow.key}
                data-index={virtualRow.index}
                className={rowClass}
                onClick={onRowClick ? (e) => onRowClick(item, virtualRow.index) : undefined}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {columns.map((col) => (
                  <TableCell key={col.key}>
                    {col.renderCell(item)}
                  </TableCell>
                ))}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
