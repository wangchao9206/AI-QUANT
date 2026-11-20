<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FlowGraph, FlowNode } from '../services/workflows'
import { clone, ports, specs, type ParamSpec } from '../utils/workflowGraph'
import { summarizeWorkflow } from '../utils/workflowGuide'

const props = defineProps<{ graph: FlowGraph; disabled?: boolean }>()
const emit = defineEmits<{ 'update:graph': [graph: FlowGraph] }>()
const fieldError = ref('')

function value(node: FlowNode, key: string) {
  return node.params[key] ?? specs[node.type].defaults[key]
}

function numericStep(node: FlowNode, field: ParamSpec) {
  if (node.type === 'CONSTANT') return 'any'
  if (node.type === 'RISK' && field.key !== 'lots') return 0.0001
  return field.step
}

const form = computed(() => {
  const { graph } = props
  const summaries = new Map(summarizeWorkflow(graph).nodes.map(row => [row.id, row]))
  const nodes = new Map(graph.nodes.map(node => [node.id, node]))
  const editable = new Map<string, { node: FlowNode; title: string }>()
  const actions = graph.nodes.filter(node => node.type === 'ACTION')
  const risks = graph.nodes.filter(node => node.type === 'RISK')
  let needsCanvas = false

  function input(node: FlowNode, port: string) {
    const edges = graph.edges.filter(edge => edge.target === node.id && edge.targetPort === port)
    const edge = edges.length === 1 ? edges[0] : undefined
    const source = edge && nodes.get(edge.source)
    if (!source || !edge || source.id === node.id) return
    const output = ports(source).outputs[edge.sourcePort]
    if (output && output === ports(node).inputs[port]) return source
  }

  function operand(node: FlowNode | undefined) {
    if (!node) return false
    if (node.type === 'CONSTANT' || node.type === 'POSITION') return true
    return (node.type === 'PRICE' || node.type === 'INDICATOR') && input(node, 'market')?.type === 'MARKET'
  }

  function add(node: FlowNode, title: string) {
    if (specs[node.type].params.length && !editable.has(node.id)) editable.set(node.id, { node, title })
  }

  const rules = actions.map(action => {
    const source = input(action, 'condition')
    let expression = ''
    if (source?.type === 'PRESET' || source?.type === 'CHAN_SIGNAL') {
      if (input(source, 'market')?.type === 'MARKET') {
        add(source, specs[source.type].name)
      } else {
        needsCanvas = true
      }
    } else if (source?.type === 'COMPARE') {
      const left = input(source, 'left')
      const right = input(source, 'right')
      if (left && right && operand(left) && operand(right)) {
        add(source, specs.COMPARE.name)
        add(left, '左侧 · ' + specs[left.type].name)
        add(right, '右侧 · ' + specs[right.type].name)
        expression = summaries.get(source.id)?.detail ?? ''
      } else {
        needsCanvas = true
      }
    } else {
      needsCanvas = true
    }
    const actionValue = String(value(action, 'action'))
    return {
      id: action.id,
      opening: actionValue === 'BUY' || actionValue === 'SELL',
      description: source ? summaries.get(action.id)?.detail
        : `${specs.ACTION.params[0]?.options?.[actionValue] ?? '交易动作'}的触发条件待连接`,
      expression,
    }
  })
  const risk = risks.length === 1 && actions.length && actions.every(action => input(action, 'risk') === risks[0])
    ? risks[0] : undefined

  return {
    opening: rules.filter(rule => rule.opening),
    closing: rules.filter(rule => !rule.opening),
    editable: [...editable.values()],
    risk,
    needsCanvas: needsCanvas || !risk,
  }
})

watch(() => props.graph, () => { fieldError.value = '' })

function change(node: FlowNode, field: ParamSpec, event: Event) {
  if (props.disabled) return
  const control = event.target as HTMLInputElement | HTMLSelectElement
  const previous = value(node, field.key)
  let next: string | number
  if (field.options) {
    if (!Object.hasOwn(field.options, control.value)) return
    next = control.value
  } else {
    const input = control as HTMLInputElement
    next = input.valueAsNumber
    if (!Number.isFinite(next) || !input.validity.valid) {
      fieldError.value = `请填写有效的${field.label}。`
      control.value = previous === undefined ? '' : String(previous)
      return
    }
  }
  fieldError.value = ''
  if (next === previous) return
  const graph = clone(props.graph)
  const target = graph.nodes.find(item => item.id === node.id)
  if (!target) return
  target.params[field.key] = next
  emit('update:graph', graph)
}

