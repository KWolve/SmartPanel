#ifdef FUN_BUILD
#include GENERATED_UI_DEFINITIONS
INIT_UI_EVENT_BINDINGS
#endif // FUN_BUILD
#pragma once

/*
 * scenesLogic.cc - 情景模式子页（scenes.ftu）
 *
 * 已定义情景列表（最多 8 行，可滚动）+ 每行右侧删除（二次确认弹窗）
 * + 新增情景（输入名 + 添加，校验空名/重名/超 6 字/已满 8 个）。
 * 数据源 = 业务单例 SceneManager（定义集合落在 ConfigStore 的 JSON 里，跨页共享）。
 *
 * 删除做法（SceneManager 没有 remove/delete 接口，成员 load/save 是 private）：
 *   用公开的 importScenesJson(json, merge=true) -- merge 模式的既定语义就是
 *   「删掉清单里没有的情景」。所以把「剩余情景」按完整字段（relays/devs/desc）
 *   序列化成 JSON 传进去，等于按名字删除；内存、持久化、UI 通知一次到位。
 *   主机模式下再 publishScenesConfig() 把新定义 retained 分发给从机。
 */

#include "utils/Log.h"
#include "entry/EasyUIContext.h"
#include "control/ZKButton.h"
#include "control/ZKTextView.h"
#include "control/ZKEditText.h"
#include "window/ZKWindow.h"
#include "storage/ConfigStore.h"
#include "scene/SceneManager.h"
#include "network/MqttBridge.h"
#include "storage/ConfigStore.h"
#include "network/LocalLink.h"

#include <rapidjson/stringbuffer.h>
#include <rapidjson/writer.h>

#include <stdio.h>
#include <string>
#include <vector>

static S_ACTIVITY_TIMEER REGISTER_ACTIVITY_TIMER_TAB[] = {
    {0, 1000},
};

#define SCENE_ROW_MAX  8
#define SCENE_NAME_UNITS_MAX 6      // 新增情景名最多 6 个汉字（1 个 ASCII 记 0.55）

static std::string sDelName;        // 待删除的情景名（名称快照，删除后列表会前移）

static ZKTextView* rowBg(int i) {
    ZKTextView* a[SCENE_ROW_MAX] = {
        mImageSceneRowBg1Ptr, mImageSceneRowBg2Ptr, mImageSceneRowBg3Ptr, mImageSceneRowBg4Ptr,
        mImageSceneRowBg5Ptr, mImageSceneRowBg6Ptr, mImageSceneRowBg7Ptr, mImageSceneRowBg8Ptr };
    return (i >= 0 && i < SCENE_ROW_MAX) ? a[i] : NULL;
}
static ZKTextView* rowName(int i) {
    ZKTextView* a[SCENE_ROW_MAX] = {
        mTextSceneRowName1Ptr, mTextSceneRowName2Ptr, mTextSceneRowName3Ptr, mTextSceneRowName4Ptr,
        mTextSceneRowName5Ptr, mTextSceneRowName6Ptr, mTextSceneRowName7Ptr, mTextSceneRowName8Ptr };
    return (i >= 0 && i < SCENE_ROW_MAX) ? a[i] : NULL;
}
static ZKTextView* rowDesc(int i) {
    ZKTextView* a[SCENE_ROW_MAX] = {
        mTextSceneRowDesc1Ptr, mTextSceneRowDesc2Ptr, mTextSceneRowDesc3Ptr, mTextSceneRowDesc4Ptr,
        mTextSceneRowDesc5Ptr, mTextSceneRowDesc6Ptr, mTextSceneRowDesc7Ptr, mTextSceneRowDesc8Ptr };
    return (i >= 0 && i < SCENE_ROW_MAX) ? a[i] : NULL;
}
static ZKButton* rowDel(int i) {
    ZKButton* a[SCENE_ROW_MAX] = {
        mButtonSceneDel1Ptr, mButtonSceneDel2Ptr, mButtonSceneDel3Ptr, mButtonSceneDel4Ptr,
        mButtonSceneDel5Ptr, mButtonSceneDel6Ptr, mButtonSceneDel7Ptr, mButtonSceneDel8Ptr };
    return (i >= 0 && i < SCENE_ROW_MAX) ? a[i] : NULL;
}
static ZKTextView* rowDelIcon(int i) {
    ZKTextView* a[SCENE_ROW_MAX] = {
        mImageSceneDelIcon1Ptr, mImageSceneDelIcon2Ptr, mImageSceneDelIcon3Ptr,
        mImageSceneDelIcon4Ptr, mImageSceneDelIcon5Ptr, mImageSceneDelIcon6Ptr,
        mImageSceneDelIcon7Ptr, mImageSceneDelIcon8Ptr };
    return (i >= 0 && i < SCENE_ROW_MAX) ? a[i] : NULL;
}

