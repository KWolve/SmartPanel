# -*- coding: utf-8 -*-
"""MCP open 版版本号 + 版本史（MCP_FEATURES）追加一条：小程序传图/视频对接方案入库。"""
import re

P = r'C:\Users\zkswe\.openclaw\workspace\tools\FlyThings_mcp_open\kb_tools.py'
OLD = '0.27.111-open'
NEW = '0.27.112-open'

ENTRY = (
    "'2026-09-24: **小程序传图/视频对接方案入库（相册传输模式）** v0.27.112-open"
    "（钟工：`小程序传输对接指南.zip` 是相册传输模式下的对接方案，已在其他产品上验证过，先入库、开干后再用）——"
    "① **知识文档**：新增 `knowledge/devflow/mp-transfer-miniprogram.md`（协议速查表 / ACK 规则 6 条不可改边界 / "
    "设备端实现要点（广播与 `handleClient` 代码摘录）/ 移植清单（`base::Task`/`MP_PATH`/媒体缓存怎么替）/ PC 模拟验证 / "
    "协议边界 / 12 条联调清单 + 检索词）② **源码归档**：新增 `components/mp_transfer/`（`README.md` 协议速查 + "
    "`src/mp_transfer/broadcast_task.{h,cpp}` · `tcp_receive.{h,cpp}` · `runtime_coordinator.h` + "
    "`src/system/transfer_type_and_data.h` + `src/python/receiver.py`（PC 模拟设备端，纯标准库）+ "
    "`docs/miniprogram-transfer-guide.md` 指南全文；示例 IP 已做占位符化，过隐私闸门）③ **口径要点**：设备主动 UDP 广播 "
    "`255.255.255.255:8899`（每 ≈2 s，正文 `zkswe:<设备名>`，无换行）→ 小程序用报文来源 IP 连 TCP `9000`；"
    "包头 `type(uint8)+len(uint32 大端)`，文件包再接 `nameLen(uint16)+filename(UTF-8,1..256B)` + 文件体；"
    "32 KiB 分块，**非末块**回 `ACK <累计字节>\\n`、**末块**校验落盘后回 `OK\\n`（≤32768 B 无分块 ACK、整数倍同理）；"
    "设备端 socket 阻塞超时 2 s（**不是整文件限时**）；一个连接可连续收多文件；先写 `.tmp` 再校验改名；"
    "**无版本协商/认证/CRC/断点续传，仅适合可信局域网**；落地目录 = 原工程 `config.h` 的 `MP_PATH`（移植换自己可写目录、末尾带 `/`）"
    "④ 实测依据：`F133UhaleAlbum` 设备端提交 `39c25c1`（2026-09-24），附带 Python 接收端已由项目维护者用**上线小程序**验证通过；"
    "v0.27.112-open',\n"
)


def main():
    t = open(P, encoding='utf-8').read()
    assert "MCP_VERSION = '%s'" % OLD in t, 'MCP_VERSION 未找到'
    t = t.replace("MCP_VERSION = '%s'" % OLD, "MCP_VERSION = '%s'" % NEW, 1)
    m = re.search(r'MCP_FEATURES = \[\n', t)
    assert m, 'MCP_FEATURES 未找到'
    t = t[:m.end()] + '    ' + ENTRY + t[m.end():]
    open(P, 'w', encoding='utf-8').write(t)
    print('MCP_VERSION -> %s' % NEW)
    print('MCP_FEATURES 首条:', ENTRY[:70].replace('\n', ''))


if __name__ == '__main__':
    main()
