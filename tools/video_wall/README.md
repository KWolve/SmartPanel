# 多屏拼接切块工具（PC 端，配套 ffmpeg）

> 用途：把一条"整墙"视频按时**横向裁剪**成 N 段，每段 = 单台 Z20 面板的分辨率（480×480），
> 让 N 台面板各播自己那段、拼起来就是完整画面（多屏联动）。
> 钟工口径（2026-09-25）：**参数完全一样**才不会各行其是。
> 钟工口径③（2026-09-27 11:55）：**绿框 = 唯一裁剪窗口**
> - **没有"缝"（bezel）这个概念**：数学里恒为 0、UI 不暴露、**不画橙色斜纹、没有"丢弃区"**；
> - N 个 480×480 绿框**相邻无缝**，它们的并集就是裁剪窗口；**框组以外的画面直接丢弃**；
> - 交互只有两件：**拖框组**（改裁剪原点）+ **缩放**（改框组相对视频的大小）；视频画面固定不动；
> - 框组被钳制在视频内 → **结构上不可能出现黑边**（也就不需要缺口/黑边开关）；
> - 导出 = 框内所见（同一时间点逐像素对齐）。
> 口径⑤（2026-09-28，**本版 v3**）：**每个屏幕的窗口可以独立移动**
> - 理由：面板拼在一起时有**物理拼缝**，整组刚性位移没考虑它；
> - 交互：**拖某一屏的框 = 只动那一屏**（拖空白处 / 按住 Alt / 勾「拖整组」= 整组一起动）；
>   滚轮/缩放条永远改**整组大小**（各屏边长一致 → 缩放一致，画面才对得上）；
> - **屏缝**（bezel 补偿）：相邻两屏之间可留 N px，缝内的源画面**不导出（丢弃）**；
>   **缝 = 0（默认）且连着摆时与旧口径逐像素一致**（后端自动按旧单框滤镜链导出）；
> - 右栏新增：**清空设备内的视频**（拼接素材 / 屏保视频 / 相册 / 全部；默认先预览不删）；
>   分发时还可勾「推送前先清空旧拼接素材」。
> 口径④（2026-09-27 16:xx，**本版 v2**）：**一个组 = 多个视频轮播**
> - 组里每个视频 = 一个 **clip**（c1…cK，可改名），各 clip **各自摆框、长短不限**（这就是"播放时长没有约束"）；
> - 同一 clip 内 N 段必须**等长、参数完全一致**（这才是各屏能对齐的前提）；
> - 组目录里 **必须**写 `playlist.json`（v2 清单，见下）；同时保留写 `wall.json`（v1 兼容壳）；
> - 旧布局（组目录直接放 `seg_<idx>.mp4`、没有 playlist.json）**继续支持**，`/api/split` 语义不变。

## 依赖
- `ffmpeg` / `ffprobe`（已在 PATH；本机 8.1.1）— 工具本体**不需要任何 Python 三方库**
- 验收脚本 `web/verify_roundtrip.py` 会用 `PIL`（可选，缺失时退化为 ffmpeg 独立复算）与
  `node` + 系统 Edge/Chrome（方法②截图；缺 node/浏览器时加 `--no-shot` 跳过）

## 两种用法

### A. 网页交互（推荐：所见即所得）
```bash
python web/server.py --host 0.0.0.0 --port 8796      # 局域网：http://192.0.2.188:8796/
```
**四步**：
1. **导入视频**：选文件（或直接把视频**拖到页面上**）；上传有进度条。已导入过的视频在「已导入」里
   **点一下就加入队列**（不用重传）；右侧 × 可从导入目录删掉（同时从队列移除）。
