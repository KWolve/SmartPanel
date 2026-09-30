#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * videoLogic.cc - 屏保视频子页（video.ftu）
 *
 * 素材 = 数据分区里的 **mp4 + 相册上传的图片**（/mnt/sdnand/video 优先，再 /mnt/sdnand/album，
 * 退 /mnt/extsd/video、/mnt/usb1/video）；图片也进列表（混播，设计说明书 3.4.5：图片每张 15 秒）。
 * 选中清单 + 轮播间隔**存 /data**（StoragePreferences，钟工 2026-09-24 口径）：
 *   sp_video_sel = 选中的绝对路径，'\n' 分隔（空 = 全选）
 *   sp_video_int = 轮播间隔秒（0=连续）
 * 屏保页（main.ftu）按同一份配置轮播。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/ConfigStore.h"
#include "storage/StoragePreferences.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"

#include <stdio.h>
#include <ctype.h>
#include <string>
#include <vector>

#define KEY_VIDEO_SEL "sp_video_sel"
#define KEY_VIDEO_INT "sp_video_int"
#define MAX_ROWS      12

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

static const int kIntervalSec[6] = { 0, 3600, 7200, 21600, 43200, 86400 };

static std::vector<std::string> sFiles;
static std::vector<std::string> sSel;      // 选中路径（空 = 全选）
static int sInterval = 0;

