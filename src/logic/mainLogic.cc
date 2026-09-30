#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * mainLogic.cc -- 屏保页（main.ftu = 应用入口 Activity）
 *
 * 职责：屏保视频轮播（ZKVideoView，最底层）+ 时钟/温湿度浮层 + 触摸进主页 +
 *       息屏时段判定（关屏设置子页配置，钟工 2026-09-24 23:40 口径）+
 *       屏保项显隐/位置自由拖动（设计说明书 3.4.3）。
 * 多 Activity 口径：本页只碰自己的控件；配置走业务单例 ConfigStore。
 */

#include "utils/Log.h"
#include "utils/TimeHelper.h"
#include "utils/BrightnessHelper.h"
#include "entry/EasyUIContext.h"
#include "os/SystemProperties.h"
#include "control/ZKTextView.h"
#include "control/ZKVideoView.h"
#include "control/ZKButton.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "network/LocalLink.h"
#include "network/MqttBridge.h"
#include "network/PanelLink.h"
#include "scene/SceneManager.h"
#include "device/RelayManager.h"
#include "device/SensorManager.h"
#include "system/ClockManager.h"
#include "wall/WallLink.h"
#include "wall/WallPlayer.h"
#include "system/NetKeeper.h"
#include "system/DisplayFlip.h"

#include <stdio.h>
#include <ctype.h>
#include <string>
#include <vector>
#include <algorithm>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <thread>

#define SS_TIMEOUT_SEC   15          // 空闲进屏保 / 关屏时段内空闲熄屏（系统 Screensaver）
#define SS_PHOTO_SEC     15          // 图片素材默认显示 15 秒（可在「屏保视频」页配 5/10/15/30/60s）
#define SS_EDGE_KEEP     40          // 拖动夹取：至少 40px（或 1/3 宽）留在屏内
#define SS_SCR_W         480
#define SS_SCR_H         480
#define SS_GROUP_N       5

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
    {1, 50},        // ① 拼墙起播踩点调度（主线程，别挪到线程里——会踩 MI 图层，见 09-29 21:15 事故）
};

// 全局触摸监听：任意页面触摸都复位系统屏保计时（钟工 2026-09-25 报告 2/3：
// 之前子页/编辑态的触摸没复位系统屏保，操作到一半就被屏保打断）
class GlobalTouchReset : public EasyUIContext::ITouchListener {
public:
    virtual bool onTouchEvent(const MotionEvent &ev) {
        if (ev.mActionStatus == MotionEvent::E_ACTION_DOWN || ev.mActionStatus == MotionEvent::E_ACTION_MOVE) {
            EASYUICONTEXT->resetScreensaverTimeOut();
        }
        return false;      // 不消费，继续正常分发
    }
};
static GlobalTouchReset sGlobalTouchReset;

static long long nowMs() { return TimeHelper::getCurrentTime(); }

static const char* kWeek[] = { "日", "一", "二", "三", "四", "五", "六" };
static std::vector<std::string> sVideos;   // 混播清单（视频 + 相册上传的图片）
static int sVideoIdx = 0;

// 素材类型：图片（屏保直接铺图，每张 15s）/ 视频（走 ZKVideoView）
static bool isImagePath(const std::string& p) {
    size_t dot = p.find_last_of('.');
    if (dot == std::string::npos) return false;
    std::string ext = p.substr(dot);
    for (size_t i = 0; i < ext.size(); i++) ext[i] = (char)tolower((unsigned char)ext[i]);
    return ext == ".jpg" || ext == ".jpeg" || ext == ".png" || ext == ".bmp" || ext == ".gif";
}

static bool isVideoPath(const std::string& p) {
    size_t dot = p.find_last_of('.');
    if (dot == std::string::npos) return false;
    std::string ext = p.substr(dot);
    for (size_t i = 0; i < ext.size(); i++) ext[i] = (char)tolower((unsigned char)ext[i]);
    return ext == ".mp4" || ext == ".avi" || ext == ".mkv" || ext == ".mov";
}
static bool sScreenOff = false;         // true = 当前黑屏（关屏时段内空闲到点）
static long long sLastTouchMs = 0;      // 本页最后交互时刻（关屏时段内空闲判定）
static long long sVideoStartedMs = 0;   // 当前视频开播时刻（保留：仅供日志参考）
// 播放/空闲计时改用**心跳 tick 计数**：TimeHelper::getCurrentTime() 在部分会话返回 0
// （NTP 校时前后不一致）-> 用墙钟算 elapsed 会永不推进（2026-09-25 实测踩到）
static int sMediaTicks = 0;             // 当前素材已显示秒数（每秒 +1）
static int sIdleTicks = 0;              // 本页空闲秒数（触摸/onUI_show 归零）

