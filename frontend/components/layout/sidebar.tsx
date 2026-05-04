"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  Settings2,
  FileText,
  LogOut,
  Building2,
  ChevronDown,
  Plus,
  Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/components/providers";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { toast } from "sonner";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/reports/daily", label: "Báo cáo ngày", icon: Calendar },
  { href: "/extraction", label: "Trích xuất dữ liệu", icon: Settings2 },
  { href: "/documents", label: "Tài liệu", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();
  const { email, tenantId, tenantList, isLoggedIn, logout, selectTenant, createTenant, reloadTenants } =
    useAuth();

  const [newTenantOpen, setNewTenantOpen] = useState(false);
  const [newTenantName, setNewTenantName] = useState("");
  const [creating, setCreating] = useState(false);

  const currentTenant = tenantList.find((t) => t.id === tenantId);

  async function handleCreateTenant() {
    if (!newTenantName.trim()) return;
    setCreating(true);
    const err = await createTenant(newTenantName.trim());
    setCreating(false);
    if (err) {
      toast.error(`Tạo tổ chức thất bại: ${err}`);
    } else {
      toast.success("Tạo tổ chức thành công!");
      setNewTenantOpen(false);
      setNewTenantName("");
    }
  }

  return (
    <>
      <aside className="flex h-screen w-64 flex-col border-r bg-background">
        {/* Logo */}
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <FileText className="h-6 w-6 text-primary" />
          <span className="text-lg font-semibold">Doc Automation</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={isLoggedIn ? href : "/login"}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        {/* Bottom: tenant + user */}
        {isLoggedIn && (
          <div className="border-t p-3 space-y-2">
            {/* Tenant selector */}
            <div className="flex items-center gap-1">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="w-full justify-between text-xs">
                    <span className="flex items-center gap-1.5 truncate">
                      <Building2 className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{currentTenant?.name ?? "Chọn tổ chức"}</span>
                    </span>
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent className="w-56">
                  <DropdownMenuLabel>Tổ chức</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {tenantList.map((t) => (
                    <DropdownMenuItem
                      key={t.id}
                      onClick={() => selectTenant(t.id)}
                      className={cn(t.id === tenantId && "bg-accent")}
                    >
                      {t.name}
                    </DropdownMenuItem>
                  ))}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => reloadTenants()}>
                    🔄 Tải lại danh sách
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setNewTenantOpen(true)}>
                    <Plus className="h-4 w-4 mr-1" /> Tạo tổ chức mới
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* User + logout */}
            <div className="flex items-center justify-between rounded-md px-2 py-1.5">
              <span className="text-xs text-muted-foreground truncate">{email}</span>
              <div className="flex items-center gap-0.5 shrink-0">
                <ThemeToggle />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={logout}
                  title="Đăng xuất"
                >
                  <LogOut className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
        )}

        {!isLoggedIn && (
          <div className="border-t p-3">
            <Link href="/login">
              <Button className="w-full" size="sm">
                Đăng nhập
              </Button>
            </Link>
          </div>
        )}
      </aside>

      {/* Create tenant dialog */}
      <Dialog open={newTenantOpen} onOpenChange={setNewTenantOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tạo tổ chức mới</DialogTitle>
            <DialogDescription>
              Tạo tenant mới để tách dữ liệu và thao tác theo từng tổ chức.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="new-tenant-name">Tên tổ chức</Label>
            <Input
              id="new-tenant-name"
              value={newTenantName}
              onChange={(e) => setNewTenantName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreateTenant()}
              placeholder="Ví dụ: Phòng CSPCCC quận 3"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setNewTenantOpen(false)}>
              Huỷ
            </Button>
            <Button onClick={handleCreateTenant} disabled={creating || !newTenantName.trim()}>
              {creating ? "Đang tạo…" : "Tạo"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
