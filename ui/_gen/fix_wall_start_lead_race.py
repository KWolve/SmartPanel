# -*- coding: utf-8 -*-
"""修 ① 的回归：**起播不能从 detached 线程里拉**（2026-09-29 21:15「1.91 视频卡死」）

原因：simple 引擎起播前有一串**与主线程 tick 强耦合**的 MI 图层处理
（先 stop easyui 播放器 → 沉降 400ms 等 MI 拆层 → 再 wp->start，见 09-26 实测的
「stop 后立刻 start 会踩坏 disp 图层 → 画面冻住不动的 workingTask」）。
我上一版把"延后起播"放进了 detached 线程 → 起播落在 tick 之外 → 正好踩回那个竞态 ⇒ 视频卡死。

做法：延后起播改由 **主线程的 50ms 调度定时器** 驱动（`{1,50}`），到点后走与 tick 完全相同的
      "stop v4 + 沉降 + start" 序列；另加逃生开关：`sp_wall_start_lead_ms <= 0` = 不踩点（立即起播，老行为）。
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'src', 'logic', 'mainLogic.cc')
t = io.open(P, encoding='utf-8').read()

# 1) 线程版 -> 调度版（去掉 detached 线程，改成主线程定时器到点执行）
OLD = '''static void wallStartAtBoundary(const std::string& seg, long long targetMs) {
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
}'''
NEW = '''static long long sWallStartTargetMs = 0;      // 踩点目标时刻（ms）
// 到点后由**主线程**执行起播：与 tick 同一条 MI 图层序列（stop v4 + 沉降 + start）
static void wallStartDo(const std::string& seg) {
    if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) {
        mVideoSsPtr->stop();
        LOGD("wall[simple]: (踩点) v4 player stopped -> settle %dms", WALL_V4_SETTLE_MS);
        usleep(WALL_V4_SETTLE_MS * 1000);
    }
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);
    sWallStartPending = false;
    LOGI("wall[simple]: 边界踩点起播 %s（第一帧落整边界）", seg.c_str());
    WallPlayer::getInstance()->start(seg, 0, 0, SS_SCR_W, SS_SCR_H);
}'''
assert OLD in t, '锚点未找到：wallStartAtBoundary'
t = t.replace(OLD, NEW, 1)

# 2) 排队处：记录目标时刻（不再起线程）
OLD_Q = '''            sWallSpFile = seg;                                     // 占位：别让下一拍重复进这里
            sWallStartPending = true;
            sWallStartPendingSeg = seg;
            LOGI("wall[simple]: 边界踩点排队 %s 距边界=%lldms lead=%dms -> %.1fs 后起播",
                 seg.c_str(), wait, lead, (wait - lead) / 1000.0);
            wallStartAtBoundary(seg, wl->nextBoundaryMs() - lead);
            return;'''
NEW_Q = '''            sWallSpFile = seg;                                     // 占位：别让下一拍重复进这里
            sWallStartPending = true;
            sWallStartPendingSeg = seg;
            sWallStartTargetMs = wl->nextBoundaryMs() - lead;
            LOGI("wall[simple]: 边界踩点排队 %s 距边界=%lldms lead=%dms -> %.1fs 后起播（主线程 50ms 调度）",
                 seg.c_str(), wait, lead, (wait - lead) / 1000.0);
            return;'''
assert OLD_Q in t, '锚点未找到：排队处'
t = t.replace(OLD_Q, NEW_Q, 1)

# 3) lead <= 0 = 关闭踩点（逃生开关）
OLD_L = '''        int lead = StoragePreferences::getInt("sp_wall_start_lead_ms", wl->leadMs());
        if (lead <= 0) lead = WALL_START_LEAD_MS;
        const long long wait = wl->waitToBoundaryMs();
        if (wl->hasEpoch() && wait > (long long)lead + 100) {'''
NEW_L = '''        // 逃生开关：sp_wall_start_lead_ms <= 0 -> 不踩点（立即起播，等价老行为）
        const int lead = StoragePreferences::getInt("sp_wall_start_lead_ms", wl->leadMs());
        const long long wait = wl->waitToBoundaryMs();
        if (lead > 0 && wl->hasEpoch() && wait > (long long)lead + 100) {'''
assert OLD_L in t, '锚点未找到：lead 判定'
t = t.replace(OLD_L, NEW_L, 1)

# 4) 定时器表加 50ms 调度拍；onUI_Timer 里处理
t = t.replace('''static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},''', '''static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
    {1, 50},        // ① 拼墙起播踩点调度（主线程，别挪到线程里——会踩 MI 图层，见 09-29 21:15 事故）''', 1)

m = re.search(r'static bool onUI_Timer\(int id\) \{\n', t)
assert m, '锚点未找到：onUI_Timer'
ins = m.end()
t = t[:ins] + '''    if (id == 1) {                                   // 50ms：拼墙踩点调度（到点后主线程起播）
        if (sWallStartPending && nowMs() >= sWallStartTargetMs) {
            wallStartDo(sWallStartPendingSeg);
        }
        return true;
    }
''' + t[ins:]

io.open(P, 'w', encoding='utf-8').write(t)
print('patched', P)
