/* ============================================================================
   AYT 启动器 · live.js —— 真数据层（Phase 2b/3）
   ----------------------------------------------------------------------------
   行为契约：
   - file:// 直接打开（无后端）→ 静默不激活，原型演示行为原样保留；
   - 被启动器加载（同源 /api/health 可达）→ 接管：
       · 各页数据填充（datasets / runs / registry / queue / env-report / models）
       · 训练提交 / 入队 / 停止（POST 真动作）
       · WS /ws/training 实时日志 + 指标 + 曲线累积
   依赖 index.html 顶层符号（classic script 共享全局词法环境）：
       $ $$ setScene go toast drawChart fldVal ddSyncAll makeDD cfgValidate state chartGeo
   ============================================================================ */
(function () {
  'use strict';

  var LIVE = {
    on: false, health: null,
    datasets: [], statuses: [], models: [],
    runs: [], checkpoints: [], registry: {}, queue: [], env: null,
    status: {}, logs: [], lastLogBlock: '',
    series: { loss: [], m50: [], m95: [] }, lastEp: 0,
    ws: null, wasRunning: false, selectSig: '', lastDataAt: null,
  };
  window.__live = LIVE;

  /* ======================== 工具 ======================== */
  function el(id) { return document.getElementById(id); }
  function setTxt(id, t) { var e = el(id); if (e) e.textContent = t; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function get(p) {
    return fetch(p, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(p + ' → ' + r.status);
      return r.json();
    });
  }
  function post(p, body) {
    return fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) throw new Error(d.detail || (p + ' → ' + r.status));
          return d;
        });
      });
  }
  function fmtDur(sec) {
    if (sec == null) return '';
    if (sec < 90) return Math.round(sec) + ' 秒';
    if (sec < 3600) return Math.round(sec / 60) + ' 分';
    return (sec / 3600).toFixed(1) + ' 小时';
  }
  function fmtDate(s) {
    if (!s) return '—';
    s = String(s);
    return s.length >= 10 ? s.slice(0, 10) : s;
  }
  function statusOf(name) {
    for (var i = 0; i < LIVE.statuses.length; i++) if (LIVE.statuses[i].name === name) return LIVE.statuses[i];
    return null;
  }
  function runNameOf(path) {
    var m = /[\\/]runs[\\/][^\\/]+[\\/]([^\\/]+)[\\/]weights[\\/]/.exec(String(path || ''));
    return m ? m[1] : '';
  }
  function map50OfRun(run) {
    var ds = Object.keys(LIVE.registry);
    for (var i = 0; i < ds.length; i++) {
      var items = LIVE.registry[ds[i]] || [];
      for (var j = 0; j < items.length; j++) {
        if (runNameOf(items[j].model_path) === run) {
          var v = items[j].metrics && items[j].metrics.mAP50;
          return (v == null) ? '—' : (+v).toFixed(4);
        }
      }
    }
    for (var k = 0; k < LIVE.checkpoints.length; k++) if (LIVE.checkpoints[k].run === run) return '—';
    return '—';
  }

  /* ======================== 探测 → 启动 ======================== */
  /* file:// 演示模式直接短路：不发 fetch（file:// 下 fetch 会撞 CORS policy，在控制台留噪音） */
  if (location.protocol !== 'http:' && location.protocol !== 'https:') {
    console.log('[live] 非 http(s) 上下文（' + location.protocol + '）—— 演示模式');
    return;
  }
  fetch('/api/health', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (h) {
      if (!h || h.status !== 'ok') { console.log('[live] 无后端 —— 演示模式'); return; }
      LIVE.on = true; LIVE.health = h;
      console.log('[live] 已连接管理面后端 —— 接管数据');
      boot();
    })
    .catch(function () { console.log('[live] 演示模式（fetch 失败）'); });

  function boot() {
    overlayRender();
    wireActions();
    bindInferenceBtn();
    refreshAll();
    setInterval(refreshAll, 15000);
    addEventListener('focus', refreshAll);
    connectWS();
  }

  /* ======================== 拉取 ======================== */
  function refreshAll() {
    return Promise.all([
      get('/api/datasets').catch(nn), get('/api/trainings/status').catch(nn),
      get('/api/trainings/runs').catch(nn), get('/api/models').catch(nn),
      get('/api/registry').catch(nn), get('/api/queue/tasks').catch(nn),
      get('/api/launcher/env-report').catch(nn),
      get('/api/inference/status').catch(nn), get('/api/recycle').catch(nn),
    ]).then(function (r) {
      if (r[0]) { LIVE.datasets = r[0].datasets || []; LIVE.statuses = r[0].statuses || []; }
      if (r[1]) LIVE.status = r[1];
      if (r[2]) { LIVE.runs = r[2].runs || []; LIVE.checkpoints = r[2].checkpoint_details || []; LIVE.artifacts = r[2].artifacts || {}; }
      if (r[3]) LIVE.models = r[3].models || [];
      if (r[4]) LIVE.registry = r[4].datasets || {};
      if (r[5]) LIVE.queue = r[5].tasks || [];
      if (r[6]) LIVE.env = r[6];
      if (r[7]) LIVE.inference = r[7];
      if (r[8]) LIVE.recycle = r[8].items || [];
      LIVE.lastDataAt = new Date();
      applyAll();
    });
  }
  function nn(e) { console.warn('[live] 端點读取失败', e && e.message); return null; }

  function fixPathCopy() {
    document.querySelectorAll('.sec-head .hint').forEach(function (n) {
      var t = n.textContent || '';
      if (t.indexOf('runs/detect') >= 0 && t.indexOf('artifacts') < 0) {
        n.textContent = t.replace('runs/detect', 'artifacts/runs/detect');
      }
    });
  }

  function applyAll() {
    applyHome(); applyDatasets(); applyConfigSelects(); applyCheckpoints();
    applyResults(); applyRegistry(); applyQueue(); applyCheckup(); applyStatus();
    applyInference(); applyRecycle(); fixPathCopy();
  }

  /* ======================== 首页 ======================== */
  function applyHome() {
    var trainable = LIVE.datasets.length;
    var total = LIVE.statuses.length || trainable;
    var last = LIVE.checkpoints[0];
    var lastInfo = last ? (last.run + ' · ' + fmtDate(last.modified)) : '';
    setTxt('heroSub', trainable + ' 个数据集可训练 · 共 ' + total + ' 个已扫描'
      + (last ? ' · 最近断点 ' + lastInfo : ''));

    /* 服务区：训练任务行 */
    /* 右栏 chips */
    updateChips(trainable, total);
    updateHmeta(last);

    /* 最近训练表（源：checkpoint_details，按最近修改倒序） */
    var tb = document.querySelector('#page-home .tbl tbody');
    if (tb) {
      var rows = LIVE.checkpoints.slice(0, 6);
      if (!rows.length) {
        tb.innerHTML = '<tr><td colspan="6" style="color:var(--ink3)">还没有训练记录 —— 从「配置并启动训练」开始</td></tr>';
      } else {
        tb.innerHTML = rows.map(function (c) {
          return '<tr><td class="name">' + esc(c.run) + '</td><td>' + esc(c.dataset || '—')
            + '</td><td>' + esc(fmtDate(c.modified)) + '</td><td class="r">' + esc(map50OfRun(c.run))
            + '</td><td class="r">last · ' + c.epochs_done + ' 轮</td>'
            + '<td class="r"><button class="btn xs ghost" type="button" data-go="results">打开</button></td></tr>';
        }).join('');
        bindGo(tb);
      }
    }
    /* 版本脚注 */
    if (LIVE.env) {
      var vl = document.querySelector('#page-home .verlines');
      if (vl) {
        vl.innerHTML = '<div>Python ' + esc(LIVE.env.python || '—') + ' · torch ' + esc(LIVE.env.torch || '—')
          + ' · ultralytics ' + esc(LIVE.env.ultralytics || '—') + '</div>'
          + '<div>' + esc(LIVE.env.platform || '') + (LIVE.env.gpu && LIVE.env.gpu.name ? ' · ' + esc(LIVE.env.gpu.name) : '') + '</div>'
          + '<div>工作目录 <span class="mono">' + esc(LIVE.env.base_dir || '—') + '</span></div>';
      }
    }
  }

  function updateChips(trainable, total) {
    var chips = document.querySelectorAll('#page-home .home-right .chips .chip');
    if (!chips.length) return;
    var gpu = LIVE.env && LIVE.env.gpu && LIVE.env.gpu.name ? (LIVE.env.gpu.name + (LIVE.env.gpu.memory ? ' · ' + LIVE.env.gpu.memory : '')) : 'GPU 未检测';
    var disks = (LIVE.env && LIVE.env.disks) || {};
    var dkey = Object.keys(disks).filter(function (k) { return /^[A-Z]:/.test(k); })[0];
    var diskTxt = dkey ? (dkey + ' 可用 ' + disks[dkey].free_gb + ' GB') : '磁盘 —';
    var regVersions = 0;
    Object.keys(LIVE.registry).forEach(function (k) { regVersions += (LIVE.registry[k] || []).length; });
    var txts = [gpu, diskTxt, '数据集 ' + total + ' · ' + trainable + ' 可训练', '注册表 ' + regVersions + ' 版本'];
    for (var i = 0; i < chips.length && i < txts.length; i++) {
      chips[i].innerHTML = '<span class="led"></span>' + esc(txts[i]);
    }
  }
  function updateHmeta(last) {
    var hm = document.querySelector('#page-home .home-right .hmeta');
    if (!hm) return;
    var running = LIVE.status && LIVE.status.is_running;
    hm.innerHTML =
      '<div><em>最近</em><span class="mono">' + esc(last ? last.run : '—') + '</span></div>'
      + '<div><em>断点</em>' + (last ? (last.epochs_done + '/' + last.epochs_planned + ' 轮 · ' + fmtDate(last.modified)) : '—') + '</div>'
      + '<div><em>运行</em>' + LIVE.runs.length + ' 个 run · ' + LIVE.checkpoints.length + ' 个可续训断点</div>'
      + '<div><em>队列</em>' + (LIVE.queue.length ? LIVE.queue.length + ' 个任务 · 串行执行' : '空闲 · 串行执行') + '</div>';
  }

  /* ======================== 数据集页 ======================== */
  function applyDatasets() {
    var tb = document.querySelector('#page-datasets .tbl tbody');
    if (!tb || !LIVE.statuses.length) return;
    tb.innerHTML = LIVE.statuses.map(function (s) {
      var chip = s.is_trainable
        ? '<span class="chip ok"><span class="led"></span>可训练</span>'
        : '<span class="chip warn"><span class="led"></span>不可训练</span>';
      var note = (s.issues && s.issues.length) ? '<span class="hint">' + esc(s.issues[0]) + '</span>' : '';
      var acts = s.is_trainable
        ? '<button class="btn xs" type="button" data-toast="重新校验（原型演示）">校验</button> <button class="btn xs ghost" type="button" data-toast="打开样本预览（原型演示）">预览</button>'
        : '<button class="btn xs" type="button" data-toast="生成 data.yaml（原型演示）">生成配置</button> <button class="btn xs ghost" type="button" data-toast="打开样本预览（原型演示）">预览</button>';
      return '<tr><td class="name">' + esc(s.name) + '</td><td class="r">' + s.image_count + '</td><td class="r">' + s.label_count
        + '</td><td>' + chip + '</td><td>' + (s.format || '—') + '</td><td>' + note + '</td><td class="r">' + acts + '</td></tr>';
    }).join('');
    /* 警示横幅：不可训练集合的原因 */
    var banner = document.querySelector('#page-datasets .warnbanner');
    if (banner) {
      var bad = LIVE.statuses.filter(function (s) { return !s.is_trainable; });
      var span = banner.querySelector('.wb-t') || banner.querySelector('span') || banner;
      if (bad.length) {
        span.textContent = '另 ' + bad.length + ' 个不可选：' + bad.map(function (s) { return s.name; }).join('、') + ' —— 缺 data.yaml 或标注不完整。';
        banner.hidden = false;
      } else { banner.hidden = true; }
    }
  }

  /* ======================== 配置页 ======================== */
  function rebuildDD(sel, opts) {
    if (!sel) return;
    while (sel.options.length) sel.remove(0);
    opts.forEach(function (o) {
      var op = document.createElement('option');
      op.value = o.value; op.textContent = o.label;
      sel.appendChild(op);
    });
    var wrap = sel.closest('.dd');
    if (wrap) {
      var parent = wrap.parentNode;
      parent.insertBefore(sel, wrap);
      wrap.remove();
      delete sel.dataset.dd;
      sel.classList.remove('dd-native');
    }
    makeDD(sel);
    ddSyncAll();
  }
  function applyConfigSelects() {
    var sig = LIVE.datasets.join('|') + '##' + LIVE.models.map(function (m) { return m.filename + (m.local ? '1' : '0'); }).join('|');
    if (sig === LIVE.selectSig) return;
    LIVE.selectSig = sig;
    var ds = el('cfgDS');
    if (ds && LIVE.datasets.length) {
      rebuildDD(ds, LIVE.datasets.map(function (n) {
        var st = statusOf(n);
        var suffix = st ? (' · ' + st.image_count + ' 图' + (st.issues && st.issues.length ? '（' + st.issues.length + ' 项注意）' : '')) : '';
        return { value: n, label: n + suffix };
      }).sort(function (a, b) { return ((statusOf(b.value) || {}).image_count || 0) - ((statusOf(a.value) || {}).image_count || 0); }));
    }
    var md = el('cfgModel');
    if (md && LIVE.models.length) {
      var locals = LIVE.models.filter(function (m) { return m.local; });
      var src = locals.length ? locals : LIVE.models;
      rebuildDD(md, src.map(function (m) {
        return { value: m.filename, label: m.filename + (m.local ? '（本地' + (m.size_mb ? ' · ' + m.size_mb + ' MB' : '') + '）' : '（需下载）') };
      }));
    }
    cfgRefresh0();
  }
  function applyCheckpoints() {
    var box = el('cfgResumeBox');
    var sel = box ? box.querySelector('select') : null;
    if (!sel || !LIVE.checkpoints.length) return;
    var sig = LIVE.checkpoints.map(function (c) { return c.path; }).join('|');
    if (sig === LIVE.cpSig) return;
    LIVE.cpSig = sig;
    rebuildDD(sel, LIVE.checkpoints.map(function (c) {
      return {
        value: c.path,
        label: c.run + ' · ' + c.epochs_done + '/' + c.epochs_planned + ' 轮 · ' + c.modified + ' · ' + c.size_mb + ' MB',
      };
    }));
  }
  function cfgRefresh0() { try { cfgRefresh(); } catch (e) { console.warn('[live] cfgRefresh', e); } }

  /* ======================== 结果页 / 注册中心 / 队列 ======================== */
  function applyResults() {
    var tb = document.querySelector('#page-results .tbl tbody');
    if (!tb) return;
    var rows = LIVE.checkpoints.slice(0, 12);
    tb.innerHTML = rows.length ? rows.map(function (c) {
      var art = (LIVE.artifacts || {})[c.run] || {};
      var artTxt = art.best || art.has_best ? '<span class="chip ok"><span class="led"></span>best · last</span>' : '<span class="hint">断点 · 产物以磁盘为准</span>';
      return '<tr><td class="name">' + esc(c.run) + '</td><td>' + esc(c.dataset || '—') + '</td><td>' + esc(fmtDate(c.modified))
        + '</td><td class="r">' + (c.size_mb != null ? c.size_mb + ' MB' : '—') + '</td><td>' + artTxt
        + '</td><td class="r">' + esc(map50OfRun(c.run)) + '</td><td class="r">'
        + '<button class="btn xs" type="button" data-toast="下载 best.pt（原型演示）">下载 best</button> '
        + '<button class="btn xs ghost" type="button" data-toast="断点续训已预填（原型演示）" data-go="config">续训</button>'
        + '</td></tr>';
    }).join('') : '<tr><td colspan="7" style="color:var(--ink3)">还没有训练结果</td></tr>';
    bindGo(tb);
    var stat = document.querySelector('#page-results .stat-strip');
    if (stat) {
      var last = LIVE.checkpoints[0];
      var vers = 0; Object.keys(LIVE.registry).forEach(function (k) { vers += (LIVE.registry[k] || []).length; });
      stat.innerHTML = '<div class="stat"><div class="k">最近断点</div><div class="v">' + esc(last ? last.run : '—') + '</div></div>'
        + '<div class="stat"><div class="k">可续训</div><div class="v">' + LIVE.checkpoints.length + ' <small>个</small></div></div>'
        + '<div class="stat"><div class="k">注册版本</div><div class="v">' + vers + ' <small>个</small></div></div>'
        + '<div class="stat"><div class="k">目录</div><div class="v mono" style="font-size:11px">artifacts/runs/detect</div></div>';
    }
  }

  function applyRegistry() {
    var tb = document.querySelector('#page-registry .tbl tbody');
    if (!tb) return;
    var items = [];
    Object.keys(LIVE.registry).forEach(function (ds) {
      (LIVE.registry[ds] || []).forEach(function (it) { items.push({ ds: ds, it: it }); });
    });
    items.sort(function (a, b) { return String(b.it.created_at || '').localeCompare(String(a.it.created_at || '')); });
    tb.innerHTML = items.length ? items.map(function (x) {
      var it = x.it;
      var m50 = it.metrics && it.metrics.mAP50 != null ? (+it.metrics.mAP50).toFixed(4) : '—';
      var pr = it.params || {};
      var weights = it.weights_missing ? ' <span class="chip err"><span class="led"></span>权重缺失</span>' : '';
      return '<tr><td class="name">' + esc(it.version_id) + '</td><td>' + esc(runNameOf(it.model_path) || x.ds) + '</td>'
        + '<td><span class="chip ' + (it.weights_missing ? 'err' : 'acc') + '"><span class="led"></span>' + esc(it.status || (it.weights_missing ? 'missing' : 'staging')) + '</span>' + weights + '</td>'
        + '<td class="r">' + m50 + '</td>'
        + '<td><span class="hint mono">' + esc('epochs ' + (pr.epochs != null ? pr.epochs : '?') + ' · imgsz ' + (pr.imgsz != null ? pr.imgsz : '?') + ' · ' + (pr.model || '')) + '</span></td>'
        + '<td class="r">' + esc(fmtDate(it.created_at)) + '</td>'
        + '<td class="r">'
        + '<button class="btn xs" type="button" data-toast="已晋升为生产版本（原型演示）">晋升生产</button> '
        + '<button class="btn xs ghost" type="button" data-toast="打标签（原型演示）">打标</button> '
        + '<button class="btn xs ghost" type="button" data-toast="删除版本（原型演示）">删除</button>'
        + '</td></tr>';
    }).join('') : '<tr><td colspan="7" style="color:var(--ink3)">注册表为空 —— 训练完成后在这里登记版本</td></tr>';
    bindGo(tb);
  }

  function applyQueue() {
    var page = el('page-queue');
    if (!page) return;
    var empty = page.querySelector('.empty-state');
    var list = el('liveQueueList');
    if (!LIVE.queue.length) {
      if (list) list.remove();
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    if (!list) {
      list = document.createElement('div');
      list.id = 'liveQueueList';
      list.className = 'rows';
      (empty && empty.parentNode ? empty.parentNode : page).appendChild(list);
    }
    list.innerHTML = LIVE.queue.map(function (t) {
      return '<div class="row"><span class="rtxt"><b>#' + t.id + ' · ' + esc(t.dataset_name || t.dataset || '—')
        + '</b><span>' + esc(t.status || '—') + (t.created_at ? ' · ' + esc(fmtDate(t.created_at)) : '') + '</span></span>'
        + '<span class="rctl">' + (String(t.status).indexOf('run') === 0 || String(t.status) === 'pending'
          ? '<button class="btn xs" type="button" data-qcancel="' + t.id + '">取消</button>' : '') + '</span></div>';
    }).join('');
    list.querySelectorAll('[data-qcancel]').forEach(function (b) {
      b.addEventListener('click', function () {
        post('/api/queue/' + b.dataset.qcancel + '/cancel', {}).then(function () {
          toast('ok', '已取消队列任务', ''); refreshAll();
        }).catch(function (e) { toast('err', '取消失败', String(e.message || e)); });
      });
    });
  }

  /* ======================== 环境自检页 ======================== */
  function applyCheckup() {
    var wraps = document.querySelectorAll('#page-checkup .rows');
    var wrap = wraps.length ? wraps[wraps.length - 1] : null;   /* 检查行容器（页面里还有一个说明 .rows） */
    if (!wrap || !LIVE.env) return;
    var env = LIVE.env;
    var rows = [
      ['平台', env.platform || '—', 'ok'],
      ['Python', env.python || '—', env.python ? 'ok' : 'warn'],
      ['PyTorch', env.torch || '未安装', env.torch ? 'ok' : 'err'],
      ['Ultralytics', env.ultralytics || '未安装', env.ultralytics ? 'ok' : 'err'],
      ['GPU', env.gpu && env.gpu.name ? (env.gpu.name + ' · ' + (env.gpu.memory || '') + ' · 驱动 ' + (env.gpu.driver || '')) : '未检测到（nvidia-smi 不可用）', env.gpu && env.gpu.name ? 'ok' : 'warn'],
      ['工作目录', env.base_dir || '—', 'ok'],
      ['管理面后端', '已连接 · /api/health ok · 随启动器生命周期', 'ok'],
    ];
    var disks = env.disks || {};
    Object.keys(disks).forEach(function (k) {
      rows.push(['磁盘 ' + k, '总 ' + disks[k].total_gb + ' GB · 可用 ' + disks[k].free_gb + ' GB', disks[k].free_gb < 10 ? 'warn' : 'ok']);
    });
    wrap.innerHTML = rows.map(function (r) {
      return '<div class="row"><span class="tile"><svg class="i"><use href="#i-shield"/></svg></span>'
        + '<span class="rtxt"><b>' + esc(r[0]) + '</b><span>' + esc(r[1]) + '</span></span>'
        + '<span class="rctl"><span class="chip ' + r[2] + '"><span class="led"></span>' + (r[2] === 'ok' ? '通过' : r[2] === 'warn' ? '注意' : '缺失') + '</span></span></div>';
    }).join('');
    var hint = document.querySelector('#page-checkup .sec-head .hint') || document.querySelector('#page-checkup .ptop .hint');
    if (hint) hint.textContent = rows.length + ' 项只读检查 · 数据来自 /api/launcher/env-report';
  }

  /* ======================== 状态（首页/监控联动） ======================== */
  function applyStatus() {
    var st = LIVE.status || {};
    var running = !!st.is_running;
    if (running && state.scene !== 'training') setScene('training');
    else if (!running && state.scene === 'training' && LIVE.wasRunning) { setScene('idle'); }
    LIVE.wasRunning = running;

    setTxt('heroTitle', running ? '训练进行中' : '一切就绪');
    var led = el('heroLed');
    if (led) led.className = 'led ' + (running ? 'acc live' : 'ok');
    setTxt('btnRunLabel', running ? '打开监控' : '配置并启动训练');

    /* 服务区训练行 */
    var trainLine = st.is_running
      ? (st.current_epoch + '/' + st.total_epochs + ' 轮 · loss ' + (+st.current_loss || 0).toFixed(3))
      : '空闲 · 无进行中的训练';
    setTxt('svcTrainMeta', trainLine);
    var chip = el('svcTrainChip');
    if (chip) chip.innerHTML = '<span class="led"></span>' + (running ? '训练中' : '空闲');
    if (chip) chip.className = 'chip ' + (running ? 'acc' : '');
    var jmon = el('jmonSub');
    if (jmon) jmon.textContent = running ? ('实时曲线与日志 · E' + st.current_epoch + '/' + st.total_epochs) : '实时曲线与日志 · 当前空闲';
    var tprog = el('tprog');
    if (tprog) {
      tprog.hidden = !running;
      if (running) {
        var bar = tprog.querySelector('.bar i');
        if (bar) bar.style.width = Math.max(0, Math.min(100, st.progress || 0)) + '%';
        var span = tprog.querySelector('span');
        if (span) span.textContent = '训练中 · E' + st.current_epoch + '/' + st.total_epochs + ' · mAP@50 ' + (+st.current_map50 || 0).toFixed(4);
      }
    }
  }

  /* ======================== 监控：指标 / 日志 / 曲线 ======================== */
  function livePaintMetrics(st) {
    var running = !!st.is_running;
    setTxt('cState', running ? ('训练中 · E' + st.current_epoch + '/' + st.total_epochs) : '空闲');
    setTxt('mEpoch', running || st.current_epoch ? (st.current_epoch + ' / ' + st.total_epochs) : '—');
    setTxt('mEpochH', st.total_epochs ? ('总计 ' + st.total_epochs + ' 轮') : '总计轮数待定');
    setTxt('mLoss', (st.current_epoch ? (+st.current_loss || 0).toFixed(3) : '—'));
    setTxt('mMap0', (st.current_epoch ? (+st.current_map50 || 0).toFixed(4) : '—'));
    setTxt('mMap1', (st.current_epoch ? (+st.current_map50_95 || 0).toFixed(4) : '—'));
    setTxt('mpPct', ((+st.progress || 0)).toFixed(1) + '%');
    var bar = el('mpBar'); if (bar) bar.style.width = Math.max(0, Math.min(100, +st.progress || 0)) + '%';
    setTxt('mpSub', running
      ? ('第 ' + st.current_epoch + '/' + st.total_epochs + ' 轮'
        + (st.eta_seconds ? ' · 预计剩余 ' + fmtDur(st.eta_seconds) : '')
        + ' · 训练在后台子进程，关窗不中断')
      : (LIVE.runs.length ? '等待训练开始 —— 上次：' + LIVE.checkpoints[0].run : '等待训练开始'));
  }

  var LC_TEXT = { sys: '系统', out: '输出', err: '错误', warn: '警告', ok: '成功' };
  function liveBuildLine(panel, t, k, m) {
    var ln = document.createElement('div');
    ln.className = 'ln in';
    ln.innerHTML = '<span class="lt">' + esc(t) + '</span><span class="lc ' + k + '">' + LC_TEXT[k] + '</span><span class="lm">' + esc(m) + '</span>';
    panel.appendChild(ln);
  }
  function liveRepaintLog() {
    var panel = el('logPanel');
    if (!panel) return;
    panel.innerHTML = '';
    if (!LIVE.logs.length) {
      liveBuildLine(panel, '', 'sys', LIVE.status.is_running ? '等待训练输出…' : '已连接管理面 · 等待训练');
    } else {
      LIVE.logs.forEach(function (l) { liveBuildLine(panel, l.t, l.k, l.m); });
    }
    panel.scrollTop = panel.scrollHeight;
  }
  function liveAppendLogs(text) {
    if (!text || text === LIVE.lastLogBlock) return;
    LIVE.lastLogBlock = text;
    String(text).replace(/\r/g, '').split('\n').forEach(function (raw) {
      var s = raw.trim(); if (!s) return;
      var t = '', k = 'out', m = s;
      var mm = /^\[(\d{2}:\d{2}:\d{2})\]\s*\[([A-Z]+)\]\s*(.*)$/.exec(s);
      if (mm) {
        t = mm[1]; m = mm[3];
        k = mm[2] === 'WARNING' ? 'warn' : (mm[2] === 'ERROR' || mm[2] === 'CRITICAL') ? 'err' : (mm[2] === 'SUCCESS' ? 'ok' : 'out');
      } else {
        var tm = /^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$/.exec(s);
        if (tm) { t = tm[1]; m = tm[2]; }
      }
      LIVE.logs.push({ t: t, k: k, m: m });
    });
    if (LIVE.logs.length > 200) LIVE.logs = LIVE.logs.slice(-200);
    if (state.page === 'monitor') liveRepaintLog();
  }

  function redrawCharts() {
    var cl = el('chartLoss'), cm = el('chartMap');
    if (!cl || state.page !== 'monitor' || LIVE.series.loss.length < 2 || !window.drawChart) return;
    var acc = 'rgb(' + getComputedStyle(document.documentElement).getPropertyValue('--acc-rgb').trim() + ')';
    var loss = LIVE.series.loss.map(function (p) { return p[1]; });
    var m50 = LIVE.series.m50.map(function (p) { return p[1]; });
    var m95 = LIVE.series.m95.map(function (p) { return p[1]; });
    var geoL = drawChart(cl, [{ data: loss, color: acc, dots: true, name: 'loss' }], { gid: 'lo' });
    var hiM = Math.max(0.02, Math.max.apply(null, m50) * 1.25);
    var geoM = drawChart(cm, [
      { data: m50, color: acc, dots: true, name: 'mAP@50' },
      { data: m95, color: 'rgba(150,162,176,.9)', w: '1.6', dash: '3 3', name: 'mAP@95', area: false },
    ], { lo: 0, hi: hiM, gid: 'mp', fmt: 4 });
    if (window.chartGeo) { chartGeo.loss = geoL; chartGeo.map = geoM; }
  }

  /* ======================== WS ======================== */
  function connectWS() {
    try {
      var ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/training');
      LIVE.ws = ws;
      ws.onmessage = function (e) {
        var m; try { m = JSON.parse(e.data); } catch (_) { return; }
        if (m.type !== 'training') return;
        var st = m.status || {};
        LIVE.status = st;
        applyStatus();
        if (state.page === 'monitor') livePaintMetrics(st);
        if (m.logs && String(m.logs).trim()) liveAppendLogs(m.logs);
        if (st.is_running && st.current_epoch > 0 && st.current_epoch !== LIVE.lastEp) {
          LIVE.lastEp = st.current_epoch;
          LIVE.series.loss.push([st.current_epoch, +st.current_loss || 0]);
          LIVE.series.m50.push([st.current_epoch, +st.current_map50 || 0]);
          LIVE.series.m95.push([st.current_epoch, +st.current_map50_95 || 0]);
          redrawCharts();
        }
      };
      ws.onclose = function () { setTimeout(connectWS, 3000); };
    } catch (e) { setTimeout(connectWS, 3000); }
  }

  /* ======================== 动作（训练提交 / 入队 / 停止） ======================== */
  function fv(id) { var e = el(id); return e ? e.value : ''; }
  function fsel(id) { return String(fv(id)).split(' · ')[0].trim(); }
  function fnum(id) { var v = parseFloat(fv(id)); return isNaN(v) ? undefined : v; }
  function numFld(gid, label) {
    var v = (typeof fldVal === 'function') ? fldVal(gid, label) : '—';
    var n = parseFloat(v); return isNaN(n) ? undefined : n;
  }
  function chk(txt) {
    var r = false;
    document.querySelectorAll('#page-config .chk').forEach(function (l) {
      if (l.textContent.indexOf(txt) >= 0) { var i = l.querySelector('input'); if (i) r = i.checked; }
    });
    return r;
  }
  function resumePath() {
    var box = el('cfgResumeBox');
    if (box && !box.hidden) {
      var s = box.querySelector('select');
      if (s && s.selectedIndex >= 0 && s.options[s.selectedIndex]) return s.options[s.selectedIndex].value;
    }
    return '';
  }
  function buildTrainingRequest() {
    return {
      dataset_name: fv('cfgDS'),
      model: fv('cfgModel'),
      task: fsel('cfgTask') || 'detect',
      epochs: fnum('f-epochs'), imgsz: fnum('f-imgsz'),
      batch: fv('s-batch') === '-1' ? -1 : (parseInt(fv('s-batch'), 10) || 16),
      device: fsel('s-device') === 'auto' ? '' : fsel('s-device'),
      workers: fnum('f-workers'),
      lr0: fnum('f-lr0'), optimizer: fsel('s-optimizer') || 'AdamW',
      cos_lr: chk('余弦'), lrf: fnum('f-lrf'), warmup_epochs: fnum('f-warmup'),
      patience: fnum('f-patience'), weight_decay: fnum('f-wdeca'),
      dropout: numFld('reg', 'Dropout'), label_smoothing: numFld('reg', '标签平滑'), freeze: numFld('reg', '冻结层数'),
      box: numFld('loss', 'Box 权重'), cls: numFld('loss', '分类权重'), dfl: numFld('loss', 'DFL 权重'),
      close_mosaic: numFld('aug', '最后关 Mosaic'), mosaic: numFld('aug', 'Mosaic 概率'),
      mixup: numFld('aug', 'Mixup 概率'), copy_paste: numFld('aug', 'Copy-Paste'),
      degrees: numFld('aug', '旋转范围'), translate: numFld('aug', '平移幅度'), scale: numFld('aug', '缩放幅度'),
      shear: numFld('aug', '剪切范围'), perspective: numFld('aug', '透视幅度'), flipud: numFld('aug', '上下翻转概率'),
      hsv_h: numFld('aug', '色相扰动'), hsv_s: numFld('aug', '饱和度扰动'), hsv_v: numFld('aug', '明度扰动'),
      cache: fsel('s-cache') || 'disk',
      rect: chk('矩形'), deterministic: chk('确定性'),
      skip_validation: !!(el('cfgSkipVal') && el('cfgSkipVal').checked),
      resume_from: resumePath(),
    };
  }

  LIVE.cfgRun = function () {
    if (typeof cfgValidate === 'function' && !cfgValidate()) return;
    var req = buildTrainingRequest();
    if (!req.dataset_name) { toast('warn', '请先选择数据集', ''); return; }
    if (req.resume_from) { req.epochs = undefined; }
    post('/api/trainings/start', req).then(function () {
      toast('ok', '训练已启动', req.dataset_name + ' · ' + req.model + ' · ' + (req.epochs || '按断点') + ' 轮');
      LIVE.logs = []; LIVE.lastLogBlock = '';
      setScene('training'); go('monitor');
      setTimeout(refreshAll, 800);
    }).catch(function (e) { toast('err', '启动失败', String(e.message || e)); });
  };
  LIVE.enqueue = function () {
    if (typeof cfgValidate === 'function' && !cfgValidate()) return;
    var req = buildTrainingRequest();
    if (!req.dataset_name) { toast('warn', '请先选择数据集', ''); return; }
    post('/api/queue/enqueue', req).then(function (d) {
      toast('ok', '已加入队列', 'task #' + (d.task_id != null ? d.task_id : '?') + ' · 队列页可见');
      setTimeout(refreshAll, 600);
    }).catch(function (e) { toast('err', '入队失败', String(e.message || e)); });
  };
  LIVE.stop = function () {
    post('/api/trainings/stop', {}).then(function () {
      toast('warn', '已请求停止训练', '检查点保留：可断点续训');
      setScene('idle');
      setTimeout(refreshAll, 1200);
    }).catch(function (e) { toast('err', '停止失败', String(e.message || e)); });
  };

  /* ======================== P2 · 动作接线（零 HTML 改动） ======================== */

  function launcherApi() { return (window.pywebview && window.pywebview.api) || null; }

  function del(p) {
    return fetch(p, { method: 'DELETE' }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) throw new Error(d.detail || (p + ' → ' + r.status));
        return d;
      });
    });
  }
  function rowNameOf(btn) {
    var tr = btn.closest('tr');
    if (!tr) return '';
    var td = tr.querySelector('td.name');
    return td ? td.textContent.trim() : '';
  }
  function versionDataset(verId) {
    for (var ds in LIVE.registry) {
      var items = LIVE.registry[ds] || [];
      for (var i = 0; i < items.length; i++) if (items[i].version_id === verId) return ds;
    }
    return '';
  }
  function copyText(t, msg) {
    try {
      navigator.clipboard.writeText(t).then(
        function () { if (msg) toast('ok', msg, ''); },
        function () { toast('warn', '复制失败（剪贴板不可用）', t.slice(0, 60)); }
      );
    } catch (e) { toast('warn', '复制失败', String(e)); }
  }
  function openRel(rel) {
    post('/api/launcher/open-path?rel_path=' + encodeURIComponent(rel), {})
      .then(function (r) { toast('ok', '已打开', r.opened || rel); })
      .catch(function (e) { toast('err', '打开失败', String(e.message || e)); });
  }
  function needLauncher(name) {
    if (!launcherApi()) { toast('ok', name, '该操作在启动器窗口内生效 · 当前为浏览器预览'); return false; }
    return true;
  }

  /* ---------- 各动作 ---------- */

  function actPreview(btn) {
    var name = rowNameOf(btn);
    if (!name) return toast('warn', '未识别到数据集', '');
    get('/api/datasets/' + encodeURIComponent(name) + '/preview')
      .catch(function () { return null; })
      .then(function () { openRel('logs/preview_cache/' + name); });
  }
  function actValidate(btn) {
    var n = rowNameOf(btn);
    if (!n) return;
    post('/api/datasets/' + encodeURIComponent(n) + '/validate', {})
      .then(function (r) {
        toast('ok', '校验完成：' + n, (r.issues && r.issues.length) ? r.issues.length + ' 项注意（见数据集页）' : '无问题');
        LIVE.selectSig = ''; refreshAll();
      })
      .catch(function (e) { toast('err', '校验失败', String(e.message || e)); });
  }
  function actConvert(btn) {
    var n = rowNameOf(btn);
    if (!n) return;
    post('/api/datasets/' + encodeURIComponent(n) + '/convert', {})
      .then(function (r) {
        toast('ok', '已生成 data.yaml', n + (r.message ? ' · ' + r.message : ''));
        LIVE.selectSig = ''; refreshAll();
      })
      .catch(function (e) { toast('err', '生成配置失败', String(e.message || e)); });
  }
  function actPickConvertDir() {
    if (!needLauncher('选择待转换的数据集目录')) return;
    launcherApi().pick_dir().then(function (dir) {
      if (!dir) return;
      toast('ok', '已选择目录', dir + ' —— 若尚未被扫描，请把目录放到 dataset/ 下后刷新');
    });
  }
  function actUpload() {
    if (!needLauncher('上传数据集')) return;
    launcherApi().pick_file(true).then(function (p) {
      if (!p) return;
      toast('ok', '正在上传…', String(p).split(/[\\/]/).pop());
      launcherApi().upload_zip(p, location.origin).then(function (r) {
        if (r && r.status === 'error') { toast('err', '上传失败', r.message || ''); return; }
        toast('ok', '上传完成', (r && (r.message || r.name)) || '');
        LIVE.selectSig = ''; refreshAll();
      });
    });
  }
  function actPromote(btn) {
    var ver = rowNameOf(btn), ds = versionDataset(ver);
    if (!ver || !ds) return toast('warn', '未识别到版本', '');
    post('/api/registry/' + encodeURIComponent(ds) + '/' + encodeURIComponent(ver) + '/promote', {})
      .then(function () { toast('ok', '已晋升为生产版本', ver); refreshAll(); })
      .catch(function (e) { toast('err', '晋升失败', String(e.message || e)); });
  }
  function actDeleteVersion(btn) {
    var ver = rowNameOf(btn), ds = versionDataset(ver);
    if (!ver || !ds) return toast('warn', '未识别到版本', '');
    if (!window.confirm('确认删除版本 ' + ver + '？')) return;
    del('/api/registry/' + encodeURIComponent(ds) + '/' + encodeURIComponent(ver))
      .then(function () { toast('ok', '已删除版本', ver); refreshAll(); })
      .catch(function (e) { toast('err', '删除失败', String(e.message || e)); });
  }
  function actTag(btn) {
    var ver = rowNameOf(btn), ds = versionDataset(ver);
    if (!ver || !ds) return toast('warn', '未识别到版本', '');
    var input = window.prompt('标签（逗号分隔）', '');
    if (input == null) return;
    var tags = input.split(/[,，]/).map(function (s) { return s.trim(); }).filter(Boolean);
    if (!tags.length) return;
    post('/api/registry/' + encodeURIComponent(ds) + '/' + encodeURIComponent(ver) + '/tags', { tags: tags })
      .then(function (r) { toast('ok', '已更新标签', (r.tags || tags).join('、')); refreshAll(); })
      .catch(function (e) { toast('err', '打标失败', String(e.message || e)); });
  }
  function actDownloadBest(btn) {
    var run = rowNameOf(btn);
    if (!run) return;
    if (!needLauncher('下载 best.pt')) return;
    var url = location.origin + '/api/trainings/results/' + encodeURIComponent(run) + '/download';
    launcherApi().save_from_url(url, run + '_best.pt').then(function (p) {
      if (p) toast('ok', '已保存', p);
    }).catch(function (e) { toast('err', '下载失败', String(e.message || e)); });
  }
  function actResumePrefill(btn) {
    var run = rowNameOf(btn);
    var cp = null;
    for (var i = 0; i < LIVE.checkpoints.length; i++) {
      if (LIVE.checkpoints[i].run === run) { cp = LIVE.checkpoints[i]; break; }
    }
    if (!cp) { toast('warn', '该 run 无可用断点', run); return; }
    try { go('config'); } catch (e) { /* 非主窗上下文时忽略 */ }
    setTimeout(function () {
      var sw = el('cfgResume');
      if (sw && !sw.classList.contains('on')) sw.click();
      var box = el('cfgResumeBox');
      var sel = box ? box.querySelector('select') : null;
      if (sel) {
        sel.value = cp.path;
        if (typeof ddSyncAll === 'function') ddSyncAll();
      }
      toast('ok', '断点续训已预填', cp.run + ' · ' + cp.epochs_done + '/' + cp.epochs_planned + ' 轮');
    }, 320);
  }
  function actCopyRunPath(btn) {
    var run = rowNameOf(btn);
    var text = 'artifacts/runs/detect/' + run;
    copyText(text, '已复制路径：' + text);
  }
  function actOpenExports() { openRel('artifacts/exports'); }
  function actOpenRuns() { openRel('artifacts/runs/detect'); }
  function actOpenLogs() { openRel('artifacts/logs'); }
  function actRestoreRecycle(btn) {
    var row = btn.closest('.row');
    var name = row ? (row.dataset.recycle || '') : '';
    if (!name) return toast('warn', '未识别到回收项', '');
    post('/api/recycle/' + encodeURIComponent(name) + '/restore', {})
      .then(function () { toast('ok', '已恢复', name); refreshAll(); })
      .catch(function (e) { toast('err', '恢复失败', String(e.message || e)); });
  }
  function actPurgeRecycle(btn) {
    var row = btn.closest('.row');
    var name = row ? (row.dataset.recycle || '') : '';
    if (!window.confirm('彻底删除' + (name ? '「' + name + '」' : '回收站全部内容') + '？不可恢复。')) return;
    post('/api/recycle/purge' + (name ? '?name=' + encodeURIComponent(name) : ''), {})
      .then(function (r) { toast('ok', '已彻底删除 ' + (r.removed || 0) + ' 项', ''); refreshAll(); })
      .catch(function (e) { toast('err', '删除失败', String(e.message || e)); });
  }
  function actRefresh() { refreshAll().then(function () { toast('ok', '已刷新', '数据来自管理面实时状态'); }); }
  function actRecycleInfo() {
    var n = (LIVE.recycle || []).length;
    toast('ok', n ? ('回收站：' + n + ' 项') : '回收站为空', n ? '在结果页「回收站」行可恢复 / 彻底删除' : '');
  }
  function actExportManifest() {
    get('/api/registry').then(function (d) {
      var rows = [['dataset', 'version_id', 'status', 'mAP50', 'created_at', 'model_path']];
      var reg = d.datasets || {};
      Object.keys(reg).forEach(function (ds) {
        (reg[ds] || []).forEach(function (it) {
          rows.push([ds, it.version_id, it.status || '', (it.metrics && it.metrics.mAP50 != null) ? it.metrics.mAP50 : '', it.created_at || '', it.model_path || '']);
        });
      });
      var csv = '\ufeff' + rows.map(function (r) {
        return r.map(function (c) { return '"' + String(c).replace(/"/g, '""') + '"'; }).join(',');
      }).join('\n');
      if (!needLauncher('导出清单')) return;
      launcherApi().save_text(csv, 'registry_manifest.csv').then(function (p) {
        if (p) toast('ok', '清单已导出', p);
      }).catch(function (e) { toast('err', '导出失败', String(e.message || e)); });
    });
  }
  function actCopyReport() {
    get('/api/launcher/env-report').then(function (env) {
      var lines = [
        'AYT 环境报告 · ' + new Date().toLocaleString(),
        'Python ' + env.python + ' · ' + env.platform,
        'torch ' + (env.torch || '-') + ' · ultralytics ' + (env.ultralytics || '-'),
        'GPU ' + (env.gpu && env.gpu.name ? (env.gpu.name + ' · ' + (env.gpu.memory || '') + ' · 驱动 ' + (env.gpu.driver || '')) : '未检测'),
        '磁盘 ' + Object.keys(env.disks || {}).map(function (k) { return k + ' 可用 ' + env.disks[k].free_gb + 'GB'; }).join(' · '),
        '工作目录 ' + env.base_dir,
      ].join('\n');
      copyText(lines, '报告已复制到剪贴板');
    }).catch(function (e) { toast('err', '获取报告失败', String(e.message || e)); });
  }
  function actRecheck() {
    refreshAll();
    toast('ok', '已重新检测', '环境报告已刷新（/api/launcher/env-report）');
  }
  function actDiagPack() {
    post('/api/launcher/diag-pack', {}).then(function (r) {
      toast('ok', '诊断包已生成', r.file + '（' + Math.round((r.bytes || 0) / 1024) + ' KB）');
    }).catch(function (e) { toast('err', '诊断包失败', String(e.message || e)); });
  }
  function pickPath(btn, key, label) {
    if (!needLauncher('选择 ' + label + ' 路径')) return;
    launcherApi().pick_file(false).then(function (p) {
      if (!p) return;
      try { localStorage.setItem(key, p); } catch (e) { /* 隐私模式忽略 */ }
      var row = btn.closest('.row');
      var span = row ? row.querySelector('.rtxt span') : null;
      if (span) span.textContent = p;
      toast('ok', '已保存 ' + label + ' 路径', p);
    });
  }
  function actPickPython(btn) { pickPath(btn, 'ayt.python', 'Python'); }
  function actPickGit(btn) { pickPath(btn, 'ayt.git', 'Git'); }
  function actCheckUpdate() { actRefresh(); }

  var ACTIONS = [
    ['打开样本预览', actPreview],
    ['重新校验', actValidate],
    ['生成 data.yaml', actConvert],
    ['选择待转换的数据集目录', actPickConvertDir],
    ['选择 ZIP 上传', actUpload],
    ['晋升为生产版本', actPromote],
    ['删除版本', actDeleteVersion],
    ['打标签', actTag],
    ['下载 best.pt', actDownloadBest],
    ['断点续训已预填', actResumePrefill],
    ['复制路径', actCopyRunPath],
    ['定位 exports', actOpenExports],
    ['恢复该 run', actRestoreRecycle],
    ['永久删除', actPurgeRecycle],
    ['已打开 runs/detect', actOpenRuns],
    ['已打开日志目录', actOpenLogs],
    ['已重新扫描 dataset', actRefresh],
    ['队列已刷新', actRefresh],
    ['已刷新', actRefresh],
    ['已是最新版本', actCheckUpdate],
    ['清单已导出', actExportManifest],
    ['报告已复制', actCopyReport],
    ['重新检测', actRecheck],
    ['诊断包已生成', actDiagPack],
    ['选择 Python 路径', actPickPython],
    ['选择 Git 路径', actPickGit],
    ['回收站为空', actRecycleInfo],
  ];

  function wireActions() {
    document.addEventListener(
      'click',
      function (e) {
        if (!LIVE.on) return;
        var el2 = e.target && e.target.closest ? e.target.closest('[data-toast]') : null;
        if (!el2) return;
        var text = el2.dataset.toast || '';
        for (var i = 0; i < ACTIONS.length; i++) {
          if (text.indexOf(ACTIONS[i][0]) >= 0) {
            e.stopPropagation();
            e.preventDefault();
            try { ACTIONS[i][1](el2, e); } catch (err) { console.warn('[live] action error', err); }
            return;
          }
        }
      },
      true
    );
  }

  function bindInferenceBtn() {
    var btn = el('svcInferBtn');
    if (!btn) return;
    btn.onclick = function () {
      if (!LIVE.on) return;
      var running = LIVE.inference && LIVE.inference.running;
      if (running) {
        post('/api/inference/stop', {})
          .then(function () {
            toast('warn', '推理服务已停止', '端口已释放');
            if (state.scene === 'running') setScene('idle');
            refreshAll();
          })
          .catch(function (e) { toast('err', '停止失败', String(e.message || e)); });
      } else {
        toast('ok', '正在启动推理服务…', '加载模型中，请稍候（约 5-15 秒）');
        post('/api/inference/start', {})
          .then(function (r) {
            toast('ok', '推理服务已启动', '127.0.0.1:' + (r.port || '') + ' · ' + String(r.model || '').split(/[\\/]/).slice(-3).join('/'));
            setScene('running');
            refreshAll();
          })
          .catch(function (e) { toast('err', '启动失败', String(e.message || e)); });
      }
    };
  }

  function applyInference() {
    var st = LIVE.inference || {};
    var chip = el('svcInferChip'), meta = el('svcInferMeta'), btn = el('svcInferBtn');
    var running = !!st.running;
    if (chip) {
      chip.innerHTML = '<span class="led"></span>' + (running ? '运行中' : '已停止');
      chip.className = 'chip' + (running ? ' ok' : '');
    }
    if (meta) {
      meta.textContent = running
        ? ('运行中 · 127.0.0.1:' + st.port + ' · ' + String(st.model || '').split(/[\\/]/).slice(-3).join('/'))
        : '未运行 · 端口 8000 · ayt-serve';
    }
    if (btn) btn.textContent = running ? '停止' : '启动';
  }

  function applyRecycle() {
    var items = LIVE.recycle || [];
    var rows = document.querySelectorAll('#page-results .row');
    var target = null;
    rows.forEach(function (r) { if (!target && r.textContent.indexOf('回收站') >= 0) target = r; });
    if (!target) return;
    var host = target.parentNode;
    host.querySelectorAll('.row[data-live-recycle]').forEach(function (n) { if (n !== target) n.remove(); });
    target.dataset.liveRecycle = '1';
    if (!items.length) {
      delete target.dataset.recycle;
      var s0 = target.querySelector('.rtxt span');
      if (s0) s0.textContent = '空 · 删除的数据集会进这里，可恢复';
      return;
    }
    items.forEach(function (it, idx) {
      var row = idx === 0 ? target : target.cloneNode(true);
      row.dataset.liveRecycle = '1';
      row.dataset.recycle = it.recycled_name || '';
      var s = row.querySelector('.rtxt span');
      if (s) {
        s.textContent = (it.original_name || it.recycled_name) + ' · ' + (it.size_mb != null ? it.size_mb + ' MB · ' : '') + (it.recycled_at || '');
      }
      if (idx > 0) host.appendChild(row);
    });
  }

  /* ======================== 覆写渲染（live 下不生成演示数据） ======================== */
  function overlayRender() {
    window.renderLog = function (scene) {
      if (!LIVE.on) return;
      liveRepaintLog();
      livePaintMetrics(LIVE.status || {});
    };
    window.paintScene = function () { if (LIVE.on) applyStatus(); };
  }

  function bindGo(root) {
    (root || document).querySelectorAll('[data-go]').forEach(function (b) {
      b.onclick = function () { if (window.go) go(b.dataset.go); };
    });
  }
})();
