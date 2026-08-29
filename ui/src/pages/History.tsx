import { useEffect, useState } from "react"
import { AlertCircleIcon, ArrowLeft } from "lucide-react"

import { UserLists } from "@/components/user-lists"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatWhen } from "@/lib/format"
import {
  getScans,
  type ReportCounts,
  type ScanSummary,
} from "@/lib/api"

function countsFrom(scan: ScanSummary): ReportCounts {
  return {
    following: scan.following_fetched,
    followers: scan.followers_fetched,
    unfollowers: scan.unfollowers_count ?? 0,
    vanished: scan.vanished_count ?? 0,
    new_following: scan.new_following_count ?? 0,
  }
}

export function HistoryPage() {
  const [scans, setScans] = useState<ScanSummary[] | null>(null)
  const [selected, setSelected] = useState<ScanSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getScans()
      .then((rows) => {
        if (!cancelled) setScans(rows)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (selected) {
    const incomplete = selected.state !== "done"
    return (
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Button
            variant="ghost"
            className="-ml-2 w-fit"
            onClick={() => setSelected(null)}
          >
            <ArrowLeft />
            All scans
          </Button>
          <div className="flex flex-col gap-1">
            <h1 className="font-heading text-xl font-medium tracking-tight">
              Scan {formatWhen(selected.finished_at ?? selected.started_at)}
            </h1>
            <p className="max-w-xl text-sm text-muted-foreground">
              Following {selected.following_fetched.toLocaleString()}
              {" · "}
              Followers {selected.followers_fetched.toLocaleString()}
              {" · "}
              Unfollowers {(selected.unfollowers_count ?? 0).toLocaleString()}
              {" · "}
              Vanished {(selected.vanished_count ?? 0).toLocaleString()}
              {" · "}
              New {(selected.new_following_count ?? 0).toLocaleString()}
            </p>
          </div>
        </div>

        {incomplete && (
          <Alert>
            <AlertCircleIcon />
            <AlertTitle>Incomplete scan</AlertTitle>
            <AlertDescription>
              This scan did not finish. Following and follower lists may be
              partial; unfollower and vanished counts are only written when a
              scan completes.
            </AlertDescription>
          </Alert>
        )}

        <UserLists scanId={selected.id} counts={countsFrom(selected)} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-xl font-medium tracking-tight">
          History
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Every completed scan stores the full following and follower lists.
          Open a row to search that snapshot. Vanished accounts only appear
          once there is a previous snapshot to compare against.
        </p>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      <div className="overflow-hidden rounded-xl border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Finished</TableHead>
              <TableHead>State</TableHead>
              <TableHead className="text-right">Following</TableHead>
              <TableHead className="text-right">Followers</TableHead>
              <TableHead className="text-right">Unfollowers</TableHead>
              <TableHead className="text-right">Vanished</TableHead>
              <TableHead className="text-right">New</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(scans ?? []).map((scan) => (
              <TableRow
                key={scan.id}
                className="cursor-pointer"
                tabIndex={0}
                aria-label={`View scan from ${formatWhen(scan.finished_at ?? scan.started_at)}`}
                onClick={() => setSelected(scan)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    setSelected(scan)
                  }
                }}
              >
                <TableCell>{formatWhen(scan.finished_at ?? scan.started_at)}</TableCell>
                <TableCell className="capitalize">{scan.state}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {scan.following_fetched.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {scan.followers_fetched.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {scan.unfollowers_count ?? "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {scan.vanished_count ?? "—"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {scan.new_following_count ?? "—"}
                </TableCell>
              </TableRow>
            ))}
            {scans && scans.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-muted-foreground">
                  No scans yet.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
