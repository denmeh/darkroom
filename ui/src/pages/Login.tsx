import type { ReactNode } from "react"
import { AlertCircleIcon, Aperture, UserRoundPlus, X } from "lucide-react"

import { Brand } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
} from "@/components/ui/field"
import { Separator } from "@/components/ui/separator"
import { Spinner } from "@/components/ui/spinner"
import type { AppStatus, SavedSession } from "@/lib/api"
import { initials } from "@/lib/format"

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center gap-6 bg-background p-6 md:p-10">
      <div className="absolute top-4 right-4">
        <ModeToggle />
      </div>
      <div className="flex w-full max-w-md flex-col gap-6">
        <Brand className="self-center" />
        {children}
      </div>
    </div>
  )
}

type LoginFormProps = {
  status: AppStatus
  busy: boolean
  switchingPk: string | null
  forgettingPk: string | null
  onLogin: () => void
  onSwitch: (pk: string) => void
  onForget: (pk: string) => void
}

export function LoginForm({
  status,
  busy,
  switchingPk,
  forgettingPk,
  onLogin,
  onSwitch,
  onForget,
}: LoginFormProps) {
  const waiting = status.login.state === "waiting" || busy
  const switching = switchingPk != null
  const locked = waiting || switching || forgettingPk != null
  const error = status.login.state === "error" ? status.login.error : null
  const sessions = status.sessions ?? []
  const hasSessions = sessions.length > 0

  return (
    <div className="mx-auto flex w-full flex-col gap-6">
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">
            {hasSessions ? "Choose an account" : "Instagram login"}
          </CardTitle>
          <CardDescription>
            {hasSessions
              ? "Use a saved session on this machine, or sign in with a new account."
              : "A Chromium window will open. Sign in there; Darkroom waits for the session cookie and stores it on this machine."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              onLogin()
            }}
          >
            <FieldGroup>
              {waiting && (
                <Alert>
                  <Spinner />
                  <AlertTitle>Waiting for Instagram</AlertTitle>
                  <AlertDescription>
                    Finish signing in in the browser window. This page updates
                    when the session is saved.
                  </AlertDescription>
                </Alert>
              )}
              {error && (
                <Alert variant="destructive">
                  <AlertCircleIcon />
                  <AlertTitle>Login failed</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              {hasSessions ? (
                <Field>
                  <div className="flex flex-col gap-2">
                    {sessions.map((session) => (
                      <SavedAccountRow
                        key={session.pk}
                        session={session}
                        disabled={locked}
                        switching={switchingPk === session.pk}
                        forgetting={forgettingPk === session.pk}
                        onSwitch={() => onSwitch(session.pk)}
                        onForget={() => onForget(session.pk)}
                      />
                    ))}
                  </div>
                </Field>
              ) : null}
              {hasSessions ? (
                <div className="flex items-center gap-3">
                  <Separator className="flex-1" />
                  <span className="text-xs text-muted-foreground">or</span>
                  <Separator className="flex-1" />
                </div>
              ) : null}
              <Field>
                <Button type="submit" disabled={locked}>
                  {waiting ? <Spinner /> : hasSessions ? <UserRoundPlus /> : <Aperture />}
                  {hasSessions ? "Add another account" : "Continue in browser"}
                </Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription className="px-6 text-center break-all">
        Sessions folder: {status.session_path}
      </FieldDescription>
    </div>
  )
}

function SavedAccountRow({
  session,
  disabled,
  switching,
  forgetting,
  onSwitch,
  onForget,
}: {
  session: SavedSession
  disabled: boolean
  switching: boolean
  forgetting: boolean
  onSwitch: () => void
  onForget: () => void
}) {
  const label =
    session.full_name ||
    (session.username ? `@${session.username}` : `Account ${session.pk}`)
  const handle = session.username ? `@${session.username}` : null

  return (
    <div className="flex items-center gap-1">
      <Button
        type="button"
        variant="outline"
        className="h-auto min-w-0 flex-1 justify-start gap-2.5 px-2 py-2"
        disabled={disabled}
        onClick={onSwitch}
      >
        <Avatar size="sm">
          {session.avatar_url ? (
            <AvatarImage src={session.avatar_url} alt="" />
          ) : null}
          <AvatarFallback>
            {initials(session.full_name, session.username)}
          </AvatarFallback>
        </Avatar>
        <span className="flex min-w-0 flex-1 flex-col text-left">
          <span className="truncate text-sm font-medium">{label}</span>
          {handle && session.full_name ? (
            <span className="truncate text-xs text-muted-foreground">
              {handle}
            </span>
          ) : null}
        </span>
        {switching ? <Spinner /> : null}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        disabled={disabled}
        aria-label={
          session.username
            ? `Remove @${session.username}`
            : "Remove saved account"
        }
        onClick={onForget}
      >
        {forgetting ? <Spinner /> : <X />}
      </Button>
    </div>
  )
}
