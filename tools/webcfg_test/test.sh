#!/bin/bash
# WebConfigServer x86 冒烟：起服务 -> 读配置页 -> POST 保存 -> 读回 status / 页面回填
set -u
pkill -f /tmp/webcfg >/dev/null 2>&1
nohup /tmp/webcfg > /tmp/webcfg.log 2>&1 &
sleep 1
BASE=http://127.0.0.1:18080/AB12CD

echo "=== 1) 长令牌粘贴（带换行与空格）POST 保存 ==="
curl -s -o /tmp/saved.html -w 'HTTP %{http_code}\n' -X POST "$BASE/save" \
  --data-urlencode 'server=192.0.2.50' \
  --data-urlencode 'user=homeassistant' \
  --data-urlencode 'pass=eyJhbGciOiJIUzI1NiJ9
  .eyJpYXQiOjE3  MSAifQ' \
  --data-urlencode 'enabled=1'
grep -o '配置已写入[^<]*' /tmp/saved.html | head -2

echo "=== 2) 地址归一化 + status JSON ==="
curl -s "$BASE/status"; echo

echo "=== 3) 重新打开配置页：应回填服务器/用户名/令牌 ==="
curl -s "$BASE/" > /tmp/page2.html
python3 - <<'PY'
import re, io
h = io.open('/tmp/page2.html', encoding='utf-8').read()
for k in ('server', 'user'):
    m = re.search(r'name="%s" value="([^"]*)"' % k, h)
    print('  %-7s = %r' % (k, m.group(1) if m else None))
m = re.search(r'name="pass"[^>]*>([^<]*)</textarea>', h)
print('  %-7s = %r' % ('pass', m.group(1) if m else None))
print('  勾选启用 =', 'checked' in re.search(r'id="en"[^>]*', h).group(0))
PY

echo "=== 4) 口令码错误 -> 应 404 ==="
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:18080/WRONG1/status

echo "=== 5) 停机 ==="
tail -3 /tmp/webcfg.log
pkill -f /tmp/webcfg >/dev/null 2>&1
echo done