static void loadVideoList() {
    // 多屏拼接（钟工 2026-09-25）：启用且未失联时，本机只播自己的段（失联自动落回下面的普通轮播）
    WallLink* wl = WallLink::getInstance();
    if (wl->enabled() && wl->readyToPlay()) {
        sVideos.clear();
        // v5：playlist 模式给 v4 兜底用第 1 个 clip 的段（simple 引擎自己会在内部切 clip，不读这个清单）
        sVideos.push_back(wl->playlistMode() ? wl->segPathForClip(0) : wl->segPath());
        LOGD("wall: local segment %s (playlist=%d clips=%d)",
             sVideos[0].c_str(), wl->playlistMode() ? 1 : 0, wl->clipCount());
        return;
    }
    sVideos.clear();
    // 优先用 /data 里的选中清单（屏保视频子页配置；空 = 未配置 -> 退扫目录）
    // 钟工 2026-09-25：选中清单里**已不存在的路径要跳过**（否则清单全是死路径 -> 播什么都不出来，
    // 表现为“选了文件但屏保不轮播”）；若全部无效则自动退扫目录。
    std::string all = StoragePreferences::getString("sp_video_sel", "");
    int dropped = 0;
    size_t pos = 0;
    while (pos < all.size()) {
        size_t nl = all.find('\n', pos);
        std::string one = all.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        if (!one.empty()) {
            struct stat st = {0};
            if (stat(one.c_str(), &st) == 0) {
                sVideos.push_back(one);
            } else {
                dropped++;
            }
        }
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    if (!sVideos.empty()) {
        LOGD("screensaver videos(from /data sel): %d (dropped %d missing)",
             (int)sVideos.size(), dropped);
        return;
    }
    if (dropped > 0) LOGW("screensaver: all %d selected item(s) missing -> fallback to dir scan", dropped);
    // 素材目录：视频 + 相册上传落盘目录（钟工 2026-09-24 口径）；图片也扫（混播，3.4.5）
    // 用 opendir/readdir（不用 popen+ls：省进程创建、目录不存在也不报错）
    const char* dirs[] = { "/mnt/sdnand/video", "/mnt/sdnand/album",
                           "/mnt/extsd/video", "/mnt/usb1/video" };
    for (size_t d = 0; d < sizeof(dirs) / sizeof(dirs[0]); d++) {
        DIR* dp = opendir(dirs[d]);
        if (dp == NULL) continue;
        std::vector<std::string> found;
        struct dirent* ent = NULL;
        while ((ent = readdir(dp)) != NULL) {
            std::string nm = ent->d_name;
            if (nm == "." || nm == ".." || nm[0] == '.') continue;
            std::string full = std::string(dirs[d]) + "/" + nm;
            if (isImagePath(full) || isVideoPath(full)) found.push_back(full);
        }
        closedir(dp);
        std::sort(found.begin(), found.end());          // 名称序（稳定，便于对账）
        for (size_t i = 0; i < found.size(); i++) sVideos.push_back(found[i]);
    }
    LOGD("screensaver media: %d", (int)sVideos.size());
}

// ── 素材变化检测（钟工 2026-09-25：新上传的素材不进轮播）────────────────
static void playItem(int index, bool force);   // 前向声明（定义在下方，默认参数在原声明处）

// 签名 = 选中清单原文 + 各素材目录里的候选文件（名称序拼接）
static std::string mediaSignature() {
    std::string sig = StoragePreferences::getString("sp_video_sel", "");
    const char* dirs[] = { "/mnt/sdnand/video", "/mnt/sdnand/album",
                           "/mnt/extsd/video", "/mnt/usb1/video" };
    for (size_t d = 0; d < sizeof(dirs) / sizeof(dirs[0]); d++) {
        DIR* dp = opendir(dirs[d]);
        if (dp == NULL) continue;
        std::vector<std::string> found;
        struct dirent* ent = NULL;
        while ((ent = readdir(dp)) != NULL) {
            std::string nm = ent->d_name;
            if (nm == "." || nm == ".." || nm[0] == '.') continue;
            std::string full = std::string(dirs[d]) + "/" + nm;
            if (isImagePath(full) || isVideoPath(full)) found.push_back(nm);
        }
        closedir(dp);
        std::sort(found.begin(), found.end());
        for (size_t i = 0; i < found.size(); i++) {
            sig += '|';
            sig += dirs[d];
            sig += '/';
            sig += found[i];
        }
    }
    return sig;
}

static std::string sListSig;          // 上次构建清单时的素材签名
static int sListCheckTicks = 0;       // 变化检测节流（每 5s 一次）
static bool sWallPending = false;     // 拼接模式：正在等下一个墙钟边界起播
static long long sWallTargetMs = 0;    // v2：本次起播目标 = 整边界**绝对墙钟 ms**（0 = 未定标）
static bool sWallLateRetried = false;  // v2：本段是否已做过“迟起播兜底”（一周期一次）
static long long sWallFireAdj = 0;     // v2 自校准：把“起播调用返回”对齐到整边界的修正量
static long long sWallStopMs = 120;    // v2 自校准：上一轮实测的 stop()（播放器拆解）耗时

// ── 播放内核开关（钟工 2026-09-26 10:04 拍板：多屏拼接改走内网 SimplePlayer 路线）──
//   sp_wall_engine = 0  v4      easyui ZKVideoView + 整边界两段式起播（已实测 |Δ|≤19ms 通过）
//                  = 1  simple  自读包 + I 帧追赶 + 墙钟按 PTS 控速（src/wall/WallPlayer.*）
// 默认 0：v4 是已验证通过的状态；新引擎验证通过后再现场切 1，随时可回退。
#define WALL_ENGINE_V4     0
#define WALL_ENGINE_SIMPLE 1
// simple 引擎接棒前，等 easyui 播放器的 MI 图层拆解完（实测 stop 后立即 start 会踩坏 disp 图层）
#define WALL_V4_SETTLE_MS  400
static int wallEngine() {
    int v = StoragePreferences::getInt("sp_wall_engine", WALL_ENGINE_V4);
    // v5（2026-09-27）：playlist（一组多视频轮播）**只有 simple 引擎**（WallPlayer）支持多 clip 切换，
    //   v4（easyui ZKVideoView）是单文件循环 —— 检测到 playlist 就强制 simple，只提示一次。
    if (v != WALL_ENGINE_SIMPLE && WallLink::getInstance()->playlistMode()) {
        static bool warned = false;
        if (!warned) {
            warned = true;
            LOGW("wall: playlist（多 clip）需要 simple 引擎 -> 本次强制 sp_wall_engine=1；"
                 "如需回退 v4：删掉组目录的 playlist.json（回到旧布局单 clip）");
        }
        return WALL_ENGINE_SIMPLE;
    }
    return (v == WALL_ENGINE_SIMPLE) ? WALL_ENGINE_SIMPLE : WALL_ENGINE_V4;
}
static std::string sWallSpFile;        // simple 引擎当前在播的段（换段才重开）
static int sWallSpFailTicks = 0;       // simple 引擎起播失败重试节流（每 5s 一次）

// ── ① 边界预热踩点（钟工 2026-09-29 21:03）──────────────────────────────
//   起播不再"发现空闲就拉"，而是等「下一个整边界 − lead」再拉，让**第一帧正好落在整边界**
//   → 三屏同刻出画（不用 seek；官方 simple-player 包没有 seek API）。
//   lead 口径：sp_wall_start_lead_ms（默认 150ms）；也兼容已有的 sp_wall_lead_ms。
#define WALL_START_LEAD_MS  150
static bool sWallStartPending = false;          // 已排队等踩点
static std::string sWallStartPendingSeg;        // 排队的段（换段即取消）

static long long sWallStartTargetMs = 0;      // 踩点目标时刻（ms）
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
}

// 设备倒装（钟工 2026-09-27）：
//   UI/触摸的旋转由 DisplayFlip::applyStored() 下发（幂等）；视频层**只能在没播放器跑的时候**
//   下发（MI DISP 层属性播放中改会踩坏通道）。开机与每次进屏保页各查一次。
static void applyFlipWhenIdle(const char* why) {
    const int mode = DisplayFlip::videoRotateMode();
    bool busy = WallPlayer::getInstance()->running()
                || (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying());
    if (busy) {
        LOGD("flip180[%s]: player busy -> video layer keep mode=%d (下次起播自动带上)", why, mode);
        return;
    }
    const int r = DisplayFlip::applyVideoLayer();
    LOGI("flip180[%s]: video layer mode=%d ret=%d", why, mode, r);
}

