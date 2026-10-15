import { storeToRefs } from 'pinia'
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMarketStore } from '../stores/market'

export function useDashboard() {
  const store = useMarketStore()
  const refs = storeToRefs(store)
  const route = useRoute()
  const router = useRouter()
  const normalizeRouteSymbol = (value: unknown) => {
    const symbol = typeof value === 'string' ? value.trim().toUpperCase() : ''
    return /^[A-Z]{1,4}[A-Z0-9]{0,8}$/.test(symbol) ? symbol : ''
  }
  onMounted(() => {
    if (!store.catalog) void store.loadCatalog()
    const routeSymbol = normalizeRouteSymbol(route.query.symbol)
    const target = routeSymbol || store.symbol
    if (route.query.symbol !== target) void router.replace({ query: { ...route.query, symbol: target } })
    if (store.state === 'idle' || store.symbol !== target) void store.load(target)
  })
  watch(() => route.query.symbol, (value) => {
    const routeSymbol = normalizeRouteSymbol(value)
    if (routeSymbol && routeSymbol !== store.symbol) void store.load(routeSymbol)
  })
  return { store, ...refs }
}
