# -*- coding: utf-8 -*-
"""开关显隐「持久化」收口（钟工 2026-09-29 19:51：这个设置要记住）

现状：homeLogic / keysetLogic 各自直接读写 StoragePreferences("sw_show_N")，
      没有集中日志、也没有单一数据源（其余业务都走 ConfigStore）。
做法：键名不变（sw_show_1..3，历史值兼容），但**统一由 ConfigStore 读写**：
      · ConfigStore::swVisible(ch) / setSwVisible(ch, on)（写时打日志，现场可查）
      · homeLogic 读、keysetLogic 写都走它；homeLogic 重排日志带上 sw_show 三值
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def rw(rel, repls, must=True):
    p = os.path.join(ROOT, rel)
    t = open(p, encoding='utf-8').read()
    for old, new in repls:
        if old not in t:
            if must:
                raise SystemExit('!! %s 未找到锚点: %r' % (rel, old[:60]))
            continue
        t = t.replace(old, new, 1)
    open(p, 'w', encoding='utf-8').write(t)
    print('   patched', rel)


# ── 1) ConfigStore.h：声明 ─────────────────────────────────────
rw('src/storage/ConfigStore.h', [(
    """    static const int kMaxNameBytes = 24;                     // 8 个汉字（UTF-8）""",
    """    static const int kMaxNameBytes = 24;                     // 8 个汉字（UTF-8）

    // ── 主界面开关显隐（按键配置子页；钟工 2026-09-29：必须记住）──
    // ch = 1..3；false = 主界面不显示该开关并自动重排（默认 true）
    bool swVisible(int ch);
    void setSwVisible(int ch, bool visible);"""
)])

# ── 2) ConfigStore.cpp：键名 + 实现 ────────────────────────────
rw('src/storage/ConfigStore.cpp', [
    ("""static const char* kKeyRelayState = "sp_relay_state";    // bitmask""",
     """static const char* kKeyRelayState = "sp_relay_state";    // bitmask
static const char* kKeySwShow     = "sw_show_";          // + "1".."3"（按键配置子页；历史键，勿改）"""),
    ("""bool ConfigStore::relayState(int ch) {""",
     """// ── 主界面开关显隐（钟工 2026-09-29：设置要持久化/记住）──────
bool ConfigStore::swVisible(int ch) {
    if (ch < 1 || ch > 3) return true;
    return StoragePreferences::getInt(std::string(kKeySwShow) + char('0' + ch), 1) != 0;
}

void ConfigStore::setSwVisible(int ch, bool visible) {
    if (ch < 1 || ch > 3) return;
    std::string k = std::string(kKeySwShow) + char('0' + ch);
    StoragePreferences::putInt(k, visible ? 1 : 0);
    LOGD("ConfigStore: %s -> %d", k.c_str(), visible ? 1 : 0);   // 现场可查（记忆是否落盘）
}

bool ConfigStore::relayState(int ch) {"""),
])

# ── 3) homeLogic.cc：读走 ConfigStore + 日志带三值 ─────────────
rw('src/logic/homeLogic.cc', [
    ("""static bool homeSwVisible(int i) {
    char k[32];
    snprintf(k, sizeof(k), "sw_show_%d", i + 1);
    return StoragePreferences::getInt(k, 1) != 0;      // 默认显示
}""",
     """static bool homeSwVisible(int i) {
    return ConfigStore::getInstance()->swVisible(i + 1);   // 统一走 ConfigStore（持久化口径）
}"""),
    ("""    LOGD("home: switch layout -> mask=0x%x (n=%d, cardW=%d)", mask, n, w);""",
     """    LOGD("home: switch layout -> mask=0x%x (n=%d, cardW=%d) sw_show=%d,%d,%d",
         mask, n, w, mask & 1 ? 1 : 0, mask & 2 ? 1 : 0, mask & 4 ? 1 : 0);"""),
])

# ── 4) keysetLogic.cc：写走 ConfigStore ───────────────────────
rw('src/logic/keysetLogic.cc', [
    ("""static bool swVisible(int i) {
    return StoragePreferences::getInt(swKey(i), 1) != 0;
}""",
     """static bool swVisible(int i) {
    return ConfigStore::getInstance()->swVisible(i + 1);   // 统一走 ConfigStore（持久化口径）
}"""),
    ("""    StoragePreferences::putInt(swKey(i), next);
    LOGD("keyset: %s -> %d", swKey(i).c_str(), next);""",
     """    ConfigStore::getInstance()->setSwVisible(i + 1, next != 0);
    LOGD("keyset: %s -> %d", swKey(i).c_str(), next);"""),
])

print('done')
