import { useCallback, useEffect, useState } from "react"
import {
  AlertCircleIcon,
  BadgeCheck,
  Ghost,
  Lock,
  ScanSearch,
  UserMinus,
  UserPlus,
  Users,
} from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  getReport,
  getReportUsers,
  getScan,
  startScan,
  stopScan,
  type Account,
  type ListKind,
  type Report,
  type ScanStatus,
} from "@/lib/api"

function formatWait(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, "0")}`
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

function phaseLabel(scan: ScanStatus): string {
  if (scan.state === "waiting") {
    return `Waiting ${formatWait(scan.wait_seconds ?? 0)}`
  }
  if (scan.phase === "following") {
    return `Following ${scan.following_fetched.toLocaleString()}${
      scan.following_total != null ? ` / ~${scan.following_total.toLocaleString()}` : ""
    }`
  }
  if (scan.phase === "followers") {
    return `Followers ${scan.followers_fetched.toLocaleString()}${
      scan.followers_total != null ? ` / ~${scan.followers_total.toLocaleString()}` : ""
    }`
  }
  if (scan.phase === "comparing") return "Comparing snapshots"
  if (scan.state === "running") return "Starting"
  return ""
}

const LISTS: { kind: ListKind; label: string }[] = [
  { kind: "unfollowers", label: "Unfollowers" },
  { kind: "vanished", label: "Vanished" },
  { kind: "new_following", label: "New" },
  { kind: "following", label: "Following" },
  { kind: "followers", label: "Followers" },
]

function initials(user: Account): string {
  const source = (user.full_name || user.username || "?").trim()
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) {
    return (parts[0]![0]! + parts[1]![0]!).toUpperCase()
  }
  return source.slice(0, 1).toUpperCase()
}

function UserTable({ users }: { users: Account[] }) {
  if (users.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Nothing in this list yet.
      </p>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Username</TableHead>
          <TableHead>Name</TableHead>
          <TableHead className="w-[1%]"></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((user) => (
          <TableRow key={user.pk}>
            <TableCell className="font-medium">
              <div className="flex items-center gap-2.5">
                <Avatar size="sm">
                  {user.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt="" />
                  ) : null}
                  <AvatarFallback>{initials(user)}</AvatarFallback>
                </Avatar>
                <span>@{user.username ?? user.pk}</span>
              </div>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {user.full_name || "—"}
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
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
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export function ScanPage() {
  const [scan, setScan] = useState<ScanStatus | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [kind, setKind] = useState<ListKind>("unfollowers")
  const [users, setUsers] = useState<Account[]>([])
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  const refresh = useCallback(async () => {
    const [nextScan, nextReport] = await Promise.all([getScan(), getReport()])
    setScan(nextScan)
    setReport(nextReport)
    setError(null)
    return nextScan
  }, [])

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Failed to load")
    })
  }, [refresh])

  const active = scan?.state === "running" || scan?.state === "waiting"

  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => {
      void refresh()
    }, 1000)
    return () => window.clearInterval(id)
  }, [active, refresh])

  useEffect(() => {
    if (active) return
    let cancelled = false
    getReportUsers(kind, 0, 100)
      .then((page) => {
        if (cancelled) return
        setUsers(page.users)
        setTotal(page.total)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Failed to load list")
      })
    return () => {
      cancelled = true
    }
  }, [kind, active, report?.latest?.id])

  async function onScan() {
    setStarting(true)
    try {
      setScan(await startScan())
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Scan failed")
    } finally {
      setStarting(false)
    }
  }

  async function onStop() {
    try {
      setScan(await stopScan())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Stop failed")
    }
  }

  const counts = report?.counts
  const scanError = scan?.state === "error" ? scan.error : null
  const idleNote =
    scan?.state === "idle" && scan.error ? scan.error : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="font-heading text-xl font-medium tracking-tight">
            Scan
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            Walks your following and your followers, slowly. Unfollowers are
            people you follow who do not follow you back. Vanished accounts
            were on the previous following list and are gone now — they
            blocked you, deactivated, or you unfollowed.
          </p>
        </div>
        {active ? (
          <Button variant="outline" onClick={() => void onStop()}>
            Stop
          </Button>
        ) : (
          <Button disabled={starting} onClick={() => void onScan()}>
            {starting ? <Spinner /> : <ScanSearch />}
            Run scan
          </Button>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Request failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {scanError && (
        <Alert variant="destructive">
          <AlertCircleIcon />
          <AlertTitle>Scan failed</AlertTitle>
          <AlertDescription>{scanError}</AlertDescription>
        </Alert>
      )}
      {idleNote && (
        <Alert>
          <AlertCircleIcon />
          <AlertTitle>Incomplete</AlertTitle>
          <AlertDescription>{idleNote}</AlertDescription>
        </Alert>
      )}

      {active && scan && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Spinner />
              {phaseLabel(scan)}
            </CardTitle>
            <CardDescription>
              Pages are saved to SQLite as they arrive. If this stops, run
              scan again to resume.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={UserMinus}
          label="Unfollowers"
          value={counts?.unfollowers ?? 0}
          hint="You follow them; they don't follow you"
        />
        <StatCard
          icon={Ghost}
          label="Vanished"
          value={counts?.vanished ?? 0}
          hint="On the last following list, missing now"
        />
        <StatCard
          icon={Users}
          label="Following"
          value={counts?.following ?? 0}
          hint="Current following snapshot"
        />
        <StatCard
          icon={UserPlus}
          label="New"
          value={counts?.new_following ?? 0}
          hint="Added since the previous scan"
        />
      </div>

      {report?.latest && (
        <p className="text-xs text-muted-foreground">
          Last complete scan {formatWhen(report.latest.finished_at)}
          {report.previous
            ? ` · compared with ${formatWhen(report.previous.finished_at)}`
            : " · first snapshot, so vanished is empty"}
        </p>
      )}

      <Card>
        <CardContent>
          <Tabs
            value={kind}
            onValueChange={(value) => setKind(value as ListKind)}
          >
            <TabsList>
              {LISTS.map((item) => (
                <TabsTrigger key={item.kind} value={item.kind}>
                  {item.label}
                  {item.kind === "unfollowers" && counts
                    ? ` ${counts.unfollowers}`
                    : null}
                  {item.kind === "vanished" && counts
                    ? ` ${counts.vanished}`
                    : null}
                </TabsTrigger>
              ))}
            </TabsList>
            {LISTS.map((item) => (
              <TabsContent key={item.kind} value={item.kind}>
                <UserTable users={kind === item.kind ? users : []} />
                {kind === item.kind && total > users.length && (
                  <p className="pt-3 text-sm text-muted-foreground">
                    Showing {users.length} of {total}.
                  </p>
                )}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof Users
  label: string
  value: number
  hint: string
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <CardDescription>{label}</CardDescription>
          <CardTitle className="text-2xl tabular-nums">
            {value.toLocaleString()}
          </CardTitle>
        </div>
        <div className="flex size-8 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="size-4" />
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}
