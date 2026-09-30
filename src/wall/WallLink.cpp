/*
 * WallLink.cpp -- 多屏拼接联动实现（v2：毫秒墙钟 + 整边界定标；v4：playlist 多视频轮播）
 * 协议（明文、局域网）：wall|<组名>|<t0_ms>|<seg_ms>|<n>|<pub_ms>[|<clips>|<total_ms>]
 *   （每条 ≤160 字节，1s 一发；末尾两个字段是 v4 追加的，老从机只读前 6 段不受影响）
 *   组名不匹配直接丢弃；从机用最新 t0 算相位；pub_ms = 主机发包瞬间墙钟（供从机算时钟偏差）。
 *   playlist 模式下 seg_ms 字段填“第 1 个 clip 的时长”（供老读法/诊断）；
 *   clips = clip 数 K（旧布局 = 0）、total_ms = 总时长（旧布局 = 0）。
 * v2 变更（2026-09-26）：nowMs() 直取 clock_gettime(CLOCK_REALTIME) 毫秒 ——
 *   上一版回退链会落到 getDateTime() 秒级（now 全是 x500），只能测到 ±1000ms，
 *   两台起播相位差无法收敛到 1 帧（40ms）；v2 起实测 delta/相位差均为毫秒级。
 * v4 变更（2026-09-27）：读 /mnt/sdnand/wall/<组>/playlist.json（rapidjson）——
 *   多 clip 时间轴（pos = g mod total；clip k = 满足 cum[k] <= pos < cum[k]+dur[k]）。
 *   时长一律**以本地 playlist.json 为准**；与广播 total_ms 不符只 WARN，不停播。
 */
#include "wall/WallLink.h"

#include "system/ClockManager.h"   // v7.7: group clock follow
#include "utils/Log.h"
#include "utils/TimeHelper.h"
#include "storage/StoragePreferences.h"

#include <rapidjson/document.h>

#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <algorithm>
#include <vector>

#define WALL_UDP_PORT 8901
#define WALL_LOST_MS  10000
#define WALL_ROOT     "/mnt/sdnand/wall"

static long long nowMs() {
    // v2 主路径：clock_gettime(CLOCK_REALTIME) 直取毫秒，不依赖 TimeHelper
    //（TimeHelper::getCurrentTime() 在未校时/异常会话会退到秒级，见上一版踩坑）
    struct timespec ts;
    if (clock_gettime(CLOCK_REALTIME, &ts) == 0) {
        long long ms = (long long)ts.tv_sec * 1000LL + (long long)(ts.tv_nsec / 1000000L);
        if (ms > 1000000000000LL) return ms;            // 形如 ms 时间戳（2001 以后）
    }
    // 回退链：与 TimeHelper::getCurrentTime() 在未校时/异常时会返回 0
    //（今天已踩过：NTP 校时前后不一致）-> 退化用 getDateTime() 换算到秒级
    long long t = TimeHelper::getCurrentTime();
    if (t > 1000000000000LL) return t;          // 形如 ms 时间戳（2001 以后）
    struct tm* tm = TimeHelper::getDateTime();
    if (tm != NULL) {
        tm->tm_isdst = -1;
        time_t sec = mktime(tm);                // 本地时间 -> epoch 秒
        if (sec > 1000000000LL) return (long long)sec * 1000LL + 500;   // 取秒中值
    }
    return t;
}

long long WallLink::wallNowMs() { return nowMs(); }

WallLink* WallLink::getInstance() {
    static WallLink s;
    return &s;
}

std::string WallLink::wallRoot() { return WALL_ROOT; }

std::string WallLink::groupDir() const { return wallRoot() + "/" + mGroup; }

std::string WallLink::playlistPath() const { return groupDir() + "/playlist.json"; }

std::string WallLink::segPath() const {
    char b[256];
    snprintf(b, sizeof(b), "%s/seg_%d.mp4", groupDir().c_str(), mIdx);
    return b;
}

// 播放器“当前节目”键：
//   playlist 模式 = <组目录>/playlist.json（**稳定**，播放器内部自己切 clip；换组/换清单才换键）
//   单 clip 模式 = seg_<idx>.mp4（与 v1 完全一致）
std::string WallLink::playKey() const {
    return playlistMode() ? playlistPath() : segPath();
}

long long WallLink::clipDurMs(int k) const {
    if (k < 0 || k >= (int)mClips.size()) return 0;
    return mClips[(size_t)k].durMs;
}

long long WallLink::clipStartMs(int k) const {
    long long c = 0;
    for (int i = 0; i < k && i < (int)mClips.size(); i++) c += mClips[(size_t)i].durMs;
    return c;
}

long long WallLink::periodMs() const {
    if (playlistMode()) return mTotalMs;
    return (mSegMs >= 1000) ? mSegMs : 30000;
}

// 组内时间 g -> (clip k, 段内偏移 off)；单 clip 模式返回 false（调用方按老口径走）
bool WallLink::clipAt(long long groupTimeMs, int* k, long long* offMs) const {
    if (!playlistMode()) return false;
    long long pos = groupTimeMs % mTotalMs;
    if (pos < 0) pos += mTotalMs;
    long long cum = 0;
    for (int i = 0; i < (int)mClips.size(); i++) {
        const long long d = mClips[(size_t)i].durMs;
        if (pos < cum + d) {
            if (k) *k = i;
            if (offMs) *offMs = pos - cum;
            return true;
        }
        cum += d;
    }
    // 清单异常（Σdur < total）兜底：落最后一个 clip 的段内 0
    if (k) *k = (int)mClips.size() - 1;
    if (offMs) *offMs = 0;
    return true;
}

