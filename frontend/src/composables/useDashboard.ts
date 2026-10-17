import { storeToRefs } from 'pinia'
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMarketStore } from '../stores/market'

export function useDashboard(requirePrediction=true) {
  const store = useMarketStore()
  const refs = storeToRefs(store)
  const route = useRoute()
  const router = useRouter()
  const load=(symbol:string)=>requirePrediction?store.load(symbol):store.loadMarket(symbol)
  const normalizeRouteSymbol = (value: unknown) => {
    const symbol = typeof value === 'string' ? value.trim().toUpperCase() : ''
    return /^[A-Z]{1,4}[A-Z0-9]{0,8}$/.test(symbol) ? symbol : ''
  }
  onMounted(() => {
    if (!store.catalog) void store.loadCatalog()
    const routeSymbol = normalizeRouteSymbol(route.params.symbol??route.query.symbol)
    const target = routeSymbol || store.symbol
    if (!route.params.symbol&&route.query.symbol !== target) void router.replace({ query: { ...route.query, symbol: target } })
    if (store.state === 'idle' || store.state==='error' || store.symbol !== target || (requirePrediction&&!store.prediction)||(!requirePrediction&&!store.quote)) void load(target)
  })
  watch(() => route.params.symbol??route.query.symbol, (value) => {
    const routeSymbol = normalizeRouteSymbol(value)
    if (routeSymbol && routeSymbol !== store.symbol) void load(routeSymbol)
  })
  return { store, ...refs }
}
