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
    timeZone: 'Asia/Shanghai',
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date)
}

export const formatTradingDate = (value?:string|null) => {
  if(!value)return '日期未知'
  if(/^\d{4}-\d{2}-\d{2}$/.test(value))return value
  const stamp=new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(value)?value:value+'+08:00')
  if(Number.isNaN(stamp.getTime()))return '日期未知'
  const parts=new Intl.DateTimeFormat('en',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(stamp)
  const get=(type:string)=>parts.find(p=>p.type===type)?.value
  return `${get('year')}-${get('month')}-${get('day')}`
}
