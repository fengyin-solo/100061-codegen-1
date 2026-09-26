<template>
  <section class="page" data-module="personnel">
    <header class="page-head">
      <div>
        <h2>人员资质台账</h2>
        <p class="page-desc">维护证书与资质到期日期，按岗位汇总持证情况；到期前 30 天进入预警，已过期证书不允许保存可承接状态。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">{{ showCreate ? '收起登记表单' : '登记人员资质' }}</button>
        <button class="btn" type="button" @click="exportRows">导出人员资质清单</button>
      </div>
    </header>

    <div class="notice-bar">判定口径：{{ ruleText }}</div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <table class="data-table summary-table">
      <thead>
        <tr>
          <th>岗位</th><th>人数</th><th>证书数</th><th>正常</th><th>预警</th><th>已过期</th><th>可承接</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in positionSummary" :key="row.岗位">
          <td>{{ row.岗位 }}</td>
          <td>{{ row.人数 }}</td>
          <td>{{ row.证书数 }}</td>
          <td>{{ row.正常 }}</td>
          <td>{{ row.预警 }}</td>
          <td>{{ row.已过期 }}</td>
          <td>{{ row.可承接 }}</td>
        </tr>
        <tr v-if="!positionSummary.length">
          <td colspan="7" class="empty-state">暂无岗位持证数据</td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="create-panel">
      <h3>登记人员资质（同一人同一证书重复登记时按最近一次有效期合并）</h3>
      <div class="form-grid">
        <label v-for="field in createFields" :key="field.key" class="form-item">
          <span>{{ field.label }}<template v-if="field.required">（必填）</template></span>
          <select v-if="field.options" v-model="createForm[field.key]">
            <option value="">请选择</option>
            <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
          </select>
          <input v-else-if="field.type === 'date'" v-model="createForm[field.key]" type="date" />
          <input v-else v-model="createForm[field.key]" :placeholder="`请输入${field.label}`" />
        </label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="button" @click="submitCreate">保存登记</button>
        <button class="btn ghost" type="button" @click="toggleCreate">取消</button>
      </div>
    </div>

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="按人员编号、姓名、证书检索" />
      </label>
      <label class="filter-item">
        <span>岗位</span>
        <select v-model="filters.position">
          <option value="">全部岗位</option>
          <option v-for="option in positionOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>预警状态</span>
        <select v-model="filters.warning">
          <option value="">全部状态</option>
          <option v-for="option in warningOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>承接状态</span>
        <select v-model="filters.undertake">
          <option value="">全部</option>
          <option v-for="option in undertakeOptions" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['人员编号'] ?? '—' }}</td>
          <td>{{ row['姓名'] ?? '—' }}</td>
          <td>{{ row['岗位'] ?? '—' }}</td>
          <td>{{ row['证书名称'] ?? '—' }}</td>
          <td>{{ row['证书编号'] ?? '—' }}</td>
          <td>{{ row['发证日期'] ?? '—' }}</td>
          <td>{{ row['有效期至'] ?? '—' }}</td>
          <td>{{ remainDaysText(row['剩余天数']) }}</td>
          <td><span class="badge" :class="warningBadge(row['资质状态'])">{{ row['资质状态'] ?? '—' }}</span></td>
          <td><span class="badge" :class="row['承接状态'] === '可承接' ? 'badge-ok' : 'badge-muted'">{{ row['承接状态'] ?? '—' }}</span></td>
          <td class="row-actions">
            <button v-if="row['承接状态'] === '可承接'" class="link" type="button" @click="runAction('暂停承接', row)">暂停承接</button>
            <button v-else class="link" type="button" @click="runAction('恢复承接', row)">恢复承接</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无人员资质数据，可先登记人员资质</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条人员资质记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type PositionSummary = { 岗位: string; 人数: number; 证书数: number; 正常: number; 预警: number; 已过期: number; 可承接: number }

