# webcfg_test — 板内配置网页的 x86 替身冒烟

不接真机、不接 QEMU：用**内存版替身**（`utils/Log.h`、`storage/ConfigStore.h`、
`network/MqttBridge.h`、`system/NetKeeper.h`）编译**真实的**`../../src/network/WebConfigServer.cpp`，
起服务后 curl 走完「读配置页 → POST 保存 → 读回 status / 页面回填」全链路。

## 跑

```bash
g++ -std=c++14 -Wall -I . -I ../../src stubs.cpp ../../src/network/WebConfigServer.cpp -o /tmp/webcfg -lpthread
bash test.sh
```

`test.sh` 五步：
1. 长令牌（带换行与空格）POST 保存 → HTTP 200 + 「配置已写入」
2. 地址归一化（`192.0.2.50` → `mqtt://192.0.2.50:1883`）+ `status` JSON
3. 重开配置页：服务器/用户名/令牌/启用勾选回填正确
4. 口令码错误 → HTTP 404
5. 停机 + 打印日志

> 替身只负责 `WebConfigServer` 依赖的那几个接口；真机实现见 `../../src/storage/ConfigStore.cpp` 等。
> 改 `WebConfigServer.{h,cpp}` 后请重跑本冒烟（见 `docs/HA-CONFIG-WEB.md` §5）。
