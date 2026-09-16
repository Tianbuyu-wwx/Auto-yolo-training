import { createRouter, createWebHistory } from 'vue-router'

import OverviewPage from './pages/OverviewPage.vue'
import DatasetsPage from './pages/DatasetsPage.vue'
import TrainConfigPage from './pages/TrainConfigPage.vue'
import TrainMonitorPage from './pages/TrainMonitorPage.vue'
import ResultsPage from './pages/ResultsPage.vue'
import QueuePage from './pages/QueuePage.vue'
import NotFoundPage from './pages/NotFoundPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', name: 'overview', component: OverviewPage, meta: { title: '总览' } },
    { path: '/datasets', name: 'datasets', component: DatasetsPage, meta: { title: '数据集' } },
    { path: '/train/config', name: 'train-config', component: TrainConfigPage, meta: { title: '训练配置' } },
    { path: '/train/monitor', name: 'train-monitor', component: TrainMonitorPage, meta: { title: '训练监控' } },
    { path: '/results', name: 'results', component: ResultsPage, meta: { title: '结果 · 模型库' } },
    { path: '/queue', name: 'queue', component: QueuePage, meta: { title: '任务队列' } },
    // 兜底：后端 SPA 回退会把任意路径都吐回 index.html，没有这条时
    // 用户访问 /nope 会看到「侧栏正常、内容区全空白」，无从判断是页面不存在
    // 还是前端崩了。
    { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFoundPage, meta: { title: '页面不存在' } },
  ],
})
