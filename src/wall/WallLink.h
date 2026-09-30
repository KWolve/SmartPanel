/*
 * WallLink.h -- 多屏拼接联动（钟工 2026-09-25）
 *
 * 角色：组内序号 1 = 主机（唯一权威，发 epoch），其余从机跟随。
 * 时间：先做自包含 UDP 广播通道（局域网兜底口径，无需改 MQTT 层）；
 *       epoch = 本轮循环的墙钟起点（ms），从机据此算相位。
 * 关键：**不靠"播完即播"**（实测每循环多 ~1.22s）—— 每段结束等到下一个墙钟整边界再起播；
 *       两台各自用 nextBoundaryMs() 拿到**同一个绝对墙钟**，本地精等到点起播（不靠互发开始信令）。
 * v2（2026-09-26）：墙钟走 clock_gettime(CLOCK_REALTIME) 毫秒（旧版秒级分辨率测不出 40ms）。
 * 失联：>10s 收不到 epoch → 回退普通屏保轮播（mainLogic 判断 readyToPlay()）。
 *
 * v4（2026-09-27，钟工）：**一组多视频轮播（playlist.json v2）**
 *   磁盘布局：/mnt/sdnand/wall/<组名>/playlist.json + c1/seg_1.mp4…c1/seg_N.mp4 + c2/…
 *   时间轴：g = 本机组内时间 - epoch；pos = g mod total_ms；
 *            find k: cum[k] <= pos < cum[k] + dur[k]，off = pos - cum[k]
 *   兼容：**旧布局**（组目录下直接 seg_<idx>.mp4、无 playlist.json）= 单 clip 模式，
 *          时间轴口径与 v1 完全一致（period = 广播 seg_ms）。
 *   UDP：老 6 字段不变，末尾追加 `|clips|total_ms`（老从机只读前 6 段不受影响）。
 */
#pragma once

#include <string>
#include <vector>

class WallLink {
public:
    static WallLink* getInstance();

    void init();          // 读配置；启用则起 UDP 通道
    void stop();          // 关闭（关拼接/退出）
    void tick();          // 1s 心跳：主发 epoch + 从机判失联 + 统计漂移
    void onEpoch(const std::string& payload);   // 收到 epoch JSON

    bool enabled() const { return mEnabled; }
    bool isMaster() const { return mEnabled && mMaster; }
    int segIndex() const { return mIdx; }
    int panelCount() const { return mN; }
    std::string group() const { return mGroup; }
    std::string segPath() const;                // 旧布局：/mnt/sdnand/wall/<组>/seg_<idx>.mp4
    long long segMs() const { return mSegMs; }

    // ── v4：playlist.json v2（一组多视频轮播）──────────────────────────────
    //   清单统计（设置页/日志用；**不**改动内部播放状态，可对任意组名查询）
    struct PlaylistInfo {
        bool ok = false;            // true = 该组可用 playlist 模式
        int  version = 0;
        int  clips = 0;             // clip 数 K
        int  cols = 0;              // 排布列数（工具侧写，仅展示/诊断）
        long long totalMs = 0;      // 总时长 = Σ clip.dur_ms
        long long firstClipMs = 0;  // 第 1 个 clip 时长（= 广播 seg_ms 字段口径）
        int  mismatchSegs = 0;      // 同一 clip 内各段声明时长不一致的 clip 数（WARN 口径）
        std::string why;            // 未进入 playlist 模式的原因（无文件/解析失败…）
    };
    static bool queryPlaylist(const std::string& group, int panels, PlaylistInfo* out);
    // 组目录清单（/mnt/sdnand/wall 下真实存在的目录，名称序）——设置页“组名自定义”用
    static std::vector<std::string> listGroups();
    static std::string wallRoot();                       // /mnt/sdnand/wall