2. **组的视频队列**（= 轮播顺序）：一个视频 = 一个 **clip**，点视频名即可入队；每行可
   **改名**（= 设备上的子目录名，非法字符自动清洗 + 重名自动去重）/ **↑↓ 上下移** / **✕ 删除**；
   点一行 = 选中它摆框（缩略图 / 分辨率 / 时长 / 当前 crop 都显示在行里）；
   还有「当前框套用全部」「清空队列」。多个 clip 时长**可以不一样**。
   > clip 名 = 设备上的子目录名（= playlist 里 `file` 的前缀），**只允许字母/数字/`_.-`**（首字符字母或数字）：
   > 中文/空格/符号会被自动清洗（如 `开场 Intro` → `Intro`，中文会被去掉）、重名自动加 `_2`；
   > 自动名是 `c1..cK`（随队列顺序重编；手工改过名的保持不动）。组名则允许中文。
3. **摆框**（对当前选中的那个 clip）：视频画面固定不动，**每屏的绿框可以各自独立拖动**
   （拖框 = 只动那一屏；拖空白 / Alt / 勾「拖整组」= 整组一起动），**滚轮/缩放条 = 改窗口大小**；
   **屏缝**输入 = 相邻两屏之间留 N px（缝内源画面不导出 = 丢弃，用于补偿物理拼缝）；
   还有「铺满（最大框）」「居中」「±10%」「重置」「对齐 y」、外框精确输入、方向键微调。
   底部实时显示**每屏窗口 + 外框（旧 crop 口径）+ 缝**、缩放 ×(输出÷源) / 每段 480×480 / 编码参数。
   **每个 clip 各存各的窗口组**。
4. **导出整组** → `c1/seg_1..N.mp4、c2/seg_1..N.mp4 …` + `playlist.json` + `wall.json`
   （左侧卡片**按 clip 分组**：clip 名 / 时长 / 段列表 / 每段缩略图与大小 / 下载 + 打开输出目录）；
   再「扫描设备 / 一键分发整组」。已导出过的分组在⑦里点一下即可重新分发（v2 组会列出每个 clip）。

**组名**：在④导出那一行填（默认取第一个源片名，非法字符自动清洗，如 `zksw wall/组:1` → `zksw-wall-组-1`），
写进 `playlist.json` 的 `group`，也是设备上 `/mnt/sdnand/wall/<组名>/` 的目录名；改动会记进 localStorage。

**顺手能用的交互**（2026-09-27 15:0x 优化）：
- **时间轴**：拖一下即刷新预览帧（防抖 + 帧缓存），另有 ◀帧/帧▶ 逐帧按钮 → 可沿全片检查裁剪；
- **显示绿框/压暗** 开关（不想被框挡住看画面时关掉）；
- **快捷键**（点一下画面后生效）：方向键微调 **2px**（Shift = 20px；裁剪矩形必须偶数对齐，
  最小步长就是 2px）——**只动当前选中的那一屏**，**Alt + 方向键 = 整组**；
  `+`/`-` 缩放、`M` 铺满、`C` 居中、`[`/`]` 前后一帧；
- **记忆**：分割数量 / 组名 / 设备列表 / 绿框开关写 localStorage，下次打开自动带出；
- 窄屏（<1000px）自动变单列。

> 自动化/回归接口挂在 `window.VW`（`crop()/setCrop()/maxCrop()/setViewWidth()/canvasRect()/K()/setOverlay()`
> 等**名字一律没改**；v3 新增：`frames()/setFrames()/sel()/setSel()/moveFrame()/nudge()/gap()/setGap()/`
> `alignY()/regular()/perScreen()/setSide()/clearDevices()`；v2 的 `queue()/addClip()/…/exportGroup()` 照旧）。
> URL 参数新增 `?frames=200:80:520:520;760:120:520:520`（每屏一个窗口，分号/竖线分隔）。

