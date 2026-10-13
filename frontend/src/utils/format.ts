export const formatNumber = (value?: number | null, digits = 2) => value == null
  ? '—'
  : new Intl.NumberFormat('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)

export const formatPct = (value?: number | null, digits = 2) => value == null
  ? '—'
  : `${value >= 0 ? '+' : ''}${formatNumber(value, digits)}%`

export const formatTime = (value?: string | null) => {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
}
