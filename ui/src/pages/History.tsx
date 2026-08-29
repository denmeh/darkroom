import { useEffect, useState } from "react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getScans, type ScanSummary } from "@/lib/api"

function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

export function HistoryPage() {
  const [scans, setScans] = useState<ScanSummary[] | null>(null)
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

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-xl font-medium tracking-tight">
          History
        </h1>
        <p className="max-w-xl text-sm text-muted-foreground">
          Every completed scan stores the full following and follower lists.
          Vanished accounts only appear once there is a previous snapshot to
          compare against.
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
              <TableRow key={scan.id}>
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