### B. 命令行
```bash
# ① 生成测试用整墙视频（带 P1..PN 标号 + 帧号 + 时间码，便于肉眼验证帧对齐）
python split_wall.py sample --out sample_960x480.mp4 --cols 2 --seconds 20

# ①' 每屏独立窗口（可留缝）：帧列表用分号分隔（每屏一个 x:y:w:h）；缝 = 相邻两屏之间那段
python split_wall.py group --src a.mp4 --cols 3 --group-name gapwall \
       --frames "120:80:400:400;600:140:400:400;1000:60:400:400"
#   缝 = 0 且连着摆（regular）时后端自动走旧单框口径 → 与旧版逐像素一致

# ② 单视频裁剪切分（默认 mode=crop，绿框语义，**无缝、无 pad、无黑边**；旧接口行为不变）
python split_wall.py split --in src.mp4 --cols 2 --out-dir wall2
#   常用可选参数：
#     --crop 128:66:1024:512   直接给源裁剪矩形 x:y:w:h（须 w = N×h），优先于下面的
#     --zoom 0.9375            缩放（输出像素/源像素）：>1 放大（框更小）、<1 缩小（框更大）
#     --pos 640:360            框组中心在源上的坐标（默认居中）
#                              默认（都不给）= 最大框组居中，即网页的「铺满（最大框）」
#     --fps 25 --gop-sec 1 --crf 20 --bitrate 3000k --preset medium --quiet
#     --profile main|high --vcodec libx264|libx265
#     --audio-index 0          只让第 1 段带音频，其余静音；不给=全部静音
#     --mode direct            老式等分（源正好 = N×480×480 时一把切）
#   ⚠ 已删除：--bezel / --allow-black / --mode insert|discard（旧"缝"与补黑边概念去掉；
#      新口径的"屏缝"= 每屏独立窗口 frames 之间的间距，见 ①'）

# ②' 多视频成组（v2：一个组 = 多个视频轮播；每个源各自摆框、长短不限）
python split_wall.py group --in a.mp4 --in b.mp4 --cols 2 --group-name zksw-wall --out-dir out/g1
python split_wall.py group --src a.mp4 b.mp4 c.mp4 --cols 3 \
       --crop 1=128:64:1024:512 --crop 3=0:0:960:480     # 逐 clip 裁剪（不带 k= → 所有 clip）
#     --clip-name 1=start,2=intro                          逐 clip 改名（缺省自动 c1..cK）
#   产物：out/g1/{playlist.json, wall.json, c1/seg_1..N.mp4, c2/seg_1..N.mp4, …}
#         每组打印每个 clip 的时长与总时长（总时长 = Σ clip 时长）

# ③ 校验（参数是否完全一致 / 首帧是否 IDR / 帧数与时长是否相同）
python split_wall.py verify --dir wall2            # 单视频（旧布局）
python split_wall.py verify --dir wall2/c1         # 组里某个 clip 的段

# ④ 下发到设备（整组递归推送；--dry-run 只看不推，**不碰任何设备**）
python distribute.py push --group-dir out/g1 --group zksw-wall \
       --devices 192.0.2.108=1,192.0.2.71=2
python distribute.py push --group-dir out/g1 --group zksw-wall --devices 192.0.2.108=1 --dry-run
python distribute.py push --group-dir out/g1 --group zksw-wall --devices 192.0.2.108=1 --clear  # 先清旧拼接素材
python distribute.py push --seg-dir out/wall2 --group zksw-wall --devices 192.0.2.108=1,192.0.2.71=2  # 旧单视频（兼容）

# ④' **清空设备上的视频素材**（默认只看不删；真删要 --yes）
python distribute.py clear --devices 192.0.2.108,192.0.2.71 --scope all --dry-run   # 统计将删内容
python distribute.py clear --devices 192.0.2.108 --scope wall --yes                    # 真删（拼接素材）
#     --scope wall|video|album|all = 拼接素材 / 屏保视频 / 相册 / 全部
#     真删流程：停应用 → rm -rf <目录>/*（保留目录）→ 复位 sp_wall_en/sp_video_sel → 重启应用

# ⑤ 程序化验收
python selfcheck_crop.py                 # CLI：无黑边 + 分区无缝（无丢弃列）+ 段一致 + 无 pad
python selftest_group.py                 # ⭐多视频组：布局/playlist 自洽/段一致/总时长/v1 壳/旧布局回归
python selftest_clear.py                 # ⭐清空设备视频：真机临时目录验收（dry-run 不删 / 真删 / 复位配置）
python web/smoke_api_crop.py             # 网页后端 HTTP 冒烟（自起 8797 临时实例；含 frames/缝 + /api/clear）
python web/verify_roundtrip.py           # ⭐「所见=所出」两种独立方法 + 交互自检 + 边界无黑边 + 每屏独立窗口(缝)
python web/verify_roundtrip.py --no-shot # 只跑方法①（不依赖 node/浏览器）
node web/shoot_box.mjs --url "http://127.0.0.1:8796/?src=x.mp4" --uitest   # 页面级 UI 自检（含队列/组名）
node web/shoot_box.mjs --url "..." --eval "window.VW.queue()"              # 就绪后跑一段页面 JS
```

