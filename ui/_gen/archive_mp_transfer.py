# -*- coding: utf-8 -*-
"""把「小程序传图/视频对接指南」原始资料归档进 MCP open 版仓库（components/mp_transfer/）。

- 源码 6 个文件 + Python 参考接收端原样保留（仅做隐私占位符替换）
- 指南 md 做隐私占位符替换后归档到 docs/
"""
import os
import re
import shutil

PRJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(PRJ, '参考资料', '_xiaochengxu_guide', '小程序传输对接指南')
REPO = r'C:\Users\zkswe\.openclaw\workspace\tools\FlyThings_mcp_open'
DST = os.path.join(REPO, 'components', 'mp_transfer')

SUBS = [
    (re.compile(r'192\.168\.1\.255'), '<子网广播地址>'),
    (re.compile(r'192\.168\.1\.\d+'), '<本机IP>'),
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/24'), '<本机IP>/24'),
]


def sanitize(text):
    for pat, rep in SUBS:
        text = pat.sub(rep, text)
    return text


def copy(src, dst, sanitize_text=False):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if sanitize_text:
        t = open(src, encoding='utf-8').read()
        open(dst, 'w', encoding='utf-8', newline='\n').write(sanitize(t))
    else:
        shutil.copy2(src, dst)
    print('%8d  %s' % (os.path.getsize(dst), os.path.relpath(dst, REPO).replace('\\', '/')))


def main():
    files = [
        ('src/mp_transfer/broadcast_task.h', 'src/mp_transfer/broadcast_task.h', False),
        ('src/mp_transfer/broadcast_task.cpp', 'src/mp_transfer/broadcast_task.cpp', False),
        ('src/mp_transfer/tcp_receive.h', 'src/mp_transfer/tcp_receive.h', False),
        ('src/mp_transfer/tcp_receive.cpp', 'src/mp_transfer/tcp_receive.cpp', False),
        ('src/mp_transfer/runtime_coordinator.h', 'src/mp_transfer/runtime_coordinator.h', False),
        ('src/system/transfer_type_and_data.h', 'src/system/transfer_type_and_data.h', False),
        ('src/python/receiver.py', 'src/python/receiver.py', True),
        ('其他项目接入小程序传图视频移植指南.md', 'docs/miniprogram-transfer-guide.md', True),
    ]
    for s, d, san in files:
        copy(os.path.join(SRC, s), os.path.join(DST, d), san)


if __name__ == '__main__':
    main()
