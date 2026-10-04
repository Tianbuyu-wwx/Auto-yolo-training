# -*- coding: utf-8 -*-
"""第三轮修正：hashchange 监听 / 最近训练表格重构 / 轨道指示灯 / 输入框质感 / 刻度条辉光"""
import io, sys

p = "AYT-Launcher-v1.html"
s = io.open(p, encoding="utf-8", newline="").read()
log = []

def rep(old, new, expect=None, tag=""):
    global s
    n = s.count(old)
    if expect is not None and n != expect:
        print("ABORT [%s] count=%d expected=%d :: %r" % (tag, n, expect, old[:90]))
        sys.exit(1)
    s = s.replace(old, new)
    log.append((n, tag or old[:60]))

# 1) hashchange 监听（地址栏改 hash / 前进后退都能响应）
rep("""$$('[data-goto]').forEach(el => el.addEventListener('click', e => { e.preventDefault(); nav(el.dataset.goto); }));""",
    """$$('[data-goto]').forEach(el => el.addEventListener('click', e => { e.preventDefault(); nav(el.dataset.goto); }));
addEventListener('hashchange', () => { const h = (location.hash || '').slice(1); if (SCREENS.includes(h)) nav(h); });""",
    1, "hashchange")

# 2) 轨道指示灯：待办=空心环，完成=实心，进行=铜金发光
rep(".st .lamp{ width:9px; height:9px; border-radius:0; background:rgba(255,244,225,.14); transition:background var(--t) var(--e-io); }",
    ".st .lamp{ width:10px; height:10px; border-radius:0; background:transparent; box-shadow:inset 0 0 0 1px rgba(255,244,225,.26); transition:background var(--t) var(--e-io), box-shadow var(--t) var(--e-io); }",
    1, "lamp-base")
rep(".st.done .lamp{ background:var(--ink2); }",
    ".st.done .lamp{ background:var(--ink2); box-shadow:none; }", 1, "lamp-done")
rep("content:''; position:absolute; top:4px; right:calc(50% + 12px); width:calc(100% - 24px);",
    "content:''; position:absolute; top:5px; right:calc(50% + 13px); width:calc(100% - 26px);",
    1, "lamp-line")

# 3) 输入框：微凹陷质感（与卡片精致度统一）
rep("  background:var(--bg-deep); color:var(--ink);\n  border:1px solid var(--line2); border-radius:var(--r);",
    "  background:#14110e; color:var(--ink);\n  box-shadow:inset 0 1px 2px rgba(0,0,0,.35);\n  border:1px solid var(--line2); border-radius:var(--r);",
    1, "inp-bg")
rep(".inp:focus{ border-color:var(--brass); box-shadow:0 0 0 3px rgba(201,163,92,.14); }",
    ".inp:focus{ border-color:var(--brass); box-shadow:inset 0 1px 2px rgba(0,0,0,.35), 0 0 0 3px rgba(201,163,92,.14); }",
    1, "inp-focus")

# 4) 显存刻度：去掉每格辉光（阴影总量控制）
rep(".meter i.on{ background:var(--brass); box-shadow:0 0 6px -1px rgba(201,163,92,.6); }",
    ".meter i.on{ background:var(--brass); }", 1, "meter-glow")

# 5) 表格补充：双行大行高 + 次级行
rep(".tbl tr:last-child td{ border-bottom:0; }",
    """.tbl tr:last-child td{ border-bottom:0; }
.tbl.tall td{ height:auto; padding:10px 12px; line-height:1.35; }
.tbl .sub2{ display:block; font-family:var(--f-mono); font-size:12px; color:var(--ink3); margin-top:2px; }""",
    1, "tbl-tall")