## "所见 = 所出" 的证据（`out/_evidence/`，可复现）

判据：**绿框里显示什么，导出的那段就是什么**（同一时间点逐像素对齐）；源片是合成的
**刻度网格 + 色块 + 帧号 + 运动块 + 24px 亮边框**（无损 qp0，1280×720）。
用例故意取 **非平凡位置 + 非 1.0 缩放**：`cols=2, crop=[128,64,1024,512]`（缩放 ×0.9375）。

| 方法 | 做法 | 结果（RGB 逐像素差） |
|---|---|---|
| ① 源侧独立复算 | **PIL** 独立做 `crop→LANCZOS 缩放→切片`，与导出段首帧比 | seg_1 **mean 1.53 / p99 20**，seg_2 **mean 1.14 / p99 16**（p50=0） |
| ① 控制组 A | 只换重采样器（**ffmpeg 手写链** vs PIL，同一几何） | mean **1.39** / p99 12 → 说明上面那点差主要来自**重采样器**，不是裁剪几何算错 |
| ② 所见侧 | **headless 浏览器**（Node+CDP，系统 Edge/Chrome）把网页**绿框区域 1:1 截出来**，与"导出段首帧横排"比 | 整排 **mean 1.99 / p99 20**；seg_1 2.20 / seg_2 1.78 |
| ② 分辨力自检 | 把截图右移 2px 再比 | mean **8.83**（≈4.4× 正常值）→ 比对确实有像素级分辨力 |

其它几项（都在 `verify_seen_vs_exported.json` / `selfcheck_crop_report.json`）：
- **缩放/编码带来的残差**：`crf 20` 有损编码 + 三方重采样器（浏览器/PIL/ffmpeg）各自核不同；
  实测残留集中在硬边缘（`max 92/96`，p99 ≤ 22），容忍阈值取 `mean ≤ 6 / p99 ≤ 22`。
- **交互自检**（真发鼠标/滚轮事件）：拖框移动框组 ✓、拖到画面外被**钳制在视频内** ✓、
  滚轮缩放时光标处同一相对位置保持不动（u 0.479→0.480）✓、缩到极限 = 最大框 ✓。
- **边界/无黑边**：框贴左上角 / 右下角导出 → 视频最外沿的 2px 亮度 **112.1 / 107.4 / 121.2 / 122.1**
  （亮），且与源对应位置**偏差 ≤ 0.47 luma**（像素级）→ 外沿就是源画面，不是合成黑边。
- **段一致性**：每段 480×480、参数完全一致、首帧 IDR@pts0、`+faststart`、滤镜链无 `pad=`。
- **分区无缝**（`selfcheck_crop.py` B）：无损灰阶 ramp 逐列比对 **MAE 0.179 luma**；
  seg_1 末列→seg_2 首列跳变 **0.00 luma**（= 一个正常采样步长，**没有**被丢弃的列）。

