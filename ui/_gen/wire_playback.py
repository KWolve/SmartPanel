# -*- coding: utf-8 -*-
"""屏保视频：播放流程由我们自己控制（连续=播完即切；有间隔=按 /data 的 sp_video_int 定时切）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
p = os.path.join(ROOT, 'src', 'logic', 'mainLogic.cc')
t = open(p, encoding='utf-8').read()

# 1) 记录当前视频开始时刻
t = t.replace('static bool sScreenOff = false;',
              'static bool sScreenOff = false;\nstatic long long sVideoStartedMs = 0;   // 当前视频开播时刻（间隔轮播计时）', 1)

# 2) playVideo：记录开播时刻 + 支持"强制切换"（间隔到了先停再播）
old = '''static void playVideo(int index) {
    if (mVideoSsPtr == NULL) return;
    if (sVideos.empty()) return;                      // 无视频时露出静态底图（ImageSsBg）
    if (mVideoSsPtr->isPlaying()) return;             // 已在播就不重开（跨页连续）
    sVideoIdx = (index < 0 ? 0 : index) % (int)sVideos.size();
    mVideoSsPtr->setVolume(0);
    mVideoSsPtr->play(sVideos[sVideoIdx].c_str(), 0);
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);
    LOGD("screensaver play[%d] %s", sVideoIdx, sVideos[sVideoIdx].c_str());
}'''
new = '''static void playVideo(int index, bool force = false) {
    if (mVideoSsPtr == NULL) return;
    if (sVideos.empty()) return;                      // 无视频时露出静态底图（ImageSsBg）
    if (force && mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
    if (mVideoSsPtr->isPlaying()) return;             // 已在播就不重开（跨页连续）
    sVideoIdx = (index < 0 ? 0 : index) % (int)sVideos.size();
    mVideoSsPtr->setVolume(0);
    mVideoSsPtr->play(sVideos[sVideoIdx].c_str(), 0);
    sVideoStartedMs = TimeHelper::getCurrentTime();
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);
    LOGD("screensaver play[%d] %s", sVideoIdx, sVideos[sVideoIdx].c_str());
}

static int videoIntervalSec() {
    return StoragePreferences::getInt("sp_video_int", 0);   // 0 = 连续（播完即切）
}'''
assert old in t
t = t.replace(old, new, 1)

# 3) 播完处理：连续 -> 下一条；有间隔 -> 本条循环（到点在心跳里切）
old = '''        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED:
            playVideo(sVideoIdx + 1);                 // 播完切下一条
            break;'''
new = '''        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED:
            if (videoIntervalSec() == 0) playVideo(sVideoIdx + 1);   // 连续：播完即切
            else playVideo(sVideoIdx);                               // 有间隔：本条循环
            break;'''
assert old in t
t = t.replace(old, new, 1)

# 4) 1s 心跳：间隔到点 -> 强制切下一条
old = '''    case 0:
        refreshSsClock();
        refreshSsDevNames();
        ClockManager::getInstance()->tick();   // 未同步则重试；已同步则每日刷新
        break;'''
new = '''    case 0: {
        refreshSsClock();
        refreshSsDevNames();
        ClockManager::getInstance()->tick();   // 未同步则重试；已同步则每日刷新
        // 播放流程自控：有间隔且到点 -> 切下一条
        int iv = videoIntervalSec();
        if (iv > 0 && sVideos.size() > 1 && sVideoStartedMs > 0
            && nowMs() - sVideoStartedMs >= (long long)iv * 1000) {
            playVideo(sVideoIdx + 1, true);
        }
        break; }'''
assert old in t
t = t.replace(old, new, 1)

# nowMs() 助手（原本没有）
if 'static long long nowMs()' not in t:
    t = t.replace('static const char* kWeek[]',
                  'static long long nowMs() { return TimeHelper::getCurrentTime(); }\n\nstatic const char* kWeek[]', 1)

open(p, 'w', encoding='utf-8').write(t)
print('mainLogic: 播放流程自控（连续/间隔）已写入')
