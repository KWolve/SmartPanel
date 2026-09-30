#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多屏拼接：设备发现 + 配置/素材分发 + 轮播状态核对（PC 端，供网页版复用）

四条子命令：
  scan   发现可用面板：UDP 8899 广播(面板自带) + 5555 端口探测 + 识别是否我们的面板程序
  clear  清空设备上的视频素材（拼接 wall / 屏保 video / 相册 album / 全部），可 --dry-run 只看不删
  push   把某组的分段与配置下发到指定设备（含"本机序号"->seg_<idx>、写入 /data 配置）
         · **整组模式（新）**：--group-dir <组目录> → 递归推送组目录下**所有文件**
           （playlist.json / wall.json / c1/seg_1.mp4 …，保持相对路径）
           + sp_wall_seg_ms = playlist 里**第一片**时长
           + sp_video_sel 指向本机那一片（<组>/<第一个 clip>/seg_<idx>.mp4）
         · 旧模式（保留）：--seg-dir <目录> → 只推根目录的 seg_<idx>.mp4 + wall.json
  status 读回各设备状态：当前配置 + 屏保是否在播本机段（日志） + 继电器状态

配置键（与面板侧 wallLogic.cc 一致）：
  sp_wall_en / sp_wall_group / sp_wall_idx / sp_wall_n / sp_wall_role / sp_wall_seg_ms
用法：
  python distribute.py scan
  # 清空设备视频素材（默认 dry-run 只看统计；真删要显式 --yes）
  python distribute.py clear --devices 192.0.2.108,192.0.2.71 --scope all --dry-run
  python distribute.py clear --devices 192.0.2.108 --scope wall --yes
  # 整组推送（新；多视频轮播组）
  python distribute.py push --group-dir out/g2_113221 --group zksw-wall --devices 192.0.2.108=1,192.0.2.71=2
  python distribute.py push --group-dir out/g2_113221 --group zksw-wall --devices 192.0.2.108=1 --dry-run
  # 旧单视频推送（兼容）
  python distribute.py push --seg-dir out/wall2 --group zksw-wall --devices 192.0.2.108=1,192.0.2.71=2
  python distribute.py status --devices 192.0.2.108,192.0.2.71