## 网页后端接口（web/server.py，零三方依赖）
| 接口 | 作用 |
|---|---|
| `GET /` | 页面 |
| `POST /api/upload` | 上传源片（XHR 带 `X-Filename`；页面侧有进度条） |
| `GET /api/list` | 已导入源片（含 `bytes` + 分辨率/时长/fps，带 stat 缓存） |
| `GET /api/info?src=` | 单个源片信息 |
| `GET /api/frame?file=&w=&t=` | 抽帧 PNG（源片预览 / 分段缩略图；`file` 支持 `组/c1/seg_1.mp4` 子路径） |
| `POST /api/group_split` | **v2 整组导出**：`{clips:[{file,name,frames|crop}], cols, group_name}` → `c1..cK + playlist.json + wall.json`（逐 clip 预检，失败不留目录）。`frames=[[x,y,w,h]×N]` = 每屏独立窗口（可留缝）；无缝连着摆时自动等价回旧 `crop` 口径 |
| `POST /api/split` | **旧语义保留**：单视频切分（`{file, cols, crop}`，crop 原样使用；v1 布局：根目录 `seg_i.mp4` + `wall.json`，不写 playlist.json） |
| `GET /api/out` | 已导出分组（`groups` 字符串数组保留；另给 `info[]`：是否 v2 / clip 数 / 段数 / 组名 / 总时长） |
| `GET /api/manifest?group=` | 读某组 `wall.json`（v1 壳）+ `playlist`（有则带回）（重新分发用） |
| `GET /api/playlist?group=` | 读某组 `playlist.json`，`with_files` 会标明每段是否存在与大小；旧布局返回 404+`legacy:true` |
| `GET /api/download?group=&file=` | 下载某段（支持 `c1/seg_1.mp4` 子路径；路径穿越已拦） |
| `POST /api/drop` | 从导入目录删掉一个源片 |
| `POST /api/drop_group` | **删掉一个已导出的分组**（整目录：`cN/seg_i.mp4` + `playlist.json` + `wall.json`）→ `{ok,group,files,bytes,removed}`；`dry_run:true` 只看不删；`_src` 与越界名字一律 404 |
| `POST /api/reveal` | 在资源管理器里打开输出目录（本机工具） |
| `GET /api/scan` · `POST /api/push` · `POST /api/status` | 设备扫描 / 分发 / 核对播放；`/api/push` **自动判模式**：组目录有 `playlist.json` → 整组递归推送，否则走旧单视频（返回 `mode`）；可带 `clear_wall:true` 先清旧拼接素材 |
| `POST /api/clear` | **清空设备上的视频素材**：`{devices:[ip], scope:'wall'\|'video'\|'album'\|'all', dry_run:bool}` → 每台 `{ok,before{files,bytes},after,…}`；`dry_run=true` 只看不删 |

## 为什么这样切（对齐的物理前提）
1. **段与段时间轴严格一致**：同源帧 + **完全相同的一套编码参数**分别编码 → 帧数/fps/时长/关键帧位置逐段相同；
   各面板独立解码时，只有时间轴一致，上层"同一时刻同一帧"的相位对齐才成立。
2. **每段首帧是 IDR**：起播 / `seekTo()` 到段内任意点都能立刻出画，不必等关键帧。
3. **无 B 帧（`-bf 0`）**：解码顺序 = 显示顺序，seek 与逐帧对位都更准、延迟更低。
4. **固定 GOP（默认 1s 一个关键帧）**：纠偏 `seek` 的落点更密集，收敛更快。
5. **`+faststart`**：moov 前置，设备起播不用先扫全文件。
6. **切块规范**：各段等长、无丢帧、段边界避开极端高动态画面（可留 1~2 帧重叠）。