// UTF-8 安全按「显示宽度」截断（汉字 = 1.0，ASCII = 0.55），超宽场景名列表里不撑破行
static std::string fitUnits(const std::string& s, double maxUnits) {
    std::string out;
    double used = 0.0;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        size_t len = (c < 0x80) ? 1 : ((c < 0xE0) ? 2 : ((c < 0xF0) ? 3 : 4));
        if (i + len > s.size()) break;
        double w = (c < 0x80) ? 0.55 : 1.0;
        if (used + w > maxUnits) break;
        out.append(s, i, len);
        used += w;
        i += len;
    }
    return out;
}

static double textUnits(const std::string& s) {
    double used = 0.0;
    for (size_t i = 0; i < s.size();) {
        unsigned char c = (unsigned char)s[i];
        size_t len = (c < 0x80) ? 1 : ((c < 0xE0) ? 2 : ((c < 0xF0) ? 3 : 4));
        if (i + len > s.size()) break;
        used += (c < 0x80) ? 0.55 : 1.0;
        i += len;
    }
    return used;
}

static std::string trimText(const std::string& s) {
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return std::string();
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

static void setErr(const char* text) {
    if (mTextSceneErrPtr != NULL) mTextSceneErrPtr->setText(text);
}

// 一行 = 名称（desc 优先，人读得懂）+ 键名与 3 路开关摘要
static void fillRow(int i, const SceneDef& def) {
    std::string title = def.desc.empty() ? def.name : def.desc;
    title = fitUnits(title, 16.0);                      // 18px，行宽 340 -> 约 16 汉字宽
    ZKTextView* nm = rowName(i);
    if (nm != NULL) nm->setText(title.c_str());

    char b[128];
    char s1[8], s2[8], s3[8];
    snprintf(s1, sizeof(s1), "%s", def.relays[0] ? "开" : "关");
    snprintf(s2, sizeof(s2), "%s", def.relays[1] ? "开" : "关");
    snprintf(s3, sizeof(s3), "%s", def.relays[2] ? "开" : "关");
    snprintf(b, sizeof(b), "%s - 灯1 %s - 灯2 %s - 灯3 %s", def.name.c_str(), s1, s2, s3);
    ZKTextView* ds = rowDesc(i);
    if (ds != NULL) ds->setText(b);
}

// HA 模式：行显示 HA 情景（面板只读展示，情景/自动化由 HA 执行）
static void fillRowHa(int i, const std::string& name) {
    std::string title = fitUnits(name, 16.0);
    ZKTextView* nm = rowName(i);
    if (nm != NULL) nm->setText(title.c_str());
    ZKTextView* ds = rowDesc(i);
    if (ds != NULL) ds->setText("HA 情景 - 由 HA 执行");
}

static void hideEditControls() {
    // HA 模式隐藏删除按钮/图标与新增入口（情景由 HA 管理）
    for (int i = 0; i < SCENE_ROW_MAX; i++) {
        ZKButton* dl = rowDel(i);
        ZKTextView* ic = rowDelIcon(i);
        if (dl != NULL) dl->setVisible(false);
        if (ic != NULL) ic->setVisible(false);
    }
    if (mImageSceneAddBgPtr != NULL) mImageSceneAddBgPtr->setVisible(false);
    if (mImageSceneAddBtnBgPtr != NULL) mImageSceneAddBtnBgPtr->setVisible(false);
    if (mTextScenesAddLabelPtr != NULL) mTextScenesAddLabelPtr->setVisible(false);
    // 输入框也要一起藏：只藏按钮会留一个可见但不可用的「死输入框」（钟工 2026-09-26 逐页核对发现）
    if (mEditSceneAddPtr != NULL) mEditSceneAddPtr->setVisible(false);
    if (mTextScenesHintPtr != NULL) mTextScenesHintPtr->setText("HA 模式：情景由 HA 管理（本页仅展示）");
}

static void refreshList() {
    bool ha = (ConfigStore::getInstance()->runMode() == ConfigStore::MODE_HA);
    int haN = ha ? MqttBridge::getInstance()->haSceneCount() : 0;
    if (ha && haN > 0) {
        int n = (haN > SCENE_ROW_MAX) ? SCENE_ROW_MAX : haN;
        for (int i = 0; i < SCENE_ROW_MAX; i++) {
            bool has = (i < n);
            ZKTextView* bg = rowBg(i);
            ZKTextView* nm = rowName(i);
            ZKTextView* ds = rowDesc(i);
            if (bg != NULL) bg->setVisible(has);
            if (nm != NULL) nm->setVisible(has);
            if (ds != NULL) ds->setVisible(has);
            if (has) fillRowHa(i, MqttBridge::getInstance()->haSceneName(i));
        }
        hideEditControls();
        LOGD("scenes: HA list refreshed, count=%d", haN);
        return;
    }
    std::vector<SceneDef> list = SceneManager::getInstance()->scenes();
    int n = (int)list.size();
    if (n > SCENE_ROW_MAX) n = SCENE_ROW_MAX;
    for (int i = 0; i < SCENE_ROW_MAX; i++) {
        bool has = (i < n);
        ZKTextView* bg = rowBg(i);
        ZKTextView* nm = rowName(i);
        ZKTextView* ds = rowDesc(i);
        ZKButton* dl = rowDel(i);
        ZKTextView* ic = rowDelIcon(i);
        if (bg != NULL) bg->setVisible(has);
        if (nm != NULL) nm->setVisible(has);
        if (ds != NULL) ds->setVisible(has);
        if (dl != NULL) dl->setVisible(has);
        if (ic != NULL) ic->setVisible(has);
        if (has) fillRow(i, list[i]);
    }
    LOGD("scenes: list refreshed, count=%d", (int)list.size());
}

static void passDecorations() {
    ZKTextView* pass[] = {
        mTextScenesTitlePtr, mTextScenesTitleEnPtr, mTextScenesListLabelPtr,
        mImageSceneRowBg1Ptr, mImageSceneRowBg2Ptr, mImageSceneRowBg3Ptr, mImageSceneRowBg4Ptr,
        mImageSceneRowBg5Ptr, mImageSceneRowBg6Ptr, mImageSceneRowBg7Ptr, mImageSceneRowBg8Ptr,
        mTextSceneRowName1Ptr, mTextSceneRowName2Ptr, mTextSceneRowName3Ptr, mTextSceneRowName4Ptr,
        mTextSceneRowName5Ptr, mTextSceneRowName6Ptr, mTextSceneRowName7Ptr, mTextSceneRowName8Ptr,
        mTextSceneRowDesc1Ptr, mTextSceneRowDesc2Ptr, mTextSceneRowDesc3Ptr, mTextSceneRowDesc4Ptr,
        mTextSceneRowDesc5Ptr, mTextSceneRowDesc6Ptr, mTextSceneRowDesc7Ptr, mTextSceneRowDesc8Ptr,
        mImageSceneDelIcon1Ptr, mImageSceneDelIcon2Ptr, mImageSceneDelIcon3Ptr,
        mImageSceneDelIcon4Ptr, mImageSceneDelIcon5Ptr, mImageSceneDelIcon6Ptr,
        mImageSceneDelIcon7Ptr, mImageSceneDelIcon8Ptr,
        mTextScenesAddLabelPtr, mImageSceneAddBgPtr, mImageSceneAddBtnBgPtr,
        mTextSceneErrPtr, mTextScenesHintPtr,
        mImageSceneDelDimPtr, mImageSceneDelBoxPtr, mTextSceneDelTitlePtr,
        mTextSceneDelSubPtr, mTextSceneDelNamePtr,
        mImageSceneDelOkBgPtr, mImageSceneDelCancelBgPtr,
    };
    for (size_t i = 0; i < sizeof(pass) / sizeof(pass[0]); i++) {
        if (pass[i] != NULL) {
            pass[i]->setTouchable(false);
            pass[i]->setTouchPass(true);
        }
    }
}

// 剩余情景（去掉 name 指定的那条）序列化成 JSON，交给 importScenesJson(merge=true)
static void removeSceneByName(const std::string& name) {
    SceneManager* sm = SceneManager::getInstance();
    std::vector<SceneDef> list = sm->scenes();
    rapidjson::StringBuffer sb;
    rapidjson::Writer<rapidjson::StringBuffer> w(sb);
    w.StartObject();
    int kept = 0;
    for (size_t i = 0; i < list.size(); i++) {
        const SceneDef& def = list[i];
        if (def.name == name) continue;
        w.Key(def.name.c_str());
        w.StartObject();
        w.Key("relays");
        w.StartArray();
        for (int c = 0; c < 3; c++) w.Bool(def.relays[c]);
        w.EndArray();
        if (!def.devs.empty()) {
            w.Key("devs");
            w.StartObject();
            for (std::map<std::string, std::vector<bool> >::const_iterator it = def.devs.begin();
                 it != def.devs.end(); ++it) {
                w.Key(it->first.c_str());
                w.StartArray();
                for (size_t c = 0; c < it->second.size(); c++) w.Bool(it->second[c]);
                w.EndArray();
            }
            w.EndObject();
        }
        w.Key("desc");
        w.String(def.desc.c_str());
        w.EndObject();
        kept++;
    }
    w.EndObject();
    std::string json(sb.GetString(), sb.GetSize());
    sm->importScenesJson(json, true);            // merge=true -> 清单外情景被删除
    if (ConfigStore::getInstance()->runMode() == ConfigStore::MODE_MASTER) {
        LocalLink::getInstance()->publishScenesConfig();     // 主机：retained 分发新定义
    }
    LOGD("scenes: removed '%s', kept=%d", name.c_str(), kept);
}

static bool sceneNameExists(const std::string& name) {
    std::vector<SceneDef> list = SceneManager::getInstance()->scenes();
    for (size_t i = 0; i < list.size(); i++) {
        if (list[i].name == name) return true;
        if (!list[i].desc.empty() && list[i].desc == name) return true;
    }
    return false;
}

// ── 系统回调 ─────────────────────────────────────────────
static void onUI_init() {
#ifdef FUN_BUILD
    INIT_UI_TIMERS
#endif // FUN_BUILD
    SceneManager::getInstance()->init();     // 首次启动灌出厂情景（幂等）
    passDecorations();
    refreshList();
    setErr("");
}

static void onUI_intent(const Intent *intentPtr) { (void)intentPtr; }

static void onUI_show() {
    EASYUICONTEXT->setScreensaverEnable(false);   // 子页不进屏保（钟工 09251751-1）
    SceneManager::getInstance()->init();
    refreshList();
    setErr("");
}

static void onUI_hide() {}
static void onUI_quit() {}
static void onProtocolDataUpdate(const SProtocolData &data) { (void)data; }
static bool onUI_Timer(int id) { (void)id; return true; }
static bool onscenesActivityTouchEvent(const MotionEvent &ev) { (void)ev; return false; }

// ── 回调 ─────────────────────────────────────────────────
static bool onButtonClick_ButtonScenesBack(ZKButton *p) {
    (void)p;
    EASYUICONTEXT->goBack();
    return true;
}

// 删除：先弹二次确认（同一页模态），确认后才真删
static void askDelete(int idx) {
    std::vector<SceneDef> list = SceneManager::getInstance()->scenes();
    if (idx < 0 || idx >= (int)list.size()) return;
    sDelName = list[idx].name;
    if (mTextSceneDelNamePtr != NULL) {
        std::string show = fitUnits(list[idx].desc.empty() ? list[idx].name : list[idx].desc, 14.0);
        mTextSceneDelNamePtr->setText(show.c_str());
    }
    if (mWindowSceneDelPtr != NULL) mWindowSceneDelPtr->showWnd();
}

static bool onButtonClick_ButtonSceneDel1(ZKButton *p) { (void)p; askDelete(0); return true; }
static bool onButtonClick_ButtonSceneDel2(ZKButton *p) { (void)p; askDelete(1); return true; }
static bool onButtonClick_ButtonSceneDel3(ZKButton *p) { (void)p; askDelete(2); return true; }
static bool onButtonClick_ButtonSceneDel4(ZKButton *p) { (void)p; askDelete(3); return true; }
static bool onButtonClick_ButtonSceneDel5(ZKButton *p) { (void)p; askDelete(4); return true; }
static bool onButtonClick_ButtonSceneDel6(ZKButton *p) { (void)p; askDelete(5); return true; }
static bool onButtonClick_ButtonSceneDel7(ZKButton *p) { (void)p; askDelete(6); return true; }
static bool onButtonClick_ButtonSceneDel8(ZKButton *p) { (void)p; askDelete(7); return true; }

static bool onButtonClick_ButtonSceneDelOk(ZKButton *p) {
    (void)p;
    if (mWindowSceneDelPtr != NULL) mWindowSceneDelPtr->hideWnd();
    if (sDelName.empty()) return true;
    std::vector<SceneDef> list = SceneManager::getInstance()->scenes();
    if (list.size() <= 1) {                       // 至少留一个，否则重启会灌回出厂情景
        setErr("至少保留一个情景");
        LOGW("scenes: refuse to remove last scene");
        sDelName.clear();
        return true;
    }
    removeSceneByName(sDelName);
    sDelName.clear();
    refreshList();
    setErr("");
    return true;
}

static bool onButtonClick_ButtonSceneDelCancel(ZKButton *p) {
    (void)p;
    sDelName.clear();
    if (mWindowSceneDelPtr != NULL) mWindowSceneDelPtr->hideWnd();
    return true;
}

static bool onButtonClick_ButtonSceneAdd(ZKButton *p) {
    (void)p;
    std::string name = (mEditSceneAddPtr != NULL) ? trimText(mEditSceneAddPtr->getText())
                                                  : std::string();
    if (name.empty()) {
        setErr("情景名不能为空");
        return true;
    }
    if (textUnits(name) > (double)SCENE_NAME_UNITS_MAX) {
        setErr("情景名最多 6 个字");
        return true;
    }
    std::vector<SceneDef> list = SceneManager::getInstance()->scenes();
    if ((int)list.size() >= SCENE_ROW_MAX) {
        setErr("最多 8 个情景");
        return true;
    }
    if (sceneNameExists(name)) {
        setErr("情景名已存在");
        return true;
    }
    bool off[3] = { false, false, false };        // 新情景默认全关，之后按需编辑
    std::string desc = name + " - 自定义";
    SceneManager::getInstance()->defineScene(name, off, desc);   // 内部 save + 主机分发
    if (mEditSceneAddPtr != NULL) mEditSceneAddPtr->setText("");
    setErr("");
    refreshList();
    LOGD("scenes: defined '%s'", name.c_str());
    return true;
}

static void onEditTextChanged_EditSceneAdd(const std::string &text) {
    (void)text;
    setErr("");
}
