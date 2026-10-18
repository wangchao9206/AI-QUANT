import {computed, ref, watch, type Ref, type WatchSource} from 'vue'

/** Paginate one fetched snapshot, retaining the page on background refresh. */
export function usePagination<T>(rows: Readonly<Ref<T[]>>, size = 20, resetOn: WatchSource[] = []) {
  const page = ref(1), pageSize = ref(size)
  const total = computed(() => rows.value.length)
  const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
  const items = computed(() => rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
  watch([pages, pageSize], () => { page.value = Math.min(page.value, pages.value) }, {flush:'sync'})
  watch(resetOn, () => { page.value = 1 }, {flush:'sync'})
  return {page, pageSize, total, pages, items}
}