## 几何与滤镜（唯一事实源）
```
画布 = N×480 宽 × 480 高
唯一事实源（v3）：frames = N 个方框 [x_i,y_i,s,s]（源像素；各屏边长一致 s = 480/缩放）
   · 缝 gap_i = x_{i+1} − (x_i + s)，可为 0；缝内的源画面**不输出**（丢弃）
   · 缝隙全 0 且同 y 连着摆（regular）→ 与旧口径逐像素一致；"外框"= 各框并集（旧 crop 口径）
唯一事实源（≤v2 旧口径，仍兼容）：crop = [x, y, w, h]（源像素，恒 w = N×h）
滤镜链（旧口径 / regular，第 i 段）：crop(w:h:x:y) → scale(N×480 : 480 : flags=lanczos) → crop(480:480:i*480:0)
滤镜链（每屏独立窗口 / 非 regular，第 i 段）：crop(s:s:x_i:y_i) → scale(480:480:flags=lanczos)
    · 不许出现 pad；每屏边长必须一致（不一致 → 直接拒绝：各屏缩放不同、拼起来对不上）
    · 每个窗口恒被钳制在源内 → 结构上不可能有黑边
前端 alignCrop/maxCrop/framesToRect 与后端 split_wall.py **逐行同式**：
    · 前端把每屏窗口 **原样**发 /api/group_split 的 frames；后端只做偶数对齐+钳制（正规形是恒等），
      并把**真正生效**的窗口回给前端显示 → 画框与导出用同一组矩形，不会两套映射打架。
    · maxCrop：h = min(源高, 源宽/N)，w = N×h（"铺满"档 = 默认）
    · 源小于单屏 480×480 时前端直接禁导出并提示
```
> 相机侧提示：源片**自带**的 letterbox 黑边不会自动消失（工具只保证不"自己造"黑边）；
> 现场让用户放大到黑条出框即可（框外即丢弃）。

## Z20（SigmaStar SSD201/SSD202）编码参数建议
| 项 | 建议值 | 说明 |
|---|---|---|
| 编码 | H.264（`libx264`） | 兼容性最好；SSD202D 另支持 H.265 4M，可作备选 |
| Profile/Level | **Main / 4.0** | 硬件解码通常支持 High，Main 更稳 |
| 像素格式 | **yuv420p** | 硬件解码只吃 420 |
| 分辨率 | 480×480 / 段 | 与面板一致，避免解码后缩放 |
| 帧率 | 25（或 30） | **注意**：当前固定 25fps；源 24/30fps 会被重采样（时间轴仍逐段一致） |
| B 帧 | **0** | seek/对齐友好 |
| 关键帧 | 每 1s | `-g 25`（25fps） |
| 码率 | CRF 20 或 2~4 Mbps | 480×480 足够 |
| 音频 | 默认全段静音 | 需要声音用 `--audio-index` 只让一段带音轨 |

## 组清单 playlist.json v2（**工具 ↔ 固件的唯一契约**，勿改字段名）

磁盘布局（工具产出 == 设备 `/mnt/sdnand/wall/<组名>/`）：
```
playlist.json                     ← v2 清单（必须写）
c1/seg_1.mp4 … c1/seg_N.mp4       ← 第 1 个视频切成 N 段（每段 480×480）
c2/seg_1.mp4 … c2/seg_N.mp4       ← 第 2 个视频（段数同 cols，时长可不同）
wall.json                         ← v1 兼容壳（保留写，给旧版/其它读者）
```
> 另外每个 `cN/` 里还有一份 v1 的 `cN/wall.json`（该 clip 的完整旧式清单：crop/filter/md5…），
> 供旧读者或排查用，不影响固件；删除也无害。

`playlist.json`（严格这样写，键序即下表顺序）：
```json
{
  "version": 2,
  "group": "zksw-wall",
  "n": 2,
  "cols": 2,
  "total_ms": 10000,
  "clips": [
    {"name": "c1", "dur_ms": 4000, "segments": [
        {"index": 1, "file": "c1/seg_1.mp4", "dur_ms": 4000},
        {"index": 2, "file": "c1/seg_2.mp4", "dur_ms": 4000}]},
    {"name": "c2", "dur_ms": 6000, "segments": [
        {"index": 1, "file": "c2/seg_1.mp4", "dur_ms": 6000},
        {"index": 2, "file": "c2/seg_2.mp4", "dur_ms": 6000}]}
  ]
}
```
| 字段 | 含义（**固件侧按此实现**） |
|---|---|
| `version` | 恒 `2` |
| `group` | 组名（= 目录名，工具已清洗路径非法字符） |
| `n` | **组内 clip 数**（轮播几个视频）= `len(clips)` |
| `cols` | **每个 clip 的段数 = 屏数 N**（同一 clip 内 N 段同时播、各占一屏） |
| `total_ms` | **一整轮轮播时长** = Σ `clip.dur_ms` |
| `clips[]` | 按**轮播顺序**排；`name` = 子目录名（与 `file` 前缀一致） |
| `clip.dur_ms` | 该 clip 的播放时长（同 clip 内各段等长，所以等价于单片时长） |
| `segments[]` | `index` 从 1 连续到 `cols`；`file` = 相对组目录的路径；`dur_ms` = 该段时长 |

