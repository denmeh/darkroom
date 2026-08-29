export function formatWhen(iso: string | null): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString()
}

export function initials(...parts: Array<string | null | undefined>): string {
  const source = parts.find((part) => part && part.trim())?.trim() || "?"
  const words = source.split(/\s+/).filter(Boolean)
  if (words.length >= 2) {
    return (words[0]![0]! + words[1]![0]!).toUpperCase()
  }
  return source.slice(0, 1).toUpperCase()
}
