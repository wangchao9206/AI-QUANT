/** Works on both secure origins and HTTP development/LAN origins. */
export function requestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  const bytes = new Uint32Array(4)
  if (typeof globalThis.crypto?.getRandomValues === 'function') {
    globalThis.crypto.getRandomValues(bytes)
    return Array.from(bytes, n => n.toString(16).padStart(8, '0')).join('')
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}

/** UUID commands also work on HTTP LAN origins, where randomUUID is absent.
 * These identifiers are for idempotency, never authentication credentials.
 */
export function requestUuid():string {
  if(typeof globalThis.crypto?.randomUUID==='function')return globalThis.crypto.randomUUID()
  const bytes=new Uint8Array(16)
  if(typeof globalThis.crypto?.getRandomValues==='function')globalThis.crypto.getRandomValues(bytes)
  else for(let i=0;i<bytes.length;i++)bytes[i]=Math.floor(Math.random()*256)
  bytes[6]=(bytes[6]!&15)|64;bytes[8]=(bytes[8]!&63)|128
  const hex=Array.from(bytes,n=>n.toString(16).padStart(2,'0')).join('')
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`
}
