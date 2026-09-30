# -*- coding: utf-8 -*-
"""
add_mode_qr.py -- 在「运行模式」页(mode.ftu)加一块「扫码配置 HA 服务器」二维码区

钟工 2026-09-30：HA 服务器地址/令牌从代码里挪到配置里，长令牌用手机粘贴最省事 ->
面板显示二维码，手机扫码打开板内网页填。

口径：
  - 二维码区只在 **HA 模式** 显示（IP 行是给「本地从机」用的，两种模式互斥显示）
  - 二维码内容运行时由 modeLogic 调 WebConfigServer::pageUrl() 填（含本机 IP + 口令码）
  - 复用现有 IP 行的区域（y 302..394），不新开页面、不动其它控件
幂等：重复执行会先删掉上次加的键再重加。
"""
import io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, 'ui', 'mode.json')

CLR_TITLE = 15527152   # 亮字
CLR_MUTED = 10132130   # 次级灰

NEW_KEYS = ['qrcode__1', 'textview__26', 'textview__27', 'textview__28']

def textview(next_id, cap, left, top, w, h, size, color, text, touchable=False):
    return {
        "id": next_id,
        "caption": cap,
        "position": {"left": left, "top": top, "width": w, "height": h},
        "alignment": 0,
        "colorTab": {"color0": color, "color1": -1, "color2": -1, "color3": -1, "color4": -1},
        "fontSize": size,
        "touchable": touchable,
        "bold": False,
        "italic": False,
        "text": text,
        "visible": False,
        "rollEnable": False,
        "rollDirection": 1,
        "rollIntervalTime": 150,
        "rollStep": 5,
        "bgColorTab": {"color0": -1, "color1": -1, "color2": -1, "color3": -1, "color4": -1},
    }

def main():
    with io.open(PATH, encoding='utf-8') as f:
        doc = json.load(f)

    # 幂等：清掉上次
    for k in NEW_KEYS:
        doc.pop(k, None)

    # 占用 id 校验（新 id 不能撞车）
    used = set(v['id'] for v in doc.values() if isinstance(v, dict) and 'id' in v)

    qr = {
        "id": 92002,
        "codeStr": "",
        "padding": 10,
        "position": {"left": 14, "top": 300, "width": 104, "height": 104},
        "backgroundColor": -1,
        "touchable": False,
        "visible": False,
    }
    qr["caption"] = "QrcodeModeHa"
    # 新 textview id 从现有最大值往上拿，避免与历史页面撞车
    tv_ids = [v['id'] for k, v in doc.items()
              if isinstance(v, dict) and k.startswith('textview__') and 'id' in v]
    base = (max(tv_ids) if tv_ids else 50000) + 1
    t1 = textview(base + 0, "TextModeQrTitle", 128, 300, 338, 24, 18, CLR_TITLE, "扫码配置 HA 服务器")
    t2 = textview(base + 1, "TextModeQrUrl", 128, 328, 338, 22, 13, CLR_MUTED, "")
    t3 = textview(base + 2, "TextModeQrHint", 128, 354, 338, 44, 13, CLR_MUTED,
                  "手机扫码后粘贴服务器与令牌")

    for node in [qr, t1, t2, t3]:
        if node['id'] in used:
            raise SystemExit('id 冲突: %s' % node['id'])

    doc['qrcode__1'] = qr
    doc['textview__26'] = t1
    doc['textview__27'] = t2
    doc['textview__28'] = t3

    # 键顺序：按类型分组、连续编号（铁律 #5）
    order = []
    for k in doc:
        if not isinstance(doc[k], dict):
            order.append(k)
    type_keys = {}
    for k, v in doc.items():
        if isinstance(v, dict) and 'position' in v:
            t = k.split('__')[0]
            type_keys.setdefault(t, []).append(k)
    for t in ['textview', 'button', 'edittext', 'qrcode', 'seekbar', 'listview', 'image']:
        if t in type_keys:
            type_keys[t].sort(key=lambda s: int(s.split('__')[1]))
            order += type_keys[t]
    seen = set(order)
    for k in doc:
        if k not in seen:
            order.append(k)
    out = {k: doc[k] for k in order}

    with io.open(PATH, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write('\n')

    print('mode.json updated: %s' % PATH)
    for k in NEW_KEYS:
        print('  %-12s id=%-6s pos=%s' % (k, out[k]['id'], out[k]['position']))

if __name__ == '__main__':
    main()
