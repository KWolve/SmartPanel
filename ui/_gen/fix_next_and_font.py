# -*- coding: utf-8 -*-
"""两处修复：
① 「视频不自动播下一个」→ 完成回调里必须 force 切（绕开 isPlaying 守卫）+ 心跳加时长兜底看门狗；
② 字库缺「嫦」→ GB2312 一级扩到**全字库（一级+二级 6763 字）**重建 HanSans-Medium。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def patch(rel, pairs):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in pairs:
        assert old in t, 'MISS %s: %r' % (rel, old[:80])
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('patched', rel)


# ---------- ① mainLogic：播完强制切 + 看门狗 ----------
patch('src/logic/mainLogic.cc', [
    # 完成/出错回调：force=true（此时 isPlaying() 可能仍为 true，不 force 会被守卫挡掉 → 永远不切）
    ("""        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED:
            if (videoIntervalSec() == 0) playVideo(sVideoIdx + 1);   // 连续：播完即切
            else playVideo(sVideoIdx);                               // 有间隔：本条循环
            break;
        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_ERROR:
            LOGW("ss video error, retry");
            playVideo(sVideoIdx);
            break;""",
     """        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED:
            LOGD("ss video completed idx=%d interval=%d", sVideoIdx, videoIntervalSec());
            if (videoIntervalSec() == 0) playVideo(sVideoIdx + 1, true);   // 连续：播完即切（force 绕开守卫）
            else playVideo(sVideoIdx, true);                               // 有间隔：本条循环
            break;
        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_ERROR:
            LOGW("ss video error, next");
            playVideo(sVideoIdx + 1, true);
            break;"""),
    # 心跳：间隔到点切 + 连续模式下按实际时长兜底（防播放器完成消息不回来的机型/编码）
    ("""        // 播放流程自控：有间隔且到点 -> 切下一条
        int iv = videoIntervalSec();
        if (iv > 0 && sVideos.size() > 1 && sVideoStartedMs > 0
            && nowMs() - sVideoStartedMs >= (long long)iv * 1000) {
            playVideo(sVideoIdx + 1, true);
        }""",
     """        // 播放流程自控：①有间隔且到点 -> 切；②连续模式按时长兜底（完成消息不可靠时也轮播）
        int iv = videoIntervalSec();
        if (sVideos.size() > 1 && sVideoStartedMs > 0) {
            long long el = nowMs() - sVideoStartedMs;
            if (iv > 0) {
                if (el >= (long long)iv * 1000) playVideo(sVideoIdx + 1, true);
            } else {
                int dur = (mVideoSsPtr != NULL) ? mVideoSsPtr->getDuration() : 0;
                if (dur > 0 && el >= (long long)dur + 1500) playVideo(sVideoIdx + 1, true);
                else if (dur <= 0 && el >= 60000) playVideo(sVideoIdx + 1, true);   // 取不到时长 -> 60s 兜底
            }
        }"""),
])

# ---------- ② 字库：GB2312 全字库 ----------
patch('ui/_gen/build_fonts.py', [
    ("def gb2312_level1():",
     """def gb2312_level2():
    # GB2312 二级汉字（0xD8-0xF7）：嫦 娥 等一级没有的字都在这里
    out = []
    for hi in range(0xD8, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('gb2312'))
            except Exception:
                pass
    return out


def gb2312_level1():"""),
    ("    cs = gb2312_level1()",
     "    cs = gb2312_level1() + gb2312_level2()   # 全字库：一级+二级（含 嫦、娥 等）"),
])

r = subprocess.run([sys.executable, os.path.join(ROOT, 'ui', '_gen', 'build_fonts.py')],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
print((r.stdout or '') + (r.stderr or '')[-600:])
