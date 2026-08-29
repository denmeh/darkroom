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

export type FollowingState = "idle" | "running" | "waiting" | "done" | "error"

export type FollowingUser = {
  pk: string
  username: string | null
  full_name: string | null
  is_private: boolean | null
  is_verified: boolean | null
}

export type FollowingStatus = {
  state: FollowingState
  username: string | null
  user_id: string | null
  fetched: number
  total: number | null
  wait_seconds: number | null
  error: string | null
  path: string | null
  resumed: boolean
  is_private: boolean
  users: FollowingUser[]
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

async function parseStatus(response: Response): Promise<AppStatus> {
  return parseJson<AppStatus>(response)
}

export async function getStatus(): Promise<AppStatus> {
  return parseStatus(await fetch("/api/status"))
}

export async function startLogin(): Promise<AppStatus> {
  const response = await fetch("/api/login", { method: "POST" })
  if (response.status === 409) {
    return getStatus()
  }
  return parseStatus(response)
}

export async function getFollowing(): Promise<FollowingStatus> {
  return parseJson<FollowingStatus>(await fetch("/api/following"))
}

export async function startFollowing(username: string): Promise<FollowingStatus> {
  const response = await fetch("/api/following", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  })
  if (response.status === 409) {
    return getFollowing()
  }
  return parseJson<FollowingStatus>(response)
}

export async function stopFollowing(): Promise<FollowingStatus> {
  return parseJson<FollowingStatus>(
    await fetch("/api/following/stop", { method: "POST" }),
  )
}