"""
import argparse
import concurrent.futures as cf
import io
import json
import os
import posixpath
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ADB = os.environ.get('ADB', r'C:\Users\zkswe\.openclaw\workspace\sim\tools\platform-tools\adb.exe')
TOUCH_SRC = os.environ.get(
    'TOUCH_BIN',
    r'C:\Users\zkswe\.openclaw\workspace\tools\FlyThings_mcp_open\bin_tools\z20\touch')
WALL_ROOT = '/mnt/sdnand/wall'

# ── 清空设备视频素材（2026-09-28）：可清的范围 ─────────────────────────────
CLEAR_TARGETS = {
    'wall': [('/mnt/sdnand/wall', '拼接素材')],
    'video': [('/mnt/sdnand/video', '屏保视频')],
    'album': [('/mnt/sdnand/album', '相册')],
    'all': [('/mnt/sdnand/wall', '拼接素材'), ('/mnt/sdnand/video', '屏保视频'),
            ('/mnt/sdnand/album', '相册')],
}

KEYS = ['sp_wall_en', 'sp_wall_group', 'sp_wall_idx', 'sp_wall_n', 'sp_wall_role',
        'sp_wall_seg_ms']


def sh(dev, cmd, timeout=15):
    try:
        p = subprocess.run([ADB, '-s', dev, 'shell', cmd], capture_output=True, timeout=timeout)
        return p.stdout.decode('utf-8', 'replace')
    except Exception as e:
        return ''


def adb(*args, timeout=60):
    try:
        p = subprocess.run([ADB] + list(args), capture_output=True, timeout=timeout)
        return p.returncode == 0, p.stdout.decode('utf-8', 'replace') + p.stderr.decode('utf-8', 'replace')
    except Exception as e:
        return False, str(e)


# ── 设备发现 ────────────────────────────────────────────────────────
def udp_panels(seconds=6):
    """面板自带 UDP 8899 广播（每 2s 一次，内容 zkswe:<name>）"""
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(('', 8899))
    except OSError:
        return found
    s.settimeout(0.6)
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            data, addr = s.recvfrom(2048)
            found[addr[0]] = data.decode('utf-8', 'replace').strip()
        except socket.timeout:
            pass
    s.close()
    return found


def probe_5555(ip, timeout=0.35):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, 5555)) == 0
    finally:
        s.close()


def scan(a):
    subnet = a.subnet if a is not None else '192.168.1.'
    print('① 监听面板 UDP 广播（8899）…')
    bcast = udp_panels(6)
    print('   广播命中: %s' % (bcast if bcast else '（无）'))

    print('② 扫描 %s0/24 的 adb(5555) 端口 …' % subnet)
    ips = [subnet + str(i) for i in range(1, 255)]
    hits = []
    with cf.ThreadPoolExecutor(max_workers=64) as ex:
        for ip, ok in zip(ips, ex.map(probe_5555, ips)):
            if ok:
                hits.append(ip)
    print('   开放 adb 的主机: %s' % ', '.join(hits))

    print('③ 识别型号与面板程序 …')
    rows = []
    for ip in hits:
        dev = '%s:5555' % ip
        adb('connect', dev, timeout=10)
        model = sh(dev, 'getprop ro.product.model').strip()
        so = sh(dev, 'busybox ls -l /res/lib/libzkgui.so').strip()
        has_wall = 'wall.ftu' in sh(dev, 'busybox ls /res/ui')
        did = ''
        m = re.search('"sp_device_id"\\s*:\\s*"([^"]+)"',
                      sh(dev, 'cat /data/preferences.json'))
        if m:
            did = m.group(1)
        rows.append((ip, model, did, has_wall, so.split()[-2] if so else '-'))
    print()
    print('%-16s %-24s %-18s %-9s %s' % ('IP', 'model', 'panel id', '含拼接页', 'libzkgui.so'))
    for r in rows:
        print('%-16s %-24s %-18s %-9s %s' % (r[0], r[1][:24], r[2], 'Y' if r[3] else '-', r[4]))
    print()
    print('提示：推送时用  --devices ip=序号 指定每台播哪一段')
    return rows


# ── 下发配置 + 素材 ─────────────────────────────────────────────────
def set_prefs(dev, kv):
    """外科式改 /data/preferences.json：只替换指定键的值，不动其它字节"""
    sh(dev, 'setprop ctl.stop zkswe')
    time.sleep(2.5)
    raw = sh(dev, 'cat /data/preferences.json')
    if not raw.strip().startswith('{'):
        print('   ! 读不到 prefs，跳过')
        sh(dev, 'setprop ctl.start zkswe')
        return False
    for k, v in kv.items():
        if isinstance(v, str):
            val = '"%s"' % v
        elif isinstance(v, bool):
            val = 'true' if v else 'false'
        else:
            val = str(v)
        pat = '("%s"\\s*:\\s*)("(?:[^"\\\\]|\\\\.)*"|[^,}\\s]+)' % k
        if re.search(pat, raw):
            raw = re.sub(pat, lambda m: m.group(1) + val, raw, count=1)
        else:
            raw = raw.rstrip()
            if raw.endswith('}'):
                body = raw[:-1].rstrip().rstrip(',')
                raw = body + ',\n   "%s" : %s\n}' % (k, val)
    p = os.path.join(HERE, 'out', '.prefs_tmp.json')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, 'w', encoding='utf-8').write(raw)
    ok, _ = adb('-s', dev, 'push', p, '/data/preferences.json')
    return ok


# ── 清空设备视频素材 ────────────────────────────────────────────────
def ls_files(dev, d):
    """列目录下所有文件 → [(绝对路径, 字节)]（设备 busybox 是裁剪版：没有 find/du/wc/stat，
    只能用 `ls -lR` 递归列，再在本机侧解析）"""
    out = sh(dev, 'busybox ls -lR %s 2>/dev/null' % d, timeout=60)
    cur, rows = '', []
    for line in out.splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.startswith('/') and line.endswith(':'):
            cur = line[:-1]
            continue
        p = line.split()
        if len(p) >= 5 and p[0].startswith('-'):
            try:
                size = int(p[4])
            except ValueError:
                continue
            rows.append((posixpath.join(cur, ' '.join(p[8:]) if len(p) > 8 else ''), size))
    return rows


def clear_scan(dev, scope='wall'):
    """清空前后的统计（文件数 + 字节数），按目录分组"""
    targets = CLEAR_TARGETS.get(scope) or CLEAR_TARGETS['wall']
    dirs = []
    for d, label in targets:
        rows = ls_files(dev, d)
        dirs.append({'dir': d, 'label': label, 'files': len(rows),
                     'bytes': sum(r[1] for r in rows)})
    return {'dirs': dirs, 'files': sum(x['files'] for x in dirs),
            'bytes': sum(x['bytes'] for x in dirs)}


def clear_device(dev, scope='wall', dry=True, quiet=False):
    """清空设备上的视频素材。

    scope: wall=拼接素材 / video=屏保视频 / album=相册 / all=三者
    dry=True **只统计不删除**（不碰设备内容，只读 ls）
    真删流程：停应用 → rm -rf <目录>/*（保留目录本身）→ 复位相关配置 → 重启应用
    返回 {dev, scope, dry, before:{...}, after:{...}, cleared:bool}
    """
    rep = {'dev': dev, 'scope': scope, 'dry': bool(dry), 'cleared': False}
    rep['before'] = clear_scan(dev, scope)
    if dry:
        if not quiet:
            print('=== %s  范围 %s  [dry-run 不删]  %d 个文件 / %.1f MB' % (
                dev, scope, rep['before']['files'], rep['before']['bytes'] / 1048576.0))
            for x in rep['before']['dirs']:
                print('   %-20s %-8s %4d 个文件  %.1f MB' % (
                    x['dir'], x['label'], x['files'], x['bytes'] / 1048576.0))
        return rep
    sh(dev, 'setprop ctl.stop zkswe')       # 先停应用，免得播放器占着文件
    time.sleep(2.5)
    for d, label in (CLEAR_TARGETS.get(scope) or CLEAR_TARGETS['wall']):
        sh(dev, 'busybox rm -rf %s/* %s/.[!.]* 2>/dev/null' % (d, d), timeout=120)
    # 复位相关配置：别让面板继续去找已经删掉的文件
    if scope in ('wall', 'all'):
        set_prefs(dev, {'sp_wall_en': False})
    set_prefs(dev, {'sp_video_sel': ''})
    sh(dev, 'setprop ctl.start zkswe')
    rep['after'] = clear_scan(dev, scope)
    rep['cleared'] = True
    if not quiet:
        freed = rep['before']['bytes'] - rep['after']['bytes']
        print('=== %s  范围 %s  已清空：删 %d 个文件 / 释放 %.1f MB（残留 %d 个）' % (
            dev, scope, rep['before']['files'] - rep['after']['files'],
            freed / 1048576.0, rep['after']['files']))
    return rep


def cmd_clear(a):
    ips = [s.strip() for s in str(a.devices).split(',') if s.strip()]
    dry = not bool(a.yes)
    print('清空设备视频：范围=%s  %s（%s）' % (
        a.scope, 'dry-run 只看不删' if dry else '**真删**', ', '.join(ips)))
    bad = 0
    for ip in ips:
        dev = '%s:5555' % ip
        adb('connect', dev, timeout=10)
        try:
            clear_device(dev, a.scope, dry=dry)
        except Exception as e:
            bad += 1
            print('   ! %s 失败：%s' % (ip, e))
    print('\n%s' % ('预览完成（没删任何东西；要真删加 --yes）' if dry else '清空完成') +
          ('' if not bad else '（%d 台失败）' % bad))


def push_one(dev, idx, n, group, seg_dir, master):
    print('=== %s  ->  seq %d/%d（%s）' % (dev, idx, n, '主机' if master else '从机'))
    sh(dev, 'mkdir -p %s/%s' % (WALL_ROOT, group))
    seg = os.path.join(seg_dir, 'seg_%d.mp4' % idx)
    ok, out = adb('-s', dev, 'push', seg, '%s/%s/seg_%d.mp4' % (WALL_ROOT, group, idx), timeout=900)
    print('   分段: %s' % ('OK' if ok else '失败'))
    wj = os.path.join(seg_dir, 'wall.json')
    if os.path.exists(wj):
        adb('-s', dev, 'push', wj, '%s/%s/wall.json' % (WALL_ROOT, group))
    # 传给面板的配置（wallLogic 读这些键）
    seg_ms = 0
    try:
        j = json.load(io.open(wj, encoding='utf-8'))
        seg_ms = int(round(j['segments'][0]['info']['duration'] * 1000))
    except Exception:
        pass
    ok2 = set_prefs(dev, {'sp_wall_en': True, 'sp_wall_group': group, 'sp_wall_idx': idx,
                          'sp_wall_n': n, 'sp_wall_role': 1 if master else 0,
                          'sp_wall_seg_ms': seg_ms})
    # 顺手把"屏保选中清单"指向本机段，保证当前版本就能看到画面（面板侧联动播放器接入后改走 wall 逻辑）
    set_prefs(dev, {'sp_video_sel': '%s/%s/seg_%d.mp4' % (WALL_ROOT, group, idx)})
    adb('-s', dev, 'push', TOUCH_SRC, '/tmp/touch')
    sh(dev, 'chmod 777 /tmp/touch')
    sh(dev, 'logcat -c')
    sh(dev, 'setprop ctl.start zkswe')
    print('   配置: %s（idx=%d n=%d role=%s seg=%dms）' %
          ('OK' if ok2 else '部分失败', idx, n, 'master' if master else 'slave', seg_ms))
    return True


def cmd_push(a):
    if not a.seg_dir and not a.group_dir:
        print('[错误] 需要 --group-dir（整组，推荐）或 --seg-dir（旧单视频）')
        raise SystemExit(2)
    if a.seg_dir and a.group_dir:
        print('[错误] --seg-dir 与 --group-dir 只能给一个')
        raise SystemExit(2)
    devs = seq_devices(a.devices)
    n = len(devs)
    if a.group_dir:
        group_dir = a.group_dir
        meta = group_meta(group_dir)
        group = a.group or meta['group'] or os.path.basename(os.path.normpath(group_dir)) or 'zksw-wall'
        print('共 %d 台，组名 %s（整组递归推送%s）' % (n, group, '；dry-run 不碰设备' if a.dry_run else ''))
        for i, (dev, idx) in enumerate(devs):
            if not a.dry_run:
                adb('connect', dev, timeout=10)
            push_group_one(dev, idx, n, group, group_dir, master=(i == 0), dry=a.dry_run,
                           only_mine=bool(getattr(a, 'only_mine', False)),
                           clear_wall=bool(getattr(a, 'clear_wall', False)))
        print('\n%s。用 status 子命令核对播放情况。' % ('演练完成（未推送）' if a.dry_run else '下发完成'))
        return
    print('共 %d 台，组名 %s%s' % (n, a.group or 'zksw-wall',
                                '（旧单视频模式 dry-run）' if a.dry_run else ''))
    for i, (dev, idx) in enumerate(devs):
        if a.dry_run:
            grp = a.group or 'zksw-wall'
            seg = os.path.join(a.seg_dir, 'seg_%d.mp4' % idx)
            print('   [dry-run] push %s → %s/%s/seg_%d.mp4' % (seg, WALL_ROOT, grp, idx))
            wj = os.path.join(a.seg_dir, 'wall.json')
            if os.path.exists(wj):
                print('   [dry-run] push wall.json → %s/%s/wall.json' % (WALL_ROOT, grp))
            seg_ms = 0
            try:
                seg_ms = int(round(json.load(io.open(wj, encoding='utf-8'))['segments'][0]
                                   ['info']['duration'] * 1000))
            except Exception:
                pass
            print('   [dry-run] prefs: %s' % json.dumps(
                {'sp_wall_en': True, 'sp_wall_group': grp, 'sp_wall_idx': idx, 'sp_wall_n': n,
                 'sp_wall_role': 1 if i == 0 else 0, 'sp_wall_seg_ms': seg_ms},
                ensure_ascii=False))
            print('   [dry-run] prefs: %s' % json.dumps(
                {'sp_video_sel': '%s/%s/seg_%d.mp4' % (WALL_ROOT, grp, idx)}, ensure_ascii=False))
            continue
        adb('connect', dev, timeout=10)
        push_one(dev, idx, n, a.group or 'zksw-wall', a.seg_dir, master=(i == 0))
    print('\n%s。用 status 子命令核对播放情况。' % ('演练完成（未推送）' if a.dry_run else '下发完成'))


def seq_devices(spec):
    """'ip=idx,ip=idx' → [(dev:5555, idx)]（不给 idx 的按顺序编号）"""
    devs = []
    for item in str(spec).split(','):
        item = item.strip()
        if not item:
            continue
        if '=' in item:
            ip, idx = item.split('=')
            devs.append(('%s:5555' % ip.strip(), int(idx)))
        else:
            devs.append(('%s:5555' % item, len(devs) + 1))
    return devs


# ── 整组（v2：多视频轮播）递归推送 ───────────────────────────────────
def group_files(group_dir):
    """递归列出组目录下所有文件 → [(本地绝对路径, 相对路径 posix)]（保持相对路径，排序确定）"""
    out = []
    for root, dirs, files in os.walk(group_dir):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, group_dir).replace('\\', '/')
            out.append((p, rel))
    return out


def group_meta(group_dir):
    """组清单摘要（优先 playlist.json v2；旧布局只有 wall.json 也支持）

    返回 {group, cols, n, total_ms, first_clip, first_dur_ms, legacy}
    """
    miss = {'group': None, 'cols': 0, 'n': 0, 'total_ms': 0, 'first_clip': '',
            'first_dur_ms': 0, 'legacy': True}
    pp = os.path.join(group_dir, 'playlist.json')
    if os.path.exists(pp):
        try:
            pl = json.load(io.open(pp, encoding='utf-8'))
            clips = pl.get('clips') or []
            first = clips[0] if clips else {}
            return {'group': pl.get('group'), 'cols': int(pl.get('cols') or 0),
                    'n': int(pl.get('n') or len(clips)),
                    'total_ms': int(pl.get('total_ms') or 0),
                    'first_clip': first.get('name') or '',
                    'first_dur_ms': int(first.get('dur_ms') or 0), 'legacy': False}
        except Exception as e:
            print('   ! 读 playlist.json 失败：%s' % e)
    wp = os.path.join(group_dir, 'wall.json')
    if os.path.exists(wp):
        try:
            wj = json.load(io.open(wp, encoding='utf-8'))
            segs = wj.get('segments') or []
            d = int(wj.get('seg_ms') or 0)
            if not d and segs:
                d = int(round(float((segs[0].get('info') or {}).get('duration', 0)) * 1000))
            m = dict(miss)
            m.update({'group': wj.get('group'), 'cols': len(segs), 'n': 1, 'total_ms': d,
                      'first_dur_ms': d})
            return m
        except Exception as e:
            print('   ! 读 wall.json 失败：%s' % e)
    return miss


def mine_only(rel, idx):
    """--only-mine 过滤：只要 playlist.json / wall.json / <clip>/seg_<idx>.mp4（旧布局根 seg_<idx>.mp4）"""
    r = rel.replace('\\', '/')
    if '/' not in r:
        return r in ('playlist.json', 'wall.json') or r == 'seg_%d.mp4' % idx
    return r.rsplit('/', 1)[-1] == 'seg_%d.mp4' % idx


def push_group_one(dev, idx, n, group, group_dir, master=False, dry=False, only_mine=False,
                   clear_wall=False):
    """**整组递归推送**：组目录下所有文件（含 playlist.json）→ /mnt/sdnand/wall/<group>/<相对路径>

    + 写 prefs：sp_wall_en/group/idx/n/role/seg_ms(=第一片时长)；sp_video_sel = 本机第一片。
    dry=True 时**完全不碰设备**（不 connect/不 push），只打印将执行的命令与将写的配置。
    """
    files = group_files(group_dir)
    meta = group_meta(group_dir)
    if only_mine:
        all_n = len(files)
        files = [(p, r) for (p, r) in files if mine_only(r, idx)]
        if len(files) < all_n:
            print('   （--only-mine：本机只推 %d/%d 个文件，其余段不占设备空间）' % (len(files), all_n))
    first_clip = meta['first_clip'] or ''
    seg_ms = int(meta['first_dur_ms'] or 0)
    rel0 = ('%s/seg_%d.mp4' % (first_clip, idx)) if first_clip else ('seg_%d.mp4' % idx)
    sel = '%s/%s/%s' % (WALL_ROOT, group, rel0)
    kv_wall = {'sp_wall_en': True, 'sp_wall_group': group, 'sp_wall_idx': idx,
               'sp_wall_n': n, 'sp_wall_role': 1 if master else 0,
               'sp_wall_seg_ms': seg_ms}
    kv_sel = {'sp_video_sel': sel}
    print('=== %s  ->  seq %d/%d（%s）  整组模式' % (dev, idx, n, '主机' if master else '从机'))
    print('   组目录: %s  文件 %d 个  组名 %s  clip 数 %s  每 clip %s 段  总时长 %dms%s'
          % (group_dir, len(files), group, meta['n'] or '?', meta['cols'] or '?',
             meta['total_ms'], '（旧布局/v1）' if meta['legacy'] else '（playlist.json v2）'))
    if dry:
        for p, rel in files:
            print('   [dry-run] push %s → %s/%s/%s' % (os.path.basename(p), WALL_ROOT, group, rel))
        print('   [dry-run] prefs: %s' % json.dumps(kv_wall, ensure_ascii=False))
        print('   [dry-run] prefs: %s' % json.dumps(kv_sel, ensure_ascii=False))
        print('   [dry-run] 未连接/未推送任何设备')
        return True
    if not files:
        print('   ! 组目录是空的，放弃')
        return False
    if clear_wall:                              # 先清掉设备上旧的拼接素材（换视频时不残留）
        rep = clear_device(dev, 'wall', dry=False, quiet=True)
        print('   先清空旧拼接素材：删 %d 个文件 / 释放 %.1f MB'
              % (rep['before']['files'] - rep['after']['files'],
                 (rep['before']['bytes'] - rep['after']['bytes']) / 1048576.0))
    dirs = sorted({posixpath.dirname('%s/%s/%s' % (WALL_ROOT, group, r)) for _p, r in files})
    for d in dirs:
        sh(dev, 'mkdir -p %s' % d)
    bad = []
    for p, rel in files:
        # v6.1：大段（~20MB）在 0.3MB/s 的 WiFi 上要 60~70s，默认 60s 超时会静默失败
        #   （2026-09-27 实测：wallA 两台各挂一个 c2/seg_*.mp4）-> 推送单独放宽到 900s
        ok, _o = adb('-s', dev, 'push', p, '%s/%s/%s' % (WALL_ROOT, group, rel), timeout=900)
        if not ok:
            bad.append(rel)
    print('   整组推送: %d/%d 个文件 OK%s'
          % (len(files) - len(bad), len(files), ('' if not bad else '  失败: ' + ', '.join(bad))))
    ok2 = set_prefs(dev, kv_wall)
    set_prefs(dev, kv_sel)
    adb('-s', dev, 'push', TOUCH_SRC, '/tmp/touch')
    sh(dev, 'chmod 777 /tmp/touch')
    sh(dev, 'logcat -c')
    sh(dev, 'setprop ctl.start zkswe')
    print('   配置: %s（idx=%d n=%d role=%s seg=%dms  sel=%s）'
          % ('OK' if ok2 else '部分失败', idx, n, 'master' if master else 'slave', seg_ms, sel))
    return True


# ── 状态核对 ────────────────────────────────────────────────────────
def cmd_status(a):
    for ip in a.devices.split(','):
        ip = ip.strip()
        dev = '%s:5555' % ip
        adb('connect', dev, timeout=10)
        prefs = sh(dev, 'cat /data/preferences.json')
        cfg = {}
        for k in KEYS:
            m = re.search('"%s"\\s*:\\s*("([^"]*)"|[^,}\\s]+)' % k, prefs)
            cfg[k] = (m.group(1) if m else '-')
        log = sh(dev, 'logcat -d -v time')
        plays = [l.strip()[:110] for l in log.splitlines() if 'screensaver play[' in l][-3:]
        state = sh(dev, 'getprop sys.zkapp.state').strip()
        print('=== %s  state=%s' % (ip, state))
        print('   en=%s group=%s idx=%s n=%s role=%s seg=%s' % (
            cfg['sp_wall_en'], cfg['sp_wall_group'], cfg['sp_wall_idx'], cfg['sp_wall_n'],
            cfg['sp_wall_role'], cfg['sp_wall_seg_ms']))
        for p in plays:
            print('   ' + p)


def main():
    ap = argparse.ArgumentParser(description='多屏拼接：设备发现 / 配置与素材分发 / 状态核对')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s1 = sub.add_parser('scan', help='发现可用面板')
    s1.add_argument('--subnet', default='192.168.1.')
    s1.set_defaults(func=scan)
    s2 = sub.add_parser('push', help='下发配置与分段（整组递归 / 旧单视频）')
    s2.add_argument('--seg-dir', dest='seg_dir', default=None,
                    help='旧：单视频分段目录（根目录 seg_<idx>.mp4 + wall.json）')
    s2.add_argument('--group-dir', dest='group_dir', default=None,
                    help='新：整组目录（playlist.json + cN/seg_i.mp4…）—— 递归推送所有文件，保持相对路径')
    s2.add_argument('--group', default=None, help='组名（缺省：取 playlist.json 的 group / 目录名 / zksw-wall）')
    s2.add_argument('--devices', required=True, help='ip=序号,ip=序号 …（序号 = 本机播第几段）')
    s2.add_argument('--dry-run', dest='dry_run', action='store_true',
                    help='只打印将推送的文件与将写入的 prefs，**不连接/不推送任何设备**')
    s2.add_argument('--only-mine', dest='only_mine', action='store_true',
                    help='只推本机要播的那一段（+ playlist.json/wall.json），省设备空间；'
                         '默认整组全推（换序号不用重推）')
    s2.add_argument('--clear', dest='clear_wall', action='store_true',
                    help='推送前先清空设备上的拼接素材目录（/mnt/sdnand/wall，换视频时不残留旧组）')
    s2.set_defaults(func=cmd_push)
    s4 = sub.add_parser('clear', help='清空设备上的视频素材（拼接/屏保/相册/全部）')
    s4.add_argument('--devices', required=True, help='ip,ip …')
    s4.add_argument('--scope', default='wall', choices=['wall', 'video', 'album', 'all'],
                    help='wall=拼接素材 / video=屏保视频 / album=相册 / all=全部（默认 wall）')
    s4.add_argument('--dry-run', dest='dry_run', action='store_true',
                    help='只统计将删除的内容（**默认就是 dry-run**，与 --yes 互斥）')
    s4.add_argument('--yes', action='store_true', help='确认真删（不加 = 只看不删）')
    s4.set_defaults(func=cmd_clear)
    s3 = sub.add_parser('status', help='核对配置与轮播')
    s3.add_argument('--devices', required=True, help='ip,ip …')
    s3.set_defaults(func=cmd_status)
    a = ap.parse_args()
    a.func(a)


if __name__ == '__main__':
    main()