    bool playlistMode() const { return mClipCount > 0 && mTotalMs > 0; }
    int clipCount() const { return mClipCount; }        // 单 clip 模式 = 0
    long long clipDurMs(int k) const;                   // 0-based；越界返回 0
    long long clipStartMs(int k) const;                 // 第 k 个 clip 相对轮起点的偏移（Σ dur[0..k-1]）
    long long totalMs() const { return mTotalMs; }      // playlist 总时长（单 clip 模式 = 0）
    long long periodMs() const;                         // 时间轴周期：playlist=total，单 clip=segMs
    bool clipAt(long long groupTimeMs, int* k, long long* offMs) const;   // g -> (clip, 段内偏移)
    std::string groupDir() const;                       // /mnt/sdnand/wall/<组>
    std::string playlistPath() const;                   // <组目录>/playlist.json
    std::string segPathForClip(int k) const;            // 该 clip 下本机那一格的绝对路径
    std::string playKey() const;                        // 播放器“当前节目”键（换键才重开播放器）

    void publishNow();                          // 主机：立即（重）发一次 epoch（进屏保时调用；从机非主机时为空操作）
    // v3：进屏保的从机“等 epoch”快通道 —— 广播一次 "wall?|<组>"，主机收到立刻补发 epoch，
    //     并把收包缓冲自己排空，于是等待从「等 1s 心跳」压到 ms 级（超时兜底不变）。
    void requestEpoch();
    void pingNow();                              // v7：从机立刻发一次双向测时探针（join 前先把钟差量准）
    void poll();                                // 立刻排空一次收包（等价 tick 的收包步骤；可从玩家线程调）

    bool readyToPlay() const;                   // 已启用 && 有 epoch && 未失联
    bool hasEpoch() const { return mT0Ms > 0; }
    long long epochMs() const { return mT0Ms; }
    long long phaseMs() const;                  // 当前应在段内的位置
    long long waitToBoundaryMs() const;         // 距下一个整边界还有多久
    long long nextBoundaryMs() const;           // 下一个整边界的**绝对墙钟 ms**（两台同式 = 同一时刻）
    int leadMs() const { return mLeadMs; }      // 起播提前量（补偿引擎起播延迟；sp_wall_lead_ms）
    // v7（2026-09-28）：钟差口径改成**双向测时 RTT/2**（本机钟 - 主机钟），失败才退到
    //   「epoch 单程最小延迟」（会偏高 ≈ 最小投递延迟）。旧版用单程中值 = 钟差 + 排队延迟，
    //   现场实测被污染成 116 ms / 8.0 s（画面差同量级）。
    int skewMs() const { return mSkewMs; }
    int skewRttMs() const { return mSkewRttMs; }        // 最佳样本的往返时间（越小越可信；-1 = 单程兜底）
    const char* skewSrc() const { return mSkewFromPp ? "pingpong" : "epoch"; }
    bool skewValid() const { return mSkewValid; }
    // v7.8\uff1a\u77ed\u7a97\uff08\u6700\u8fd1 6 \u4e2a pong\uff09min-RTT \u4f30\u8ba1\u2014\u2014\u8ddf\u968f\u73af\u8981"\u65b0\u9c9c"\uff0c\u4e0d\u80fd\u7528 32 \u6837\u672c\u957f\u7a97\uff08\u6ede\u540e\u6700\u957f 32s\uff0c\u4e0e\u6bcf\u79d2\u589e\u76ca\u53e0\u52a0\u4f1a\u9707\u8361\uff09
    int fastSkewMs() const { return mFastSkewMs; }
    int fastSkewRttMs() const { return mFastRttMs; } // 是否拿到过有效钟差样本
    bool clockPlausible() const;                // 本机墙钟是否可信（>= 2024-01-01；掉电后未校时会 false）
    static long long wallNowMs();               // 墙钟毫秒（clock_gettime 优先，回退 TimeHelper）
    void markPlayStarted(long long targetMs);   // 起播时记录（target = 本次对齐的整边界墙钟）
    int driftMs() const { return mDriftMs; }    // 上次实测偏差（正文 = 迟于目标；负 = 早于目标）
    std::string stateText() const;              // 给设置页显示

private:
    WallLink() = default;
    void publishEpoch();
    void sendUdp(const std::string& s);
    void drainUdp();
    // v7.10（钟工 2026-09-29：组内不得大量广播）—— epoch 改**单播**
    void sendEpochToPeers(const char* payload);
    void addPeer(unsigned int ip, int port, long long nowMsVal);                            // 收包（含 ping/pong 测时与 wall? 补发请求）

