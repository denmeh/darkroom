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

async function parseStatus(response: Response): Promise<AppStatus> {
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`)
  }
  return (await response.json()) as AppStatus
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
