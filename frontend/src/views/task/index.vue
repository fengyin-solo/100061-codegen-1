<template>
  <section class="page" data-module="task">
    <header class="page-head">
      <div>
        <h2>检测任务管理</h2>
        <p class="page-desc">维护检测任务，围绕任务编号、关联样品、检测项目、承检人员做登记、筛选与状态流转；派发前会核查承检人员资质。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测任务</button>
        <button class="btn" type="button" @click="exportRows">导出检测任务清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无检测任务数据，可先登记检测任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条检测任务记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dispatchDialog.visible" class="dialog-mask" @click.self="closeDispatch">
      <div class="dialog">
        <h3>派发任务 {{ dispatchDialog.taskCode }}</h3>
        <label class="form-item">
          <span>承检人员（仅列出资质有效且可承接的人员）</span>
          <select v-model="dispatchDialog.assignee">
            <option value="">请选择承检人员</option>
            <option v-for="option in dispatchDialog.options" :key="option.key" :value="option.name">
              {{ option.label }}
            </option>
          </select>
        </label>
        <p v-if="dispatchDialog.error" class="error-text">{{ dispatchDialog.error }}</p>
        <div class="form-actions">
          <button class="btn primary" type="button" @click="confirmDispatch">确认派发</button>
          <button class="btn ghost" type="button" @click="closeDispatch">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type DispatchOption = { key: string; name: string; label: string }

const ENDPOINT = '/api/task'
const columns = ["任务编号", "关联样品", "检测项目", "承检人员", "计划完成日", "实际完成日", "任务优先级", "任务状态"]
const actions = ["派发任务", "提交复核", "确认完成"]
const statuses = ["待派发", "检测中", "待复核", "已完成"]
const stats = [{"label": "待派发任务", "value": 0}, {"label": "检测中任务", "value": 0}, {"label": "超期任务", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const dispatchDialog = ref({
  visible: false,
  taskId: 0,
  taskCode: '',
  assignee: '',
  options: [] as DispatchOption[],
  error: '',
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测任务登记入口尚未接入审批流'
}

async function readPayload(response: Response): Promise<{ ok: boolean; message?: string }> {
  const payload = (await response.json()) as { ok?: boolean; message?: string }
  return { ok: response.ok && payload.ok !== false, message: payload.message }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  if (action === '派发任务') {
    await openDispatch(row)
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      throw new Error(result.message ?? '检测任务动作未生效，请稍后重试')
    }
    infoMessage.value = result.message ?? ''
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务操作失败'
  }
}

async function openDispatch(row: Row) {
  dispatchDialog.value = {
    visible: true,
    taskId: Number(row.id),
    taskCode: String(row['任务编号'] ?? ''),
    assignee: '',
    options: [],
    error: '',
  }
  try {
    const response = await request('/api/personnel/options')
    if (!response.ok) {
      throw new Error('可派发人员名单读取失败')
    }
    const payload = await response.json()
    const options: DispatchOption[] = (payload.items ?? []).map((item: Record<string, string>) => ({
      key: `${item['人员编号']}-${item['证书名称']}`,
      name: item['姓名'],
      label: `${item['姓名']} · ${item['岗位']} · ${item['证书名称']}（${item['资质状态']}，有效期至 ${item['有效期至']}）`,
    }))
    dispatchDialog.value.options = options
    const current = String(row['承检人员'] ?? '')
    if (current && options.some((option) => option.name === current)) {
      dispatchDialog.value.assignee = current
    }
  } catch (error) {
    dispatchDialog.value.error = error instanceof Error ? error.message : '可派发人员名单读取失败'
  }
}

function closeDispatch() {
  dispatchDialog.value.visible = false
}

async function confirmDispatch() {
  const dialog = dispatchDialog.value
  dialog.error = ''
  errorMessage.value = ''
  infoMessage.value = ''
  if (!dialog.assignee) {
    dialog.error = '请先选择承检人员'
    return
  }
  try {
    const response = await request(`${ENDPOINT}/${dialog.taskId}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action: '派发任务', 承检人员: dialog.assignee } }),
    })
    const result = await readPayload(response)
    if (!result.ok) {
      // 资质未登记、已过期或暂停承接都会被拦下，原因直接展示在弹窗里。
      dialog.error = result.message ?? '派发被拦下，请确认承检人员资质'
      return
    }
    infoMessage.value = result.message ?? '检测任务已派发'
    closeDispatch()
    await reload()
  } catch (error) {
    dialog.error = error instanceof Error ? error.message : '检测任务派发失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检测任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '检测任务列表读取失败'
  }
}

onMounted(reload)
</script>
