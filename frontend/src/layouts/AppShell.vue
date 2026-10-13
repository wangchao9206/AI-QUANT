<script setup lang="ts">
import {
  Activity,
  BrainCircuit,
  ChartCandlestick,
  CircleHelp,
  LayoutDashboard,
} from 'lucide-vue-next'
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import AppMark from '../components/AppMark.vue'

const route = useRoute()
const navigation = [
  { label: '总览', to: '/overview', icon: LayoutDashboard },
  { label: '市场', to: '/market', icon: ChartCandlestick },
  { label: '策略', to: '/strategy', icon: BrainCircuit },
  { label: '系统', to: '/system', icon: Activity },
]

const title = computed(() => String(route.meta.title ?? '总览'))
const eyebrow = computed(() => String(route.meta.eyebrow ?? '决策控制台'))
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
          v-for="item in navigation"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :aria-label="item.label"
        >
          <component :is="item.icon" :size="18" :stroke-width="1.8" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

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
        <div class="market-state" aria-label="系统状态可观测">
          <span class="market-state__dot" aria-hidden="true" />
          状态可观测
        </div>
      </header>

      <main id="main-content" class="content" tabindex="-1">
        <RouterView />
      </main>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航">
      <RouterLink
        v-for="item in navigation"
        :key="item.to"
        :to="item.to"
        class="mobile-nav__item"
        :aria-label="item.label"
      >
        <component :is="item.icon" :size="20" :stroke-width="1.8" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
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

.nav-item.router-link-active {
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
    padding-bottom: 4.6rem;
  }

  .topbar {
    min-height: 6.5rem;
    align-items: center;
    padding-top: var(--space-5);
  }

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
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    min-height: 4.1rem;
    padding: var(--space-1);
    border: 1px solid #303236;
    border-radius: 1.15rem;
    background: rgb(23 24 26 / 96%);
    box-shadow: 0 16px 42px rgb(21 22 24 / 28%);
  }

  .mobile-nav__item {
    display: grid;
    place-items: center;
    align-content: center;
    gap: 0.18rem;
    color: var(--color-sidebar-muted);
    border-radius: var(--radius-md);
    font-size: 0.62rem;
    text-decoration: none;
  }

  .mobile-nav__item.router-link-active {
    color: white;
    background: #2b2d31;
  }
}
</style>
