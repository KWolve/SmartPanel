#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest_clear.py — 「清空设备上的视频素材」在真机上的验收（不碰真实素材）

做法（2026-09-28）：
  · 真机（默认 192.0.2.108:5555，可用 --dev 换）上建一个**临时目录**当"素材目录"，
    往里面塞几个文件（含子目录），然后 **monkeypatch distribute.CLEAR_TARGETS**
    只指向这个临时目录 → 跑 clear_device(dry=False) → 断言文件真的没了、目录还在。
  · 同时 monkeypatch `setprop ctl.stop/start zkswe` 与 set_prefs 为**记录器**，
    避免打断正在演示的面板（真机停/启应用那两行与 push 走的是同一份代码，已被 push 用例覆盖）。
  · 另跑一遍 dry_run=True，断言"只看不删"（文件数不变）。

覆盖点：ls -lR 解析（设备 busybox 无 find/du/wc）、rm -rf 删除、目录保留、dry-run 不删、
        停止/复位/重启应用的调用顺序。
用法： python selftest_clear.py [--dev 192.0.2.108:5555] [--keep]
"""
import argparse
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import distribute as dz  # noqa: E402

SCRATCH = '/mnt/sdnand/__clr_selftest'
fails = []


def check(name, cond, detail=''):
    print('  %s %-52s %s' % ('[OK]  ' if cond else '[FAIL]', name, detail))
    if not cond:
        fails.append(name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dev', default='192.0.2.108:5555')
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    dev = a.dev
    ok, out = dz.adb('connect', dev, timeout=10)
    print('=== 设备 %s（connect=%s）' % (dev, out.strip().splitlines()[-1] if out.strip() else ok))
    if not dz.sh(dev, 'busybox ls /mnt/sdnand/').strip():
        print('[FAIL] 设备没连上或读不到 /mnt/sdnand')
        return 2

    # 1) 造临时"素材目录"
    dz.sh(dev, 'busybox rm -rf %s' % SCRATCH)
    dz.sh(dev, 'busybox mkdir -p %s/c1 %s/c2' % (SCRATCH, SCRATCH))
    for f in ('playlist.json', 'wall.json', 'c1/seg_1.mp4', 'c1/seg_2.mp4', 'c2/seg_1.mp4'):
        dz.sh(dev, 'busybox touch %s/%s' % (SCRATCH, f))
    before = dz.ls_files(dev, SCRATCH)
    print('=== 造好临时素材：%d 个文件' % len(before))
    check('ls -lR 解析出全部 5 个文件（含子目录）', len(before) == 5,
          ', '.join(os.path.basename(p) for p, _s in before))

    # 2) dry-run：只看不删
    real_targets, real_prefs, real_sh = dz.CLEAR_TARGETS, dz.set_prefs, dz.sh
    # 用 scope='wall' 的真实语义（复位 sp_wall_en / sp_video_sel），只把“要删的目录”换成临时目录
    dz.CLEAR_TARGETS = dict(real_targets, wall=[(SCRATCH, '测试素材')])
    calls = []

    def fake_prefs(d, kv):
        calls.append(('prefs', d, dict(kv)))
        return True

    def fake_sh(d, cmd, timeout=15):
        if 'setprop ctl.stop zkswe' in cmd or 'setprop ctl.start zkswe' in cmd:
            calls.append(('sh', d, cmd.strip()))
            return ''
        return real_sh(d, cmd, timeout)

    dz.set_prefs = fake_prefs
    dz.sh = fake_sh
    try:
        rep = dz.clear_device(dev, 'wall', dry=True, quiet=True)
        check('dry-run 报告 5 个文件', rep['before']['files'] == 5, json.dumps(rep['before'], ensure_ascii=False))
        check('dry-run 没删文件（still 5）', len(dz.ls_files(dev, SCRATCH)) == 5)
        check('dry-run 没动应用（无 stop/start 调用）',
              not any(c[2].startswith('setprop') for c in calls), str(calls))

        # 3) 真删（只针对临时目录；停/启应用被记录器拦下，不打断面板）
        rep2 = dz.clear_device(dev, 'wall', dry=False, quiet=True)
        left = dz.ls_files(dev, SCRATCH)
        check('真删后 0 个文件（目录保留）',
              len(left) == 0 and dz.sh(dev, 'busybox ls -d %s' % SCRATCH).strip().endswith('__clr_selftest'),
              'left=%d' % len(left))
        check('报告：before 5 → after 0',
              rep2['before']['files'] == 5 and rep2['after']['files'] == 0,
              'before=%s after=%s' % (rep2['before']['files'], rep2['after']['files']))
        seq = [c[2] for c in calls if c[0] == 'sh']
        check('流程顺序 = 先停应用 → 再启应用',
              seq[:1] and 'stop' in seq[0] and any('start' in s for s in seq[1:]),
              ' / '.join(seq))
        keys = [k for c in calls if c[0] == 'prefs' for k in c[2]]
        check('复位拼接配置（sp_wall_en / sp_video_sel）',
              'sp_wall_en' in keys and 'sp_video_sel' in keys, ','.join(keys))
    finally:
        dz.CLEAR_TARGETS, dz.set_prefs, dz.sh = real_targets, real_prefs, real_sh

    # 4) 真机真实素材的 dry-run（只看统计，不删）
    rep3 = dz.clear_device(dev, 'wall', dry=True, quiet=True)
    check('真机 /mnt/sdnand/wall 统计可读（dry-run 不删）',
          rep3['before']['files'] >= 0 and len(rep3['before']['dirs']) == 1,
          json.dumps(rep3['before'], ensure_ascii=False))
    if not a.keep:
        dz.sh(dev, 'busybox rm -rf %s' % SCRATCH)
        print('=== 临时目录已清理：%s' % SCRATCH)

    print('\n=== 总判定: %s ===' % ('[PASS] 全部通过' if not fails else '[FAIL] %s' % fails))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
