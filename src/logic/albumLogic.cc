#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * albumLogic.cc -- 相册上传子页（album.ftu）v2（钟工 2026-09-25 12:29/12:33 定稿）
 *
 * 页面构成：
 *   状态卡：大号相册图标 + 「相册模式已开启/已关闭」+ 副行状态 + 呼吸灯（空闲）/ 帧动画（接收中）
 *   二维码区：160x160 白卡 + qrcode 控件（扫码传图，运行时 loadQRCode(本机上传地址)）
 *   上传内容：图片 JPG/PNG - N 个 / 视频 MP4 - N 个（绿徽标）
 *   混播说明 + 常规按钮「结束相册模式」/「重新开启相册模式」
 * 传输本体在 src/mp_transfer/（UDP 8899 广播 zkswe:<name> / TCP 9000），落盘 /mnt/sdnand/album/。
 */

#include "utils/Log.h"
#include "utils/TimeHelper.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "system/NetKeeper.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"
#include "control/ZKQrcode.h"

#include <http/downloader.h>
#include <sys/stat.h>

#include "mp_transfer/mp_config.h"
#include "mp_transfer/runtime_coordinator.h"
#include "mp_transfer/tcp_receive.h"
#include "system/transfer_type_and_data.h"

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <dirent.h>
#include <ctype.h>
#include <string>
#include <vector>

static const char* kOwner = "albumActivity";
#define KEY_ALBUM_MODE "sp_album_mode"      // 1=相册模式开启（默认）0=已结束

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},     // 状态/计数刷新
    {1, 120},      // 帧动画 + 呼吸灯
};

// ── 接收模式帧动画（8 帧旋转弧；路径用字面量表，check_all 会扫代码里的图片引用）──
static const char* kAlAnim[8] = {
    "images/al_anim_0.png", "images/al_anim_1.png", "images/al_anim_2.png", "images/al_anim_3.png",
    "images/al_anim_4.png", "images/al_anim_5.png", "images/al_anim_6.png", "images/al_anim_7.png",
};
#define AL_ANIM_FRAMES 8
static int sAnimFrame = 0;
static int sPulseStep = 0;

static bool modeEnabled() {
    return StoragePreferences::getInt(KEY_ALBUM_MODE, 1) != 0;
}

static void setModeEnabled(bool on) {
    StoragePreferences::putInt(KEY_ALBUM_MODE, on ? 1 : 0);
}

static std::string deviceName() {
    // 广播名：优先用 /data 里的设备名称（设备名称子页可改），没有就取默认
    return StoragePreferences::getString("sp_dev_name", MP_DEVICE_NAME);
}

// 相册目录里按类型计数（图片 / 视频）
// 注：设备上**没有 wc**（busybox 裁剪）-> 不能用 `ls | wc -l`，改用 opendir/readdir 直接数
static bool extIn(const char* name, const char* const* exts, size_t n) {
    const char* dot = strrchr(name, '.');
    if (dot == NULL) return false;
    for (size_t i = 0; i < n; i++) {
        size_t l = strlen(exts[i]);
        size_t d = strlen(dot);
        if (d == l) {
            bool same = true;
            for (size_t k = 0; k < l; k++) {
                char a = (char)tolower((unsigned char)dot[k]);
                char b = (char)tolower((unsigned char)exts[i][k]);
                if (a != b) { same = false; break; }
            }
            if (same) return true;
        }
    }
    return false;
}

static void countAlbum(int& nImg, int& nVid) {
    nImg = nVid = 0;
    static const char* kImg[] = { ".jpg", ".jpeg", ".png", ".bmp" };
    static const char* kVid[] = { ".mp4", ".avi", ".mkv", ".mov" };
    DIR* d = opendir("/mnt/sdnand/album");
    if (d == NULL) return;
    struct dirent* e = NULL;
    while ((e = readdir(d)) != NULL) {
        if (e->d_name[0] == '.') continue;
        if (extIn(e->d_name, kImg, sizeof(kImg) / sizeof(kImg[0]))) nImg++;
        else if (extIn(e->d_name, kVid, sizeof(kVid) / sizeof(kVid[0]))) nVid++;
    }
    closedir(d);
}

