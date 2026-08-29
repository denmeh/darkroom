import { useCallback, useEffect, useState } from "react"
import { AlertCircleIcon } from "lucide-react"

import { Brand } from "@/components/brand"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { getStatus, startLogin, type AppStatus } from "@/lib/api"
import { AuthLayout, LoginForm } from "@/pages/Login"
import { PlaceholderPage } from "@/pages/Placeholder"

type PhaseId = "login" | "phase-2" | "phase-3"

function phaseFor(status: AppStatus): PhaseId {
  return status.logged_in ? "phase-2" : "login"
}

export default function App() {
  const [status, setStatus] = useState<AppStatus | null>(null)
  const [phase, setPhase] = useState<PhaseId>("login")
  const [loadError, setLoadError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refresh = useCallback(async () => {
    const next = await getStatus()
    setStatus(next)
    setLoadError(null)
    if (next.logged_in) {
      setPhase((current) => (current === "login" ? "phase-2" : current))
    }
    return next
  }, [])

  useEffect(() => {
    let cancelled = false
    getStatus()
      .then((next) => {
        if (cancelled) return
        setStatus(next)
        setPhase(phaseFor(next))
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

  async function onLogin() {
    setStarting(true)
    try {
      const next = await startLogin()
      setStatus(next)
      setLoadError(null)
      if (next.logged_in) {
        setPhase((current) => (current === "login" ? "phase-2" : current))
      }
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
    <div className="flex min-h-svh flex-col">
      <header className="flex h-14 shrink-0 items-center border-b">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between px-6">
          <Brand />
          {status.login.state === "waiting" ? (
            <Badge variant="secondary">
              <Spinner />
              Waiting
            </Badge>
          ) : (
            <Badge variant="secondary">@{status.username}</Badge>
          )}
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col p-6">
        <Tabs
          value={phase}
          onValueChange={(value) => setPhase(value as PhaseId)}
        >
          <TabsList className="w-full">
            <TabsTrigger value="login">Login</TabsTrigger>
            <TabsTrigger value="phase-2">Phase 2</TabsTrigger>
            <TabsTrigger value="phase-3">Phase 3</TabsTrigger>
          </TabsList>
          <TabsContent value="login">
            <LoginForm
              status={status}
              busy={starting}
              onLogin={() => void onLogin()}
            />
          </TabsContent>
          <TabsContent value="phase-2">
            <PlaceholderPage title="Phase 2" phase={2} />
          </TabsContent>
          <TabsContent value="phase-3">
            <PlaceholderPage title="Phase 3" phase={3} />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}
