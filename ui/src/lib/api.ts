export type LoginState = "idle" | "waiting" | "done" | "error"

export type AppStatus = {
  logged_in: boolean
  username: string | null
  session_path: string
  login: {
    state: LoginState
    error: string | null
  }
}

export type ScanState = "idle" | "running" | "waiting" | "done" | "error"
export type ScanPhase = "following" | "followers" | "comparing" | null

export type ScanStatus = {
  state: ScanState
  phase: ScanPhase
  scan_id: number | null
  wait_seconds: number | null
  following_fetched: number
  following_total: number | null
  followers_fetched: number
  followers_total: number | null
  error: string | null
}

export type ScanSummary = {
  id: number
  started_at: string
  finished_at: string | null
  state: string
  following_fetched: number
  followers_fetched: number
  unfollowers_count: number | null
  vanished_count: number | null
  new_following_count: number | null
}

export type ReportCounts = {
  following: number
  followers: number
  unfollowers: number
  vanished: number
  new_following: number
}

export type Report = {
  latest: ScanSummary | null
  previous: ScanSummary | null
  counts: ReportCounts
}

export type Account = {
  pk: string
  username: string | null
  full_name: string | null
  is_private: boolean | null
  is_verified: boolean | null
  avatar_url: string | null
}

export type ListKind =
  | "unfollowers"
  | "vanished"
  | "new_following"
  | "following"
  | "followers"

export type UserPage = {
  kind: ListKind
  total: number
  offset: number
  users: Account[]
}

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail: string | undefined
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === "string") {
        detail = body.detail
      }
    } catch {
      // ignore
    }
    throw new Error(detail ?? `Request failed (${response.status})`)
  }
  return (await response.json()) as T
}

export async function getStatus(): Promise<AppStatus> {
  return parseJson<AppStatus>(await fetch("/api/status"))
}

export async function startLogin(): Promise<AppStatus> {
  const response = await fetch("/api/login", { method: "POST" })
  if (response.status === 409) {
    return getStatus()
  }
  return parseJson<AppStatus>(response)
}

export async function signOut(): Promise<AppStatus> {
  return parseJson<AppStatus>(await fetch("/api/logout", { method: "POST" }))
}

export async function getScan(): Promise<ScanStatus> {
  return parseJson<ScanStatus>(await fetch("/api/scan"))
}

export async function startScan(): Promise<ScanStatus> {
  const response = await fetch("/api/scan", { method: "POST" })
  if (response.status === 409) {
    return getScan()
  }
  return parseJson<ScanStatus>(response)
}

export async function stopScan(): Promise<ScanStatus> {
  return parseJson<ScanStatus>(await fetch("/api/scan/stop", { method: "POST" }))
}

export async function getReport(): Promise<Report> {
  return parseJson<Report>(await fetch("/api/report"))
}

export async function getScans(): Promise<ScanSummary[]> {
  return parseJson<ScanSummary[]>(await fetch("/api/scans"))
}

export async function getReportUsers(
  kind: ListKind,
  offset = 0,
  limit = 100,
): Promise<UserPage> {
  const params = new URLSearchParams({
    kind,
    offset: String(offset),
    limit: String(limit),
  })
  return parseJson<UserPage>(await fetch(`/api/report/users?${params}`))
}
