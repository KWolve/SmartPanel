# -*- coding: utf-8 -*-
"""拼墙「零配置」口径（钟工 2026-09-29 20:26 定）

要求：默认只保留 `sp_wall_en`；**不需要**配置组名 / 组内第几屏 / 屏数 ——
      「推送的时候决定设备即可」（推送时给每台选好它那一份素材 → sp_video_sel）。

做法（`WallLink::init()`）：
  1. 从 `sp_video_sel` 推导：
       · 组名  = `/mnt/sdnand/wall/<组名>/…` 里的 `<组名>`
       · 第几屏 = 文件名 `seg_<N>.mp4` 的 N
  2. 屏数（mN）= 该组 `playlist.json` 的 `cols`（缺则回退旧 `sp_wall_n`，再缺 =2）
  3. 主机：`sp_wall_role` **缺省时 = 第 1 屏**（idx==1 当主机）；写了就按写的（0=从机/1=主机）
  4. 兼容：老 prefs（显式 sp_wall_group/idx/n）仍然优先，不动老现场
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
P = os.path.join(ROOT, 'src', 'wall', 'WallLink.cpp')

t = io.open(P, encoding='utf-8').read()

OLD = '''void WallLink::init() {
    mEnabled = StoragePreferences::getBool("sp_wall_en", false);
    mGroup = StoragePreferences::getString("sp_wall_group", "zksw-wall");
    mIdx = StoragePreferences::getInt("sp_wall_idx", 1);
    mN = StoragePreferences::getInt("sp_wall_n", 2);
    mMaster = StoragePreferences::getInt("sp_wall_role", 1) != 0;
'''

NEW = '''// v7.13（钟工 2026-09-29 20:26「零配置」）：组名/第几屏/屏数**从推送的素材推导**
//   · 素材路径 sp_video_sel = /mnt/sdnand/wall/<组名>/c<k>/seg_<N>.mp4
//       → 组名 = <组名>；第几屏 = N
//   · 屏数 = 该组 playlist.json 的 "cols"（缺 -> 旧 sp_wall_n -> 2）
//   · 主机 = 第 1 屏（未显式写 sp_wall_role 时）
//   · 老现场：显式写了 sp_wall_group/idx/n 时**以老值为准**（向后兼容）
static void deriveWallFromMedia(std::string& group, int& idx, int& n) {
    std::string sel = StoragePreferences::getString("sp_video_sel", "");
    if (sel.size() < 8) return;
    std::string s = sel;
    // 去掉结尾换行/空白
    while (!s.empty() && (s[s.size() - 1] == '\\n' || s[s.size() - 1] == '\\r' || s[s.size() - 1] == ' '))
        s.erase(s.size() - 1);
    size_t wp = s.find("/wall/");
    if (wp == std::string::npos) return;
    size_t g0 = wp + 6;                             // "/wall/" 之后
    size_t g1 = s.find('/', g0);
    if (g1 == std::string::npos || g1 <= g0) return;
    std::string g = s.substr(g0, g1 - g0);
    // 文件名 seg_<N>.mp4 -> N
    size_t sl = s.rfind('/');
    std::string base = (sl == std::string::npos) ? s : s.substr(sl + 1);
    int seg = 0;
    size_t sp = base.find("seg_");
    if (sp != std::string::npos) seg = atoi(base.c_str() + sp + 4);
    group = g;
    if (seg > 0) idx = seg;                         // 第几屏 = 推送时选的那一份
    if (n <= 0) n = 3;
    LOGI("WallLink: 从素材推导 group=%s idx=%d n=%d (sel=%s)", group.c_str(), idx, n, s.c_str());
}

void WallLink::init() {
    mEnabled = StoragePreferences::getBool("sp_wall_en", false);
    // ── 零配置口径：优先按素材推导；老 prefs 显式值仍作兜底 ──────────────
    mGroup = StoragePreferences::getString("sp_wall_group", "");
    mIdx = StoragePreferences::getInt("sp_wall_idx", 0);
    mN = StoragePreferences::getInt("sp_wall_n", 0);
    {
        std::string g = mGroup;
        int ix = mIdx, nn = mN;
        deriveWallFromMedia(g, ix, nn);             // 素材推导（可能覆盖/补齐）
        if (!g.empty()) mGroup = g;
        if (ix > 0) mIdx = ix;
        if (nn > 0) mN = nn;
    }
    if (mGroup.empty()) mGroup = "zksw-wall";
    if (mIdx < 1) mIdx = 1;
    if (mN < 1) mN = 2;
    // 主机：显式 sp_wall_role 优先；缺省 = 第 1 屏当主机（组内零配置）
    {
        int role = StoragePreferences::getInt("sp_wall_role", -1);
        mMaster = (role < 0) ? (mIdx == 1) : (role != 0);
        if (role < 0)
            LOGI("WallLink: sp_wall_role 未配置 -> 按「第 1 屏为主机」判定 master=%d (idx=%d)", mMaster ? 1 : 0, mIdx);
    }
'''

assert OLD in t, '锚点未找到：init() 头部'
t = t.replace(OLD, NEW, 1)
io.open(P, 'w', encoding='utf-8').write(t)
print('patched', P)