std::string WallLink::segPathForClip(int k) const {
    if (!playlistMode()) return segPath();                 // 旧布局：口径不变
    if (k < 0) k = 0;
    if (k >= (int)mClips.size()) k = (int)mClips.size() - 1;
    const Clip& c = mClips[(size_t)k];
    const int i = mIdx - 1;
    std::string rel;
    if (i >= 0 && i < (int)c.files.size() && !c.files[(size_t)i].empty()) rel = c.files[(size_t)i];
    if (rel.empty()) {
        char b[64];
        snprintf(b, sizeof(b), "%s/seg_%d.mp4", c.name.c_str(), mIdx);
        rel = b;
    }
    if (rel[0] == '/') return rel;                         // 清单里给了绝对路径就用它
    return groupDir() + "/" + rel;
}

std::vector<std::string> WallLink::listGroups() {
    std::vector<std::string> out;
    DIR* dp = opendir(WALL_ROOT);
    if (dp == NULL) return out;
    struct dirent* ent = NULL;
    while ((ent = readdir(dp)) != NULL) {
        std::string nm = ent->d_name;
        if (nm.empty() || nm == "." || nm == ".." || nm[0] == '.') continue;
        const std::string full = std::string(WALL_ROOT) + "/" + nm;
        struct stat st = {0};
        if (stat(full.c_str(), &st) != 0 || !S_ISDIR(st.st_mode)) continue;
        out.push_back(nm);
    }
    closedir(dp);
    std::sort(out.begin(), out.end());
    return out;
}

// 读整个文件到 std::string（清单只有几 KB；用 FILE* 避免 filereadstream 的缓冲管理）
static bool readFileAll(const std::string& path, std::string* out) {
    FILE* f = fopen(path.c_str(), "rb");
    if (f == NULL) return false;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return false; }
    const long n = ftell(f);
    if (n <= 0 || n > 4 * 1024 * 1024) { fclose(f); return false; }
    rewind(f);
    out->resize((size_t)n);
    const size_t rd = fread(&(*out)[0], 1, (size_t)n, f);
    fclose(f);
    out->resize(rd);
    return rd > 0;
}

static long long jLong(const rapidjson::Value& o, const char* key, long long def) {
    if (!o.IsObject() || !o.HasMember(key)) return def;
    const rapidjson::Value& v = o[key];
    if (v.IsInt64()) return (long long)v.GetInt64();
    if (v.IsInt()) return (long long)v.GetInt();
    if (v.IsUint()) return (long long)v.GetUint();
    if (v.IsDouble()) return (long long)(v.GetDouble() + 0.5);
    return def;
}

static std::string jStr(const rapidjson::Value& o, const char* key) {
    if (!o.IsObject() || !o.HasMember(key)) return std::string();
    const rapidjson::Value& v = o[key];
    return v.IsString() ? std::string(v.GetString()) : std::string();
}

