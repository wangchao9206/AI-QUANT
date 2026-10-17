export const validInstrument=(value:unknown)=>typeof value==='string'&&/^[A-Z]{1,4}[A-Z0-9]{0,8}$/.test(value.trim().toUpperCase())?value.trim().toUpperCase():''
export const instrumentPath=(symbol:string)=>`/market/${encodeURIComponent(symbol.toUpperCase())}`
export const researchPath=(symbol:string)=>`/strategy/${encodeURIComponent(symbol.toUpperCase())}`