// simple 引擎的 1s 心跳：相位由播放器自己锁（不用每轮 stop/play），
// 主线程只负责“该起就起 / 该停就停 / 每 5s 打一条自证日志”。
static void wallSimpleTick(WallLink* wl) {
    WallPlayer* wp = WallPlayer::getInstance();
    // v5：播放器“当前节目”键 —— playlist 模式 = playlist.json（**稳定**，播放器内部自己切 clip）；
    //     旧布局 = seg_<idx>.mp4。只用它判断“要不要重开播放器”，不能拿“当前 clip 文件”当键，
    //     否则每切一个 clip 都会被外层当成换节目 -> 反复拆重建 MI 图层。
    const std::string seg = wl->playKey();

    // 编辑态/熄屏态不该出画面（v4 里是靠 ZKVideoView 自己停播，simple 引擎要显式停）
    if (ConfigStore::getInstance()->ssEditMode() || sScreenOff) {
        wallSimpleStop("edit/off");
        return;
    }

    // 两个内核不能同时在显：simple 模式要 ZKVideoView 让位（MI 图层/解码通道）
    // 注意 2026-09-26 实测（71 = 从机）：easyui 播放器 stop() 的 MI 拆解是**异步**的，紧接着
    //    wp->start() 起 simple 引擎会踩在正在拆的图层上 -> disp chn0 留下一个卡死的 workingTask
    //    + 142 帧陈旧输入（/proc/mi_modules/mi_disp：UsrInjectQ_cnt=1、workingTask_cnt=1、
    //    FinishCnt 冻在 142，108 同版本没踩到 = 竞态）-> 表现就是「屏保页画面冻住不动」。
    //    所以 stop 之后留一段沉降时间，等 MI 拆完再建新图层。
    bool stoppedV4 = false;
    if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) {
        mVideoSsPtr->stop();
        stoppedV4 = true;
    }
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);
    if (stoppedV4) {
        LOGD("wall[simple]: v4 player stopped -> settle %dms before MI start", WALL_V4_SETTLE_MS);
        usleep(WALL_V4_SETTLE_MS * 1000);
    }

    if (!wp->running() || sWallSpFile != seg) {
        if (sWallStartPending) {
            if (sWallStartPendingSeg == seg) return;               // 已排队，等踩点线程
            sWallStartPending = false;                             // 换段 -> 取消旧排队
        }
        if (wp->running() || !sWallSpFile.empty()) wp->stop();
        if (sWallSpFailTicks > 0) { sWallSpFailTicks--; return; }   // 失败后歇 5s 再试
        // ① 边界预热踩点：有 epoch 且离整边界还早 -> 排队（等到边界前 lead 再拉播放器）
        // 逃生开关：sp_wall_start_lead_ms <= 0 -> 不踩点（立即起播，等价老行为）
        const int lead = StoragePreferences::getInt("sp_wall_start_lead_ms", wl->leadMs());
        const long long wait = wl->waitToBoundaryMs();
        if (lead > 0 && wl->hasEpoch() && wait > (long long)lead + 100) {
            sWallSpFile = seg;                                     // 占位：别让下一拍重复进这里
            sWallStartPending = true;
            sWallStartPendingSeg = seg;
            sWallStartTargetMs = wl->nextBoundaryMs() - lead;
            LOGI("wall[simple]: 边界踩点排队 %s 距边界=%lldms lead=%dms -> %.1fs 后起播（主线程 50ms 调度）",
                 seg.c_str(), wait, lead, (wait - lead) / 1000.0);
            return;
        }
        sWallSpFile = seg;
        wp->start(seg, 0, 0, SS_SCR_W, SS_SCR_H);
    }

    if (!wp->lastError().empty() && sWallSpFailTicks == 0) {
        LOGW("wall[simple]: start error -> %s (静默 5s 后重试)", wp->lastError().c_str());
        sWallSpFailTicks = 5;
    }

    if ((sMediaTicks % 5) == 0) {
        LOGD("wall[simple]: pkg=1 cyc=%d secs=%d period=%lldms anchor=%lldms begin=%lldms locked=%d catchup=%d pts=%lldms want=%lldms now=%lldms err=%lldms running=%d state=%s",
             wp->cycles(), wp->secs(), wp->periodMs(), wp->anchorMs(), wp->beginMs(),
             wp->locked() ? 1 : 0, wp->catchupFrames(),
             wp->lastPtsMs(), wp->lastWantMs(), wp->lastNowMs(), wp->lastErrMs(),
             wp->running() ? 1 : 0, wl->stateText().c_str());
        // v5：playlist 诊断（clips / 当前 clip / 当前文件）—— 现场对账用
        if (wl->playlistMode()) {
            LOGD("wall[simple]: playlist clips=%d total=%lldms clip=%d file=%s (local seg_%d/%d)",
                 wl->clipCount(), wl->totalMs(), wp->clipIndex(), wp->clipFile().c_str(),
                 wl->segIndex(), wl->panelCount());
        }
    }
}

// 精等到 deadline（毫秒级；只允许在临近起播时调用，单次阻塞 ≤1600ms）
// 为什么不能只靠 1s 心跳：两台心跳相位各不相同，靠“心跳里判断接近边界”只能做到 ±1s，
// 而目标是 ≤40ms（1 帧）——必须本地把“到点”这个瞬间等到毫秒级。
#define WALL_WAIT_MAX_MS 1600
static void wallWaitUntil(long long deadlineMs) {
    // 分片 ≤4ms：实测单次 usleep(几百 ms) 可超时 10~30ms，直接变成起播相位抖动
    for (int i = 0; i < 40000; i++) {             // 硬上限：防时钟跳变导致死等
        long long n = WallLink::wallNowMs();
        if (n <= 0) return;
        long long d = deadlineMs - n;
        if (d <= 0) return;
        if (d > WALL_WAIT_MAX_MS) return;         // 不该发生；宁可不等也不卡 UI
        if (d > 4) usleep(4000);
        else if (d > 1) usleep((useconds_t)((d - 1) * 1000));
        else usleep(200);
    }
}

// 素材变了就重建清单；保持当前项（越界则回第 0 项），非编辑/非息屏时立即切到当前项
static void refreshListIfChanged(bool force) {
    std::string sig = mediaSignature();
    if (!force && sig == sListSig) return;
    sListSig = sig;
    loadVideoList();
    if (sVideos.empty()) {
        LOGW("screensaver: media list is empty after refresh");
        return;
    }
    if (sVideoIdx >= (int)sVideos.size()) sVideoIdx = 0;
    LOGD("screensaver list refreshed -> %d items (idx=%d)", (int)sVideos.size(), sVideoIdx);
    if (!ConfigStore::getInstance()->ssEditMode() && !sScreenOff) {
        WallLink* wl = WallLink::getInstance();
        if (wl->enabled() && wl->readyToPlay()) {
            // v2：拼接模式下改清单也不抢跑（两台进页/改清单时刻不同步）-> 重新落到整边界
            sWallTargetMs = 0;
            LOGD("wall: list refreshed -> re-arm next boundary");
        } else {
            playItem(sVideoIdx, true);      // 立即切到最新清单里的当前项
        }
    }
}

