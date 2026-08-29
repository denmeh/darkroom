import { useState } from "react"
import {
  BadgeCheck,
  ExternalLink,
  Lock,
  LogOut,
} from "lucide-react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
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
import { Spinner } from "@/components/ui/spinner"
import { initials } from "@/lib/format"
import { openProfile, type AppStatus } from "@/lib/api"

function formatCount(value: number | null | undefined): string {
  if (value == null) return "—"
  return value.toLocaleString()
}

export function AccountPage({
  status,
  signingOut,
  onSignOut,
}: {
  status: AppStatus
  signingOut: boolean
  onSignOut: () => void
}) {
  const me = status.me
  const username = me?.username ?? status.username
  const name = me?.full_name || username || "Instagram"
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onOpen() {
    if (!username) return
    setOpening(true)
    setError(null)
    try {
      await openProfile(username)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not open profile")
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-heading text-xl font-medium tracking-tight">
          Account
        </h1>
        <p className="text-sm text-muted-foreground">
          Switching accounts keeps this session saved so you can come back
          later. History and scans stay with this Instagram account.
        </p>
      </div>

      <Card>
        <CardHeader className="justify-items-center text-center">
          <Avatar size="lg" className="size-20">
            {me?.avatar_url ? (
              <AvatarImage src={me.avatar_url} alt="" />
            ) : null}
            <AvatarFallback className="text-lg">
              {initials(me?.full_name, username)}
            </AvatarFallback>
          </Avatar>
          <CardTitle className="text-xl">{name}</CardTitle>
          <CardDescription className="flex flex-wrap items-center justify-center gap-1.5">
            {username ? <span>@{username}</span> : null}
            {me?.is_private ? (
              <Badge variant="outline">
                <Lock />
                Private
              </Badge>
            ) : null}
            {me?.is_verified ? (
              <Badge variant="outline">
                <BadgeCheck />
                Verified
              </Badge>
            ) : null}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {me?.biography ? (
            <p className="text-center text-sm whitespace-pre-wrap text-muted-foreground">
              {me.biography}
            </p>
          ) : null}
          <div className="grid grid-cols-3 divide-x overflow-hidden rounded-xl border">
            <Stat label="Posts" value={formatCount(me?.media_count)} />
            <Stat label="Followers" value={formatCount(me?.follower_count)} />
            <Stat label="Following" value={formatCount(me?.following_count)} />
          </div>
          {error ? (
            <p className="text-center text-sm text-destructive">{error}</p>
          ) : null}
        </CardContent>
        <CardFooter className="flex flex-col gap-2">
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={!username || opening}
            onClick={() => void onOpen()}
          >
            {opening ? <Spinner /> : <ExternalLink />}
            Open Instagram
          </Button>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={signingOut}
            onClick={onSignOut}
          >
            {signingOut ? <Spinner /> : <LogOut />}
            Switch account
          </Button>
        </CardFooter>
      </Card>

      <p className="px-1 text-center text-xs break-all text-muted-foreground">
        Session file {status.session_path}
      </p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-3 py-3">
      <p className="text-lg font-medium tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}