static ZKButton* rowBtn(int i) {
    ZKButton* a[MAX_ROWS] = { mButtonVidRow1Ptr, mButtonVidRow2Ptr, mButtonVidRow3Ptr, mButtonVidRow4Ptr,
                              mButtonVidRow5Ptr, mButtonVidRow6Ptr, mButtonVidRow7Ptr, mButtonVidRow8Ptr,
                              mButtonVidRow9Ptr, mButtonVidRow10Ptr, mButtonVidRow11Ptr, mButtonVidRow12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}
static ZKTextView* rowName(int i) {
    ZKTextView* a[MAX_ROWS] = { mTextVidRowName1Ptr, mTextVidRowName2Ptr, mTextVidRowName3Ptr, mTextVidRowName4Ptr,
                                mTextVidRowName5Ptr, mTextVidRowName6Ptr, mTextVidRowName7Ptr, mTextVidRowName8Ptr,
                                mTextVidRowName9Ptr, mTextVidRowName10Ptr, mTextVidRowName11Ptr, mTextVidRowName12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}
static ZKTextView* rowChk(int i) {
    ZKTextView* a[MAX_ROWS] = { mImageVidRowChk1Ptr, mImageVidRowChk2Ptr, mImageVidRowChk3Ptr, mImageVidRowChk4Ptr,
                                mImageVidRowChk5Ptr, mImageVidRowChk6Ptr, mImageVidRowChk7Ptr, mImageVidRowChk8Ptr,
                                mImageVidRowChk9Ptr, mImageVidRowChk10Ptr, mImageVidRowChk11Ptr, mImageVidRowChk12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}
static ZKTextView* rowBg(int i) {
    ZKTextView* a[MAX_ROWS] = { mImageVidRowBg1Ptr, mImageVidRowBg2Ptr, mImageVidRowBg3Ptr, mImageVidRowBg4Ptr,
                                mImageVidRowBg5Ptr, mImageVidRowBg6Ptr, mImageVidRowBg7Ptr, mImageVidRowBg8Ptr,
                                mImageVidRowBg9Ptr, mImageVidRowBg10Ptr, mImageVidRowBg11Ptr, mImageVidRowBg12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}

// 行编号（01..12）与「视/图」徐标（设计说明书 3.4.5：图片 = 绿底）
static ZKTextView* rowIdx(int i) {
    ZKTextView* a[MAX_ROWS] = { mTextVidRowIdx1Ptr, mTextVidRowIdx2Ptr, mTextVidRowIdx3Ptr,
                                mTextVidRowIdx4Ptr, mTextVidRowIdx5Ptr, mTextVidRowIdx6Ptr,
                                mTextVidRowIdx7Ptr, mTextVidRowIdx8Ptr, mTextVidRowIdx9Ptr,
                                mTextVidRowIdx10Ptr, mTextVidRowIdx11Ptr, mTextVidRowIdx12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}
static ZKTextView* rowBadge(int i) {
    ZKTextView* a[MAX_ROWS] = { mImageVidRowBadge1Ptr, mImageVidRowBadge2Ptr, mImageVidRowBadge3Ptr,
                                mImageVidRowBadge4Ptr, mImageVidRowBadge5Ptr, mImageVidRowBadge6Ptr,
                                mImageVidRowBadge7Ptr, mImageVidRowBadge8Ptr, mImageVidRowBadge9Ptr,
                                mImageVidRowBadge10Ptr, mImageVidRowBadge11Ptr, mImageVidRowBadge12Ptr };
    return (i >= 0 && i < MAX_ROWS) ? a[i] : NULL;
}

// 图片素材（与 mainLogic 的 isImagePath 同一套扩展名）
static bool isImageFile(const std::string& p) {
    size_t dot = p.find_last_of('.');
    if (dot == std::string::npos) return false;
    std::string e = p.substr(dot);
    for (size_t i = 0; i < e.size(); i++) e[i] = (char)tolower((unsigned char)e[i]);
    return e == ".jpg" || e == ".jpeg" || e == ".png" || e == ".bmp" || e == ".gif";
}
static ZKTextView* intBg(int i) {
    ZKTextView* a[6] = { mImageVidIntBg1Ptr, mImageVidIntBg2Ptr, mImageVidIntBg3Ptr,
                         mImageVidIntBg4Ptr, mImageVidIntBg5Ptr, mImageVidIntBg6Ptr };
    return (i >= 0 && i < 6) ? a[i] : NULL;
}
static ZKTextView* intText(int i) {
    ZKTextView* a[6] = { mTextVidInt1Ptr, mTextVidInt2Ptr, mTextVidInt3Ptr,
                         mTextVidInt4Ptr, mTextVidInt5Ptr, mTextVidInt6Ptr };
    return (i >= 0 && i < 6) ? a[i] : NULL;
}

// 图片显示时长 chips（钟工 2026-09-25：可配，5s/10s/15s/30s/60s）
static const int kPhotoSec[5] = { 5, 10, 15, 30, 60 };
static int sPhotoSec = 15;

static ZKTextView* photoBg(int i) {
    ZKTextView* a[5] = { mImagePhotoDurBg1Ptr, mImagePhotoDurBg2Ptr, mImagePhotoDurBg3Ptr,
                         mImagePhotoDurBg4Ptr, mImagePhotoDurBg5Ptr };
    return (i >= 0 && i < 5) ? a[i] : NULL;
}
static ZKTextView* photoText(int i) {
    ZKTextView* a[5] = { mTextPhotoDur1Ptr, mTextPhotoDur2Ptr, mTextPhotoDur3Ptr,
                         mTextPhotoDur4Ptr, mTextPhotoDur5Ptr };
    return (i >= 0 && i < 5) ? a[i] : NULL;
}

static void scanVideos() {
    sFiles.clear();
    const char* dirs[] = { "/mnt/sdnand/video", "/mnt/sdnand/album", "/mnt/extsd/video", "/mnt/usb1/video" };
    const char* pats[] = { "*.mp4", "*.avi", "*.mkv", "*.mov",
                           "*.jpg", "*.jpeg", "*.png", "*.bmp" };
    for (size_t d = 0; d < sizeof(dirs) / sizeof(dirs[0]); d++) {
        for (size_t q = 0; q < sizeof(pats) / sizeof(pats[0]); q++) {
            std::string cmd = std::string("ls ") + dirs[d] + "/" + pats[q] + " 2>/dev/null";
            FILE* fp = popen(cmd.c_str(), "r");
            if (fp == NULL) continue;
            char line[512];
            while (fgets(line, sizeof(line), fp) && sFiles.size() < MAX_ROWS) {
                std::string p = line;
                while (!p.empty() && (p.back() == '\n' || p.back() == '\r')) p.pop_back();
                if (!p.empty()) sFiles.push_back(p);
            }
            pclose(fp);
        }
    }
    LOGD("videoLogic: found %d files", (int)sFiles.size());
}

static void loadConfig() {
    sSel.clear();
    std::string all = StoragePreferences::getString(KEY_VIDEO_SEL, "");
    size_t pos = 0;
    while (pos < all.size()) {
        size_t nl = all.find('\n', pos);
        std::string one = all.substr(pos, nl == std::string::npos ? std::string::npos : nl - pos);
        if (!one.empty()) sSel.push_back(one);
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    sInterval = StoragePreferences::getInt(KEY_VIDEO_INT, 0);
    sPhotoSec = ConfigStore::getInstance()->photoIntervalSec();   // 钟工：图片时长可配（默认 15s）
}

static bool isSelected(int i) {
    if (i < 0 || i >= (int)sFiles.size()) return false;
    if (sSel.empty()) return true;                 // 空 = 全选
    for (size_t k = 0; k < sSel.size(); k++) {
        if (sSel[k] == sFiles[i]) return true;
    }
    return false;
}

static void saveConfig() {
    std::string all;
    for (size_t k = 0; k < sSel.size(); k++) {
        all += sSel[k];
        all += '\n';
    }
    StoragePreferences::putString(KEY_VIDEO_SEL, all);
    LOGD("videoLogic: saved %d selected", (int)sSel.size());
}

static void refreshRows() {
    for (int i = 0; i < MAX_ROWS; i++) {
        ZKButton* b = rowBtn(i);
        ZKTextView* n = rowName(i);
        ZKTextView* c = rowChk(i);
        ZKTextView* g = rowBg(i);
        bool has = i < (int)sFiles.size();
        if (b != NULL) b->setVisible(has);
        if (g != NULL) g->setVisible(has);      // 空行连同底条一起藏：列表只显示实际条目
        if (n != NULL) {
            n->setVisible(has);
            if (has) {
                size_t slash = sFiles[i].find_last_of('/');
                n->setText((slash == std::string::npos ? sFiles[i] : sFiles[i].substr(slash + 1)).c_str());
                n->setTextColor(isSelected(i) ? 0x7BE0A3 : 0xECECF0);
            }
        }
        if (c != NULL) c->setVisible(has && isSelected(i));

        // 编号 + 徐标（图片 = 绿底深字 / 视频 = 灰底浅字）
        ZKTextView* ix = rowIdx(i);
        ZKTextView* bd = rowBadge(i);
        if (ix != NULL) {
            ix->setVisible(has);
            if (has) {
                char b[8];
                snprintf(b, sizeof(b), "%02d", i + 1);
                ix->setText(b);
            }
        }
        if (bd != NULL) {
            bd->setVisible(has);
            if (has) {
                // 图标版（钟工 2026-09-25 11:55）：视频=广播三角、图片=照片图标，不写字
                bool img = isImageFile(sFiles[i]);
                bd->setBackgroundPic(img ? "images/badge_image.png" : "images/badge_video.png");
                bd->setText("");
            }
        }
    }
}

static void refreshInterval() {
    for (int i = 0; i < 6; i++) {
        bool on = (kIntervalSec[i] == sInterval);
        ZKTextView* bg = intBg(i);
        ZKTextView* tx = intText(i);
        if (bg != NULL) bg->setBackgroundPic(on ? "images/chip68x44_hl.png" : "images/chip68x44.png");
        if (tx != NULL) tx->setTextColor(on ? 0x10141A : 0xECECF0);
    }
}

// 图片显示时长 chip 高亮（选中 = 绿底深字）
static void refreshPhotoDur() {
    for (int i = 0; i < 5; i++) {
        bool on = (kPhotoSec[i] == sPhotoSec);
        ZKTextView* bg = photoBg(i);
        ZKTextView* tx = photoText(i);
        if (bg != NULL) bg->setBackgroundPic(on ? "images/chip68x44_hl.png" : "images/chip68x44.png");
        if (tx != NULL) tx->setTextColor(on ? 0x10141A : 0xECECF0);
    }
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextVidTitlePtr, mTextVidTitleEnPtr, mTextVidListHintPtr, mTextVidIntLabelPtr,
        mImageVidRowBg1Ptr, mImageVidRowBg2Ptr, mImageVidRowBg3Ptr, mImageVidRowBg4Ptr,
        mImageVidRowBg5Ptr, mImageVidRowBg6Ptr, mImageVidRowBg7Ptr, mImageVidRowBg8Ptr,
        mImageVidRowBg9Ptr, mImageVidRowBg10Ptr, mImageVidRowBg11Ptr, mImageVidRowBg12Ptr,
        mTextVidRowName1Ptr, mTextVidRowName2Ptr, mTextVidRowName3Ptr, mTextVidRowName4Ptr,
        mTextVidRowName5Ptr, mTextVidRowName6Ptr, mTextVidRowName7Ptr, mTextVidRowName8Ptr,
        mTextVidRowName9Ptr, mTextVidRowName10Ptr, mTextVidRowName11Ptr, mTextVidRowName12Ptr,
        mImageVidRowChk1Ptr, mImageVidRowChk2Ptr, mImageVidRowChk3Ptr, mImageVidRowChk4Ptr,
        mImageVidRowChk5Ptr, mImageVidRowChk6Ptr, mImageVidRowChk7Ptr, mImageVidRowChk8Ptr,
        mImageVidRowChk9Ptr, mImageVidRowChk10Ptr, mImageVidRowChk11Ptr, mImageVidRowChk12Ptr,
        mImageVidIntBg1Ptr, mImageVidIntBg2Ptr, mImageVidIntBg3Ptr,
        mImageVidIntBg4Ptr, mImageVidIntBg5Ptr, mImageVidIntBg6Ptr,
        mTextVidInt1Ptr, mTextVidInt2Ptr, mTextVidInt3Ptr,
        mTextVidInt4Ptr, mTextVidInt5Ptr, mTextVidInt6Ptr, mTextPhotoDurLabelPtr,
        mImagePhotoDurBg1Ptr, mImagePhotoDurBg2Ptr, mImagePhotoDurBg3Ptr,
        mImagePhotoDurBg4Ptr, mImagePhotoDurBg5Ptr,
        mTextPhotoDur1Ptr, mTextPhotoDur2Ptr, mTextPhotoDur3Ptr,
        mTextPhotoDur4Ptr, mTextPhotoDur5Ptr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    passDecorations();
    loadConfig();
    scanVideos();
    refreshRows();
    refreshInterval();
    refreshPhotoDur();
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    loadConfig();
    scanVideos();
    refreshRows();
    refreshInterval();
    refreshPhotoDur();
}

static void onUI_hide() {
}

static void onUI_quit() {
}

static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }

static bool onUI_Timer(int id) { (void)id; return true; }

static bool onvideoActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────
static bool onButtonClick_ButtonVidBack(ZKButton *pButton) {
    (void)pButton;
    EASYUICONTEXT->goBack();
    return true;
}

static void toggleRow(int i) {
    if (i < 0 || i >= (int)sFiles.size()) return;
    if (sSel.empty()) {                    // 首次点击：把全选展开成显式清单
        for (size_t k = 0; k < sFiles.size(); k++) sSel.push_back(sFiles[k]);
    }
    for (size_t k = 0; k < sSel.size(); k++) {
        if (sSel[k] == sFiles[i]) {
            sSel.erase(sSel.begin() + k);
            saveConfig();
            refreshRows();
            return;
        }
    }
    sSel.push_back(sFiles[i]);
    saveConfig();
    refreshRows();
}

static bool onButtonClick_ButtonVidRow1(ZKButton *p) { (void)p; toggleRow(0); return true; }
static bool onButtonClick_ButtonVidRow2(ZKButton *p) { (void)p; toggleRow(1); return true; }
static bool onButtonClick_ButtonVidRow3(ZKButton *p) { (void)p; toggleRow(2); return true; }
static bool onButtonClick_ButtonVidRow4(ZKButton *p) { (void)p; toggleRow(3); return true; }
static bool onButtonClick_ButtonVidRow5(ZKButton *p) { (void)p; toggleRow(4); return true; }
static bool onButtonClick_ButtonVidRow6(ZKButton *p) { (void)p; toggleRow(5); return true; }
static bool onButtonClick_ButtonVidRow7(ZKButton *p) { (void)p; toggleRow(6); return true; }
static bool onButtonClick_ButtonVidRow8(ZKButton *p) { (void)p; toggleRow(7); return true; }
static bool onButtonClick_ButtonVidRow9(ZKButton *p) { (void)p; toggleRow(8); return true; }
static bool onButtonClick_ButtonVidRow10(ZKButton *p) { (void)p; toggleRow(9); return true; }
static bool onButtonClick_ButtonVidRow11(ZKButton *p) { (void)p; toggleRow(10); return true; }
static bool onButtonClick_ButtonVidRow12(ZKButton *p) { (void)p; toggleRow(11); return true; }

static bool onButtonClick_ButtonVidIntN(int idx) {
    if (idx < 0 || idx > 5) return true;
    sInterval = kIntervalSec[idx];
    StoragePreferences::putInt(KEY_VIDEO_INT, sInterval);
    refreshInterval();
    return true;
}
static bool onButtonClick_ButtonVidInt1(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(0); }
static bool onButtonClick_ButtonVidInt2(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(1); }
static bool onButtonClick_ButtonVidInt3(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(2); }
static bool onButtonClick_ButtonVidInt4(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(3); }
static bool onButtonClick_ButtonVidInt5(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(4); }
static bool onButtonClick_ButtonVidInt6(ZKButton *p) { (void)p; return onButtonClick_ButtonVidIntN(5); }

// 图片显示时长（钟工 2026-09-25：可配）
static bool onButtonClick_ButtonPhotoDurN(int idx) {
    if (idx < 0 || idx > 4) return true;
    sPhotoSec = kPhotoSec[idx];
    ConfigStore::getInstance()->setPhotoIntervalSec(sPhotoSec);
    LOGD("videoLogic: photo duration -> %d s", sPhotoSec);
    refreshPhotoDur();
    return true;
}
static bool onButtonClick_ButtonPhotoDur1(ZKButton *p) { (void)p; return onButtonClick_ButtonPhotoDurN(0); }
static bool onButtonClick_ButtonPhotoDur2(ZKButton *p) { (void)p; return onButtonClick_ButtonPhotoDurN(1); }
static bool onButtonClick_ButtonPhotoDur3(ZKButton *p) { (void)p; return onButtonClick_ButtonPhotoDurN(2); }
static bool onButtonClick_ButtonPhotoDur4(ZKButton *p) { (void)p; return onButtonClick_ButtonPhotoDurN(3); }
static bool onButtonClick_ButtonPhotoDur5(ZKButton *p) { (void)p; return onButtonClick_ButtonPhotoDurN(4); }