# 6) 最近训练表格：重构为 5 列（运行含模型 / 数据集 / 轮数 / mAP / 状态）
old_tbl = """              <table class="tbl" id="recentTbl">
                <colgroup><col style="width:25%"><col style="width:19%"><col style="width:15%"><col style="width:9%"><col style="width:12%"><col style="width:20%"></colgroup>
                <thead><tr>
                  <th>运行</th><th>数据集</th><th>模型</th><th class="num">轮数</th><th class="num">mAP@50</th><th>状态</th>
                </tr></thead>
                <tbody>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">data_auto</span></td>
                    <td>data</td><td class="mono" style="font-size:12px">yolo26n.pt</td>
                    <td class="num">50</td><td class="num">—</td>
                    <td><span class="row" style="gap:8px"><span class="mini"><i class="d"></i><i class="d"></i><i></i><i class="f"></i><i></i><i></i></span><span class="chip warn" style="height:20px"><span class="led warn"></span>中断</span></span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_auto-2</span></td>
                    <td>_smoke_test</td><td class="mono" style="font-size:12px">yolov8n.pt</td>
                    <td class="num">2</td><td class="num">0.0082</td>
                    <td><span class="row" style="gap:8px"><span class="mini"><i class="d"></i><i class="d"></i><i></i><i class="d"></i><i class="d"></i><i></i></span><span class="chip ok" style="height:20px"><span class="led ok"></span>完成</span></span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_auto-3</span></td>
                    <td>_smoke_test</td><td class="mono" style="font-size:12px">yolov8n.pt</td>
                    <td class="num">1</td><td class="num">0.0000</td>
                    <td><span class="row" style="gap:8px"><span class="mini"><i class="d"></i><i class="d"></i><i></i><i class="d"></i><i class="d"></i><i></i></span><span class="chip ok" style="height:20px"><span class="led ok"></span>完成</span></span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_eval</span></td>
                    <td>_smoke_test</td><td class="mono" style="font-size:12px">—</td>
                    <td class="num">—</td><td class="num">—</td>
                    <td><span class="row" style="gap:8px"><span class="mini"><i></i><i></i><i></i><i></i><i class="d"></i><i></i></span><span class="chip plain" style="height:20px">仅评估</span></span></td>
                  </tr>
                </tbody>
              </table>"""
new_tbl = """              <table class="tbl tall" id="recentTbl">
                <colgroup><col style="width:34%"><col style="width:22%"><col style="width:10%"><col style="width:12%"><col style="width:22%"></colgroup>
                <thead><tr>
                  <th>运行</th><th>数据集</th><th class="num">轮数</th><th class="num">mAP@50</th><th>状态</th>
                </tr></thead>
                <tbody>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">data_auto</span><span class="sub2">yolo26n.pt</span></td>
                    <td>data</td>
                    <td class="num">50</td><td class="num">—</td>
                    <td><span class="chip warn" style="height:20px"><span class="led warn"></span>中断于训练</span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_auto-2</span><span class="sub2">yolov8n.pt</span></td>
                    <td>_smoke_test</td>
                    <td class="num">2</td><td class="num">0.0082</td>
                    <td><span class="chip ok" style="height:20px"><span class="led ok"></span>完成</span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_auto-3</span><span class="sub2">yolov8n.pt</span></td>
                    <td>_smoke_test</td>
                    <td class="num">1</td><td class="num">0.0000</td>
                    <td><span class="chip ok" style="height:20px"><span class="led ok"></span>完成</span></td>
                  </tr>
                  <tr data-row>
                    <td><span class="nm mono" style="font-size:12px">_smoke_test_eval</span><span class="sub2">评估产物 · predictions.json</span></td>
                    <td>_smoke_test</td>
                    <td class="num">—</td><td class="num">—</td>
                    <td><span class="chip plain" style="height:20px">仅评估</span></td>
                  </tr>
                </tbody>
              </table>"""
rep(old_tbl, new_tbl, 1, "recent-table")

io.open(p, "w", encoding="utf-8", newline="").write(s)
for n, t in log:
    print("%3d  %s" % (n, t))
print("OK fix3 applied")
