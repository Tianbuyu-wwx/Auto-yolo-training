# -*- coding: utf-8 -*-
"""字体本地化：下载 fontsource CSS + 全部 woff2 切片到 fonts/，供离线使用"""
import os, re, sys, time, urllib.request
import concurrent.futures as cf

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'fonts')
FILES = os.path.join(OUT, 'files')
os.makedirs(FILES, exist_ok=True)

SOURCES = [
    ('instrument-serif-400.css', 'https://cdn.jsdelivr.net/npm/@fontsource/instrument-serif@5/400.css'),
    ('instrument-sans-var.css', 'https://cdn.jsdelivr.net/npm/@fontsource-variable/instrument-sans@5/index.css'),
    ('ibm-plex-mono-400.css', 'https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-mono@5/400.css'),
    ('ibm-plex-mono-500.css', 'https://cdn.jsdelivr.net/npm/@fontsource/ibm-plex-mono@5/500.css'),
    ('noto-serif-sc-400.css', 'https://cdn.jsdelivr.net/npm/@fontsource/noto-serif-sc@5/400.css'),
    ('noto-sans-sc-400.css', 'https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-sc@5/400.css'),
    ('noto-sans-sc-500.css', 'https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-sc@5/500.css'),
]
CDN_FILES = 'https://cdn.jsdelivr.net/npm/@fontsource/@@CASE@@/files/'

def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.2 * (i + 1))

# 1) 抓 CSS，收集切片引用
tasks = []  # (filename, url)
for name, url in SOURCES:
    css = fetch(url).decode('utf-8')
    refs = sorted(set(re.findall(r'url\(\./files/([^)]+?\.woff2)\)', css)))
    css2 = re.sub(r",\s*url\(\./files/[^)]+\.woff\)\s*format\('woff'\)", '', css)
    pkg = url.split('/npm/')[1].rsplit('/', 1)[0]  # e.g. @fontsource/instrument-serif@5
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(css2)
    for r in refs:
        tasks.append((r, 'https://cdn.jsdelivr.net/npm/' + pkg + '/files/' + r))
    print('%-28s refs=%d' % (name, len(refs)))

# 2) 并发下载切片（跳过已存在）
def dl(item):
    fn, url = item
    dst = os.path.join(FILES, fn)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return ('skip', fn)
    data = fetch(url)
    with open(dst, 'wb') as f:
        f.write(data)
    return ('ok', fn)

done = okc = skipc = 0
fails = []
with cf.ThreadPoolExecutor(max_workers=12) as ex:
    for res in ex.map(dl, tasks):
        done += 1
        if res[0] == 'ok': okc += 1
        elif res[0] == 'skip': skipc += 1

# 3) 校验完整性
missing = [fn for fn, _ in tasks if not (os.path.exists(os.path.join(FILES, fn)) and os.path.getsize(os.path.join(FILES, fn)) > 0)]
sizes = sum(os.path.getsize(os.path.join(FILES, fn)) for fn, _ in tasks if os.path.exists(os.path.join(FILES, fn)))
print('\ntasks=%d downloaded=%d skipped=%d missing=%d total=%.1f MB' % (len(tasks), okc, skipc, len(missing), sizes / 1e6))
if missing:
    print('MISSING:', missing[:20])
    sys.exit(1)
print('FONT BUNDLE OK')