// 解析 playlist.json v2（严格按规格；缺字段一律回退默认值）
//   成功判据：clips>=1 且 Σ clip.dur_ms > 0
bool WallLink::loadPlaylist(const std::string& group, int panels,
                            PlaylistInfo* info, std::vector<Clip>* clips) {
    if (info) { *info = PlaylistInfo(); }
    if (clips) clips->clear();
    if (group.empty()) { if (info) info->why = "empty_group"; return false; }

    const std::string path = wallRoot() + "/" + group + "/playlist.json";
    std::string js;
    if (!readFileAll(path, &js)) {
        if (info) info->why = "no_playlist_json";      // 旧布局（单 clip）走这条 -> 不打 WARN
        return false;
    }
    rapidjson::Document doc;
    if (doc.Parse(js.c_str()).HasParseError() || !doc.IsObject()) {
        if (info) info->why = "playlist_parse_error";
        LOGW("WallLink: playlist parse error: %s", path.c_str());
        return false;
    }

    const int version = (int)jLong(doc, "version", 0);
    const int nDecl = (int)jLong(doc, "n", 0);
    const int cols = (int)jLong(doc, "cols", 0);
    const long long totalDecl = jLong(doc, "total_ms", 0);
    if (version != 2) {
        LOGW("WallLink: playlist version=%d (expect 2) -> 按 v2 口径解析: %s", version, path.c_str());
    }
    if (!doc.HasMember("clips") || !doc["clips"].IsArray() || doc["clips"].Size() == 0) {
        if (info) info->why = "no_clips";
        LOGW("WallLink: playlist has no clips array: %s", path.c_str());
        return false;
    }

    const int fileSlots = (panels > 0) ? panels : 4;
    std::vector<Clip> tmp;
    long long sum = 0;
    int mismatch = 0;
    const rapidjson::Value& arr = doc["clips"];
    for (rapidjson::SizeType i = 0; i < arr.Size(); i++) {
        const rapidjson::Value& cv = arr[i];
        if (!cv.IsObject()) continue;
        Clip cl;
        cl.name = jStr(cv, "name");
        if (cl.name.empty()) {
            char b[16];
            snprintf(b, sizeof(b), "c%u", (unsigned)(i + 1));
            cl.name = b;
        }
        long long d = jLong(cv, "dur_ms", 0);
        cl.files.assign((size_t)fileSlots, std::string());
        long long segMin = 0, segMax = 0;
        bool segSeen = false;
        if (cv.HasMember("segments") && cv["segments"].IsArray()) {
            const rapidjson::Value& segs = cv["segments"];
            for (rapidjson::SizeType j = 0; j < segs.Size(); j++) {
                const rapidjson::Value& sv = segs[j];
                if (!sv.IsObject()) continue;
                const int idx = (int)jLong(sv, "index", 0);
                const std::string f = jStr(sv, "file");
                const long long sd = jLong(sv, "dur_ms", 0);
                if (idx >= 1 && idx <= fileSlots && !f.empty()) cl.files[(size_t)(idx - 1)] = f;
                if (sd > 0) {
                    if (!segSeen) { segMin = segMax = sd; segSeen = true; }
                    else { if (sd < segMin) segMin = sd; if (sd > segMax) segMax = sd; }
                }
            }
        }
        if (d <= 0) d = segMax;                     // clip.dur_ms 缺省 -> 用段声明时长
        if (d <= 0) {
            if (info) info->why = "clip_dur_invalid";
            LOGW("WallLink: playlist clip[%u] dur_ms invalid -> 退回单 clip 模式: %s",
                 (unsigned)i, path.c_str());
            return false;
        }
        cl.durMs = d;                               // ★ 必须回写：时间轴全靠它（clipAt/clipStartMs）
        tmp.push_back(cl);
        sum += d;
        if (segSeen && (segMax - segMin) > 40) {
            mismatch++;
            LOGW("WallLink: clip %s 内各段时长不一致 (min=%lld max=%lld ms, clip=%lld ms) -> "
                 "请核对同一切块工具导出的各段等长（只警告，不停播）",
                 cl.name.c_str(), segMin, segMax, d);
        }
    }
    if (tmp.empty() || sum <= 0) {
        if (info) info->why = "clips_invalid";
        LOGW("WallLink: playlist clips invalid -> 退回单 clip 模式: %s", path.c_str());
        return false;
    }
    if (totalDecl > 0 && (totalDecl - sum > 40 || sum - totalDecl > 40)) {
        LOGW("WallLink: playlist total_ms=%lld != Σdur=%lld -> 以 Σdur 为准（%s）",
             totalDecl, sum, path.c_str());
    }
    if (nDecl > 0 && panels > 0 && nDecl != panels) {
        LOGW("WallLink: playlist n=%d != prefs sp_wall_n=%d（以 prefs 为准，只警告）", nDecl, panels);
    }

    if (clips) *clips = tmp;
    if (info) {
        info->ok = true;
        info->version = version;
        info->clips = (int)tmp.size();
        info->cols = cols;
        info->totalMs = sum;
        info->firstClipMs = tmp[0].durMs;
        info->mismatchSegs = mismatch;
        info->why.clear();
    }
    return true;
}

bool WallLink::queryPlaylist(const std::string& group, int panels, PlaylistInfo* out) {
    std::vector<Clip> clips;
    return loadPlaylist(group, panels, out, &clips);
}

