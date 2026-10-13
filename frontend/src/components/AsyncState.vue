<script setup lang="ts">
import { Inbox, RotateCcw, WifiOff } from 'lucide-vue-next'

defineProps<{
  state: 'loading' | 'empty' | 'error' | 'ready'
  emptyTitle?: string
  emptyMessage?: string
  errorMessage?: string
}>()

defineEmits<{
  retry: []
}>()
</script>

<template>
  <div v-if="state === 'loading'" class="skeleton" role="status" aria-label="正在加载">
    <span class="skeleton__line skeleton__line--short" />
    <span class="skeleton__line" />
    <span class="skeleton__line skeleton__line--medium" />
  </div>

  <div v-else-if="state === 'empty'" class="message" role="status">
    <Inbox :size="22" aria-hidden="true" />
    <strong>{{ emptyTitle ?? '暂无数据' }}</strong>
    <p>{{ emptyMessage ?? '当前筛选条件下没有可展示的可信结果。' }}</p>
  </div>

  <div v-else-if="state === 'error'" class="message message--error" role="alert">
    <WifiOff :size="22" aria-hidden="true" />
    <strong>数据暂时不可用</strong>
    <p>{{ errorMessage ?? '服务未能返回结果，请稍后重试。' }}</p>
    <button type="button" class="retry" @click="$emit('retry')">
      <RotateCcw :size="15" aria-hidden="true" />
      重新加载
    </button>
  </div>

  <slot v-else />
</template>

<style scoped>
.skeleton {
  display: grid;
  gap: var(--space-3);
  min-height: 8.5rem;
  align-content: center;
  padding: var(--space-6);
}

.skeleton__line {
  display: block;
  width: 100%;
  height: 0.75rem;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: #e7e4de;
  animation: breathe 1.4s ease-in-out infinite alternate;
}

.skeleton__line--short {
  width: 28%;
}

.skeleton__line--medium {
  width: 62%;
}

.message {
  display: grid;
  justify-items: center;
  gap: var(--space-2);
  min-height: 12rem;
  align-content: center;
  padding: var(--space-8);
  color: var(--color-ink-secondary);
  text-align: center;
}

.message strong {
  color: var(--color-ink);
  font-size: 0.96rem;
}

.message p {
  max-width: 28rem;
  margin: 0;
  font-size: 0.83rem;
  line-height: 1.65;
}

.message--error > svg {
  color: var(--color-negative);
}

.retry {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding: 0.58rem 0.82rem;
  color: white;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-ink);
  cursor: pointer;
}

@keyframes breathe {
  from { opacity: 0.48; }
  to { opacity: 1; }
}
</style>
