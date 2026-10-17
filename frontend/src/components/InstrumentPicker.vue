<script setup lang="ts">
import { Check, ChevronDown, Search, X } from 'lucide-vue-next'
import { computed, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useMarketStore } from '../stores/market'
import {instrumentPath,researchPath} from '../utils/marketNavigation'

const store = useMarketStore()
const route = useRoute()
const router = useRouter()
const open = ref(false)
const query = ref('')
const searchInput = ref<HTMLInputElement | null>(null)
const validSymbol = /^[A-Z]{1,4}[A-Z0-9]{0,8}$/

interface PickerOption {
  symbol: string
  name: string
  exchange: string
  kind: '主力连续' | '挂牌合约'
}

const selectedName = computed(() => store.currentInstrument?.name ?? store.quote?.displayName ?? '选择期货品种')
const selectedExchange = computed(() => store.currentInstrument?.exchange ?? '全市场')
const normalizedQuery = computed(() => query.value.trim().toUpperCase())
const resultGroups = computed(() => {
  const needle = normalizedQuery.value
  let remaining = 72
  return (store.catalog?.exchanges ?? []).map((group) => {
    const options: PickerOption[] = []
    for (const instrument of group.instruments) {
      const main: PickerOption = { symbol: instrument.mainSymbol, name: instrument.name, exchange: group.code, kind: '主力连续' }
      const candidates = needle
        ? [main, ...instrument.contracts.map((symbol): PickerOption => ({ symbol, name: instrument.name, exchange: group.code, kind: '挂牌合约' }))]
        : [main]
      for (const option of candidates) {
        const haystack = `${option.symbol} ${option.name} ${option.exchange}`.toUpperCase()
        if ((!needle || haystack.includes(needle)) && remaining > 0) {
          options.push(option)
          remaining -= 1
        }
      }
    }
    return { code: group.code, name: group.name, options }
  }).filter((group) => group.options.length > 0)
})
const resultCount = computed(() => resultGroups.value.reduce((count, group) => count + group.options.length, 0))

async function showPicker() {
  open.value = true
  query.value = ''
  await nextTick()
  searchInput.value?.focus()
}

function closePicker() {
  open.value = false
  query.value = ''
}

async function selectSymbol(symbol: string) {
  const normalized = symbol.trim().toUpperCase()
  if (!validSymbol.test(normalized)) return
  await router.push(route.path.startsWith('/strategy')?researchPath(normalized):instrumentPath(normalized))
  closePicker()
}

function submitSearch() {
  const first = resultGroups.value[0]?.options[0]
  if (first) void selectSymbol(first.symbol)
  else if (validSymbol.test(normalizedQuery.value)) void selectSymbol(normalizedQuery.value)
}
</script>

<template>
  <div class="instrument-picker">
    <button
      class="instrument-trigger"
      type="button"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @click="showPicker"
    >
      <span class="instrument-trigger__symbol">{{ store.symbol }}</span>
      <span class="instrument-trigger__meta"><strong>{{ selectedName }}</strong><small>{{ selectedExchange }}</small></span>
      <ChevronDown :size="15" aria-hidden="true" />
    </button>

    <div v-if="open" class="picker-backdrop" @click.self="closePicker" @keydown.esc="closePicker">
      <section class="picker-panel" role="dialog" aria-modal="true" aria-labelledby="picker-title">
        <header class="picker-header">
          <div>
            <p>Domestic futures</p>
            <h2 id="picker-title">选择期货品种</h2>
          </div>
          <button class="picker-close" type="button" aria-label="关闭品种选择" @click="closePicker"><X :size="18" /></button>
        </header>

        <form class="picker-search" role="search" @submit.prevent="submitSearch">
          <Search :size="18" aria-hidden="true" />
          <label class="sr-only" for="global-instrument-search">搜索品种或合约</label>
          <input
            id="global-instrument-search"
            ref="searchInput"
            v-model="query"
            autocomplete="off"
            placeholder="搜索名称、代码或交易所"
          />
          <kbd>Enter</kbd>
        </form>

        <div class="picker-status">
          <span v-if="store.catalog">{{ store.catalog.exchanges.length }} 个交易所 · {{ store.instrumentCount }} 个品种</span>
          <span v-else-if="store.catalogError">{{ store.catalogError }}，仍可输入准确代码</span>
          <span v-else>正在载入真实挂牌目录…</span>
          <strong v-if="query">{{ resultCount }} 项匹配</strong>
        </div>

        <div class="picker-results" role="listbox" aria-label="期货品种搜索结果">
          <section v-for="group in resultGroups" :key="group.code" class="picker-group">
            <div class="picker-group__title"><strong>{{ group.code }}</strong><span>{{ group.name }}</span></div>
            <button
              v-for="option in group.options"
              :key="option.symbol"
              class="picker-option"
              :class="{ 'picker-option--active': option.symbol === store.symbol }"
              type="button"
              role="option"
              :aria-selected="option.symbol === store.symbol"
              @click="selectSymbol(option.symbol)"
            >
              <span class="picker-option__code">{{ option.symbol }}</span>
              <span class="picker-option__name">{{ option.name }}</span>
              <small>{{ option.kind }}</small>
              <Check v-if="option.symbol === store.symbol" :size="15" aria-hidden="true" />
            </button>
          </section>
          <div v-if="store.catalog && resultCount === 0" class="picker-empty">
            <strong>目录中没有匹配项</strong>
            <span v-if="validSymbol.test(normalizedQuery)">按 Enter 仍可查询准确合约代码 {{ normalizedQuery }}</span>
            <span v-else>可尝试品种名称、主力代码或完整合约代码。</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.instrument-picker { position: relative; }