// v7.13（钟工 2026-09-29 20:26「零配置」）：组名/第几屏/屏数**从推送的素材推导**
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
    while (!s.empty() && (s[s.size() - 1] == '\n' || s[s.size() - 1] == '\r' || s[s.size() - 1] == ' '))
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
    mSegMs = StoragePreferences::getInt("sp_wall_seg_ms", 30000);
    // v2：起播提前量（lead=0 时**零内容截断**：内容在整边界后几 ms 出画，两台同式 -> 相位差≈0；
    // 想“首帧正好落在整边界”再按实测“解码->上屏”延迟给正值，代价是尾部截掉 lead 时长）
    mLeadMs = StoragePreferences::getInt("sp_wall_lead_ms", 0);
    // v7.10（钟工 2026-09-29：组内不得大量广播）：从机从 prefs 直接知道主机地址
    //   -> 探针/epoch 全程**单播**，零广播；没配才退到节流广播兜底（>=3s 一包）。
    {
        std::string peer = StoragePreferences::getString("sp_wall_peer", "");
        unsigned int ip = 0;
        int port = WALL_UDP_PORT;
        std::string host = peer;
        if (!peer.empty()) {
            size_t c = peer.find(':');
            if (c != std::string::npos) {
                host = peer.substr(0, c);
                int p2 = atoi(peer.substr(c + 1).c_str());
                if (p2 > 0) port = p2;
            }
            struct in_addr ia;
            if (inet_aton(host.c_str(), &ia) != 0) ip = ia.s_addr;
        }
        mCfgMasterPort = port;
        if (!mMaster && ip != 0) { mPeerIp = ip; mPeerPort = port; mPeerValid = true; }
        if (mEnabled) {
            LOGI("WallLink: unicast cfg sp_wall_peer=\"%s\" master=%s:%d mode=%s",
                 peer.c_str(), ip ? host.c_str() : "(none)", port,
                 (ip != 0) ? "unicast" : (!mMaster ? "broadcast-fallback(>=3s,only when epoch stale)" : "master"));
        }
    }
    if (mIdx < 1) mIdx = 1;
    if (mN < 2 || mN > 4) mN = 2;
    if (mSegMs < 1000) mSegMs = 30000;
    if (mLeadMs < 0 || mLeadMs > 2000) mLeadMs = 0;

    // ── v4：读本地 playlist.json（多视频轮播）───────────────────────────────
    //   有且合法 -> playlist 模式（时间轴 = total_ms）；无/非法 -> 旧布局单 clip（口径与 v1 完全一致）。
    //   时长**一律以本地清单为准**（广播只用于对齐 epoch 与诊断）。
    {
        PlaylistInfo pi;
        std::vector<Clip> clips;
        if (loadPlaylist(mGroup, mN, &pi, &clips)) {
            mClips.swap(clips);
            mClipCount = pi.clips;
            mTotalMs = pi.totalMs;
            LOGI("WallLink: playlist mode group=%s clips=%d total=%lldms first=%lldms cols=%d segsMismatch=%d",
                 mGroup.c_str(), mClipCount, mTotalMs, pi.firstClipMs, pi.cols, pi.mismatchSegs);
        } else {
            mClips.clear();
            mClipCount = 0;
            mTotalMs = 0;
            if (pi.why != "no_playlist_json" && !pi.why.empty()) {
                LOGW("WallLink: playlist unusable (%s) -> 退回单 clip 模式", pi.why.c_str());
            }
        }
    }

    if (!mEnabled) {
        LOGD("WallLink: disabled (playlist=%d clips=%d)", playlistMode() ? 1 : 0, mClipCount);
        return;
    }
    if (!mUdpReady) {
        mFd = socket(AF_INET, SOCK_DGRAM, 0);
        if (mFd >= 0) {
            int on = 1;
            setsockopt(mFd, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
            setsockopt(mFd, SOL_SOCKET, SO_BROADCAST, &on, sizeof(on));
            struct sockaddr_in a;
            memset(&a, 0, sizeof(a));
            a.sin_family = AF_INET;
            a.sin_port = htons(WALL_UDP_PORT);
            a.sin_addr.s_addr = htonl(INADDR_ANY);
            if (bind(mFd, (struct sockaddr*)&a, sizeof(a)) == 0) {
                int fl = fcntl(mFd, F_GETFL, 0);
                fcntl(mFd, F_SETFL, fl | O_NONBLOCK);
                mUdpReady = true;
            } else {
                LOGW("WallLink: bind %d failed (%s)", WALL_UDP_PORT, strerror(errno));
                close(mFd);
                mFd = -1;
            }
        }
    }
    LOGD("WallLink: enabled group=%s idx=%d/%d master=%d seg=%lldms lead=%dms udp=%d playlist=%d clips=%d total=%lldms",
         mGroup.c_str(), mIdx, mN, mMaster ? 1 : 0, mSegMs, mLeadMs, mUdpReady ? 1 : 0,
         playlistMode() ? 1 : 0, mClipCount, mTotalMs);
    if (mMaster) publishEpoch();
}

void WallLink::stop() {
    if (mFd >= 0) {
        close(mFd);
        mFd = -1;
    }
    mUdpReady = false;
    mEnabled = false;
    mT0Ms = 0;
    LOGD("WallLink: stopped");
}

void WallLink::sendUdp(const std::string& s) {
    if (!mUdpReady || mFd < 0) return;
    struct sockaddr_in b;
    memset(&b, 0, sizeof(b));
    b.sin_family = AF_INET;
    b.sin_port = htons(WALL_UDP_PORT);
    b.sin_addr.s_addr = htonl(INADDR_BROADCAST);
    sendto(mFd, s.c_str(), s.size(), 0, (struct sockaddr*)&b, sizeof(b));
}

void WallLink::publishEpoch() {
    long long t = nowMs();
    if (t <= 0) return;                     // 未校时：不发布（避免垃圾 epoch）
    if (mT0Ms == 0) mT0Ms = t;              // 主机自己定 epoch（首次）
    // v4：playlist 模式下 seg_ms 字段 = 第 1 个 clip 的时长（供老读法/诊断）；
    //     clips = clip 数（旧布局 0）、total_ms = 总时长（旧布局 0）—— 末尾追加，老从机不受影响。
    const bool pl = playlistMode();
    const long long pubSeg = pl ? clipDurMs(0) : mSegMs;
    const long long pubClips = pl ? (long long)mClipCount : 0;
    const long long pubTotal = pl ? mTotalMs : 0;
    char b[176];
    // 末尾 pub_ms（v2）：主机发包瞬间墙钟 —— 从机收到即可算“两台时钟偏差 + 链路延迟”
    snprintf(b, sizeof(b), "wall|%s|%lld|%lld|%d|%lld|%lld|%lld",
             mGroup.c_str(), mT0Ms, pubSeg, mN, t, pubClips, pubTotal);
    sendEpochToPeers(b);        // v7.10：只单播给本组从机（不再广播）
    // v7.14（钟工 2026-09-29 20:26「零配置」）：再补一包**低频广播**（每 3s，1 包/组），
    //   让没配 sp_wall_peer 的从机也能发现主机（现场：广播探针不一定到得了主机）。
    if (t - mLastHbMs >= 3000) {
        mLastHbMs = t;
        sendUdp(b);
    }
}

