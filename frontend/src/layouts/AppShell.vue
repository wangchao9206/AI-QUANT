<script setup lang="ts">
import {instrumentName} from '../utils/instrumentNames'
import {CircleHelp,LayoutDashboard,Radar,ChartCandlestick,BrainCircuit,History} from 'lucide-vue-next'
import { computed,ref,watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import AppMark from '../components/AppMark.vue'
import InstrumentPicker from '../components/InstrumentPicker.vue'
import ExperienceSwitch from '../components/ExperienceSwitch.vue'
import BeginnerGuide from '../components/BeginnerGuide.vue'
import TradingContextBar from '../components/TradingContextBar.vue'
import {instrumentPath,researchPath,validInstrument} from '../utils/marketNavigation'
import { useMarketStore } from '../stores/market'
import {authState,authCall,forgetIdentity,canManage} from '../services/auth'
import {workspaceFor,workspaceNavigation} from '../utils/workspaceNavigation'
import {instrumentContextPath} from '../utils/tradingContext'

const route = useRoute()
const router = useRouter()
const store = useMarketStore()
const identityViewKey=computed(()=>JSON.stringify([authState.user?.id,authState.user?.tenantId,
  authState.user?.permissions?[...authState.user.permissions].sort():null]))
const sidebarSymbol=computed(()=>route.path==='/paper'?'':validInstrument(route.params.symbol??route.query.symbol)||store.symbol)
const workspaces=computed(()=>workspaceNavigation(authState.user))
const icons={today:LayoutDashboard,opportunities:Radar,trade:ChartCandlestick,strategies:BrainCircuit,review:History}
const navigation=computed(()=>workspaces.value.groups.map(g=>({...g,icon:icons[g.id]})))
const currentWorkspace=computed(()=>workspaceFor(route.path))
const currentGroup=computed(()=>workspaces.value.groups.find(g=>g.id===currentWorkspace.value))
const secondaryMenu=ref<HTMLDetailsElement|null>(null)
watch(()=>route.fullPath,()=>{if(secondaryMenu.value)secondaryMenu.value.open=false})
const title = computed(() => String(route.meta.title ?? '总览'))
const eyebrow = computed(() => String(route.meta.eyebrow ?? '决策控制台'))
const routeTarget = (path: string) => ({path})
async function logout(){try{await authCall('/logout',{})}catch{return}forgetIdentity();window.location.assign('/auth/login')}
async function selectSidebarSymbol(symbol: string) {
  await router.push(instrumentContextPath(route.name==='research'?researchPath(symbol):instrumentPath(symbol),route.query,symbol,String(route.params.symbol??route.query.symbol??store.symbol)))
}
</script>

<template>
  <a class="skip-link" href="#main-content">跳到主要内容</a>
  <div class="shell">
    <aside class="sidebar" aria-label="主导航">
      <div class="brand">
        <AppMark />
        <div>
          <strong>AI-QUANT</strong>
          <span>Decision system</span>
        </div>
      </div>

      <nav class="desktop-nav">
        <RouterLink
          v-for="item in navigation" :key="item.id"
          :to="routeTarget(item.to)"
          class="nav-item"
          :class="{'workspace-active':currentWorkspace===item.id}"
          :aria-current="currentWorkspace===item.id?'location':undefined"
          :aria-label="item.label"
        >
          <component :is="item.icon" :size="18" :stroke-width="1.8" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <section v-if="store.sidebarInstruments.length" class="sidebar-market" aria-labelledby="sidebar-market-title">
        <div class="sidebar-market__header">
          <span id="sidebar-market-title">品种快捷入口</span>
          <small>QUICK ACCESS</small>
        </div>
        <button
          v-for="item in store.sidebarInstruments"
          :key="item.symbol"
          class="sidebar-instrument"
          :class="{ 'sidebar-instrument--active': item.symbol === sidebarSymbol }"
          type="button"
          @click="selectSidebarSymbol(item.symbol)"
        >
          <span>{{instrumentName(item.symbol,item.name)}}</span>
          <span><strong>{{ item.name }}</strong><small>{{ item.exchange }}</small></span>
        </button>
        <p v-if="store.recentSymbolsError" role="status">{{ store.recentSymbolsError }}</p>
      </section>

      <div class="sidebar-note">
        <CircleHelp :size="17" aria-hidden="true" />
        <div>
          <strong>可信数据优先</strong>
          <span>缓存与降级状态始终可见</span>
        </div>
      </div>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div>
          <p>{{ eyebrow }}</p>
          <h1>{{ title }}</h1>
        </div>
        <div class="topbar-actions">
          <details v-if="workspaces.secondary.length" ref="secondaryMenu" class="secondary-menu"><summary>资料与设置</summary><nav aria-label="资料与设置"><RouterLink v-for="item in workspaces.secondary" :key="item.to" :to="item.to">{{item.label}}</RouterLink></nav></details>
          <RouterLink v-if="canManage()" to="/admin" class="admin-entry">后台管理 ↗</RouterLink>
          <RouterLink v-if="authState.user" to="/account" class="account-link">{{authState.user.username}} · {{authState.user.tenants.find(t=>t.id===authState.user?.tenantId)?.name}}</RouterLink>
          <button v-if="authState.user" class="account-logout" @click="logout">退出</button>
          <ExperienceSwitch />
          <InstrumentPicker v-if="route.meta.instrument" />
          <span v-else-if="['/overview','/market'].includes(route.path)" class="overview-scope">全市场视图</span>
          <div class="market-state" aria-label="系统状态可观测">
            <span class="market-state__dot" aria-hidden="true" />
            状态可观测
          </div>
        </div>
      </header>

      <main id="main-content" class="content" tabindex="-1">
        <nav v-if="currentGroup&&currentGroup.children.length>1" class="workspace-tabs" :aria-label="currentGroup.label+'工作区'"><RouterLink v-for="item in currentGroup.children" :key="item.to" :to="item.to">{{item.label}}</RouterLink></nav>
        <BeginnerGuide />
        <TradingContextBar/>
        <RouterView :key="identityViewKey" />
      </main>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航，可左右滑动">
      <RouterLink
          v-for="item in navigation"
          :key="item.id"
          :to="routeTarget(item.to)"
        class="mobile-nav__item"
        :class="{'workspace-active':currentWorkspace===item.id}"
        :aria-current="currentWorkspace===item.id?'location':undefined"
        :aria-label="item.label"
      >
        <component :is="item.icon" :size="20" :stroke-width="1.8" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
.workspace-tabs{display:flex;flex-wrap:wrap;gap:.45rem;margin-bottom:1.6rem;padding-bottom:1rem;border-bottom:1px solid var(--color-line)}.workspace-tabs a{font-size:.76rem;text-decoration:none;padding:.55rem .8rem;border-radius:.5rem;color:var(--color-ink-secondary)}.workspace-tabs a.router-link-active{color:var(--color-accent);background:var(--color-accent-soft)}
.secondary-menu{position:relative;font-size:.73rem}.secondary-menu summary{cursor:pointer;padding:.5rem;color:var(--color-accent)}.secondary-menu nav{position:absolute;z-index:40;top:100%;right:0;display:grid;gap:.2rem;min-width:11rem;padding:.6rem;background:var(--color-surface);border:1px solid var(--color-line);border-radius:.65rem;box-shadow:0 12px 35px #0002}.secondary-menu a{padding:.6rem;color:var(--color-ink);text-decoration:none}.secondary-menu a:hover{background:var(--color-accent-soft)}
.nav-group{display:block;padding:.85rem 1rem .3rem;color:var(--color-sidebar-muted);font-size:.64rem;letter-spacing:.08em}
.admin-entry{color:var(--color-accent);border:1px solid var(--color-line-strong);padding:.5rem .7rem;border-radius:.4rem;font-size:.72rem;text-decoration:none;white-space:nowrap}
.account-link{color:var(--color-accent);font-size:.7rem;max-width:15rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-decoration:none}.account-logout{border:0;background:transparent;color:var(--color-ink-secondary);font-size:.7rem;cursor:pointer}
.skip-link {
  position: fixed;
  z-index: 100;
  top: var(--space-3);
  left: var(--space-3);
  padding: var(--space-3) var(--space-4);
  color: white;
  border-radius: var(--radius-sm);
  background: var(--color-accent);
  transform: translateY(-160%);
  transition: transform var(--duration-fast) var(--ease-out);
}

.skip-link:focus {
  transform: translateY(0);
}

.shell {
  min-height: 100vh;
}

.sidebar {
  position: fixed;
  z-index: 10;
  inset: 0 auto 0 0;
  display: flex;
  width: 15.5rem;
  flex-direction: column;
  padding: var(--space-6) var(--space-4);
  color: white;
  background: var(--color-sidebar);
  border-right: 1px solid #24262a;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-2) var(--space-8);
}

.brand div {
  display: grid;
  gap: 0.05rem;
}

.brand strong {
  font-size: 0.88rem;
  letter-spacing: 0.12em;
}

.brand span {
  color: var(--color-sidebar-muted);
  font-size: 0.66rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.desktop-nav {
  display: grid;
  gap: var(--space-1);
}

.sidebar-market { display: grid; gap: .2rem; margin-top: var(--space-8); padding-top: var(--space-4); border-top: 1px solid #2c2e31; }
.sidebar-market__header { display: flex; align-items: center; justify-content: space-between; padding: 0 var(--space-3) var(--space-2); color: #d8d6d1; font-size: .61rem; font-weight: 700; letter-spacing: .08em; }
.sidebar-market__header small { color: #6f7277; font: .5rem var(--font-numeric); letter-spacing: .1em; }
.sidebar-instrument { display: grid; grid-template-columns: 3.1rem 1fr; align-items: center; gap: .55rem; width: 100%; padding: .52rem .65rem; color: var(--color-sidebar-muted); border: 0; border-radius: .55rem; background: transparent; cursor: pointer; text-align: left; transition: color var(--duration-fast), background var(--duration-fast); }
.sidebar-instrument:hover { color: white; background: #222428; }
.sidebar-instrument--active { color: white; background: #2b2d31; }
.sidebar-instrument > span:first-child { font: 650 .61rem var(--font-numeric); }
.sidebar-instrument > span:last-child { display: grid; min-width: 0; gap: .05rem; }
.sidebar-instrument strong { overflow: hidden; font-size: .6rem; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.sidebar-instrument small { color: #73767a; font: .48rem var(--font-numeric); }

.nav-item {
  display: flex;
  min-height: 2.85rem;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-3);
  color: var(--color-sidebar-muted);
  border-radius: var(--radius-sm);
  font-size: 0.84rem;
  font-weight: 550;
  text-decoration: none;
  transition: color var(--duration-fast), background var(--duration-fast), transform var(--duration-fast);
}

.nav-item:hover {
  color: white;
  background: #222428;
  transform: translateX(2px);
}

.nav-item.workspace-active {
  color: white;
  background: #2b2d31;
  box-shadow: inset 2px 0 #8fb3c7;
}

.sidebar-note {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin-top: auto;
  padding: var(--space-4) var(--space-3);
  color: var(--color-sidebar-muted);
  border-top: 1px solid #2c2e31;
}

.sidebar-note div {
  display: grid;
  gap: 0.2rem;
}

.sidebar-note strong {
  color: #e6e4df;
  font-size: 0.72rem;
}

.sidebar-note span {
  font-size: 0.65rem;
  line-height: 1.5;
}

.workspace {
  min-width: 0;
  min-height: 100vh;
  margin-left: 15.5rem;
}

.topbar {
  display: flex;
  min-height: 7.5rem;
  align-items: flex-end;
  justify-content: space-between;
  padding: var(--space-8) clamp(1.5rem, 4vw, 4rem) var(--space-5);
  border-bottom: 1px solid var(--color-line);
}

.topbar > div:first-child { min-width: 0; }

.topbar p {
  margin: 0 0 var(--space-1);
  color: var(--color-ink-tertiary);
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.topbar h1 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.9rem, 3vw, 2.6rem);
  font-weight: 500;
  letter-spacing: -0.035em;
}

.topbar-actions { display: flex; align-items: center; gap: var(--space-3); }
.overview-scope { color:var(--color-accent);background:var(--color-accent-soft);border-radius:var(--radius-pill);padding:.5rem .75rem;font-size:.7rem;white-space:nowrap; }

.market-state {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0.42rem 0.65rem;
  color: var(--color-ink-secondary);
  border: 1px solid var(--color-line);
  border-radius: var(--radius-pill);
  background: rgb(255 255 255 / 45%);
  font-size: 0.72rem;
  font-weight: 600;
}

.market-state__dot {
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--color-accent);
  box-shadow: 0 0 0 3px var(--color-accent-soft);
}

.content {
  min-width: 0;
  width: min(100%, 94rem);
  margin: 0 auto;
  padding: var(--space-8) clamp(1.5rem, 4vw, 4rem) var(--space-16);
}

.mobile-nav {
  display: none;
}

@media (max-width: 760px) {
  .sidebar {
    display: none;
  }

  .workspace {
    margin-left: 0;
    padding-bottom: 5rem;
  }

  .topbar {
    flex-wrap:wrap;
    min-height: 6.5rem;
    align-items: center;
    gap: var(--space-3);
    padding-right: var(--space-5);
    padding-left: var(--space-5);
    padding-top: var(--space-5);
  }

  .topbar h1 { font-size: 1.55rem; }

  .topbar-actions { gap: var(--space-2);width:100%;flex-wrap:wrap;padding-bottom:.8rem; }

  .market-state {
    padding: var(--space-2);
    font-size: 0;
  }

  .content {
    padding-top: var(--space-6);
  }

  .mobile-nav {
    position: fixed;
    z-index: 20;
    right: var(--space-3);
    bottom: var(--space-3);
    left: var(--space-3);
    display: flex;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-width: thin;
    min-height: 4.1rem;
    max-height: 4.1rem;
    padding: var(--space-1);
    border: 1px solid #303236;
    border-radius: 1.15rem;
    background: rgb(23 24 26 / 96%);
    box-shadow: 0 16px 42px rgb(21 22 24 / 28%);
  }

  .mobile-nav__item {
    flex: 1 0 0;
    min-width:0;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 0.18rem;
    color: var(--color-sidebar-muted);
    border-radius: var(--radius-md);
    font-size: 0.62rem;
    text-decoration: none;
  }

  .mobile-nav__item.workspace-active {
    color: white;
    background: #2b2d31;
  }
}

@media (max-width: 420px) {
  .market-state { display: none; }
  .content { padding-right: var(--space-4); padding-left: var(--space-4); }
}
</style>
