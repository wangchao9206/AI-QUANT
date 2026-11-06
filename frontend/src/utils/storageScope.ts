let activeScope:string|null=null
export function setStorageScope(scope:string|null){activeScope=scope;try{if(scope)sessionStorage.setItem('aq_context',scope);else sessionStorage.removeItem('aq_context')}catch{/* In-memory identity still isolates browser notes. */}}
export function currentScope(){if(activeScope)return activeScope;try{return sessionStorage.getItem('aq_context')}catch{return null}}
export function storageKey(key:string){const scope=currentScope();return scope?`${key}:${scope}`:key}