void WallLink::publishNow() {
    // 进屏保时调用（钟工 2026-09-26 11:30）：主机立刻重发一次 epoch ->
    //   从机马上能拿到新鲜网格 + 新鲜 skew（不等 1s 心跳），组内时间拉齐更快。
    if (!mEnabled || !mMaster || !mUdpReady) return;
    publishEpoch();
}

void WallLink::requestEpoch() {
    // 从机专用：要一次 epoch（主机收到立刻补发，不等 1s 心跳）
    // v7.10（钟工 2026-09-29）：**优先单播**给已知主机（prefs sp_wall_peer / 上次 epoch 源地址）；
    //   只有主机地址未知时才发一包**广播兜底**，且 >=3s 才允许一包（局域网里上百台设备）。
    if (!mEnabled || mMaster || !mUdpReady) return;
    char b[96];
    snprintf(b, sizeof(b), "wall?|%s", mGroup.c_str());
    if (mPeerValid) { sendUdpTo(b, mPeerIp, mPeerPort); return; }
    const long long tq = nowMs();
    if (tq > 0 && mLastAskMs > 0 && (tq - mLastAskMs) < 3000) return;
    mLastAskMs = tq;
    LOGW("WallLink: no master addr yet -> one broadcast wall? (throttled >=3s, group=%s)", mGroup.c_str());
    sendUdp(b);
}

void WallLink::pingNow() {
    // v7：从机 join 前/急需时立刻发一次探针（不等 tick 的 1s 节流）
    if (!mEnabled || mMaster || !mUdpReady || !mPeerValid) return;
    const long long t = nowMs();
    if (t <= 0) return;
    mLastPingMs = t;
    char b[64];
    snprintf(b, sizeof(b), "ping|%lld", t);
    sendUdpTo(b, mPeerIp, mPeerPort);
}

void WallLink::poll() {
    if (!mEnabled || !mUdpReady) return;
    drainUdp();
}

void WallLink::drainUdp() {
    // 收包（非阻塞）。调用者：tick()（1s 心跳）或 poll()（进屏保等 epoch 的快循环）
    //   v7（2026-09-28）：一次排空上限 8 -> 64 —— 接收队列积压时必须**一次排空**，
    //   否则手里的样本是几秒前的旧包（现场实测积压 8.0 s，被当成钟差补掉 -> 画面差 8 秒）。
    char buf[256];
    for (int k = 0; k < 64; k++) {
        struct sockaddr_in from;
        socklen_t fl = (socklen_t)sizeof(from);
        memset(&from, 0, sizeof(from));
        ssize_t n = recvfrom(mFd, buf, sizeof(buf) - 1, 0, (struct sockaddr*)&from, &fl);
        if (n <= 0) break;
        buf[n] = '\0';
        // ping/pong：PC 诊断（pong|<本机ms>）+ 从机 NTP 式双向测时（ping|<t0> -> pong|<t0>|<本机ms>）
        if (strncmp(buf, "ping|", 5) == 0) {
            char rb[80];
            const long long t0 = atoll(buf + 5);
            // v7.10：带组名的探针 = 本组从机在报活 -> 主机登记它（epoch 单播给它）
            const char* gpos = strchr(buf + 5, '|');
            if (mMaster && gpos != NULL && mGroup == (gpos + 1))
                addPeer(from.sin_addr.s_addr, (int)ntohs(from.sin_port), nowMs());
            if (t0 > 0) snprintf(rb, sizeof(rb), "pong|%lld|%lld", t0, nowMs());
            else        snprintf(rb, sizeof(rb), "pong|%lld", nowMs());   // 老 PC 探针兼容
            sendto(mFd, rb, strlen(rb), 0, (struct sockaddr*)&from, fl);
            continue;
        }
        if (strncmp(buf, "pong|", 5) == 0) {
            onPong(buf + 5);
            continue;
        }
        // v3（2026-09-26 11:30）：从机进屏保时要 epoch -> 主机立刻补发（把等待从 ~1s 压到 ms 级）
        if (strncmp(buf, "wall?", 5) == 0) {
            // v7.10：只在**组名匹配**时回（别的组/别的设备的包一律不理），并登记请求方供单播
            const std::string reqGroup(buf + 5, strnlen(buf + 5, 64));
            if (mMaster && reqGroup == mGroup) {
                addPeer(from.sin_addr.s_addr, (int)ntohs(from.sin_port), nowMs());
                publishEpoch();
            }
            continue;
        }
        // epoch 包：记下源地址 —— 从机据此向主机发双向测时探针
        if (strncmp(buf, "wall|", 5) == 0) {
            mPeerIp = from.sin_addr.s_addr;
            mPeerPort = (int)ntohs(from.sin_port);
            mPeerValid = true;
        }
        onEpoch(std::string(buf));
    }
}

// v7.10（钟工 2026-09-29：组内不得大量广播）——
//   主机不再对 255.255.255.255 每秒发 epoch（全网段每台设备都要处理的包），
//   而是**只给登记过的本组从机单播**（从机用带组名的探针/请求报活，线上单播即可维护名单）。
void WallLink::addPeer(unsigned int ip, int port, long long nowMsVal) {
    if (ip == 0 || port <= 0) return;
    for (size_t i = 0; i < mPeers.size(); i++) {
        if (mPeers[i].ip == ip && mPeers[i].port == port) { mPeers[i].lastMs = nowMsVal; return; }
    }
    if (mPeers.size() >= 8) return;                 // 一组最多 4 屏；溢出就不收了
    WallPeer p; p.ip = ip; p.port = port; p.lastMs = nowMsVal;
    mPeers.push_back(p);
    struct in_addr ia; ia.s_addr = ip;
    LOGI("WallLink: peer + %s:%d (peers=%d)", inet_ntoa(ia), port, (int)mPeers.size());
}