    // playlist 内部表示（一个 clip 一个条目；files 按“面板序号-1”索引，缺项留空 -> 用默认名兜底）
    struct Clip {
        std::string name;
        long long durMs = 0;
        std::vector<std::string> files;
    };
    // 解析 <组目录>/playlist.json；成功（clips>=1 且 Σdur>0）返回 true 并填 clips/info
    static bool loadPlaylist(const std::string& group, int panels,
                             PlaylistInfo* info, std::vector<Clip>* clips);

    bool mEnabled = false;
    bool mMaster = false;
    int  mIdx = 1, mN = 2;
    std::string mGroup;
    long long mSegMs = 30000;
    int  mLeadMs = 150;         // v2 起播提前量（ms）
    long long mT0Ms = 0;        // epoch（墙钟 ms）
    long long mLastHbMs = 0;      // 主机低频广播心跳（v7.14：每 3s 一包，零配置可发现）
    long long mLastRecvMs = 0;  // 上次收到 epoch 的墙钟
    long long mPlayStartMs = 0; // 本段起播墙钟（实测用）
    long long mLastTargetMs = 0;// 本段目标整边界墙钟（实测用）
    int  mDriftMs = 0;
    int  mSkewMs = 0;           // 两机时钟偏差（本机钟 - 主机钟；组内时间修正 gskew 的来源）
    int  mSkewRttMs = -1;       // 最佳样本的往返时间（诊断）
    bool mSkewFromPp = false;   // true = 双向测时(RTT/2)；false = epoch 单程最小延迟兜底
    bool mSkewValid = false;    // 是否拿到过落在 ±120s 内的有效样本
    int  mSkewDrop = 0;         // 被丢弃的脏样本数（诊断）
    // 双向测时（v7）：环形 32 笔 (rtt, offset)，取**最小 RTT** 那笔（NTP clock-filter；
    //   窗口短了会在“最佳样本出窗”时跳到差样本 -> 实测 gskew 在 ±100ms 间跳）
    long long mFastRtt[6];      // v7.8\uff1a\u77ed\u7a97\uff08\u8ddf\u968f\u73af\u7528\uff09
    long long mFastOff[6];
    int  mFastN = 0;
    int  mFastIdx = 0;
    int  mFastSkewMs = 0;
    int  mFastRttMs = -1;
    long long mPpRtt[32];
    long long mPpOff[32];
    int  mPpN = 0;
    int  mPpIdx = 0;
    long long mLastPongMs = 0;  // 上次收到 pong 的墙钟
    int  mPongRecv = 0;         // 收到 pong 笔数（诊断）
    long long mLastPingMs = 0;  // 上次发探针的墙钟（从机 1s 一发）
    // epoch 单程兜底：环形 8 笔取最小（delay≥0 -> 最小最接近真值）
    long long mEpochSkewRing[8] = {0, 0, 0, 0, 0, 0, 0, 0};
    int  mEpochSkewN = 0;
    int  mEpochSkewIdx = 0;
    long long mEpochSkewMs = 0;
    bool mEpochSkewValid = false;
    // 主机地址（从 epoch 包源地址学得）—— 从机做双向测时用
    unsigned int mPeerIp = 0;
    int  mPeerPort = 0;
    bool mPeerValid = false;
    // v7.10：主机侧「发 epoch 的从机名单」（从收包源地址学得，10s 没动静淘汰）；
    //        从机侧 = prefs sp_wall_peer 配的主机地址（"192.0.2.91" 或 "ip:8901"）
    struct WallPeer { unsigned int ip; int port; long long lastMs; };
    std::vector<WallPeer> mPeers;
    int  mCfgMasterPort = 8901;
    long long mLastAskMs = 0;      // 广播兜底请求的节流时间戳
    void sendUdpTo(const std::string& s, unsigned int ip, int port);
    void onPong(const char* payload);
    bool mUdpReady = false;
    int  mFd = -1;
    unsigned mHeartbeat = 0;

    // v4 playlist（mClipCount==0 => 旧布局单 clip 模式）
    std::vector<Clip> mClips;
    int  mClipCount = 0;
    long long mTotalMs = 0;
    long long mRemoteClips = 0;      // 广播里的 clips（诊断）
    long long mRemoteTotalMs = 0;    // 广播里的 total_ms（诊断）
    long long mWarnedRemoteTotal = -1;   // 已 WARN 过的广播 total（防每秒刷屏）
};
