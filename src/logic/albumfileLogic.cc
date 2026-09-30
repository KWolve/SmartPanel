/*
 * albumfileLogic.cc -- 「相册文件管理」页（albumfile.ftu）
 * 钟工 2026-09-25 需求：相册上传增加文件管理页 —— 3x3 缩略图、图片/视频区分、
 * 可全选或勾选其中一部分删除（删除二次确认；删除同步从屏保选中清单 sp_video_sel 移除）。
 *
 * 数据源：直接扫盘 /mnt/sdnand/album（小程序上传落盘目录，命名 小程序_YYMMDD_HHMMSS.ext）。
 * 缩略图：图片直接 setBackgroundPic(绝对路径)（与屏保铺图同机制）；视频显示占位框 + 视频徽标。
 */
#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD

/**
 * @brief 串口数据回调接口
 */
static void onProtocolDataUpdate(const SProtocolData &data) {
  LOGD_TRACE("");
}
#pragma once

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "storage/StoragePreferences.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"

#include <dirent.h>
#include <sys/stat.h>
#include <algorithm>
#include <ctype.h>
#include <stdio.h>
#include <string>
#include <vector>

#define AF_DIR      "/mnt/sdnand/album"
#define AF_PAGE     9
#define AF_KEY_SEL  "sp_video_sel"      // 与 videoLogic 同键：'\n' 分隔的绝对路径（空 = 全选）

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

struct AfItem {
    std::string name;
    std::string path;
    bool video;
    long long mtime;
};

static std::vector<AfItem> sItems;
static std::vector<char> sSel;      // 与 sItems 等长：1 = 勾选
static int sPage = 0;
static int sLastCount = -1;
static bool sDialogOpen = false;
// 开页防误触（钟工 2026-09-25 18:2x 实测：从相册页进入时，开启这一下触摸会落到新页的
// 「全选/删除」上 -> 误删整个目录）。用「心跳 tick 计数」而非墙钟（墙钟会校时跳变）。
static int sShowTicks = 0;
static bool afTooEarly() { return sShowTicks < 2; }   // 开页 ~2s 内：勾选/全选/删除均忽略

// ── 工具 ───────────────────────────────────────────────────────────
static bool afExtIn(const std::string& name, bool& video) {
    size_t dot = name.rfind('.');
    if (dot == std::string::npos) return false;
    std::string e;
    for (size_t i = dot; i < name.size(); i++) e += (char)tolower((unsigned char)name[i]);
    if (e == ".jpg" || e == ".jpeg" || e == ".png") { video = false; return true; }
    if (e == ".mp4" || e == ".mov" || e == ".m4v") { video = true; return true; }
    return false;
}

static void afScan() {
    sItems.clear();
    DIR* d = opendir(AF_DIR);
    if (d == NULL) {
        LOGE_TRACE("albumfile: opendir %s failed", AF_DIR);
        return;
    }
    struct dirent* ent = NULL;
    while ((ent = readdir(d)) != NULL) {
        std::string nm = ent->d_name;
        if (nm == "." || nm == ".." || nm[0] == '.') continue;
        bool video = false;
        if (!afExtIn(nm, video)) continue;
        AfItem it;
        it.name = nm;
        it.path = std::string(AF_DIR) + "/" + nm;
        it.video = video;
        struct stat st = {0};
        it.mtime = (stat(it.path.c_str(), &st) == 0) ? (long long)st.st_mtime : 0;
        sItems.push_back(it);
    }
    closedir(d);
    // 新的在前（mtime 降序；同秒按名降序，保证新上传的 小程序_ 在前）
    std::sort(sItems.begin(), sItems.end(), [](const AfItem& a, const AfItem& b) {
        if (a.mtime != b.mtime) return a.mtime > b.mtime;
        return a.name > b.name;
    });
    sSel.assign(sItems.size(), 0);
    LOGD("albumfile: scanned %d files", (int)sItems.size());
}

static int afPageCount() {
    int n = (int)sItems.size();
    return (n + AF_PAGE - 1) / AF_PAGE;
}

static void afClampPage() {
    int pc = afPageCount();
    if (pc < 1) pc = 1;
    if (sPage < 0) sPage = 0;
    if (sPage > pc - 1) sPage = pc - 1;
}