void WallLink::sendEpochToPeers(const char* payload) {
    if (!mMaster || !mUdpReady || payload == NULL) return;
    const long long t = nowMs();
    if (t <= 0) return;
    int sent = 0;
    for (size_t i = 0; i < mPeers.size(); ) {
        if (t - mPeers[i].lastMs > WALL_LOST_MS) {      // 10s 没报活 -> 淘汰
            struct in_addr ia0; ia0.s_addr = mPeers[i].ip;
            LOGI("WallLink: peer - %s:%d (silent >%dms)", inet_ntoa(ia0), mPeers[i].port, WALL_LOST_MS);
            mPeers.erase(mPeers.begin() + (long)i);
            continue;
        }
        sendUdpTo(payload, mPeers[i].ip, mPeers[i].port);
        sent++;
        i++;
    }
    if (sent == 0 && (mHeartbeat % 60) == 0)
        LOGD("WallLink: no slave peer yet -> epoch not sent (waiting for their probe; broadcast disabled)");
}

void WallLink::sendUdpTo(const std::string& s, unsigned int ip, int port) {
    if (!mUdpReady || mFd < 0 || ip == 0 || port <= 0) return;
    struct sockaddr_in b;
    memset(&b, 0, sizeof(b));
    b.sin_family = AF_INET;
    b.sin_port = htons((uint16_t)port);
    b.sin_addr.s_addr = ip;
    sendto(mFd, s.c_str(), s.size(), 0, (struct sockaddr*)&b, sizeof(b));
}

void WallLink::onPong(const char* payload) {
    // v7：从机 NTP 式双向测时（RTT/2 口径）—— 单程投递/排队延迟（WiFi 收发/排队，实测 60~175ms，
    //     积压时 8 s）会被 RTT/2 对消，这是能拿到「真实钟差」的唯一口径。
    long long t0 = 0, mnow = 0;
    if (sscanf(payload, "%lld|%lld", &t0, &mnow) != 2) return;
    if (t0 <= 0 || mnow <= 0) return;
    const long long t3 = nowMs();
    const long long rtt = t3 - t0;
    if (rtt < 0 || rtt > 2000) return;                       // 离谱的丢掉（计时器串了/积压太久）
    const long long off = (t0 + t3) / 2 - mnow;              // 本机钟 - 主机钟
    if (off > 120000LL || off < -120000LL) { mSkewDrop++; return; }
    mPpRtt[mPpIdx % 32] = rtt;
    mPpOff[mPpIdx % 32] = off;
    mPpIdx++;
    if (mPpN < 32) mPpN++;
    long long bestR = -1, bestO = 0;
    for (int i = 0; i < mPpN; i++) {
        if (bestR < 0 || mPpRtt[i] < bestR) { bestR = mPpRtt[i]; bestO = mPpOff[i]; }
    }
    mSkewMs = (int)bestO;
    mSkewRttMs = (int)bestR;
    // v7.8\uff1a\u77ed\u7a97\uff08\u6700\u8fd1 6 \u4e2a\u6837\u672c\uff09min-RTT \u2014\u2014 \u4f9b\u7cfb\u7edf\u949f\u8ddf\u968f\u73af\u7528
    mFastRtt[mFastIdx % 6] = rtt;
    mFastOff[mFastIdx % 6] = off;
    mFastIdx++;
    if (mFastN < 6) mFastN++;
    {
        long long fR = -1, fO = 0;
        for (int i = 0; i < mFastN; i++) {
            if (fR < 0 || mFastRtt[i] < fR) { fR = mFastRtt[i]; fO = mFastOff[i]; }
        }
        mFastSkewMs = (int)fO;
        mFastRttMs = (int)fR;
    }
    mSkewFromPp = true;
    mSkewValid = true;
    mLastPongMs = t3;
    mPongRecv++;
}