function changeRisk(field: ParamSpec, event: Event) {
  if (form.value.risk) change(form.value.risk, field, event)
}
</script>

<template>
  <section class="rule-form" aria-label="策略规则">
    <div class="trade-rules">
      <section aria-label="入场规则">
        <h3>入场规则</h3>
        <ul v-if="form.opening.length">
          <li v-for="rule in form.opening" :key="rule.id">
            {{ rule.description }}
            <span v-if="rule.expression">{{ rule.expression }}</span>
          </li>
        </ul>
        <p v-else>尚未设置开多或开空条件。</p>
      </section>
      <section aria-label="退出规则">
        <h3>退出规则</h3>
        <ul v-if="form.closing.length">
          <li v-for="rule in form.closing" :key="rule.id">
            {{ rule.description }}
            <span v-if="rule.expression">{{ rule.expression }}</span>
          </li>
        </ul>
        <p v-else>当前没有单独的平仓信号。</p>
      </section>
    </div>

    <div class="rule-parameters">
      <fieldset v-for="{ node, title } in form.editable" :key="node.id" :disabled="disabled">
        <legend>{{ title }}</legend>
        <div class="parameter-fields">
          <label v-for="field in specs[node.type].params" :key="field.key">
            <span>{{ field.label }}</span>
            <select v-if="field.options" :value="value(node, field.key)" @change="change(node, field, $event)">
              <option v-for="(label, option) in field.options" :key="option" :value="option">{{ label }}</option>
            </select>
            <input v-else type="number" required :value="value(node, field.key)"
                   :min="field.min" :max="field.max" :step="numericStep(node, field)"
                   @change="change(node, field, $event)" />
          </label>
        </div>
      </fieldset>
    </div>

    <fieldset v-if="form.risk" class="risk-parameters" :disabled="disabled">
      <legend>仓位与保护</legend>
      <div class="parameter-fields">
        <label v-for="field in specs.RISK.params" :key="field.key">
          <span>{{ field.label }}</span>
          <input type="number" required :value="value(form.risk, field.key)"
                 :min="field.min" :max="field.max" :step="numericStep(form.risk, field)"
                 @change="changeRisk(field, $event)" />
        </label>
      </div>
    </fieldset>

    <p v-if="form.needsCanvas" class="canvas-note">组合条件和待连接的规则可在高级画布里编辑。</p>
    <p v-if="fieldError" class="field-error" role="alert">{{ fieldError }}</p>
  </section>
</template>

<style scoped>
.rule-form {
  display: grid;
  gap: 1rem;
  min-width: 0;
}
.trade-rules,
.rule-parameters,
.parameter-fields {
  display: grid;
  gap: .7rem 1rem;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
}
.trade-rules section {
  border-left: 2px solid var(--color-accent);
  padding: .05rem .85rem;
}
.trade-rules h3,
legend {
  color: var(--color-ink);
  font-size: .79rem;
  font-weight: 600;
  margin: 0;
}
.trade-rules ul {
  list-style: none;
  padding: 0;
  margin: .4rem 0 0;
}
.trade-rules li,
.trade-rules p,
.canvas-note,
.field-error {
  color: var(--color-ink-secondary);
  font-size: .73rem;
  line-height: 1.65;
  margin: .4rem 0 0;
}
.trade-rules li span {
  color: var(--color-ink-tertiary);
  display: block;
  font-size: .67rem;
}
fieldset {
  min-width: 0;
  margin: 0;
  padding: .55rem .85rem .85rem;
  border: 1px solid var(--color-line);
  border-radius: .45rem;
}
legend {
  padding: 0 .3rem;
}
.parameter-fields label {
  color: var(--color-ink-secondary);
  display: grid;
  font-size: .7rem;
  gap: .35rem;
  min-width: 0;
}
.parameter-fields input,
.parameter-fields select {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-line);
  border-radius: .35rem;
  box-sizing: border-box;
  color: var(--color-ink);
  font: inherit;
  min-width: 0;
  padding: .55rem;
  width: 100%;
}
.parameter-fields :is(input, select):focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}
.field-error {
  color: var(--color-warning);
}
</style>