播放语义：第 i 号面板（i=1..cols）依次播 `clips[0].name/seg_i.mp4`（`clips[0].dur_ms`）→
`clips[1].name/seg_i.mp4`（`clips[1].dur_ms`）→ … 循环；各面板**同时**切到下一个 clip。

`wall.json`（v1 兼容壳）：字段与单视频版一致，但
- `segments` = **第 1 个 clip** 的分段（旧语义 `segments[i]` = 第 i 屏那段），`file` 写真实相对路径 `c1/seg_i.mp4`；
- 另加 `seg_ms`（= 第一片时长，旧 `distribute` 直接读它/flavor）、`total_ms`、`clips[]` 概览、
  `playlist: "playlist.json"`、`note` 说明。旧版固件/读者拿它仍能拿到"自己那一屏播多久"。

读取兼容：`split_wall.load_group(目录)` 统一返回 v2 形状；**旧布局**（只有 `wall.json`、根目录 `seg_i.mp4`）
也能读（`legacy: true`，1 个 clip，时长 = 单片时长、不是 ΣN 片）。

## 上机目录约定（联动资源与屏保资源分开）
```
/mnt/sdnand/wall/<组名>/playlist.json       ← v2 清单（固件必读）
/mnt/sdnand/wall/<组名>/wall.json           ← v1 兼容壳
/mnt/sdnand/wall/<组名>/c1/seg_1.mp4 … seg_N.mp4   ← 第 1 个视频的 N 屏片段
/mnt/sdnand/wall/<组名>/c2/seg_1.mp4 … seg_N.mp4   ← 第 2 个视频（时长可不同）
/mnt/sdnand/wall/<组名>/seg_1.mp4 … seg_N.mp4      ← 【旧布局】继续支持：组目录直接放段
/mnt/sdnand/video/…  /mnt/sdnand/album/…          ← 屏保资源（不含联动片段）
```
- 面板侧"多屏拼接"页只读 `<组名>` 目录；**失联时退回默认屏保视频**。
- 推送配置（`distribute.py push`，与 `wallLogic` 同口径）：`sp_wall_en/sp_wall_group/sp_wall_idx/`
  `sp_wall_n`（= 屏数）/`sp_wall_role`（首台=1）/`sp_wall_seg_ms`（**第一片时长**），
  `sp_video_sel` 指向本机第一片（`<组>/<第一个 clip>/seg_<idx>.mp4`；旧布局那么是 `<组>/seg_<idx>.mp4`）。