void WallLink::onEpoch(const std::string& payload) {
    // wall|<组>|<t0>|<seg>|<n>
    std::string s = payload;
    while (!s.empty() && (s[s.size() - 1] == '\n' || s[s.size() - 1] == '\r' ||
                          s[s.size() - 1] == ' ')) s.erase(s.size() - 1);
    if (s.compare(0, 5, "wall|") != 0) return;
    size_t p1 = s.find('|', 5);
    if (p1 == std::string::npos) return;
    std::string grp = s.substr(5, p1 - 5);
    if (grp != mGroup) return;
    size_t p2 = s.find('|', p1 + 1);
    if (p2 == std::string::npos) return;
    size_t p3 = s.find('|', p2 + 1);
    if (p3 == std::string::npos) return;
    long long t0 = atoll(s.substr(p1 + 1, p2 - p1 - 1).c_str());
    long long seg = atoll(s.substr(p2 + 1, p3 - p2 - 1).c_str());
    // v2：可选第 6 字段 pub_ms（老主机不带 -> 跳过偏差诊断）
    // v4：可选第 7/8 字段 clips|total_ms（老主机不带 -> 保持单 clip 口径）
    long long pub = 0, rclips = 0, rtotal = 0;
    size_t p4 = s.find('|', p3 + 1);
    if (p4 != std::string::npos) {
        size_t p5 = s.find('|', p4 + 1);
        pub = atoll(s.substr(p4 + 1, (p5 == std::string::npos) ? std::string::npos
                                                              : p5 - p4 - 1).c_str());
        if (p5 != std::string::npos) {
            size_t p6 = s.find('|', p5 + 1);
            rclips = atoll(s.substr(p5 + 1, (p6 == std::string::npos) ? std::string::npos
                                                                     : p6 - p5 - 1).c_str());
            if (p6 != std::string::npos) rtotal = atoll(s.substr(p6 + 1).c_str());
        }
    }
    long long rcv = nowMs();
    if (pub > 0 && rcv > 0) {
        // v7（2026-09-28）：**不再用单程中值**（中值 = 真钟差 + 约一半排队延迟，现场实测 116ms / 8.0s）。
        //   这里保留的只是**兜底**：窗口内最小样本（delay ≥ 0 -> 最小最接近真值）；
        //   正常路径是双向测时 onPong()（RTT/2），只有它 10s 没样本时才用本兜底。
        const long long raw = rcv - pub;
        if (raw > 120000LL || raw < -120000LL) {
            mSkewDrop++;
            LOGW("WallLink: skew sample %lldms out of +-120s -> dropped (drop=%d, local clock maybe unsynced)",
                 raw, mSkewDrop);
        } else {
            mEpochSkewRing[mEpochSkewIdx % 8] = raw;
            mEpochSkewIdx++;
            if (mEpochSkewN < 8) mEpochSkewN++;
            long long mn = mEpochSkewRing[0];
            for (int i = 1; i < mEpochSkewN; i++) if (mEpochSkewRing[i] < mn) mn = mEpochSkewRing[i];
            mEpochSkewMs = mn;
            mEpochSkewValid = true;
            // 兜底只在真没 pong（>20s）时才用，且要和当前双向值相差 ≤250ms
            //   （防积压包/尖峰注入 1.5s 级坏值 -> 画面跳一下）
            const long long sincePong = mLastPongMs > 0 ? (rcv - mLastPongMs) : 999999LL;
            if (!mSkewValid) {
                mSkewMs = (int)mEpochSkewMs;
                mSkewRttMs = -1;
                mSkewFromPp = false;
                mSkewValid = true;
            } else if (sincePong > 20000 && mSkewFromPp) {
                const long long d = mn - (long long)mSkewMs;
                if (d <= 250 && d >= -250) {
                    mSkewMs = (int)mEpochSkewMs;
                    mSkewRttMs = -1;
                    mSkewFromPp = false;
                }
            }
        }
    }
    // v4：playlist 模式以本地清单为准；广播 total_ms 不符只 WARN（绝不因它停播），
    //     且同一值只报一次（心跳 1s 一发，不节流会刷屏）。
    mRemoteClips = rclips;
    mRemoteTotalMs = rtotal;
    if (playlistMode() && rtotal > 0 && rtotal != mTotalMs) {
        if (mWarnedRemoteTotal != rtotal) {
            mWarnedRemoteTotal = rtotal;
            LOGW("WallLink: 广播 total_ms=%lld != 本地 playlist total_ms=%lld（clips=%lld vs %d）"
                 " -> 以本地清单为准继续播放，请核对各面板是否用同一份清单",
                 rtotal, mTotalMs, rclips, mClipCount);
        }
    } else if (playlistMode() && rclips > 0 && rclips != (long long)mClipCount) {
        if (mWarnedRemoteTotal != -2) {
            mWarnedRemoteTotal = -2;
            LOGW("WallLink: 广播 clips=%lld != 本地 clips=%d -> 以本地清单为准（请核对清单版本）",
                 rclips, mClipCount);
        }
    }
    if (t0 > 0 && (seg >= 1000 || playlistMode())) {
        if (mT0Ms != t0) LOGD("WallLink: epoch updated t0=%lld seg=%lld clips=%lld total=%lld",
                              t0, seg, rclips, rtotal);
        mT0Ms = t0;
        mSegMs = seg;
        mLastRecvMs = rcv;
    }
}

