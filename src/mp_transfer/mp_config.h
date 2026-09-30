#ifndef MP_TRANSFER_MP_CONFIG_H_
#define MP_TRANSFER_MP_CONFIG_H_

/*
 * 小程序传图/视频（mp_transfer）项目配置
 *
 * MP_PATH：落地目录，**末尾必须带 /**。与「屏保视频」页扫描目录保持一致，
 *          这样小程序传上来的视频会直接出现在屏保视频列表里（钟工 2026-09-24 口径）。
 */
#define MP_PATH        "/mnt/sdnand/album/"
#define MP_DEVICE_NAME "智能面板"      /* UDP 广播显示名（小程序端看到；空则 Frame） */
#define MP_LISTEN_PORT 9000

#endif /* MP_TRANSFER_MP_CONFIG_H_ */
