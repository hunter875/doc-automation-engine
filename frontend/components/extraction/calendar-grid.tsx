"use client";

import { useMemo } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getMonthName } from "@/lib/utils";

const WEEKDAYS_VI = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

export interface CalendarGridProps<T> {
  month: number;
  year: number;
  days: T[]; // Array of day data objects, each must have a `date: string` property (YYYY-MM-DD)
  renderDay: (day: T | null, dayNumber: number, isSelected: boolean) => React.ReactNode;
  selectedDay?: string | null;
  onSelectDay?: (date: string) => void;
  showHeader?: boolean;
  showLegend?: boolean;
  onPrevMonth?: () => void;
  onNextMonth?: () => void;
  onGoToday?: () => void;
  getDayStatus?: (day: T) => string; // optional: for legend or styling if needed
  getCellClassName?: (day: T, isSelected: boolean) => string;
  getCellTitle?: (day: T) => string;
}

export function CalendarGrid<T extends { date: string }>({
  month,
  year,
  days,
  renderDay,
  selectedDay,
  onSelectDay,
  showHeader = true,
  showLegend = false,
  onPrevMonth,
  onNextMonth,
  onGoToday,
  getDayStatus,
  getCellClassName,
  getCellTitle,
}: CalendarGridProps<T>) {
  // Compute grid structure
  const { numDays, firstDow, cells } = useMemo(() => {
    const numDays = new Date(year, month, 0).getDate();
    const firstDow = (() => {
      const js = new Date(year, month - 1, 1).getDay();
      return js === 0 ? 6 : js - 1;
    })();

    // Build a map for quick lookup by date
    const dayMap = new Map<string, T>();
    days.forEach((d) => dayMap.set(d.date, d));

    const cells: Array<{ day: number; data: T | null }> = [];

    // leading nulls
    for (let i = 0; i < firstDow; i++) {
      cells.push({ day: 0, data: null });
    }

    // actual days
    for (let day = 1; day <= numDays; day++) {
      const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const data = dayMap.get(dateStr) ?? null;
      cells.push({ day, data });
    }

    return { numDays, firstDow, cells };
  }, [year, month, days]);

  // Build rows (each row has 7 cells)
  const rows = useMemo(() => {
    const rows: typeof cells[] = [];
    for (let i = 0; i < cells.length; i += 7) {
      rows.push(cells.slice(i, i + 7));
    }
    return rows;
  }, [cells]);

  // Determine if a particular day is selected
  const isDaySelected = (date: string | null) => {
    return selectedDay !== undefined && selectedDay !== null ? selectedDay === date : false;
  };

  return (
    <div className="space-y-3">
      {/* Header with navigation */}
      {showHeader && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" onClick={onPrevMonth} aria-label="Tháng trước">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="font-semibold text-base">
              {getMonthName(month, year)}
            </span>
            <Button variant="ghost" size="icon" onClick={onNextMonth} aria-label="Tháng sau">
              <ChevronRight className="h-4 w-4" />
            </Button>
            {onGoToday && (
              <Button variant="outline" size="sm" onClick={onGoToday} className="text-xs px-2 py-1 h-7 ml-2">
                Hôm nay
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Weekday headers */}
      {showHeader && (
        <div className="grid grid-cols-7 gap-1 mb-1">
          {WEEKDAYS_VI.map((d) => (
            <div key={d} className="text-center text-xs font-medium text-muted-foreground py-1">
              {d}
            </div>
          ))}
        </div>
      )}

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {rows.map((row, rowIndex) =>
          row.map((cell, colIndex) => {
            const { day, data } = cell;
            if (day === 0 || data === null) {
              // Empty cell (padding or no data)
              return <div key={`${rowIndex}-${colIndex}`} className="h-12 rounded-md" />;
            }
            const date = data.date;
            const isSelected = isDaySelected(date);
            const content = renderDay(data, day, isSelected);
            if (onSelectDay) {
              const extraClass = getCellClassName ? getCellClassName(data, isSelected) : "";
              const title = getCellTitle ? getCellTitle(data) : undefined;
              return (
                <button
                  key={`${rowIndex}-${colIndex}`}
                  onClick={() => onSelectDay(date)}
                  className={`h-12 rounded-md flex flex-col items-center justify-center transition-all cursor-pointer select-none hover:shadow-md hover:scale-105 ${extraClass}`}
                  title={title}
                >
                  {content}
                </button>
              );
            }
            return (
              <div key={`${rowIndex}-${colIndex}`} className="h-12 rounded-md flex flex-col items-center justify-center">
                {content}
              </div>
            );
          })
        )}
      </div>

      {/* Legend */}
      {showLegend && getDayStatus && (
        <div className="flex gap-4 flex-wrap text-xs text-muted-foreground mt-2">
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded bg-green-100 dark:bg-green-900/40 border border-green-300 dark:border-green-700" />
            Hoàn thành
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded bg-yellow-100 dark:bg-yellow-900/40 border border-yellow-300 dark:border-yellow-700" />
            Có hồ sơ chờ
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded bg-red-100 dark:bg-red-900/40 border border-red-300 dark:border-red-700" />
            Có vấn đề
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-3 h-3 rounded bg-muted/30 border border-transparent" />
            Trống
          </span>
        </div>
      )}
    </div>
  );
}
