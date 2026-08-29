import { useEffect, useState } from "react"
import { BadgeCheck, ExternalLink, Lock, Search } from "lucide-react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
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
  getReportUsers,
  openProfile,
  type Account,
  type ListKind,
  type ReportCounts,
} from "@/lib/api"
import { initials } from "@/lib/format"

const LISTS: { kind: ListKind; label: string; countKey: keyof ReportCounts }[] =
  [
    { kind: "unfollowers", label: "Unfollowers", countKey: "unfollowers" },
    { kind: "vanished", label: "Vanished", countKey: "vanished" },
    { kind: "new_following", label: "New", countKey: "new_following" },
    { kind: "following", label: "Following", countKey: "following" },
    { kind: "followers", label: "Followers", countKey: "followers" },
  ]

function UserTable({
  users,
  query,
  onError,
}: {
  users: Account[]
  query: string
  onError: (message: string) => void
}) {
  if (users.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {query ? `No matches for "${query}".` : "Nothing in this list yet."}
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
                  <AvatarFallback>
                    {initials(user.full_name, user.username)}
                  </AvatarFallback>
                </Avatar>
                {user.username ? (
                  <button
                    type="button"
                    className="group inline-flex cursor-pointer items-center gap-1 bg-transparent p-0 font-medium hover:underline"
                    onClick={() => {
                      void openProfile(user.username!).catch(
                        (error: unknown) => {
                          onError(
                            error instanceof Error
                              ? error.message
                              : "Could not open profile",
                          )
                        },
                      )
                    }}
                  >
                    @{user.username}
                    <ExternalLink className="size-3 opacity-0 transition-opacity group-hover:opacity-50" />
                  </button>
                ) : (
                  <span>@{user.pk}</span>
                )}
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

export function UserLists({
  scanId,
  counts,
  paused = false,
}: {
  scanId?: number | null
  counts?: ReportCounts | null
  paused?: boolean
}) {
  const [kind, setKind] = useState<ListKind>("unfollowers")
  const [query, setQuery] = useState("")
  const [debounced, setDebounced] = useState("")
  const [users, setUsers] = useState<Account[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(query.trim()), 250)
    return () => window.clearTimeout(id)
  }, [query])

  useEffect(() => {
    if (paused) return
    let cancelled = false
    setLoading(true)
    setUsers([])
    getReportUsers(kind, 0, 100, scanId, debounced || undefined)
      .then((page) => {
        if (cancelled) return
        setUsers(page.users)
        setTotal(page.total)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(err instanceof Error ? err.message : "Failed to load list")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [kind, scanId, debounced, paused])

  async function onMore() {
    const forKind = kind
    const forQuery = debounced
    const forScan = scanId
    const offset = users.length
    setLoadingMore(true)
    try {
      const page = await getReportUsers(
        forKind,
        offset,
        100,
        forScan,
        forQuery || undefined,
      )
      if (kind !== forKind || debounced !== forQuery || scanId !== forScan) {
        return
      }
      setUsers((prev) => [...prev, ...page.users])
      setTotal(page.total)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load more")
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4">
        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}
        <Tabs
          value={kind}
          onValueChange={(value) => setKind(value as ListKind)}
        >
          <TabsList>
            {LISTS.map((item) => (
              <TabsTrigger key={item.kind} value={item.kind}>
                {item.label}
                {counts != null
                  ? ` ${counts[item.countKey].toLocaleString()}`
                  : null}
              </TabsTrigger>
            ))}
          </TabsList>
          <div className="relative max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search username or name"
                className="pl-8"
                autoComplete="off"
                aria-label="Search this list"
              />
          </div>
          {LISTS.map((item) => (
            <TabsContent key={item.kind} value={item.kind}>
              {loading && kind === item.kind ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : (
                <UserTable
                  users={kind === item.kind ? users : []}
                  query={kind === item.kind ? debounced : ""}
                  onError={setError}
                />
              )}
              {kind === item.kind && !loading && total > users.length && (
                <div className="flex flex-col items-center gap-2 pt-3">
                  <p className="text-sm text-muted-foreground">
                    Showing {users.length} of {total}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={loadingMore}
                    onClick={() => void onMore()}
                  >
                    {loadingMore ? <Spinner /> : null}
                    Load more
                  </Button>
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}
