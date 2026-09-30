# -*- coding: utf-8 -*-
"""拼墙「零配置」配套：主机低频心跳广播（钟工 2026-09-29 20:26）

背景：v7.10 起主机只给**登记过的从机单播** epoch（组内不刷广播）；从机没配
      `sp_wall_peer` 时靠 ≥3s 一次的广播 `wall?` 探针自报家门 —— 现场实测这条
      广播探测不一定能到主机（AP 客户端隔离等）→ 从机永远 `epoch=0 等待主机`。
做法：主机在每次 publishEpoch 时，除单播给已登记 peer 外，**每 3s 额外广播一包
      epoch**（1 包/3s/组，量很小）→ 从机无需任何配置即可拿到 epoch/时钟。

改动：WallLink.h 加 `mLastHbMs`；WallLink.cpp 的 publishEpoch() 末尾加低频广播。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1) 头文件：加成员
ph = os.path.join(ROOT, 'src', 'wall', 'WallLink.h')
t = io.open(ph, encoding='utf-8').read()
anchor = '    long long mT0Ms = 0;        // epoch（墙钟 ms）'
assert anchor in t, 'WallLink.h 锚点未找到'
add = anchor + '\n    long long mLastHbMs = 0;      // 主机低频广播心跳（v7.14：每 3s 一包，零配置可发现）'
t = t.replace(anchor, add, 1)
io.open(ph, 'w', encoding='utf-8').write(t)
print('patched', ph)

# 2) cpp：publishEpoch 末尾追加低频广播
pc = os.path.join(ROOT, 'src', 'wall', 'WallLink.cpp')
t = io.open(pc, encoding='utf-8').read()
old = '''    sendEpochToPeers(b);        // v7.10：只单播给本组从机（不再广播）
}'''
new = '''    sendEpochToPeers(b);        // v7.10：只单播给本组从机（不再广播）
    // v7.14（钟工 2026-09-29 20:26「零配置」）：再补一包**低频广播**（每 3s，1 包/组），
    //   让没配 sp_wall_peer 的从机也能发现主机（现场：广播探针不一定到得了主机）。
    if (t - mLastHbMs >= 3000) {
        mLastHbMs = t;
        sendUdp(b);
    }
}'''
assert old in t, 'WallLink.cpp 锚点未找到'
t = t.replace(old, new, 1)
io.open(pc, 'w', encoding='utf-8').write(t)
print('patched', pc)
