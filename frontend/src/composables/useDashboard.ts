import { storeToRefs } from 'pinia'
import { onMounted } from 'vue'

import { useMarketStore } from '../stores/market'

export function useDashboard() {
  const store = useMarketStore()
  const refs = storeToRefs(store)
  onMounted(() => {
    if (store.state === 'idle') void store.load()
  })
  return { store, ...refs }
}