void WallLink::tick() {
    if (!mEnabled || !mUdpReady) return;
    // 1) 收包(非阻塞)：ping/pong 测时 + wall?（补发 epoch）+ epoch 本体
    drainUdp();
    // 1.5) v7：从机每 1s 向主机发一次双向测时探针 —— pong 回来即得「真实钟差」（RTT/2）
    if (!mMaster && mPeerValid) {
        const long long t = nowMs();
        if (t > 0 && (mLastPingMs == 0 || (t - mLastPingMs) >= 1000)) {
            mLastPingMs = t;
            char b[64];
            snprintf(b, sizeof(b), "ping|%lld|%s", t, mGroup.c_str());   // v7.10: 带组名，主机据此登记单播名单
            sendUdpTo(b, mPeerIp, mPeerPort);
        }
    }
    // 1.55) v7.10：主机地址未知 / epoch 陈旧 -> 节流要一次（单播优先，无地址才广播兜底）
    if (!mMaster) {
        const long long tq = nowMs();
        const bool stale = (mLastRecvMs == 0) || (tq > 0 && (tq - mLastRecvMs) > 3000);
        if (stale && (tq - mLastAskMs) > 3000) { mLastAskMs = tq; requestEpoch(); }
    }
    // 1.6) v7.7: group clock follow (slave system clock aligns to master; Zhong 2026-09-28)
    //   fresh pingpong sample -> followGroup(); stale(>5s) -> not healthy
    if (!mMaster) {
        const long long tNow = nowMs();
        const bool ppFresh = (mSkewValid && mSkewFromPp && mLastPongMs > 0 &&
                              (tNow - mLastPongMs) < 5000);
        ClockManager::getInstance()->setGroupHealthy(ppFresh);
        if (ppFresh) ClockManager::getInstance()->groupFollow(mSkewMs, mSkewRttMs);
    } else {
        ClockManager::getInstance()->setGroupHealthy(false);   // master keeps NTP
    }
    // 2) 主机每秒心跳（同时修正从机时钟偏差感知）
    if (mMaster) {
        mHeartbeat++;
        publishEpoch();
    }
    // 3) 漂移统计（v2）：本段实际起播墙钟 - 目标整边界墙钟（正文=迟，负=早）
    if (mPlayStartMs > 0 && mLastTargetMs > 0) {
        long long d = mPlayStartMs - mLastTargetMs;
        if (d > 32767) d = 32767;
        if (d < -32768) d = -32768;
        mDriftMs = (int)d;
    }
    // 4) 无条件诊断（每秒一条，便于现场自证）
    long long now = nowMs();
    LOGD("wall tick: now=%lld epoch=%lld seg=%lld phase=%lld wait=%lld next=%lld drift=%d skew=%d(%s,rtt=%d) ready=%d lost=%d playlist=%d clips=%d total=%lld remote_clips=%lld remote_total=%lld",
         now, mT0Ms, mSegMs, phaseMs(), waitToBoundaryMs(), nextBoundaryMs(), mDriftMs, mSkewMs,
         skewSrc(), mSkewRttMs,
         readyToPlay() ? 1 : 0,
         (now > 0 && mLastRecvMs > 0 && (now - mLastRecvMs) > WALL_LOST_MS) ? 1 : 0,
         playlistMode() ? 1 : 0, mClipCount, mTotalMs, mRemoteClips, mRemoteTotalMs);
}

long long WallLink::phaseMs() const {
    if (!hasEpoch()) return 0;
    long long now = nowMs();
    if (now <= 0) return 0;
    long long d = now - mT0Ms;
    if (d < 0) d = 0;
    const long long per = periodMs();          // v4：playlist 模式 = total_ms
    return d % per;
}

long long WallLink::nextBoundaryMs() const {
    // v2 关键原语：下一个整边界的**绝对墙钟**（ms）。两台同一 epoch + 同一公式 -> 同一时刻，
    // 各自本地精确等到该时刻起播，无需互发“开始”信令（UDP 抖动不进相位）。
    // v4：墙钟整边界 = 整个 playlist 一圈的边界（period = total_ms），单 clip 模式同 v1。
    if (!hasEpoch()) return 0;
    long long now = nowMs();
    if (now <= 0) return 0;
    long long d = now - mT0Ms;
    if (d < 0) d = 0;
    const long long per = periodMs();
    return mT0Ms + (d / per + 1) * per;
}

long long WallLink::waitToBoundaryMs() const {
    if (!hasEpoch()) return 0;
    const long long per = periodMs();
    long long ph = phaseMs();
    long long w = per - ph;
    if (w <= 0 || w > per) w = per;
    return w;
}

bool WallLink::readyToPlay() const {
    if (!mEnabled) return false;
    if (mMaster && mT0Ms == 0) return false;
    if (!hasEpoch()) return false;
    long long now = nowMs();
    if (now > 0 && mLastRecvMs > 0 && (now - mLastRecvMs) > WALL_LOST_MS) return false;  // 从机失联
    return true;
}

bool WallLink::clockPlausible() const {
    // 2024-01-01 00:00:00 UTC = 1704067200000ms：比这早说明掉电后/未校时（RTC 空 -> 1970）
    const long long t = nowMs();
    return t > 1704067200000LL;
}

void WallLink::markPlayStarted(long long targetMs) {
    mPlayStartMs = nowMs();
    mLastTargetMs = targetMs;
}

std::string WallLink::stateText() const {
    if (!mEnabled) return "未开启";
    if (!hasEpoch()) return isMaster() ? "初始化中" : "等待主机 epoch";
    long long now = nowMs();
    bool lost = (now > 0 && mLastRecvMs > 0 && (now - mLastRecvMs) > WALL_LOST_MS);
    if (lost) return "失联（已回普通屏保）";
    char b[128];
    if (isMaster()) {
        if (playlistMode()) snprintf(b, sizeof(b), "主机 · seg_%d/%d · %d段轮播", mIdx, mN, mClipCount);
        else snprintf(b, sizeof(b), "主机 · seg_%d/%d · 已发 epoch", mIdx, mN);
    } else {
        if (playlistMode()) snprintf(b, sizeof(b), "从机 · seg_%d/%d · %d段轮播 · 偏差 %+dms",
                                     mIdx, mN, mClipCount, mDriftMs);
        else snprintf(b, sizeof(b), "从机 · seg_%d/%d · 偏差 %+dms", mIdx, mN, mDriftMs);
    }
    return b;
}
