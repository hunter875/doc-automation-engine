"use client";

import { cn } from "@/lib/utils";
import {
  Settings2,
  Upload,
  CheckCircle2,
  BarChart3,
} from "lucide-react";

interface Stage {
  id: string;
  label: string;
  icon: React.ReactNode;
  tab: string;
}

const STAGES: Stage[] = [
  { id: "templates", label: "Mẫu", icon: <Settings2 className="h-4 w-4" />, tab: "templates" },
  { id: "jobs", label: "Hồ sơ", icon: <Upload className="h-4 w-4" />, tab: "jobs" },
  { id: "review", label: "Duyệt", icon: <CheckCircle2 className="h-4 w-4" />, tab: "review" },
  { id: "export", label: "Báo cáo", icon: <BarChart3 className="h-4 w-4" />, tab: "export" },
];

interface PipelineIndicatorProps {
  currentTab: string;
}

export function PipelineIndicator({ currentTab }: PipelineIndicatorProps) {
  const currentIndex = STAGES.findIndex((s) => s.tab === currentTab);
  if (currentIndex === -1) return null;

  return (
    <div className="flex items-center justify-center mb-6">
      <div className="flex items-center gap-2">
        {STAGES.map((stage, idx) => {
          const isActive = idx === currentIndex;
          const isCompleted = idx < currentIndex;
          const isLast = idx === STAGES.length - 1;

          return (
            <div key={stage.id} className="flex items-center">
              <div
                className={cn(
                  "flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : isCompleted
                    ? "bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {stage.icon}
                <span>{stage.label}</span>
              </div>
              {!isLast && (
                <div
                  className={cn(
                    "w-8 h-0.5 mx-1",
                    isCompleted ? "bg-green-500" : "bg-muted"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