static void playVideo(int index, bool force = false) {
    if (mVideoSsPtr == NULL) return;
    if (sVideos.empty()) return;                      // 无视频时露出静态底图（ImageSsBg）
    if (force && mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
    if (mVideoSsPtr->isPlaying()) return;             // 已在播就不重开（跨页连续）
    sVideoIdx = (index < 0 ? 0 : index) % (int)sVideos.size();
    mVideoSsPtr->setVolume(0);
    mVideoSsPtr->play(sVideos[sVideoIdx].c_str(), 0);
    sVideoStartedMs = TimeHelper::getCurrentTime();
    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setVisible(false);
    LOGD("screensaver play[%d/%d] %s", sVideoIdx, (int)sVideos.size(), sVideos[sVideoIdx].c_str());
}

static int videoIntervalSec() {
    return ConfigStore::getInstance()->videoIntervalSec();   // 0 = 连续（播完即切）
}

// 混播入口：图片 -> 铺图 15s；视频 -> 走 ZKVideoView（原逻辑）
static void playItem(int index, bool force = false);

class SsVideoListener : public ZKVideoView::IVideoPlayerMessageListener {
public:
    virtual void onVideoPlayerMessage(ZKVideoView *pVideoView, int msg) {
        (void)pVideoView;
        switch (msg) {
        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_COMPLETED:
            LOGD("ss video completed idx=%d interval=%d", sVideoIdx, videoIntervalSec());
            // 拼接模式：**不立即再播**，而是等下一个墙钟整边界（实测“播完即播”每循环多 ~1.22s）
            if (WallLink::getInstance()->enabled() && WallLink::getInstance()->readyToPlay()) {
                if (sWallTargetMs == 0) sWallTargetMs = WallLink::getInstance()->nextBoundaryMs();
                LOGD("wall: segment done -> wait boundary (target=%lld)", sWallTargetMs);
                break;
            }
            if (videoIntervalSec() == 0) playItem(sVideoIdx + 1, true);    // 连续：播完即切（force 绕开守卫）
            else playItem(sVideoIdx, true);                               // 有间隔：本条循环
            break;
        case ZKVideoView::E_MSGTYPE_VIDEO_PLAY_ERROR:
            LOGW("ss video error, next");
            // v2 坑（2026-09-26 实测）：本机播放器播完后会**紧跟着**再报一条 ERROR（+112ms），
            // 上一版在这里直接 playItem -> 抢跑起播，把整边界对齐打乱（实测就是它把两台拆到相差 30s）。
            // 拼接模式下 ERROR 同样只等整边界（链式 target 已在起播时推进，无需额外处理）。
            if (WallLink::getInstance()->enabled() && WallLink::getInstance()->readyToPlay()) {
                if (sWallTargetMs == 0) sWallTargetMs = WallLink::getInstance()->nextBoundaryMs();
                LOGD("wall: segment error -> keep grid (target=%lld)", sWallTargetMs);
                break;
            }
            playItem(sVideoIdx + 1, true);
            break;
        default:
            break;
        }
    }
};
static SsVideoListener sSsVideoListener;

// 混播入口：图片 -> 铺图（每张 SS_PHOTO_SEC 秒）；视频 -> 交给 ZKVideoView
static void playItem(int index, bool force) {
    // 拼接 + simple 引擎：easyui 播放器（ZKVideoView）**一律不起** —— 它和 simple 引擎抢 MI 图层，
    // 交接时实测会把 disp 图层任务卡死（屏保画面冻住）。屏保画面全部交给 WallPlayer。
    // 这里做成总闸：开机 onUI_init、编辑态退出、素材轮播兜底等所有起播路径都被它拦住。
    if (WallLink::getInstance()->enabled() && wallEngine() == WALL_ENGINE_SIMPLE) {
        if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
        return;
    }
    if (mVideoSsPtr == NULL) return;
    if (sVideos.empty()) return;
    sVideoIdx = (index < 0 ? 0 : index) % (int)sVideos.size();
    const std::string& path = sVideos[sVideoIdx];
    sMediaTicks = 0;                       // 换素材 -> 计时归零
    if (isImagePath(path)) {
        if (mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
        // 复用最底层垫层（ImageSsBg）铺图：它在视频层之上、时钟等浮层之下，不会盖住屏保信息
        if (mImageSsBgPtr != NULL) {
            mImageSsBgPtr->setBackgroundPic(path.c_str());
            mImageSsBgPtr->setVisible(true);
        }
        sVideoStartedMs = TimeHelper::getCurrentTime();
        LOGD("screensaver photo[%d] %s", sVideoIdx, path.c_str());
        return;
    }    if (mImageSsBgPtr != NULL) mImageSsBgPtr->setBackgroundPic("images/ss_bg.png");   // 回退渐变底图
    playVideo(index, force);
}

// ── 屏保项：显隐 + 自由拖动（统一 5 组）────────────────────────
static ZKTextView* ssChip(int k) {
    ZKTextView* a[3] = { mImageSsChip1Ptr, mImageSsChip2Ptr, mImageSsChip3Ptr };
    return (k >= 0 && k < 3) ? a[k] : NULL;
}
static ZKTextView* ssIcon(int k) {
    ZKTextView* a[3] = { mImageSsDevIcon1Ptr, mImageSsDevIcon2Ptr, mImageSsDevIcon3Ptr };
    return (k >= 0 && k < 3) ? a[k] : NULL;
}
static ZKTextView* ssName(int k) {
    ZKTextView* a[3] = { mTextSsDevName1Ptr, mTextSsDevName2Ptr, mTextSsDevName3Ptr };
    return (k >= 0 && k < 3) ? a[k] : NULL;
}
static ZKTextView* ssState(int k) {
    ZKTextView* a[3] = { mTextSsDevState1Ptr, mTextSsDevState2Ptr, mTextSsDevState3Ptr };
    return (k >= 0 && k < 3) ? a[k] : NULL;
}

// ── 屏保状态条：三格「开/关」随继电器真实状态刷新（钟工 2026-09-28 问题单）──
//   改前：这三格只有 setPosition/setVisible，**全工程没有任何 setText** → 一直显示
//         ui/main.json 的静态文案（开/开/关），所以第三格永远显示"关"
//         （实测：三路全开 sp_relay_state=7 时，状态条第三格仍显示"关"）。
//   改法：真值只从 RelayManager 取；1s 轮询 + 值变了才 setText（避免每秒重绘）。
#define SS_STATE_ON   0x7BE0A3      // 开：绿（与首页/相册高亮同色）
#define SS_STATE_OFF  0x5F5F68      // 关：暗灰
static void refreshSsDevStates(bool force) {
    static int sLast[3] = { -1, -1, -1 };
    for (int k = 0; k < 3; k++) {
        ZKTextView* p = ssState(k);
        if (p == NULL) continue;
        int on = RelayManager::getInstance()->get(k + 1) ? 1 : 0;
        if (!force && sLast[k] == on) continue;
        sLast[k] = on;
        p->setText(on ? "开" : "关");
        p->setTextColor(0xFF000000 | (on ? SS_STATE_ON : SS_STATE_OFF));   // 0xAARRGGBB (alpha != 0)
        LOGD("ss state bar: dev%d -> %s", k + 1, on ? "ON" : "OFF");
    }
}

struct SsGroup {
    const char* key;
    ZKTextView* frame;      // 编辑模式虚线框垫层
    int dl, dt, dw, dh;     // 默认矩形（拖动夹取基准 + 位置落盘基准）
    int dx, dy;             // 当前偏移（相对默认位置）
    bool vis;               // 该组当前是否显示
};
static SsGroup sGroups[SS_GROUP_N];
static bool sGroupsReady = false;
static int sDragIdx = -1;
static int sDownX = 0, sDownY = 0, sDragBaseX = 0, sDragBaseY = 0;
static bool sDragMoved = false;

static void ssGroupsInit() {
    if (sGroupsReady) return;
    SsGroup g[SS_GROUP_N] = {
        { "time",      mImageEdTimePtr,    0,   86,  480, 140, 0, 0, true },
        { "date",      mImageEdDatePtr,    0,   236, 480, 28,  0, 0, true },
        { "weather",   mImageEdWeatherPtr, 188, 282, 168, 24,  0, 0, true },
        { "temphum",   mImageEdThPtr,      0,   326, 480, 28,  0, 0, true },
        { "statusbar", mImageEdBarPtr,     16,  396, 452, 40,  0, 0, true },
    };
    for (int i = 0; i < SS_GROUP_N; i++) sGroups[i] = g[i];
    sGroupsReady = true;
}

// 偏移应用到组内控件（withFrame=false 时不动虚线框）
static void ssApplyGroup(int i) {
    if (i < 0 || i >= SS_GROUP_N) return;
    int ox = sGroups[i].dx, oy = sGroups[i].dy;
    switch (i) {
    case 0:
        if (mTextSsClkPtr != NULL)
            mTextSsClkPtr->setPosition(LayoutPosition(0 + ox, 86 + oy, 480, 140));
        break;
    case 1:
        if (mTextSsDatePtr != NULL)
            mTextSsDatePtr->setPosition(LayoutPosition(0 + ox, 236 + oy, 480, 28));
        break;
    case 2:
        if (mImageSsWxIconPtr != NULL)
            mImageSsWxIconPtr->setPosition(LayoutPosition(188 + ox, 282 + oy, 22, 22));
        if (mTextSsWxPtr != NULL)
            mTextSsWxPtr->setPosition(LayoutPosition(216 + ox, 280 + oy, 140, 26));
        break;
    case 3:
        if (mTextSsThPtr != NULL)
            mTextSsThPtr->setPosition(LayoutPosition(0 + ox, 326 + oy, 480, 28));
        break;
    case 4:
        for (int k = 0; k < 3; k++) {
            int x = 16 + k * 153;
            if (ssChip(k) != NULL)
                ssChip(k)->setPosition(LayoutPosition(x + ox, 396 + oy, 141, 40));
            if (ssIcon(k) != NULL)
                ssIcon(k)->setPosition(LayoutPosition(x + 12 + ox, 406 + oy, 20, 20));
            if (ssName(k) != NULL)
                ssName(k)->setPosition(LayoutPosition(x + 34 + ox, 404 + oy, 56, 24));
            if (ssState(k) != NULL)
                ssState(k)->setPosition(LayoutPosition(x + 91 + ox, 404 + oy, 40, 24));
        }
        break;
    default:
        break;
    }
    if (sGroups[i].frame != NULL) {
        sGroups[i].frame->setPosition(LayoutPosition(sGroups[i].dl + ox, sGroups[i].dt + oy,
                                                      sGroups[i].dw, sGroups[i].dh));
    }
}

// 位置落盘：/data 键 sp_ss_pos_<key>_x/_y（-1 = 默认位置）
static void ssSaveGroupPos(int i) {
    if (i < 0 || i >= SS_GROUP_N) return;
    ConfigStore::getInstance()->setSsItemPos(sGroups[i].key,
                                             sGroups[i].dl + sGroups[i].dx,
                                             sGroups[i].dt + sGroups[i].dy);
}

static void ssLoadLayout() {
    ssGroupsInit();
    ConfigStore* cfg = ConfigStore::getInstance();
    for (int i = 0; i < SS_GROUP_N; i++) {
        int x = -1, y = -1;
        cfg->ssItemPos(sGroups[i].key, x, y);
        // -1/越界 视为未设置（用默认位置）；负值一律当未设置（历史脏数据，见问题单 09251751-8）
        if (x < 0 || x > SS_SCR_W) x = -1;
        if (y < 0 || y > SS_SCR_H) y = -1;
        sGroups[i].dx = (x < 0) ? 0 : (x - sGroups[i].dl);
        sGroups[i].dy = (y < 0) ? 0 : (y - sGroups[i].dt);
        ssApplyGroup(i);
    }
    LOGD("ss layout loaded (edit=%d)", cfg->ssEditMode() ? 1 : 0);
}

// 拖动夹取：至少 SS_EDGE_KEEP（或 1/3 尺寸）留在屏内（钟工 2026-09-24 口径）
//  钟工 2026-09-25（问题单 09251751-8）：**绝不允许绝对坐标出现负值** ——
//   LayoutPosition 里负值会被引擎当成「从右/下算」的 bottom/right 值，重启后控件位置就跑了。
//   所以左/上边界夹到绝对 0（而不是「可以推出去大半」）。
static int ssClampX(int i, int dx) {
    int keep = SS_EDGE_KEEP;
    if (sGroups[i].dw / 3 < keep) keep = sGroups[i].dw / 3;
    int lo = -sGroups[i].dl;                      // 绝对左 >= 0
    int hi = SS_SCR_W - keep - sGroups[i].dl;
    if (dx < lo) dx = lo;
    if (dx > hi) dx = hi;
    return dx;
}
static int ssClampY(int i, int dy) {
    int keep = SS_EDGE_KEEP;
    if (sGroups[i].dh / 3 < keep) keep = sGroups[i].dh / 3;
    int lo = -sGroups[i].dt;                      // 绝对上 >= 0
    int hi = SS_SCR_H - keep - sGroups[i].dt;
    if (dy < lo) dy = lo;
    if (dy > hi) dy = hi;
    return dy;
}

static int ssHitTest(int x, int y) {
    for (int i = 0; i < SS_GROUP_N; i++) {
        if (!sGroups[i].vis) continue;
        int l = sGroups[i].dl + sGroups[i].dx, t = sGroups[i].dt + sGroups[i].dy;
        if (x >= l && x < l + sGroups[i].dw && y >= t && y < t + sGroups[i].dh) return i;
    }
    return -1;
}

static void ssApplyVisible() {
    ConfigStore* cfg = ConfigStore::getInstance();
    bool v[SS_GROUP_N];
    v[0] = cfg->ssItemVisible("time", true);
    v[1] = cfg->ssItemVisible("date", true);
    v[2] = cfg->ssItemVisible("weather", true);
    v[3] = cfg->ssItemVisible("temphum", true);
    v[4] = cfg->ssItemVisible("statusbar", true);
    if (mTextSsClkPtr != NULL) mTextSsClkPtr->setVisible(v[0]);
    if (mTextSsDatePtr != NULL) mTextSsDatePtr->setVisible(v[1]);
    if (mImageSsWxIconPtr != NULL) mImageSsWxIconPtr->setVisible(v[2]);
    if (mTextSsWxPtr != NULL) mTextSsWxPtr->setVisible(v[2]);
    if (mTextSsThPtr != NULL) mTextSsThPtr->setVisible(v[3]);
    for (int k = 0; k < 3; k++) {
        if (ssChip(k) != NULL) ssChip(k)->setVisible(v[4]);
        if (ssIcon(k) != NULL) ssIcon(k)->setVisible(v[4]);
        if (ssName(k) != NULL) ssName(k)->setVisible(v[4]);
        if (ssState(k) != NULL) ssState(k)->setVisible(v[4]);
    }
    for (int i = 0; i < SS_GROUP_N; i++) sGroups[i].vis = v[i];
}

// 编辑模式开/关（虚线框 + 「完成」按钮；帧只在编辑态显示）
static void ssEnterEdit(bool on) {
    ConfigStore::getInstance()->setSsEditMode(on);
    ssGroupsInit();
    ssApplyVisible();
    for (int i = 0; i < SS_GROUP_N; i++) {
        if (sGroups[i].frame != NULL) sGroups[i].frame->setVisible(on && sGroups[i].vis);
    }
    if (mImageSsEditDoneBgPtr != NULL) mImageSsEditDoneBgPtr->setVisible(on);
    if (mButtonSsEditDonePtr != NULL) mButtonSsEditDonePtr->setVisible(on);
    if (on) {
        if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
        if (mImageSsBgPtr != NULL) {
            mImageSsBgPtr->setBackgroundPic("images/ss_bg.png");   // 编辑态用干净底图
            mImageSsBgPtr->setVisible(true);
        }
        EASYUICONTEXT->setScreensaverEnable(false);   // 编辑期间禁止进屏保（钟工报告 2）
    } else {
        EASYUICONTEXT->setScreensaverEnable(true);
        EASYUICONTEXT->resetScreensaverTimeOut();
    }
    sIdleTicks = 0;
    LOGD("ss edit mode -> %d", on ? 1 : 0);
}

// 屏保底部状态芯片的设备名：从业务单例（ConfigStore /data）读，主页改名后同步显示
static void refreshSsDevNames() {
    ConfigStore* cfg = ConfigStore::getInstance();
    for (int i = 0; i < 3; i++) {
        ZKTextView* p = ssName(i);
        if (p == NULL) continue;
        std::string n = cfg->relayName(i + 1);
        std::string out;                     // 芯片宽 141：名字最多 3 个汉字（UTF-8 安全截断）
        int chars = 0;
        for (size_t k = 0; k < n.size() && chars < 3;) {
            unsigned char c = (unsigned char)n[k];
            size_t len = (c < 0x80) ? 1 : ((c < 0xE0) ? 2 : 3);
            if (k + len > n.size()) break;
            out.append(n, k, len);
            k += len;
            ++chars;
        }
        p->setText(out.c_str());
    }
}

static void refreshSsClock() {
    struct tm* t = TimeHelper::getDateTime();
    if (t == NULL) return;
    char buf[64];
    snprintf(buf, sizeof(buf), "%02d:%02d", t->tm_hour, t->tm_min);
    if (mTextSsClkPtr != NULL) mTextSsClkPtr->setText(buf);
    snprintf(buf, sizeof(buf), "%04d年%02d月%02d日 星期%s",
             t->tm_year + 1900, t->tm_mon + 1, t->tm_mday, kWeek[t->tm_wday]);
    if (mTextSsDatePtr != NULL) mTextSsDatePtr->setText(buf);
}

// ── 息屏链路（钟工 2026-09-24 23:40 口径）────────────────────
//   (1) 熄屏状态点屏幕 -> 立即解除熄屏（无延迟、不需多点）
//   (2) 关屏时段内空闲 15s -> 熄屏（黑屏，不显屏保画面）；时段外空闲 15s -> 系统屏保（本页）
static void enterScreenOff() {
    if (sScreenOff) return;
    LOGD("enter screen-off (off period)");
    if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
    wallSimpleStop("screen-off");
    BRIGHTNESSHELPER->screenOff();
    sScreenOff = true;
}

static void leaveScreenOff() {
    if (!sScreenOff) return;
    LOGD("leave screen-off -> screen on");
    BRIGHTNESSHELPER->screenOn();
    BRIGHTNESSHELPER->setBrightness(ConfigStore::getInstance()->screensaverBrightness());
    sScreenOff = false;
}

static void tickScreenOff() {
    struct tm* t = TimeHelper::getDateTime();
    if (t == NULL) return;
    if (ConfigStore::getInstance()->inOffPeriod(t->tm_hour)) {
        if (!sScreenOff && sIdleTicks >= SS_TIMEOUT_SEC) {
            enterScreenOff();
        }
    } else {
        leaveScreenOff();
    }
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    NetKeeper_start();          // 只要程序在跑就保活 WiFi（钟工 2026-09-24 口径）
    // Z20/zkdisplay 板：不设 sys.zkapp.state=running 会永停开机 logo
    SystemProperties::setString("sys.zkapp.state", "running");
    SystemProperties::setString("sys.zkapp.dbg", "main:onUI_init");
    ConfigStore::getInstance()->init();        // /data 参数（名称/亮度/关屏时段/屏保项）
    RelayManager::getInstance()->init();      // 继电器先就绪（恢复断电前状态；HA 上电上报才是真值）
    SceneManager::getInstance()->init();      // 情景定义就绪（HA discovery 要发情景按钮）
    LocalLink::getInstance()->start();        // 按已存运行模式拉起链路（HA 模式内部只记日志，不起 broker）
    MqttBridge::getInstance()->init();        // HA 模式：连外接 broker + HA discovery（内部自判模式/开关）
    // 局域网外部控制 API（UDP 5050，小程序/其他设备发现与控制）+ 状态变化广播。
    // 钟工 2026-09-27：本函数以前全工程无调用点 -> PanelLink 内部 mRelay 恒 nullptr，
    // prefix/status 的 relays 恒为 false（HA 开关状态自相矛盾）。
    PanelLink::getInstance()->init(RelayManager::getInstance(),
                                   SceneManager::getInstance(),
                                   SensorManager::getInstance());
    ClockManager::getInstance()->init();      // 上电即校时（之后每日自动刷新）
    // 息屏链路：空闲 15s -> 系统屏保（本页）；关屏时段内空闲 15s -> 黑屏（tickScreenOff）
    EASYUICONTEXT->setScreensaverTimeOut(SS_TIMEOUT_SEC);
    EASYUICONTEXT->registerGlobalTouchListener(&sGlobalTouchReset);   // 任意页面触摸都复位屏保计时
    WallLink::getInstance()->init();          // 多屏拼接：读配置 + 起 UDP epoch 通道
    // 设备倒装（钟工 2026-09-27）：开机按 /data 的 sp_flip180 上屏（UI+触摸），并下发视频层旋转。
    //   为何不放在 Main.cpp 的 onEasyUIInit：那一阶段 disp/fbdev 还没 init，libeasyui 里
    //   _fbdev_set_rotate 会直接 return（旋转值被丢掉），必须等本页（首页）真的起画面后再调用。
    DisplayFlip::applyStored();
    applyFlipWhenIdle("init");
    loadVideoList();
    refreshSsDevNames();
    refreshSsDevStates(true);
    if (mVideoSsPtr != NULL) mVideoSsPtr->setVideoPlayerMessageListener(&sSsVideoListener);
    refreshSsClock();
    ssLoadLayout();
    ssApplyVisible();
    ssEnterEdit(ConfigStore::getInstance()->ssEditMode());   // 从「屏保显示 -> 编辑位置」进来时直接进编辑态
    sLastTouchMs = nowMs();
    sIdleTicks = 0;
    sMediaTicks = 0;
    if (!ConfigStore::getInstance()->ssEditMode()) playItem(0);
}

static void onUI_intent(const Intent *intentPtr) {
    if (intentPtr != NULL) {
        // 子页返回参数按需扩展
    }
}

static void onUI_show() {
    refreshSsClock();
    refreshSsDevNames();
    refreshSsDevStates(true);
    DisplayFlip::applyStored();      // 倒装：从设置页回来也立即对齐（幂等，已经是目标角就不动）
    applyFlipWhenIdle("show");
    BRIGHTNESSHELPER->setBrightness(ConfigStore::getInstance()->screensaverBrightness());
    ssLoadLayout();
    ssApplyVisible();
    ssEnterEdit(ConfigStore::getInstance()->ssEditMode());
    sLastTouchMs = nowMs();
    sIdleTicks = 0;
    sMediaTicks = 0;
    if (!ConfigStore::getInstance()->ssEditMode()) {
        if (sVideos.empty()) loadVideoList();
        // v2：拼接模式下屏保页进来**不立即起播**（两台进页时刻不同 -> 首段就错位）；
        // 交给主循环定标到下一个整边界统一起播。失联/未就绪时才走普通起播。
        WallLink* wlShow = WallLink::getInstance();
        if (wlShow->enabled() && wallEngine() == WALL_ENGINE_SIMPLE) {
            // 9/26 11:30（钟工）：simple 引擎下屏保页**一进来就起播**——播放器内部先拉齐组内时间，
            //   再直跳到“当前时刻该显示的位置”，所以两台进页时刻不同也不再影响首帧（首帧就是同一帧）。
            //   从机此刻还没 epoch 就由播放器自己等（超时兜底）；不再等 1s 心跳，避免进页后黑一下。
            LOGD("wall: onUI_show -> simple 引擎立即起播（播放器内部拉齐+直跳）");
            wallSimpleTick(wlShow);
        } else if (wlShow->enabled() && wlShow->readyToPlay()) {
            sWallTargetMs = 0;
            LOGD("wall: onUI_show -> re-arm next boundary (no immediate play)");
        } else {
            playItem(sVideoIdx);
        }
    }
}

static void onUI_hide() {
    BRIGHTNESSHELPER->setBrightness(ConfigStore::getInstance()->workBrightness());
}

static void onUI_quit() {
    EASYUICONTEXT->unregisterGlobalTouchListener(&sGlobalTouchReset);
    WallPlayer::getInstance()->stop();      // 拼接 simple 引擎：退出屏保页就放开 MI 图层/解码通道
    sWallSpFile.clear();
    sWallSpFailTicks = 0;
    if (mVideoSsPtr != NULL) {
        mVideoSsPtr->setVideoPlayerMessageListener(NULL);
        if (mVideoSsPtr->isPlaying()) mVideoSsPtr->stop();
    }
}

static void onProtocolDataUpdate(const SProtocolData &data) {
    (void)data;
}

static bool onUI_Timer(int id) {
    if (id == 1) {                                   // 50ms：拼墙踩点调度（到点后主线程起播）
        if (sWallStartPending && nowMs() >= sWallStartTargetMs) {
            wallStartDo(sWallStartPendingSeg);
        }
        return true;
    }
    switch (id) {
    case 0: {
        refreshSsClock();
        refreshSsDevNames();
        refreshSsDevStates(false);
        ClockManager::getInstance()->tick();   // 未同步则重试；已同步则每日刷新
        MqttBridge::getInstance()->tick();     // HA 链路看门狗（断线重连）
        // 多屏拼接：epoch 收发/失联判定/漂移统计
        WallLink::getInstance()->tick();
        {
            WallLink* wl = WallLink::getInstance();
            if (wl->enabled()) {
                // v7.13（方案B）：simple 引擎**不再要求 readyToPlay（= 有主机 epoch）**——
                //   相位与本机钟对齐完全靠 NTP；断网也能播、也不影响两屏一致。
                if (wallEngine() == WALL_ENGINE_SIMPLE) {
                    // ── simple 引擎（钟工 2026-09-26 拍板）：相位由播放器自己锁 ──
                    // 不参与 v4 的每轮 stop/play；主线程只做“该起就起/该停就停”与自证日志。
                    sWallPending = false;
                    sWallTargetMs = 0;
                    wallSimpleTick(wl);
                } else if (wl->readyToPlay()) {
                    // ── v2 起播链（2026-09-26）：目标 = 下一整边界绝对墙钟，本地精等到点起播 ──
                    // 两台各自算同一个时刻（同 epoch + 同公式），因此**不靠互发开始信令**，
                    // UDP 抖动/心跳相位差都不进相位；起播后 target += seg 链式推进，仍恒落整边界。
                    if (sWallTargetMs == 0) {
                        sWallTargetMs = wl->nextBoundaryMs();
                        sWallFireAdj = 0;
                        LOGD("wall: arm target=%lld now=%lld in=%lldms lead=%dms",
                             sWallTargetMs, WallLink::wallNowMs(),
                             sWallTargetMs - WallLink::wallNowMs(), wl->leadMs());
                    }
                    if (sWallTargetMs > 0) {
                        long long noww = WallLink::wallNowMs();
                        long long lead = wl->leadMs();
                        long long fire = sWallTargetMs - lead + sWallFireAdj;  // 自校准后的实际发起时刻
                        if (noww > sWallTargetMs + 250) {
                            // 迟到 >250ms（本边界已错过/时钟跳变）-> 跳到下一个整边界，不让误差累积
                            long long nb = wl->nextBoundaryMs();
                            LOGW("wall: miss boundary target=%lld now=%lld -> re-arm %lld",
                                 sWallTargetMs, noww, nb);
                            if (nb > sWallTargetMs) sWallTargetMs = nb;
                            sWallFireAdj = 0;
                        } else if (noww >= fire - WALL_WAIT_MAX_MS) {
                            // (1) 提前停：上段还在播 -> 先 stop()，把播放器“拆解”（实测 110~150ms、
                            //    两台快慢不一）移出关键路径；起播就退化成“冷启动 play”（实测 ~6ms）。
                            //    这是收敛到 1 帧的关键：v1 把 stop+play 串在临界点上，拆解耗时差
                            //    直接变成两台的相位差（实测 25~41ms 散布）。
                            if (mVideoSsPtr != NULL && mVideoSsPtr->isPlaying()) {
                                long long ps = fire - sWallStopMs - 40;      // 留 40ms 余量
                                if (ps < fire - WALL_WAIT_MAX_MS) ps = fire - WALL_WAIT_MAX_MS;
                                wallWaitUntil(ps);
                                long long ts0 = WallLink::wallNowMs();
                                mVideoSsPtr->stop();
                                long long ts1 = WallLink::wallNowMs();
                                sWallStopMs = ts1 - ts0;
                                if (sWallStopMs < 0 || sWallStopMs > 800) sWallStopMs = 120;
                                LOGD("wall: pre-stop now=%lld (target-%lldms) stop_cost=%lldms",
                                     ts1, sWallTargetMs - ts1, sWallStopMs);
                            }
                            // (2) 精等到点起播（拆解已做完 -> 此处只剩冷启动开销）
                            wallWaitUntil(fire);
                            if (sVideos.size() != 1 ||
                                sVideos[0] != (wl->playlistMode() ? wl->segPathForClip(0) : wl->segPath()))
                                loadVideoList();
                            sVideoIdx = 0;
                            long long treq = WallLink::wallNowMs();
                            playItem(0, true);
                            long long tret = WallLink::wallNowMs();
                            wl->markPlayStarted(sWallTargetMs);
                            long long d = tret - sWallTargetMs;
                            sWallFireAdj = (d > 10 || d < -10) ? -(d / 2) : 0;   // 只修系统性偏，小抖动不参与
                            if (sWallFireAdj > 30) sWallFireAdj = 30;
                            if (sWallFireAdj < -30) sWallFireAdj = -30;
                            LOGD("wall: start target=%lld t_req=%lld t_ret=%lld delta=%lldms ovh=%lldms lead=%lldms adj=%lldms",
                                 sWallTargetMs, treq, tret, d, tret - treq, lead, sWallFireAdj);
                            sWallTargetMs += wl->segMs();      // 链式推进：下一段仍落在整边界
                            sWallLateRetried = false;
                        } else if (!sWallLateRetried && mVideoSsPtr != NULL &&
                                   !mVideoSsPtr->isPlaying() &&
                                   noww > sWallTargetMs - wl->segMs() + 3000 &&
                                   noww < sWallTargetMs - 3000) {
                            // 兜底：本段应播却没在播（起播失败/被系统打断）-> 迟起播一次保画面，
                            // 下个整边界自动归位（一周期只兜一次，避免与整边界机制对打）
                            LOGW("wall: no video mid-cycle -> late restart (grid re-aligns next boundary)");
                            sWallLateRetried = true;
                            playItem(0, true);
                        }
                    }
                    if ((sMediaTicks % 5) == 0) {
                        long long noww = WallLink::wallNowMs();
                        bool playing = (mVideoSsPtr != NULL) && mVideoSsPtr->isPlaying();
                        int pos = (mVideoSsPtr != NULL) ? mVideoSsPtr->getCurrentPosition() : -1;
                        int dur = (mVideoSsPtr != NULL) ? mVideoSsPtr->getDuration() : -1;
                        // 注：getCurrentPosition() 实测是 1s 量化、且与墙钟线性相关（不是精度源），
                        //     仅作辅助记录；主判据看 wall: start 的 delta（起播调用返回 - 整边界）。
                        LOGD("wall: phase=%lldms wait=%lldms drift=%dms pos=%d dur=%dms playing=%d state=%s",
                             wl->phaseMs(), wl->waitToBoundaryMs(), wl->driftMs(),
                             pos, dur, playing ? 1 : 0, wl->stateText().c_str());
                    }
                } else {
                    if (wallEngine() == WALL_ENGINE_SIMPLE) wallSimpleStop("not-ready");
                    sWallPending = true;      // 未就绪（等 epoch/失联）-> 保持等待
                    sWallTargetMs = 0;        // 解除定标；恢复就绪后重新落到整边界
                }
            } else {
                if (wallEngine() == WALL_ENGINE_SIMPLE) wallSimpleStop("wall-off");
                sWallPending = false;
                sWallTargetMs = 0;
            }
        }
        sIdleTicks++;                          // 空闲秒数（触摸/onUI_show 归零）
        // 素材变化检测：上传/删除后 5s 内自动重建清单（钟工 2026-09-25）
        sListCheckTicks++;
        if (sListCheckTicks >= 5) {
            sListCheckTicks = 0;
            refreshListIfChanged(false);
        }
        tickScreenOff();                       // 关屏时段内空闲 15s -> 黑屏
        if (ConfigStore::getInstance()->ssEditMode() || sScreenOff) break;
        // 播放流程自控：(1)有间隔且到点 -> 切；(2)连续模式按时长兜底（完成消息不可靠时也轮播）
        int iv = videoIntervalSec();
        if (!sVideos.empty()) sMediaTicks++;      // 素材显示秒数（心跳计数，不依赖墙钟）
        if (sVideos.size() > 1 && sMediaTicks > 0) {
            int el = sMediaTicks;
            if (isImagePath(sVideos[sVideoIdx])) {
                int ph = ConfigStore::getInstance()->photoIntervalSec();   // 图片时长可配（钟工 2026-09-25）
                if (el >= ph) playItem(sVideoIdx + 1, true);
            } else if (iv > 0) {
                if (el >= iv) playItem(sVideoIdx + 1, true);
            } else {
                int dur = (mVideoSsPtr != NULL) ? mVideoSsPtr->getDuration() : 0;
                if (dur > 0 && el >= dur / 1000 + 1) playItem(sVideoIdx + 1, true);
                else if (dur <= 0 && el >= 60) playItem(sVideoIdx + 1, true);   // 取不到时长 -> 60s 兜底
            }
        }
        break; }
    default:
        break;
    }
    return true;
}
// 屏保：编辑模式 = 拖动/点空白退出；否则触摸任意处唤屏 + 进主页
static bool onmainActivityTouchEvent(const MotionEvent &ev) {
    ConfigStore* cfg = ConfigStore::getInstance();

    if (cfg->ssEditMode()) {
        int hit = ssHitTest(ev.mX, ev.mY);
        switch (ev.mActionStatus) {
        case MotionEvent::E_ACTION_DOWN:
            sDragIdx = hit;
            sDownX = ev.mX;
            sDownY = ev.mY;
            sDragMoved = false;
            if (hit >= 0) {
                sDragBaseX = sGroups[hit].dx;
                sDragBaseY = sGroups[hit].dy;
            }
            sIdleTicks = 0;                                  // 编辑中触摸 = 活动
            EASYUICONTEXT->resetScreensaverTimeOut();
            return true;
        case MotionEvent::E_ACTION_MOVE:
            sIdleTicks = 0;                                  // 拖动同理，不被屏保打断
            EASYUICONTEXT->resetScreensaverTimeOut();
            if (sDragIdx >= 0) {
                int ndx = ssClampX(sDragIdx, sDragBaseX + (ev.mX - sDownX));
                int ndy = ssClampY(sDragIdx, sDragBaseY + (ev.mY - sDownY));
                if (ndx != sGroups[sDragIdx].dx || ndy != sGroups[sDragIdx].dy) {
                    sGroups[sDragIdx].dx = ndx;
                    sGroups[sDragIdx].dy = ndy;
                    ssApplyGroup(sDragIdx);
                    sDragMoved = true;
                }
            }
            return true;
        case MotionEvent::E_ACTION_UP:
        case MotionEvent::E_ACTION_CANCEL:
            if (sDragIdx >= 0 && sDragMoved) {
                ssSaveGroupPos(sDragIdx);        // 松手即存 /data
                LOGD("ss drag save %s -> (%d,%d)", sGroups[sDragIdx].key,
                     sGroups[sDragIdx].dl + sGroups[sDragIdx].dx,
                     sGroups[sDragIdx].dt + sGroups[sDragIdx].dy);
            } else if (sDragIdx < 0) {
                ssEnterEdit(false);              // 点空白退出编辑模式
                playItem(sVideoIdx);
            }
            sDragIdx = -1;
            sDragMoved = false;
            return true;
        default:
            break;
        }
        return true;
    }

    if (ev.mActionStatus == MotionEvent::E_ACTION_DOWN) {
        sLastTouchMs = nowMs();
        sIdleTicks = 0;
        EASYUICONTEXT->resetScreensaverTimeOut();
        if (sScreenOff) {
            leaveScreenOff();                    // 熄屏状态点击 -> 立即解除熄屏
            return true;
        }
        LOGD("screensaver touch -> homeActivity");
        EASYUICONTEXT->openActivity("homeActivity");
        return true;      // 首触只做「解除屏保 + 进主页」，不再下发（钟工报告 1：避免直接触达继电器）
    }
    return false;
}

// 「完成」按钮：保存并退出编辑模式
static bool onButtonClick_ButtonSsEditDone(ZKButton *pButton) {
    (void)pButton;
    ssEnterEdit(false);
    sLastTouchMs = nowMs();
    if (sVideos.empty()) loadVideoList();
    playItem(sVideoIdx);
    return true;
}
