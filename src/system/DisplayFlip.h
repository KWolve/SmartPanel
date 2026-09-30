/*
 * DisplayFlip.h -- 「设备倒装」：整屏 UI + 视频 180° 旋转（钟工 2026-09-27 10:43）
 *
 * 场景：面板被**倒装**在墙上（上下颠倒），要求 UI 与视频全部转 180°，且可在设置里
 *       随时切换、掉电保持（/data prefs `sp_flip180`）。
 *
 * 三条链路（缺一不可）：
 *   ① UI/触摸：easyui `CONFIGMANAGER->setScreenRotate(180)` / `setTouchRotate(180)`
 *      —— 实测 libeasyui.so 里 setScreenRotate -> zk_disp_set_rotate(rot/90)
 *         -> 系统 disp 驱动的 set_rotate 钩子（非空）-> fbdev 软件 180° 翻转 + 全屏失效重绘；
 *         setTouchRotate -> zk_event_set_touch_rotate(rot/90) -> 触摸坐标同角度映射。
 *      为什么不用"两套 ftu"：面板是 480×480 **正方形**，180° 不需要换布局（老 easyui 也没有 relayout）。
 *   ② 视频层：MI DISP 原生旋转 `MI_DISP_SetVideoLayerRotateMode(层, {eRotateMode})`
 *      —— 视频不走 /dev/fb0（截屏拿不到视频层），必须在 MI 层转；180° 对应 eRotateMode=2。
 *      厂商现成用法：AppGroup/lib-h264-player/src/player/h264_player.cpp（Z20 分支）。
 *      ⚠️ 不用厂商那套"旋转渲染线程 + getFrame()"（本工程 mi_h264_player_port.cpp 里它是报错桩），
 *         MI DISP 层旋转更轻且对两条播放引擎（v4 ZKVideoView / simple WallPlayer）都生效。
 *   ③ 播放器重启顺序：DISP 层属性改动时**必须先停播放器**（改完再让心跳重起）——
 *      今天两段式起播的经验：在播放中改 MI 图层属性会踩坏 disp 通道（画面冻住）。
 */
#ifndef _SYSTEM_DISPLAY_FLIP_H_
#define _SYSTEM_DISPLAY_FLIP_H_

namespace DisplayFlip {

/** 当前是否倒装（读 /data prefs `sp_flip180`，bool 与 0/1 两种写法都认） */
bool enabled();

/** 落盘并**立即生效**（UI + 触摸 + 视频层）；返回 false = 读回校验失败 */
bool setEnabled(bool on);

/** 开机/重新进页时按已存配置应用（避免"设置保存了但重启后没转"） */
void applyStored();

/** 只应用 UI+触摸（不动视频层） */
void applyUi();

/** 按当前开关重新下发视频层旋转；返回 MI_DISP 的返回码（0 = 成功） */
int applyVideoLayer();

/** 视频层当前开关对应的旋转模式（0 = 不转，2 = 180°），便于日志/诊断 */
int videoRotateMode();

}  // namespace DisplayFlip

#endif // _SYSTEM_DISPLAY_FLIP_H_
