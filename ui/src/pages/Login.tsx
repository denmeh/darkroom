import type { ReactNode } from "react"
import { AlertCircleIcon, Aperture, CheckCircle2Icon, LogOut } from "lucide-react"

import { Brand } from "@/components/brand"
import { ModeToggle } from "@/components/mode-toggle"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
} from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import type { AppStatus } from "@/lib/api"

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="absolute top-4 right-4">
        <ModeToggle />
      </div>
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Brand className="self-center" />
        {children}
      </div>
    </div>
  )
}

type LoginFormProps = {
  status: AppStatus
  busy: boolean
  onLogin: () => void
  onSignOut?: () => void
  signingOut?: boolean
}

export function LoginForm({
  status,
  busy,
  onLogin,
  onSignOut,
  signingOut = false,
}: LoginFormProps) {
  const waiting = status.login.state === "waiting" || busy
  const error = status.login.state === "error" ? status.login.error : null

  if (status.logged_in) {
    return (
      <Card className="mx-auto w-full max-w-sm">
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Signed in</CardTitle>
          <CardDescription>
            Session saved. Run a scan to snapshot following and find
            unfollowers.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup>
            <Alert>
              <CheckCircle2Icon />
              <AlertTitle>
                Logged in as {status.username ?? "unknown"}
              </AlertTitle>
              <AlertDescription className="font-mono break-all">
                {status.session_path}
              </AlertDescription>
            </Alert>
          </FieldGroup>
        </CardContent>
        {onSignOut ? (
          <CardFooter>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              disabled={signingOut}
              onClick={onSignOut}
            >
              {signingOut ? <Spinner /> : <LogOut />}
              Sign out
            </Button>
          </CardFooter>
        ) : null}
      </Card>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-sm flex-col gap-6">
      <Card>
        <CardHeader className="text-center">
          <CardTitle className="text-xl">Instagram login</CardTitle>
          <CardDescription>
            A Chromium window will open. Sign in there; Darkroom waits for the
            session cookie and stores it on this machine.
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
              <Field>
                <Button type="submit" disabled={waiting}>
                  {waiting ? <Spinner /> : <Aperture />}
                  Continue in browser
                </Button>
              </Field>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      <FieldDescription className="px-6 text-center break-all">
        Session file: {status.session_path}
      </FieldDescription>
    </div>
  )
}
