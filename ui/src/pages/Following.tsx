import { useCallback, useEffect, useState } from "react"
import {
  AlertCircleIcon,
  BadgeCheck,
  CheckCircle2Icon,
  Lock,
  Users,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
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
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  getFollowing,
  startFollowing,
  stopFollowing,
  type FollowingStatus,
} from "@/lib/api"

const LIST_CAP = 500

function formatWait(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}

function progressPercent(job: FollowingStatus): number {
  if (!job.total || job.total <= 0) return 0
  return Math.min(100, (job.fetched / job.total) * 100)
}

export function FollowingPage() {
  const [username, setUsername] = useState("")
  const [job, setJob] = useState<FollowingStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refresh = useCallback(async () => {
    const next = await getFollowing()
    setJob(next)
    setError(null)
    return next
  }, [])

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load")
    })
  }, [refresh])

  const active = job?.state === "running" || job?.state === "waiting"

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void refresh()
    }, 1000)
    return () => window.clearInterval(id)
  }, [active, refresh])

  async function onFetch() {
    setStarting(true)
    try {
      const next = await startFollowing(username)
      setJob(next)
      setError(null)
      if (next.username) setUsername(next.username)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Fetch failed")
    } finally {
      setStarting(false)
    }
  }

  async function onStop() {
    try {
      const next = await stopFollowing()
      setJob(next)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Stop failed")
    }
  }

  const busy = starting || active
  const visible = job?.users.slice(0, LIST_CAP) ?? []
  const extra =
    job && job.state !== "running" && job.state !== "waiting"
      ? Math.max(0, job.users.length - LIST_CAP)
      : 0
  const pct = job ? progressPercent(job) : 0
  const jobError = job?.state === "error" ? job.error : null
  const stopNote = job?.state === "idle" ? job.error : null
  const emptyPrivate = job?.state === "done" && job.error && job.fetched === 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Following</CardTitle>
        <CardDescription>
          Type an Instagram username. Darkroom walks their following list a page
          at a time, with pauses between requests so Instagram is less likely to
          rate-limit the session.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (!busy) void onFetch()
          }}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="following-username">Username</FieldLabel>
              <div className="flex gap-2">
                <div className="relative min-w-0 flex-1">
                  <span className="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-sm text-muted-foreground">
                    @
                  </span>
                  <Input
                    id="following-username"
                    name="username"
                    autoComplete="off"
                    spellCheck={false}
                    placeholder="username"
                    value={username}
                    disabled={busy}
                    className="pl-6"
                    onChange={(event) => setUsername(event.target.value)}
                  />
                </div>
                {active ? (
                  <Button type="button" variant="outline" onClick={() => void onStop()}>
                    Stop
                  </Button>
                ) : (
                  <Button type="submit" disabled={starting || !username.trim()}>
                    {starting ? <Spinner /> : <Users />}
                    Fetch
                  </Button>
                )}
              </div>
              <FieldDescription>
                Only the fields Instagram exposes on the following list: pk,
                username, name, private, verified. Progress is saved to disk
                and resumes if you fetch the same username again.
              </FieldDescription>
            </Field>

            {error && (
              <Alert variant="destructive">
                <AlertCircleIcon />
                <AlertTitle>Request failed</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {jobError && (
              <Alert variant="destructive">
                <AlertCircleIcon />
                <AlertTitle>Fetch failed</AlertTitle>
                <AlertDescription>{jobError}</AlertDescription>
              </Alert>
            )}

            {emptyPrivate && (
              <Alert>
                <Lock />
                <AlertTitle>Private account</AlertTitle>
                <AlertDescription>{job.error}</AlertDescription>
              </Alert>
            )}

            {stopNote && (
              <Alert>
                <AlertCircleIcon />
                <AlertTitle>Stopped</AlertTitle>
                <AlertDescription>{stopNote}</AlertDescription>
              </Alert>
            )}

            {job && (active || job.state === "done" || job.fetched > 0) && (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {job.state === "waiting" ? (
                    <Badge variant="secondary">
                      <Spinner />
                      Waiting {formatWait(job.wait_seconds ?? 0)}
                    </Badge>
                  ) : job.state === "running" ? (
                    <Badge variant="secondary">
                      <Spinner />
                      Fetching
                    </Badge>
                  ) : job.state === "done" ? (
                    <Badge variant="secondary">
                      <CheckCircle2Icon />
                      Done
                    </Badge>
                  ) : null}
                  {job.username && (
                    <Badge variant="outline">@{job.username}</Badge>
                  )}
                  {job.is_private && (
                    <Badge variant="outline">
                      <Lock />
                      Private
                    </Badge>
                  )}
                  {job.resumed && active && (
                    <Badge variant="outline">Resumed</Badge>
                  )}
                </div>

                <div className="flex flex-col gap-1.5">
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(pct)}
                  >
                    <div
                      className={`h-full bg-primary transition-all ${
                        active && !job.total ? "w-1/3 animate-pulse" : ""
                      }`}
                      style={
                        job.total
                          ? { width: `${pct}%` }
                          : active
                            ? undefined
                            : { width: "100%" }
                      }
                    />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {job.fetched.toLocaleString()}
                    {job.total != null
                      ? ` of ~${job.total.toLocaleString()}`
                      : ""}{" "}
                    following
                    {job.state === "waiting"
                      ? " — Instagram asked for a pause; retrying automatically."
                      : null}
                  </p>
                </div>

                {visible.length > 0 && (
                  <ul className="max-h-72 divide-y overflow-y-auto rounded-lg border">
                    {visible.map((user) => (
                      <li
                        key={user.pk}
                        className="flex items-center justify-between gap-3 px-3 py-2"
                      >
                        <div className="min-w-0">
                          <div className="truncate font-medium">
                            @{user.username ?? user.pk}
                          </div>
                          {user.full_name ? (
                            <div className="truncate text-muted-foreground">
                              {user.full_name}
                            </div>
                          ) : null}
                        </div>
                        <div className="flex shrink-0 gap-1">
                          {user.is_private ? (
                            <Badge variant="outline">
                              <Lock />
                              Private
                            </Badge>
                          ) : null}
                          {user.is_verified ? (
                            <Badge variant="outline">
                              <BadgeCheck />
                              Verified
                            </Badge>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}

                {active && job.fetched > visible.length && (
                  <p className="text-sm text-muted-foreground">
                    Showing the latest {visible.length} of {job.fetched}.
                  </p>
                )}
                {extra > 0 && (
                  <p className="text-sm text-muted-foreground">
                    Showing {LIST_CAP} of {job.users.length}. The rest is in the
                    saved file.
                  </p>
                )}
              </div>
            )}
          </FieldGroup>
        </form>
      </CardContent>
      {job?.path && (
        <CardFooter>
          <p className="font-mono text-xs break-all text-muted-foreground">
            {job.path}
          </p>
        </CardFooter>
      )}
    </Card>
  )
}
