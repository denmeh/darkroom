import { useCallback, useEffect, useState } from "react"
import {
  AlertCircleIcon,
  Clock3,
  ScanSearch,
  UserRound,
} from "lucide-react"

import { Brand } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { getStatus, signOut, startLogin, type AppStatus } from "@/lib/api"
import { initials } from "@/lib/format"
import { cn } from "@/lib/utils"
import { AccountPage } from "@/pages/Account"
import { HistoryPage } from "@/pages/History"
import { AuthLayout, LoginForm } from "@/pages/Login"
import { ScanPage } from "@/pages/Scan"

type NavId = "scan" | "history" | "account"

const NAV: { id: NavId; label: string; icon: typeof ScanSearch }[] = [
  { id: "scan", label: "Scan", icon: ScanSearch },
  { id: "history", label: "History", icon: Clock3 },
  { id: "account", label: "Account", icon: UserRound },
]

function phaseFor(status: AppStatus): NavId {
  return status.logged_in ? "scan" : "account"
}

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [nav, setNav] = useState<NavId>("scan")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const refresh = useCallback(async () => {
    const next = await getStatus()
    setStatus(next)
    setLoadError(null)
    return next
  }, [])

  useEffect(() => {
    let cancelled = false
    getStatus()
      .then((next) => {
        if (cancelled) return
        setStatus(next)
        setNav(phaseFor(next))
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setLoadError(error instanceof Error ? error.message : "Failed to load")
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (status?.login.state !== "waiting") return
    const id = window.setInterval(() => {
      void refresh()
    }, 1000)
    return () => window.clearInterval(id)
  }, [status?.login.state, refresh])

  async function onSignOut() {
    setSigningOut(true)
    try {
      const next = await signOut()
      setStatus(next)
      setLoadError(null)
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "Sign out failed")
    } finally {
      setSigningOut(false)
    }
  }

  async function onLogin() {
    setStarting(true)
    try {
      const next = await startLogin()
      setStatus(next)
      setLoadError(null)
      if (next.logged_in) setNav("scan")
    } catch (error: unknown) {
      setLoadError(error instanceof Error ? error.message : "Login failed")
    } finally {
      setStarting(false)
    }
  }

  if (!status && !loadError) {
    return (
      <AuthLayout>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Spinner />
            </EmptyMedia>
            <EmptyTitle>Checking session</EmptyTitle>
            <EmptyDescription>
              Looking for a saved Instagram session on this machine.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </AuthLayout>
    )
  }

  if (!status) {
    return (
      <AuthLayout>
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Can&apos;t reach Darkroom</AlertTitle>
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
        <Button
          variant="outline"
          onClick={() => {
            void refresh().catch((error: unknown) => {
              setLoadError(
                error instanceof Error ? error.message : "Failed to load",
              )
            })
          }}
        >
          Try again
        </Button>
      </AuthLayout>
    )
  }

  if (!status.logged_in) {
    return (
      <AuthLayout>
        {loadError && (
          <Alert variant="destructive">
            <AlertCircleIcon />
            <AlertTitle>Login failed</AlertTitle>
            <AlertDescription>{loadError}</AlertDescription>
          </Alert>
        )}
        <LoginForm
          status={status}
          busy={starting}
          onLogin={() => void onLogin()}
        />
      </AuthLayout>
    )
  }

  return (
    <div className="flex min-h-svh">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
        <div className="flex h-14 items-center justify-between gap-2 px-4">
          <Brand />
          <ModeToggle />
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          {NAV.map((item) => (
            <Button
              key={item.id}
              variant="ghost"
              className={cn(
                "w-full justify-start",
                nav === item.id &&
                  "bg-sidebar-accent text-sidebar-accent-foreground",
              )}
              onClick={() => setNav(item.id)}
            >
              <item.icon />
              {item.label}
            </Button>
          ))}
        </nav>
        <div className="border-t p-2">
          <Button
            variant="ghost"
            className={cn(
              "h-auto w-full justify-start gap-2.5 px-2 py-2",
              nav === "account" &&
                "bg-sidebar-accent text-sidebar-accent-foreground",
            )}
            onClick={() => setNav("account")}
          >
            <Avatar size="sm">
              {status.me?.avatar_url ? (
                <AvatarImage src={status.me.avatar_url} alt="" />
              ) : null}
              <AvatarFallback>
                {initials(status.me?.full_name, status.username)}
              </AvatarFallback>
            </Avatar>
            <span className="flex min-w-0 flex-1 flex-col text-left">
              <span className="truncate text-sm font-medium">
                {status.me?.full_name || status.username || "Account"}
              </span>
              {status.username ? (
                <span className="truncate text-xs text-muted-foreground">
                  @{status.username}
                </span>
              ) : null}
            </span>
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col bg-background">
        <main className="mx-auto w-full max-w-5xl flex-1 p-6">
          {nav === "scan" && <ScanPage key={status.username ?? ""} />}
          {nav === "history" && <HistoryPage key={status.username ?? ""} />}
          {nav === "account" && (
            <AccountPage
              status={status}
              signingOut={signingOut}
              onSignOut={() => void onSignOut()}
            />
          )}
        </main>
      </div>
    </div>
  )
}