static int afSelCount() {
    int c = 0;
    for (size_t i = 0; i < sSel.size(); i++) if (sSel[i]) c++;
    return c;
}

static ZKTextView* afThumb(int i) {
    ZKTextView* a[AF_PAGE] = { mImageAfThumb1Ptr, mImageAfThumb2Ptr, mImageAfThumb3Ptr,
                              mImageAfThumb4Ptr, mImageAfThumb5Ptr, mImageAfThumb6Ptr,
                              mImageAfThumb7Ptr, mImageAfThumb8Ptr, mImageAfThumb9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}
static ZKTextView* afFrame(int i) {
    ZKTextView* a[AF_PAGE] = { mImageAfSelFrame1Ptr, mImageAfSelFrame2Ptr, mImageAfSelFrame3Ptr,
                              mImageAfSelFrame4Ptr, mImageAfSelFrame5Ptr, mImageAfSelFrame6Ptr,
                              mImageAfSelFrame7Ptr, mImageAfSelFrame8Ptr, mImageAfSelFrame9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}
static ZKTextView* afKind(int i) {
    ZKTextView* a[AF_PAGE] = { mImageAfKind1Ptr, mImageAfKind2Ptr, mImageAfKind3Ptr,
                              mImageAfKind4Ptr, mImageAfKind5Ptr, mImageAfKind6Ptr,
                              mImageAfKind7Ptr, mImageAfKind8Ptr, mImageAfKind9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}
static ZKTextView* afFilm(int i) {
    ZKTextView* a[AF_PAGE] = { mImageAfFilm1Ptr, mImageAfFilm2Ptr, mImageAfFilm3Ptr,
                              mImageAfFilm4Ptr, mImageAfFilm5Ptr, mImageAfFilm6Ptr,
                              mImageAfFilm7Ptr, mImageAfFilm8Ptr, mImageAfFilm9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}
static ZKTextView* afCheck(int i) {
    ZKTextView* a[AF_PAGE] = { mImageAfCheck1Ptr, mImageAfCheck2Ptr, mImageAfCheck3Ptr,
                              mImageAfCheck4Ptr, mImageAfCheck5Ptr, mImageAfCheck6Ptr,
                              mImageAfCheck7Ptr, mImageAfCheck8Ptr, mImageAfCheck9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}
static ZKButton* afCell(int i) {
    ZKButton* a[AF_PAGE] = { mButtonAfCell1Ptr, mButtonAfCell2Ptr, mButtonAfCell3Ptr,
                            mButtonAfCell4Ptr, mButtonAfCell5Ptr, mButtonAfCell6Ptr,
                            mButtonAfCell7Ptr, mButtonAfCell8Ptr, mButtonAfCell9Ptr };
    return (i >= 0 && i < AF_PAGE) ? a[i] : NULL;
}

// ── 刷新界面 ───────────────────────────────────────────────────────
static void afRefresh() {
    afClampPage();
    int n = (int)sItems.size();
    int sel = afSelCount();

    char b[128];
    snprintf(b, sizeof(b), "共 %d 个文件 - 已选 %d 个", n, sel);
    if (mTextAfStatPtr != NULL) mTextAfStatPtr->setText(b);
    snprintf(b, sizeof(b), "%d/%d", sPage + 1, afPageCount() < 1 ? 1 : afPageCount());
    if (mTextAfPagePtr != NULL) mTextAfPagePtr->setText(b);
    if (mTextAfEmptyPtr != NULL) mTextAfEmptyPtr->setVisible(n == 0);

    bool allSel = (n > 0 && sel == n);
    if (mButtonAfAllPtr != NULL) mButtonAfAllPtr->setText(allSel ? "取消全选" : "全选");
    if (mButtonAfDelPtr != NULL) {
        mButtonAfDelPtr->setText(sel > 0 ? "删除所选" : "删除");
        mButtonAfDelPtr->setBackgroundPic(sel > 0 ? "images/af_btn_dg140x44.png"
                                                  : "images/af_btn140x44.png");
    }

    for (int i = 0; i < AF_PAGE; i++) {
        int idx = sPage * AF_PAGE + i;
        bool has = (idx < n);
        ZKTextView* th = afThumb(i);
        ZKTextView* fr = afFrame(i);
        ZKTextView* kd = afKind(i);
        ZKTextView* ck = afCheck(i);
        ZKTextView* fl = afFilm(i);
        ZKButton* cell = afCell(i);
        if (cell != NULL) cell->setVisible(has);
        if (th != NULL) {
            th->setVisible(has);
            if (has) {
                // 图片用真缩略图（绝对路径，与屏保铺图同机制）；视频用占位框 + 视频徽标
                th->setBackgroundPic(sItems[idx].video ? "images/af_thumb140x88.png"
                                                       : sItems[idx].path.c_str());
            }
        }
        if (kd != NULL) {
            kd->setVisible(has);
            if (has) kd->setBackgroundPic(sItems[idx].video ? "images/badge_video.png"
                                                            : "images/badge_image.png");
        }
        if (fr != NULL) fr->setVisible(has && sSel[idx] != 0);
        // 视频格中显示胶片图标（图片不显示）
        if (fl != NULL) fl->setVisible(has && sItems[idx].video);
        if (ck != NULL) {
            ck->setVisible(has);
            if (has) ck->setBackgroundPic(sSel[idx] ? "images/af_check_on24.png"
                                                    : "images/af_check_off24.png");
        }
    }
}

// ── 选中 / 删除 ────────────────────────────────────────────────────
static void afToggle(int slot) {
    if (afTooEarly()) {
        LOGD("albumfile: cell tap ignored (page just opened)");
        return;
    }
    int idx = sPage * AF_PAGE + slot;
    if (idx < 0 || idx >= (int)sItems.size()) return;
    sSel[idx] = sSel[idx] ? 0 : 1;
    LOGD("albumfile: cell %d toggle -> %d", slot, sSel[idx] ? 1 : 0);
    afRefresh();
}

static void afToggleAll() {
    if (afTooEarly()) {
        LOGD("albumfile: select-all ignored (page just opened)");
        return;
    }
    int sel = afSelCount();
    bool allSel = (sel == (int)sItems.size() && !sItems.empty());
    for (size_t i = 0; i < sSel.size(); i++) sSel[i] = allSel ? 0 : 1;
    LOGD("albumfile: select-all -> %s", allSel ? "none" : "all");
    afRefresh();
}

static void afDialog(bool open) {
    sDialogOpen = open;
    if (mImageAfDimPtr != NULL) mImageAfDimPtr->setVisible(open);
    if (mButtonAfDimHitPtr != NULL) mButtonAfDimHitPtr->setVisible(open);
    if (mImageAfDelCardPtr != NULL) mImageAfDelCardPtr->setVisible(open);
    if (mTextAfDelTitlePtr != NULL) mTextAfDelTitlePtr->setVisible(open);
    if (mTextAfDelSubPtr != NULL) mTextAfDelSubPtr->setVisible(open);
    if (mButtonAfDelCancelPtr != NULL) mButtonAfDelCancelPtr->setVisible(open);
    if (mButtonAfDelOkPtr != NULL) mButtonAfDelOkPtr->setVisible(open);
    if (open) {
        char b[160];
        snprintf(b, sizeof(b), "共 %d 个，删除后不可恢复", afSelCount());
        if (mTextAfDelSubPtr != NULL) mTextAfDelSubPtr->setText(b);
    }
}

// 从屏保选中清单里剔除已删文件（否则屏保会引用不存在的路径）
static void afDropFromSelection(const std::vector<std::string>& removed) {
    std::string sel = StoragePreferences::getString(AF_KEY_SEL, "");
    if (sel.empty()) return;                 // 空 = 全选，无需处理
    std::string out;
    size_t pos = 0;
    while (pos <= sel.size()) {
        size_t nl = sel.find('\n', pos);
        std::string line = (nl == std::string::npos) ? sel.substr(pos) : sel.substr(pos, nl - pos);
        if (!line.empty()) {
            bool hit = false;
            for (size_t i = 0; i < removed.size(); i++) {
                if (removed[i] == line) { hit = true; break; }
            }
            if (!hit) {
                out += line;
                out += '\n';
            }
        }
        if (nl == std::string::npos) break;
        pos = nl + 1;
    }
    StoragePreferences::putString(AF_KEY_SEL, out);
    LOGD("albumfile: sp_video_sel -> %d bytes after clean", (int)out.size());
}

static void afDeleteSelected() {
    // 防御：只允许从确认弹窗里执行（即使误触到本函数也不删）
    if (!sDialogOpen) {
        LOGD("albumfile: delete blocked (no confirm dialog)");
        return;
    }
    std::vector<std::string> removed;
    for (size_t i = 0; i < sItems.size(); i++) {
        if (!sSel[i]) continue;
        if (remove(sItems[i].path.c_str()) == 0) {
            removed.push_back(sItems[i].path);
        } else {
            LOGW("albumfile: remove failed %s", sItems[i].path.c_str());
        }
    }
    LOGD("albumfile: deleted %d files", (int)removed.size());
    afDropFromSelection(removed);
    afDialog(false);
    afScan();
    afRefresh();
}

// ── 生命周期 ───────────────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    afScan();
    afRefresh();
    afDialog(false);
}

static void onUI_intent(const Intent* intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    afScan();
    afRefresh();
    sLastCount = (int)sItems.size();
    sShowTicks = 0;                 // 开页防误触计时起点
}

static void onUI_hide() { afDialog(false); }

static void onUI_quit() {}

static bool onUI_Timer(int id) {
    if (id == 0) {
        if (sShowTicks < 2) sShowTicks++;
        if (!sDialogOpen) {
        // 上传是异步的：数量变了就重扫（每 1s 检查一次，代价低）
        DIR* d = opendir(AF_DIR);
        int c = 0;
        if (d != NULL) {
            struct dirent* ent = NULL;
            while ((ent = readdir(d)) != NULL) {
                std::string nm = ent->d_name;
                if (nm == "." || nm == ".." || nm[0] == '.') continue;
                bool v = false;
                if (afExtIn(nm, v)) c++;
            }
            closedir(d);
        }
        if (c != sLastCount) {
            sLastCount = c;
            afScan();
            afRefresh();
        }
        }
    }
    return true;
}

static bool onalbumfileActivityTouchEvent(const MotionEvent& ev) { (void)ev; return false; }

// ── 按钮回调 ───────────────────────────────────────────────────────
static bool onButtonClick_ButtonAfBack(ZKButton* p) { (void)p; EASYUICONTEXT->goBack(); return true; }
static bool onButtonClick_ButtonAfDone(ZKButton* p) { (void)p; EASYUICONTEXT->goBack(); return true; }

static bool onButtonClick_ButtonAfAll(ZKButton* p) { (void)p; afToggleAll(); return true; }

static bool onButtonClick_ButtonAfDel(ZKButton* p) {
    (void)p;
    if (afTooEarly()) {
        LOGD("albumfile: delete tap ignored (page just opened)");
        return true;
    }
    if (afSelCount() == 0) return true;
    afDialog(true);
    return true;
}

static bool onButtonClick_ButtonAfDelCancel(ZKButton* p) { (void)p; afDialog(false); return true; }
static bool onButtonClick_ButtonAfDelOk(ZKButton* p) { (void)p; afDeleteSelected(); return true; }
// 垫层：弹窗打开时吃掉垫层上的误触（不做事、也不关窗）
static bool onButtonClick_ButtonAfDimHit(ZKButton* p) { (void)p; return true; }

static bool onButtonClick_ButtonAfCell1(ZKButton* p) { (void)p; afToggle(0); return true; }
static bool onButtonClick_ButtonAfCell2(ZKButton* p) { (void)p; afToggle(1); return true; }
static bool onButtonClick_ButtonAfCell3(ZKButton* p) { (void)p; afToggle(2); return true; }
static bool onButtonClick_ButtonAfCell4(ZKButton* p) { (void)p; afToggle(3); return true; }
static bool onButtonClick_ButtonAfCell5(ZKButton* p) { (void)p; afToggle(4); return true; }
static bool onButtonClick_ButtonAfCell6(ZKButton* p) { (void)p; afToggle(5); return true; }
static bool onButtonClick_ButtonAfCell7(ZKButton* p) { (void)p; afToggle(6); return true; }
static bool onButtonClick_ButtonAfCell8(ZKButton* p) { (void)p; afToggle(7); return true; }
static bool onButtonClick_ButtonAfCell9(ZKButton* p) { (void)p; afToggle(8); return true; }
