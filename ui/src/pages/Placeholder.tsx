import { CircleDashed } from "lucide-react"

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"

type PlaceholderPageProps = {
  title: string
  phase: 2 | 3
}

export function PlaceholderPage({ title, phase }: PlaceholderPageProps) {
  return (
    <Empty className="border border-dashed">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CircleDashed />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>
          Phase {phase} is a placeholder. Login is done; this is where the next
          workflow will live.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
