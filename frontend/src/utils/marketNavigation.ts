export const validInstrument=(value:unknown)=>typeof value==='string'&&/^[A-Z]{1,4}[A-Z0-9]{0,8}$/.test(value.trim().toUpperCase())?value.trim().toUpperCase():''
export const instrumentPath=(symbol:string)=>`/market/${encodeURIComponent(symbol.toUpperCase())}`
export const researchPath=(symbol:string)=>`/strategy/${encodeURIComponent(symbol.toUpperCase())}`

// M is a continuous suffix only on an alphabetic symbol. After removing a
// delivery month, M may be part of the product itself (JM, M, RM, SM, PM, IM).
export function instrumentRoot(value: string): string {
  const symbol = validInstrument(value)
  const delivery = /^([A-Z]+)\d+$/.exec(symbol)
  if (delivery) return delivery[1]!
  return symbol.endsWith('M') ? symbol.slice(0, -1) : symbol
}
