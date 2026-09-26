<template>
  <section class="page" data-module="training">
    <header class="page-head">
      <div>
        <h2>培训记录管理</h2>
        <p class="page-desc">登记人员培训记录，跟踪培训项目、培训学时与考核结论，作为持证上岗的培训依据。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="toggleCreate">{{ showCreate ? '收起登记表单' : '登记培训记录' }}</button>
        <button class="btn" type="button" @click="exportRows">导出培训记录清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div v-if="showCreate" class="create-panel">
      <h3>登记培训记录</h3>
      <div class="form-grid">
        <label v-for="field in createFields" :key="field.key" class="form-item">
          <span>{{ field.label }}<template v-if="field.required">（必填）</template></span>
          <input v-if="field.type === 'date'" v-model="createForm[field.key]" type="date" />
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
        <input v-model="filters.keyword" placeholder="按培训编号、人员、项目检索" />
      </label>
      <label class="filter-item">
        <span>考核状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="option in statuses" :key="option" :value="option">{{ option }}</option>
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
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="row.status === '已登记'">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else>—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无培训记录数据，可先登记培训记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条培训记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/training'
const columns = ['培训编号', '人员编号', '姓名', '培训项目', '培训日期', '培训学时', '考核结果', '培训状态']
const actions = ['考核合格', '考核不合格']
const statuses = ['已登记', '已合格', '未合格']

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')

// 筛选条件同步到地址栏查询串，刷新页面后条件保持一致。
const filters = ref<Record<string, string>>({
  keyword: String(route.query.keyword ?? ''),
  status: String(route.query.status ?? ''),
})

const showCreate = ref(false)
const createForm = ref<Record<string, string>>({})
const createFields = [
  { key: '培训编号', label: '培训编号', required: true },
  { key: '人员编号', label: '人员编号', required: true },
  { key: '姓名', label: '姓名', required: true },
  { key: '培训项目', label: '培训项目', required: true },
  { key: '培训日期', label: '培训日期', required: true, type: 'date' },
  { key: '培训学时', label: '培训学时', required: false },
]

const stats = computed(() => [
  { label: '培训记录总数', value: total.value },
  { label: '待考核', value: rows.value.filter((row) => row.status === '已登记').length },
  { label: '已合格', value: rows.value.filter((row) => row.status === '已合格').length },
  { label: '未合格', value: rows.value.filter((row) => row.status === '未合格').length },
])

function toggleCreate() {
  showCreate.value = !showCreate.value
  if (showCreate.value) {
    createForm.value = {}
  }
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
  filters.value = { keyword: '', status: '' }
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
      throw new Error(result.message ?? '培训记录登记未生效，请稍后重试')
    }
    infoMessage.value = result.message ?? '培训记录已登记'
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训记录登记失败'
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
      throw new Error(result.message ?? '培训记录动作未生效，请稍后重试')
    }
    infoMessage.value = result.message ?? ''
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训记录操作失败'
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
      throw new Error('培训记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '培训记录列表读取失败'
  }
}

onMounted(reload)
</script>
