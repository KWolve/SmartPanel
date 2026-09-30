# -*- coding: utf-8 -*-
"""① 边界预热踩点（钟工 2026-09-29 21:03「用一台做主机，大家追平主机的帧，起播就直接追平」）

现状（simple 引擎 / 官方 simple-player 包）：一发现空闲就"立即起播"→ 各屏起播时刻 = 各自进屏保的时刻，
段内不再纠正 → 三屏在段内差几帧~十几帧（用户看到的"错帧"）。
官方包 API 只有 play/stop/dropoutBuffer/setSynchronizing（**没有 seek**），所以不能"跳帧追平"。

做法（不依赖 seek）：**起播推迟到「下一个整边界 − lead」**，让第一帧正好落在整边界上
→ 三屏同刻出画 = 起播直接对齐；lead 用来吃掉本机"解码→上屏"的启动延迟。
口径：sp_wall_start_lead_ms（默认 150ms；也可用现成的 sp_wall_lead_ms）
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'src', 'logic', 'mainLogic.cc')
t = io.open(P, encoding='utf-8').read()

# 0) 头文件：std::thread
if '#include <thread>' not in t:
    t = t.replace('#include <unistd.h>', '#include <unistd.h>\n#include <thread>', 1)

# 1) 插入踩点助手 + 静态量，并让 wallSimpleStop 能取消排队
OLD_STOP = '''static void wallSimpleStop(const char* why) {
    WallPlayer* wp = WallPlayer::getInstance();
    if (wp->running() || !sWallSpFile.empty()) {
        LOGD("wall[simple]: stop (%s) cyc=%d secs=%d", why, wp->cycles(), wp->secs());
    }
    wp->stop();
    sWallSpFile.clear();
    sWallSpFailTicks = 0;
}'''
NEW_STOP = '''// ── ① 边界预热踩点（钟工 2026-09-29 21:03）──────────────────────────────
//   起播不再"发现空闲就拉"，而是等「下一个整边界 − lead」再拉，让**第一帧正好落在整边界**
//   → 三屏同刻出画（不用 seek；官方 simple-player 包没有 seek API）。
//   lead 口径：sp_wall_start_lead_ms（默认 150ms）；也兼容已有的 sp_wall_lead_ms。
#define WALL_START_LEAD_MS  150
static bool sWallStartPending = false;          // 已排队等踩点
static std::string sWallStartPendingSeg;        // 排队的段（换段即取消）

static void wallStartAtBoundary(const std::string& seg, long long targetMs) {
    std::thread([seg, targetMs]() {
        for (;;) {
            long long d = targetMs - nowMs();
            if (d <= 0) break;
            usleep((unsigned)((d > 200 ? 200 : d) * 1000));      // 小段睡，便于换段取消
            if (!sWallStartPending || sWallStartPendingSeg != seg) return;
        }
        if (!sWallStartPending || sWallStartPendingSeg != seg) return;
        sWallStartPending = false;
        LOGI("wall[simple]: 边界踩点起播 %s（第一帧落整边界）", seg.c_str());
        WallPlayer::getInstance()->start(seg, 0, 0, SS_SCR_W, SS_SCR_H);
    }).detach();
}

static void wallSimpleStop(const char* why) {
    WallPlayer* wp = WallPlayer::getInstance();
    if (sWallStartPending) {                 // 取消未执行的踩点起播
        sWallStartPending = false;
        sWallStartPendingSeg.clear();
    }
    if (wp->running() || !sWallSpFile.empty()) {
        LOGD("wall[simple]: stop (%s) cyc=%d secs=%d", why, wp->cycles(), wp->secs());
    }
    wp->stop();
    sWallSpFile.clear();
    sWallSpFailTicks = 0;
}'''
assert OLD_STOP in t, '锚点未找到：wallSimpleStop'
t = t.replace(OLD_STOP, NEW_STOP, 1)

# 2) 起播分支：改成"踩点起播"
OLD_START = '''    if (!wp->running() || sWallSpFile != seg) {
        if (wp->running() || !sWallSpFile.empty()) wp->stop();
        if (sWallSpFailTicks > 0) { sWallSpFailTicks--; return; }   // 失败后歇 5s 再试
        sWallSpFile = seg;
        wp->start(seg, 0, 0, SS_SCR_W, SS_SCR_H);
    }'''
NEW_START = '''    if (!wp->running() || sWallSpFile != seg) {
        if (sWallStartPending) {
            if (sWallStartPendingSeg == seg) return;               // 已排队，等踩点线程
            sWallStartPending = false;                             // 换段 -> 取消旧排队
        }
        if (wp->running() || !sWallSpFile.empty()) wp->stop();
        if (sWallSpFailTicks > 0) { sWallSpFailTicks--; return; }   // 失败后歇 5s 再试
        // ① 边界预热踩点：有 epoch 且离整边界还早 -> 排队（等到边界前 lead 再拉播放器）
        int lead = StoragePreferences::getInt("sp_wall_start_lead_ms", wl->leadMs());
        if (lead <= 0) lead = WALL_START_LEAD_MS;
        const long long wait = wl->waitToBoundaryMs();
        if (wl->hasEpoch() && wait > (long long)lead + 100) {
            sWallSpFile = seg;                                     // 占位：别让下一拍重复进这里
            sWallStartPending = true;
            sWallStartPendingSeg = seg;
            LOGI("wall[simple]: 边界踩点排队 %s 距边界=%lldms lead=%dms -> %.1fs 后起播",
                 seg.c_str(), wait, lead, (wait - lead) / 1000.0);
            wallStartAtBoundary(seg, wl->nextBoundaryMs() - lead);
            return;
        }
        sWallSpFile = seg;
        wp->start(seg, 0, 0, SS_SCR_W, SS_SCR_H);
    }'''
assert OLD_START in t, '锚点未找到：起播分支'
t = t.replace(OLD_START, NEW_START, 1)

io.open(P, 'w', encoding='utf-8').write(t)
print('patched', P)