const ENDPOINT = '/api/personnel'
const columns = ['人员编号', '姓名', '岗位', '证书名称', '证书编号', '发证日期', '有效期至', '剩余天数', '资质状态', '承接状态']
const warningOptions = ['正常', '预警', '已过期']
const undertakeOptions = ['可承接', '暂停承接']
const RULE_FALLBACK = '以证书「有效期至」为基准按自然日比较，到期日当天仍有效；有效期至早于今天为「已过期」；距今天 30 天内（含第 30 天）为「预警」；其余为「正常」。超过预警上限（已过期）的证书不允许保存「可承接」承接状态；同一人同一证书重复登记按最近一次有效期合并。'

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const ruleText = ref(RULE_FALLBACK)
const positionSummary = ref<PositionSummary[]>([])
const positionOptions = ref<string[]>([])
const stats = ref([
  { label: '证书总数', value: 0 },
  { label: '正常', value: 0 },
  { label: '预警（30 天内到期）', value: 0 },
  { label: '已过期', value: 0 },
  { label: '可承接人员', value: 0 },
])

// 筛选条件同步到地址栏查询串，刷新页面后条件与预警状态保持一致。
const filters = ref<Record<string, string>>({
  keyword: String(route.query.keyword ?? ''),
  position: String(route.query.position ?? ''),
  warning: String(route.query.warning ?? ''),
  undertake: String(route.query.undertake ?? ''),
})

const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})
const createFields = [
  { key: '人员编号', label: '人员编号', required: true },
  { key: '姓名', label: '姓名', required: true },
  { key: '岗位', label: '岗位', required: true, options: ['检测员', '复核员', '报告签发', '质量负责人'] },
  { key: '证书名称', label: '证书名称', required: true },
  { key: '证书编号', label: '证书编号', required: false },
  { key: '发证日期', label: '发证日期', required: false, type: 'date' },
  { key: '有效期至', label: '有效期至', required: true, type: 'date' },
  { key: '承接状态', label: '承接状态', required: true, options: undertakeOptions },
]

function toggleCreate() {
  showCreate.value = !showCreate.value
  if (showCreate.value) {
    createForm.value = { 承接状态: '可承接' }
  }
}

function remainDaysText(value: Row[string]) {
  if (value === null || value === undefined || value === '') return '—'
  const days = Number(value)
  if (Number.isNaN(days)) return String(value)
  return days < 0 ? `已超 ${-days} 天` : `剩 ${days} 天`
}

function warningBadge(status: Row[string]) {
  if (status === '正常') return 'badge-ok'
  if (status === '预警') return 'badge-warn'
  if (status === '已过期') return 'badge-expired'
  return 'badge-muted'
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function syncQuery() {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) query[key] = value
  }
  void router.replace({ query })
}

function applyFilters() {
  syncQuery()
  void reload()
}

function resetFilters() {
  filters.value = { keyword: '', position: '', warning: '', undertake: '' }
  syncQuery()
  void reload()
}

async function readPayload(response: Response): Promise<{ ok: boolean; message?: string }> {
  const payload = (await response.json()) as { ok?: boolean; message?: string }
  return { ok: response.ok && payload.ok !== false, message: payload.message }
}

async function submitCreate() {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: createForm.value }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      throw new Error(result.message ?? '人员资质登记未生效，请稍后重试')
    }
    infoMessage.value = result.message ?? '人员资质已登记'
    showCreate.value = false
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员资质登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      throw new Error(result.message ?? '人员资质动作未生效，请稍后重试')
    }
    infoMessage.value = result.message ?? ''
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员资质操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) query.set(key, value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('人员资质列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员资质列表读取失败'
  }
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      throw new Error('岗位持证汇总读取失败')
    }
    const payload = await response.json()
    ruleText.value = payload.rule ?? RULE_FALLBACK
    positionSummary.value = payload.positions ?? []
    positionOptions.value = positionSummary.value.map((item) => item.岗位)
    const totals = payload.total ?? {}
    stats.value = [
      { label: '证书总数', value: totals['证书数'] ?? 0 },
      { label: '正常', value: totals['正常'] ?? 0 },
      { label: '预警（30 天内到期）', value: totals['预警'] ?? 0 },
      { label: '已过期', value: totals['已过期'] ?? 0 },
      { label: '可承接人员', value: totals['可承接人员'] ?? 0 },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '岗位持证汇总读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>