.instrument-trigger { display: grid; min-width: 15.5rem; grid-template-columns: auto 1fr auto; align-items: center; gap: .72rem; padding: .5rem .65rem .5rem .55rem; color: var(--color-ink); border: 1px solid var(--color-line); border-radius: var(--radius-md); background: rgb(255 255 255 / 62%); cursor: pointer; text-align: left; transition: border-color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast); }
.instrument-trigger:hover { border-color: var(--color-line-strong); background: white; transform: translateY(-1px); }
.instrument-trigger__symbol { min-width: 3.25rem; padding: .42rem .48rem; color: white; border-radius: .48rem; background: var(--color-ink); font: 650 .68rem var(--font-numeric); text-align: center; }
.instrument-trigger__meta { display: grid; min-width: 0; gap: .08rem; }
.instrument-trigger__meta strong { overflow: hidden; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
.instrument-trigger__meta small { color: var(--color-ink-tertiary); font: .57rem var(--font-numeric); }
.picker-backdrop { position: fixed; z-index: 60; inset: 0; display: grid; place-items: start end; padding: 5.2rem clamp(1.5rem, 4vw, 4rem); background: rgb(18 19 21 / 26%); backdrop-filter: blur(10px); }
.picker-panel { display: flex; width: min(42rem, calc(100vw - 3rem)); max-height: min(46rem, calc(100vh - 7rem)); flex-direction: column; overflow: hidden; border: 1px solid rgb(255 255 255 / 70%); border-radius: 1.35rem; background: rgb(251 250 247 / 96%); box-shadow: 0 30px 90px rgb(18 19 21 / 24%); animation: picker-in 180ms var(--ease-out); }
.picker-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 1.4rem 1.5rem 1rem; }
.picker-header p { margin: 0 0 .25rem; color: var(--color-ink-tertiary); font-size: .58rem; font-weight: 750; letter-spacing: .15em; text-transform: uppercase; }
.picker-header h2 { margin: 0; font: 500 1.45rem var(--font-display); letter-spacing: -.025em; }
.picker-close { display: grid; width: 2rem; height: 2rem; place-items: center; color: var(--color-ink-secondary); border: 0; border-radius: 50%; background: #ebe9e3; cursor: pointer; }
.picker-search { display: flex; align-items: center; gap: .7rem; margin: 0 1.5rem; padding: .75rem .85rem; border: 1px solid var(--color-line-strong); border-radius: .78rem; background: white; }
.picker-search svg { color: var(--color-accent); }
.picker-search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font-size: .82rem; }
.picker-search kbd { padding: .18rem .35rem; color: var(--color-ink-tertiary); border: 1px solid var(--color-line); border-radius: .3rem; background: var(--color-canvas); font: .55rem var(--font-numeric); }
.picker-status { display: flex; align-items: center; justify-content: space-between; min-height: 2.7rem; padding: .65rem 1.5rem .5rem; color: var(--color-ink-tertiary); font-size: .61rem; }
.picker-status strong { color: var(--color-ink-secondary); }
.picker-results { overflow-y: auto; padding: 0 .75rem 1rem; overscroll-behavior: contain; }
.picker-group { display: grid; grid-template-columns: 8rem 1fr; padding: .55rem .7rem; border-top: 1px solid var(--color-line); }
.picker-group__title { display: grid; align-content: start; gap: .2rem; padding: .58rem .75rem .58rem 0; }
.picker-group__title strong { font: 700 .67rem var(--font-numeric); letter-spacing: .06em; }
.picker-group__title span { color: var(--color-ink-tertiary); font-size: .56rem; line-height: 1.45; }
.picker-option { display: grid; grid-template-columns: 5.3rem minmax(7rem, 1fr) auto 1.2rem; align-items: center; gap: .65rem; width: 100%; padding: .58rem .68rem; color: var(--color-ink); border: 0; border-radius: .58rem; background: transparent; cursor: pointer; text-align: left; }
.picker-option:hover, .picker-option--active { background: #ebe9e2; }
.picker-option__code { font: 650 .68rem var(--font-numeric); }
.picker-option__name { overflow: hidden; font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
.picker-option small { color: var(--color-ink-tertiary); font-size: .56rem; }
.picker-option svg { color: var(--color-accent); }
.picker-empty { display: grid; place-items: center; gap: .45rem; min-height: 10rem; color: var(--color-ink-tertiary); font-size: .68rem; text-align: center; }
.picker-empty strong { color: var(--color-ink-secondary); }
@keyframes picker-in { from { opacity: 0; transform: translateY(-8px) scale(.985); } }
@media (max-width: 760px) {
  .instrument-trigger { min-width: 0; grid-template-columns: auto auto; }
  .instrument-trigger__meta { display: none; }
  .picker-backdrop { place-items: end stretch; padding: 0; }
  .picker-panel { width: 100%; max-height: 82vh; border-width: 1px 0 0; border-radius: 1.35rem 1.35rem 0 0; }
  .picker-group { grid-template-columns: 1fr; }
  .picker-group__title { display: flex; padding-right: 0; }
}
</style>
