<script setup lang="ts">
withDefaults(defineProps<{ title?: string; eyebrow?: string; padded?: boolean }>(), { padded: true })
</script>

<template>
  <section class="panel" :class="{ 'panel--padded': padded }">
    <header v-if="title || eyebrow || $slots.actions" class="panel__header">
      <div>
        <span v-if="eyebrow" class="panel__eyebrow">{{ eyebrow }}</span>
        <h2 v-if="title">{{ title }}</h2>
      </div>
      <slot name="actions" />
    </header>
    <slot />
  </section>
</template>

<style scoped>
.panel { min-width: 0; overflow: hidden; border: 1px solid var(--color-line); border-radius: var(--radius-lg); background: var(--color-surface-raised); box-shadow: var(--shadow-raised); }
.panel--padded { padding: clamp(1.15rem, 2.2vw, 1.65rem); }
.panel__header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-6); }
.panel__eyebrow { display: block; margin-bottom: .32rem; color: var(--color-ink-tertiary); font-size: .65rem; font-weight: 750; letter-spacing: .13em; text-transform: uppercase; }
h2 { margin: 0; font-size: .96rem; font-weight: 680; letter-spacing: -.015em; }
</style>
