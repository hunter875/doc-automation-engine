"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuth } from "@/components/providers";
import { toast } from "sonner";

export default function LoginPage() {
  const { login, register } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError("");

    if (mode === "login") {
      const err = await login(email, password);
      setLoading(false);
      if (err) {
        setError("Sai email hoặc mật khẩu.");
      } else {
        toast.success("Đăng nhập thành công!");
        router.push("/");
      }
    } else {
      const err = await register(email, password);
      setLoading(false);
      if (err) {
        setError(err);
      } else {
        toast.success("Đăng ký thành công! Hãy đăng nhập.");
        setMode("login");
      }
    }
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1 text-center">
          <div className="flex justify-center mb-2">
            <FileText className="h-10 w-10 text-primary" />
          </div>
          <CardTitle className="text-2xl">Doc Automation</CardTitle>
          <CardDescription>
            {mode === "login" ? "Đăng nhập vào hệ thống" : "Tạo tài khoản mới"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="email@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Mật khẩu</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </div>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Đang xử lý…" : mode === "login" ? "Đăng nhập" : "Đăng ký"}
            </Button>

            <div className="text-center text-sm">
              {mode === "login" ? (
                <span>
                  Chưa có tài khoản?{" "}
                  <button
                    type="button"
                    className="text-primary underline underline-offset-2"
                    onClick={() => { setMode("register"); setError(""); }}
                  >
                    Đăng ký
                  </button>
                </span>
              ) : (
                <span>
                  Đã có tài khoản?{" "}
                  <button
                    type="button"
                    className="text-primary underline underline-offset-2"
                    onClick={() => { setMode("login"); setError(""); }}
                  >
                    Đăng nhập
                  </button>
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