// 二维码内容（钟工 2026-09-29 改：**相册页二维码 = 微信小程序传图入口**；
//             2026-09-30 再改：**不再铺位图素材，改用二维码控件现场生成**）：
//   (1) sp_qr_img_url 非空 -> 下载**远端小程序码图**（微信原生小程序码只能这么显示，控件编不出来）
//   (2) 否则 -> ZKQrcode 控件按 sp_qr_url 现场生成
//         默认内容 = 「扫普通链接二维码打开小程序」链接（把原素材 images/album_qr_mp128.png
//         解出来的，见 ConfigStore.cpp kQrUrlDefault）—— 模块像素对齐，比 128px 位图锐利
//   (3) sp_qr_url 被部署方清空 -> 回退本机上传地址 http://<ip>:9000/upload（联调保底）
static const char* kQrLocalFile = "/mnt/sdnand/qr_code.png";
static volatile bool sQrDownloaded = false;     // 下载完成待应用（定时器里落 UI）
static std::string sQrShown;                    // 已生成的二维码内容（变了才重算，QR 重算很贵）

static void requestQrImage(const std::string& url) {
    http::Downloader::Task t;
    t.source = url;
    t.target = kQrLocalFile;
    t.retry_max = 2;
    t.result = [](const http::Downloader::Task& task, bool success) {
        (void)task;
        LOGD("album: qr image download %s", success ? "OK" : "FAIL");
        if (success) sQrDownloaded = true;
    };
    http::Downloader::instance().add(t);
    LOGD("album: qr image request %s", url.c_str());
}

static bool fileExists(const char* p) {
    struct stat st;
    return stat(p, &st) == 0 && st.st_size > 0;
}

