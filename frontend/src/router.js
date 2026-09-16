import { createRouter, createWebHistory } from 'vue-router'

// 路由级懒加载。总览页首屏同步加载，其余按需取 chunk。
// 关键收益在 /train/monitor：它依赖 LineChart → echarts，而 echarts 单独成
// chunk 有 460KB+。若静态引入，用户打开「数据集」页也要先下完整个图表库。
import OverviewPage from './pages/OverviewPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', name: 'overview', component: OverviewPage, meta: { title: '总览' } },
    { path: '/datasets', name: 'datasets', component: () => import('./pages/DatasetsPage.vue'), meta: { title: '数据集' } },
    { path: '/train/config', name: 'train-config', component: () => import('./pages/TrainConfigPage.vue'), meta: { title: '训练配置' } },
    { path: '/train/monitor', name: 'train-monitor', component: () => import('./pages/TrainMonitorPage.vue'), meta: { title: '训练监控' } },
    { path: '/results', name: 'results', component: () => import('./pages/ResultsPage.vue'), meta: { title: '结果 · 模型库' } },
    { path: '/registry', name: 'registry', component: () => import('./pages/RegistryPage.vue'), meta: { title: '模型注册中心' } },
    { path: '/queue', name: 'queue', component: () => import('./pages/QueuePage.vue'), meta: { title: '任务队列' } },
    // 兜底：后端 SPA 回退会把任意路径都吐回 index.html，没有这条时
    // 用户访问 /nope 会看到「侧栏正常、内容区全空白」，无从判断是页面不存在
    // 还是前端崩了。
    { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./pages/NotFoundPage.vue'), meta: { title: '页面不存在' } },
  ],
})