## 自测记录（本机，可复现）
| 排布 | 源分辨率 | 结果 |
|---|---|---|
| 1×2 | 960×480 | seg_1/2 = 480×480 h264 Main 750 帧 30.000s，首帧 IDR ✓ 参数完全一致 |
| 1×3 | 1440×480 | 3 段一致 ✓ |
| 1×4 | 1920×480 | 4 段一致 ✓ |
| 1×2 / 1×3 / 贴四角 / 任意框 | 1920×1080 亮边框 | 每段 480×480，**最外 2px 亮度 90~225（无黑边）**，参数一致 + 首帧 IDR ✓ |
| 1×2 | 1920×1080 无损 ramp | 逐列与几何预测 **MAE 0.179 luma**；段边界跳变 0.00（无缝）✓ |
| 1×2 crop=[128,64,1024,512] | 1280×720 刻度网格（无损） | 方法① mean 1.53/1.14，方法② mean 1.99，边界偏差 ≤0.47 luma ✓ |
| **v2 组 3 clip**（cols=2） | 1280×720 / 1920×1080 / 960×480 | 时长 **4s/6s/3s**，每 clip 2 段均 480×480、跨 clip 编码参数完全一致、首帧 IDR、无 pad；`total_ms=13000` = Σdur；逐 clip crop 各自生效；clip 内容不串（首帧互差 mean 20~49）✓ |
| **v2 旧布局回归** | 1280×720 | `split` 仍出根目录 seg_1/2 + wall.json（**不写** playlist.json）；`verify` 通过；`load_group()` legacy ✓ |
| **v3 每屏独立窗口 + 缝 40px** | 1280×720 刻度网格 | 每段 = **该屏自己窗口**的内容（PIL 独立复算 mean 1.26/1.49，p99 14/21）；拿"无缝位置"比 seg_2 **mean 17.0**（≈11×）→ 缝确实被跳过；越界窗口 → 钳制回源内 ✓ |
| **v3 清空设备视频** | 真机 192.0.2.108 | 临时目录 5 文件：dry-run 不删 ✓ / 真删后 0 个（目录保留）✓ / 先停后启应用 + 复位 sp_wall_en·sp_video_sel ✓ |

### v2 段落验收快照（`python selftest_group.py`，证据在 `out/_evidence/`）
```
[OK] 每个 clip 段数 == cols    [OK] Σ(clip.dur_ms) == total_ms (13000)
[OK] index 连续 1..cols         [OK] file 前缀 == clip 名 & 文件存在
[OK] 同 clip 内每段 dur_ms 相同  [OK] 各 clip 时长互不相同 [4000, 6000, 3000]
[OK] 每段 480×480              [OK] 跨 clip 编码参数完全一致 (h264/Main/L4.0/yuv420p/25fps)
[OK] 同 clip 内各段逐项相同      [OK] 每段首帧 IDR@pts0    [OK] 滤镜链无 pad / 无 pad 子串
[OK] 逐 clip 裁剪生效            [OK] 各 clip 首帧互不相同    [OK] 总时长 = Σ 源片时长
[OK] v1 壳 seg_ms == 第一片时长   [OK] 旧布局回归（split/verify/load_group legacy）
→ [PASS]  报告 out/_evidence/selftest_group_report.json
```
同类网页证据：`out/_evidence/uitest_8796.json`（页面 UI 自检 8 项）、
`out/_evidence/uitest_group_export.json`（页面排队→组名→导出整组→按 clip 分组卡片）、
`out/_evidence/page_ui_v4.png`（排版）、`verify_seen_vs_exported.json`（所见=所出）。

## 边界 / TODO
- 当前只做 **1×N 横向拼接**；2×2 等二维拼接需再扩（行列 + 上下切），有需求再加。
- 每屏窗口**边长必须一致**（同一缩放）——这是"拼起来对得上"的前提，不一致时后端直接拒绝。
- 屏缝只表达"相邻两屏之间丢弃多少源画面"；物理换算（mm→px）= 单屏宽(mm)×缝(mm)/单屏宽(mm)，
  现场用预览调即可。
- 源分辨率任意（自己裁）；旧 `--mode direct` 仍假设源 = `N × 480`。
- 网页端 `-r 25` 固定：源 24/30fps 会重采样（段段一致，不影响相位对齐；介意就先转 25fps）。
- 组内 clip 的**播放顺序 = 队列顺序**（自动名 c1..cK 会跟着顺序重编；手工改过名的保持不动）。
- 长度不同的 clip 之间切换时，各屏**同时**切（固件按 `dur_ms` 计时）；若某 clip 有音频，工具默认**全部静音**。
- `verify` 只做"一致性"静态校验；**真正的帧同步验收在设备上**（两个面板同拍一张图比帧号）——
  设备侧相位口径见 `references/kb/video-wall-sync.md`。