static void refreshQrcode() {
    std::string imgUrl = ConfigStore::getInstance()->qrImageUrl();
    if (!imgUrl.empty()) {
        if (!fileExists(kQrLocalFile)) requestQrImage(imgUrl);   // 没图才拉（成功后置位，定时器回落）
        if (fileExists(kQrLocalFile)) {
            if (mQrcodeAlPtr != NULL) mQrcodeAlPtr->setVisible(false);
            if (mImageAlQrRemotePtr != NULL) {
                mImageAlQrRemotePtr->setBackgroundPic(kQrLocalFile);
                mImageAlQrRemotePtr->setVisible(true);
            }
            LOGD("album: qr = remote image (%s)", kQrLocalFile);
            return;
        }
    }
    // (2) 二维码控件现场生成（默认内容 = 小程序传图链接）
    if (mImageAlQrRemotePtr != NULL) mImageAlQrRemotePtr->setVisible(false);
    std::string url = ConfigStore::getInstance()->qrUrl();
    if (url.empty()) {
        std::string ip = NetKeeper_localIp();
        if (ip.empty()) ip = "0.0.0.0";
        char buf[128];
        snprintf(buf, sizeof(buf), "http://%s:9000/upload", ip.c_str());
        url = buf;
        LOGW("album: qr url empty -> local upload fallback %s", url.c_str());
    }
    if (mQrcodeAlPtr != NULL) {
        mQrcodeAlPtr->setVisible(true);
        if (url != sQrShown) {
            mQrcodeAlPtr->loadQRCode(url.c_str());
            sQrShown = url;
        }
    }
    LOGD("album: qrcode -> %s", url.c_str());
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextAlTitlePtr, mTextAlTitleEnPtr,
        mImageAlModeBgPtr, mImageAlModeIconBgPtr, mImageAlModeIconPtr,
        mTextAlModeTitlePtr, mTextAlModeSubPtr, mImageAlAnimPtr, mImageAlPulsePtr,
        mImageAlQrCardPtr, mTextAlQrCapPtr, mTextAlQrHintPtr, mImageAlQrRemotePtr,
        mImageAlCntBgPtr, mTextAlImgLabelPtr, mImageAlImgBadgePtr, mTextAlImgCountPtr,
        mTextAlVidLabelPtr, mImageAlVidBadgePtr, mTextAlVidCountPtr,
        mTextAlMixHintPtr, mImageAlEndBgPtr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

static void refreshUi() {
    bool enabled = modeEnabled();
    bool connected = enabled && TcpReceiveTask::instance().isClientConnected();

    if (mTextAlModeTitlePtr != NULL) {
        mTextAlModeTitlePtr->setText(enabled ? "相册模式已开启" : "相册模式已关闭");
        mTextAlModeTitlePtr->setTextColor(enabled ? 0xECECF0 : 0x5F5F68);
    }
    if (mTextAlModeSubPtr != NULL) {
        if (!enabled) {
            mTextAlModeSubPtr->setText("点下方按钮可重新开启");
            mTextAlModeSubPtr->setTextColor(0x5F5F68);
        } else if (connected) {
            mTextAlModeSubPtr->setText("手机已连接，正在接收素材 - 请勿离开本页");
            mTextAlModeSubPtr->setTextColor(0x7BE0A3);
        } else {
            mTextAlModeSubPtr->setText("等待手机 APP 上传 - 同一局域网自动发现");
            mTextAlModeSubPtr->setTextColor(0x9A9AA2);
        }
    }
    // 空闲 = 呼吸灯脉冲；接收中 = 帧动画（两者共用同一格）
    if (mImageAlAnimPtr != NULL) mImageAlAnimPtr->setVisible(connected);
    if (mImageAlPulsePtr != NULL) mImageAlPulsePtr->setVisible(enabled && !connected);

    int nImg = 0, nVid = 0;
    countAlbum(nImg, nVid);
    char b[32];
    if (mTextAlImgCountPtr != NULL) {
        snprintf(b, sizeof(b), "%d 个", nImg);
        mTextAlImgCountPtr->setText(b);
    }
    if (mTextAlVidCountPtr != NULL) {
        snprintf(b, sizeof(b), "%d 个", nVid);
        mTextAlVidCountPtr->setText(b);
    }
    if (mButtonAlEndPtr != NULL) {
        mButtonAlEndPtr->setText(enabled ? "结束相册模式" : "重新开启相册模式");
    }
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    passDecorations();
    if (modeEnabled()) MpTransferRuntimeCoordinator::instance().retain(kOwner, deviceName());
    TcpReceiveTask::instance().refreshCache();
    refreshQrcode();
    refreshUi();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    if (modeEnabled()) MpTransferRuntimeCoordinator::instance().retain(kOwner, deviceName());
    TcpReceiveTask::instance().refreshCache();
    refreshQrcode();
    refreshUi();
}

static void onUI_hide() {
    // 离开页面就停传输（省电；小程序侧会显示设备不可见）
    MpTransferRuntimeCoordinator::instance().release(kOwner);
}

static void onUI_quit() {
    sQrShown.clear();   // 同上：控件随页面销毁置 NULL，缓存必须一起清，否则再进页二维码空白
    MpTransferRuntimeCoordinator::instance().release(kOwner);
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) {
    if (id == 0) {
        if (sQrDownloaded) {          // 远端小程序码图下载完成 -> 落 UI
            sQrDownloaded = false;
            refreshQrcode();
        }
        refreshUi();
    } else if (id == 1) {
        // 帧动画：每 120ms 下一帧
        if (mImageAlAnimPtr != NULL && mImageAlAnimPtr->isVisible()) {
            mImageAlAnimPtr->setBackgroundPic(kAlAnim[sAnimFrame]);
            sAnimFrame = (sAnimFrame + 1) % AL_ANIM_FRAMES;
        }
        // 呼吸灯：alpha 在 60..255 间来回（每 120ms 一档，约 12 档一个来回）
        if (mImageAlPulsePtr != NULL && mImageAlPulsePtr->isVisible()) {
            static const int kPulse[12] = { 60, 90, 125, 165, 200, 235, 255, 235, 200, 165, 125, 90 };
            mImageAlPulsePtr->setAlpha((uint8_t)kPulse[sPulseStep % 12]);
            sPulseStep++;
        }
    }
    return true;
}

static bool onalbumActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonAlBack(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->goBack();
    return true;
}

// 文件管理：3x3 缩略图 + 勾选/全选删除（albumfileLogic.cc）
static bool onButtonClick_ButtonAlFiles(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->openActivity("albumfileActivity");
    return true;
}

// 结束 / 重新开启相册模式（状态、呼吸灯、设置主页行值同步切换）
// 钟工 2026-09-25（问题单第 5 条）：结束相册模式 = 结束并**返回上一页**（否则“退不出去”）
static bool onButtonClick_ButtonAlEnd(ZKButton *pButton) {
    (void)pButton;
    if (modeEnabled()) {
        setModeEnabled(false);
        MpTransferRuntimeCoordinator::instance().release(kOwner);
        LOGD("album: mode OFF (broadcast/tcp stopped) -> goBack");
        refreshUi();
        EASYUICONTEXT->goBack();
        return true;
    }
    setModeEnabled(true);
    MpTransferRuntimeCoordinator::instance().retain(kOwner, deviceName());
    LOGD("album: mode ON (broadcast/tcp started)");
    refreshUi();
    return true;
}
