"use client";

import { Clock3, LogOut, Mail, ShieldCheck, UserRound } from "lucide-react";
import type { User } from "@/types/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

type SessionPanelProps = {
  accessTimeLeft: string;
  isLoading: boolean;
  refreshTimeLeft: string;
  user: User;
  onLogout: () => void;
};

export function SessionPanel({ accessTimeLeft, isLoading, refreshTimeLeft, user, onLogout }: SessionPanelProps) {
  return (
    <aside className="lg:sticky lg:top-6 lg:h-fit">
      <Card className="h-fit overflow-hidden">
        <div className="h-1 bg-primary" />
        <CardHeader className="pb-4 sm:p-5 sm:pb-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="eyebrow text-primary">Operator online</p>
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-50" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary">
              <UserRound className="size-5 text-primary" />
            </span>
            <div className="min-w-0">
              <CardTitle className="truncate text-lg">{user.name}</CardTitle>
              <p className="mt-1 flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                <Mail className="size-3" />
                {user.email}
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="sm:px-5 sm:pb-5">
          <div className="mb-4 h-px bg-border/70" />
          <dl className="grid gap-2 text-sm">
            <div className="flex items-center gap-3 rounded-xl bg-background/60 p-3">
              <Clock3 className="size-4 shrink-0 text-primary" />
              <div>
                <dt className="text-xs font-bold text-foreground">Access token</dt>
                <dd className="mt-0.5 text-xs text-muted-foreground">Còn {accessTimeLeft}</dd>
              </div>
            </div>
            <div className="flex items-center gap-3 rounded-xl bg-background/60 p-3">
              <ShieldCheck className="size-4 shrink-0 text-primary" />
              <div>
                <dt className="text-xs font-bold text-foreground">Refresh token</dt>
                <dd className="mt-0.5 text-xs text-muted-foreground">Còn {refreshTimeLeft}</dd>
              </div>
            </div>
          </dl>

          <Button
            className="mt-5 w-full"
            variant="outline"
            type="button"
            onClick={onLogout}
            disabled={isLoading}
          >
            {isLoading && <Spinner data-icon="inline-start" />}
            {!isLoading && <LogOut />}
            {isLoading ? "Đang đăng xuất..." : "Kết thúc phiên"}
          </Button>
        </CardContent>
      </Card>
    </aside>
  );
}
