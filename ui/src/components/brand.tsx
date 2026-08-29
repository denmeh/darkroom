import { Aperture } from "lucide-react"

import { cn } from "@/lib/utils"

export function Brand({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2 font-medium", className)}>
      <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <Aperture className="size-4" />
      </div>
      Darkroom
    </div>
  )
}
