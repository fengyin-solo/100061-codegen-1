<template>
  <section class="page" data-module="qualification">
    <header class="page-head">
      <div>
        <h2>人员资质管理</h2>
        <p class="page-desc">
          登记培训记录、维护证书与资质到期日期，并按岗位汇总持证情况。
          预警口径：证书到期日前 30 天进入临期预警；到期日早于当天即为已过期（超过预警上限），
          已过期证书不允许保存「可承接」状态；同一人同一证书重复登记时按最近一次有效期合并，只保留一条。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记人员资质</button>
        <button class="btn" type="button" @click="exportRows">导出人员资质清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section v-if="showForm" class="create-panel">
      <h3 class="panel-title">{{ formTitle }}</h3>
      <form class="form-grid" @submit.prevent="submitForm">
        <label v-for="field in formFields" :key="field.name" class="filter-item">
          <span>{{ field.label }}</span>
          <select v-if="field.options" v-model="form[field.name]">
            <option v-for="option in field.options" :key="option" :value="option">{{ option }}</option>
          </select>
          <input v-else v-model="form[field.name]" :type="field.type ?? 'text'" :placeholder="`请填写${field.label}`" />
        </label>
        <button class="btn primary" type="submit">保存</button>
        <button class="btn ghost" type="button" @click="showForm = false">取消</button>
      </form>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="按姓名、人员编号或证书名称检索" />
      </label>
      <label class="filter-item">
        <span>岗位</span>
        <input v-model="filters.position" placeholder="按岗位检索" />
      </label>
      <label class="filter-item">
        <span>预警状态</span>
        <select v-model="filters.status">
          <option value="">全部</option>
          <option v-for="item in alertStatuses" :key="item" :value="item">{{ item }}</option>
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
          <td v-for="column in columns" :key="column" :class="alertClass(column, row)">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="prefillRetrain(row)">复训登记</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无人员资质数据，可先登记人员资质</td>
        </tr>
      </tbody>
    </table>

    <h3 class="panel-title">按岗位汇总持证情况</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in summaryColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in positions" :key="String(row['岗位'])">
          <td v-for="column in summaryColumns" :key="column">{{ row[column] ?? '—' }}</td>
        </tr>
        <tr v-if="!positions.length">
          <td :colspan="summaryColumns.length" class="empty-state">暂无岗位持证数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条人员资质记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type FormField = { name: string; label: string; type?: string; options?: string[] }

const ENDPOINT = '/api/qualification'
const columns = ["人员编号", "姓名", "岗位", "证书名称", "证书编号", "培训日期", "证书到期日", "剩余天数", "承接状态", "预警状态"]
const summaryColumns = ["岗位", "持证人数", "证书数", "有效", "临期预警", "已过期"]
const alertStatuses = ["有效", "临期预警", "已过期"]
const formFields: FormField[] = [
  { name: '人员编号', label: '人员编号' },
  { name: '姓名', label: '姓名' },
  { name: '岗位', label: '岗位' },
  { name: '证书名称', label: '证书名称' },
  { name: '证书编号', label: '证书编号' },
  { name: '培训日期', label: '培训日期', type: 'date' },
  { name: '证书到期日', label: '证书到期日', type: 'date' },
  { name: '承接状态', label: '承接状态', options: ['可承接', '暂停承接'] },
]

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const positions = ref<Row[]>([])
const stats = ref<Array<{ label: string; value: number }>>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const showForm = ref(false)
const formTitle = ref('登记人员资质')

// 筛选条件从地址栏恢复，刷新后查询条件与预警状态保持一致
const filters = ref<Record<string, string>>({
  keyword: String(route.query.keyword ?? ''),
  position: String(route.query.position ?? ''),
  status: String(route.query.status ?? ''),
})

const emptyForm = (): Record<string, string> => ({
  人员编号: '',
  姓名: '',
  岗位: '',
  证书名称: '',
  证书编号: '',
  培训日期: '',
  证书到期日: '',
  承接状态: '可承接',
})
const form = ref<Record<string, string>>(emptyForm())

function activeQuery() {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters.value)) {
    if (value) {
      query[key] = value
    }
  }
  return query
}

function alertClass(column: string, row: Row) {
  if (column !== '预警状态') {
    return ''
  }
  if (row[column] === '已过期') {
    return 'alert-expired'
  }
  if (row[column] === '临期预警') {
    return 'alert-warning'
  }
  return ''
}

function resetFilters() {
  filters.value = { keyword: '', position: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  formTitle.value = '登记人员资质'
  form.value = emptyForm()
  showForm.value = true
}

function prefillRetrain(row: Row) {
  formTitle.value = `复训登记：${row['姓名']} · ${row['证书名称']}`
  form.value = {
    ...emptyForm(),
    人员编号: String(row['人员编号'] ?? ''),
    姓名: String(row['姓名'] ?? ''),
    岗位: String(row['岗位'] ?? ''),
    证书名称: String(row['证书名称'] ?? ''),
    证书编号: String(row['证书编号'] ?? ''),
  }
  showForm.value = true
}

async function submitForm() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: form.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '人员资质登记失败，请检查后重试')
    }
    noticeMessage.value = payload.message ?? '人员资质已登记'
    showForm.value = false
    form.value = emptyForm()
    await Promise.all([reload(), loadSummary()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员资质登记失败'
  }
}

async function loadSummary() {
  try {
    const response = await request(`${ENDPOINT}/summary`)
    if (!response.ok) {
      throw new Error('岗位持证汇总读取失败')
    }
    const payload = await response.json()
    stats.value = payload.cards ?? []
    positions.value = payload.positions ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '岗位持证汇总读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  // 把当前筛选条件写回地址栏，刷新页面后按同样条件重新查询
  void router.replace({ query: activeQuery() })
  const query = new URLSearchParams(activeQuery()).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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

onMounted(() => {
  void reload()
  void loadSummary()
})
</script>
