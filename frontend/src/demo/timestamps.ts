/**
 * Presentation-only clock labels for the activity + audit views.
 * The backend does not emit timestamps; these are not reconciliation data.
 */
export function demoClock(index: number, startHour = 9, startMinute = 31): string {
  const total = startMinute * 60 + index * 2
  const hours = startHour + Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}
