# -*- coding: utf-8 -*-
"""mp_transfer 移植适配：①加 mp_config.h（MP_PATH）②tcp_receive.cpp 去掉原工程 FileParseManager 依赖，
改用本地 buildFileInfo（path/name/category/size/mtime）。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MP = os.path.join(ROOT, 'src', 'mp_transfer')

# ① 配置头：MP_PATH 必须与「屏保视频」列表扫描目录一致（相册上传内容 -> 列表自动同步）
open(os.path.join(MP, 'mp_config.h'), 'w', encoding='utf-8').write('''#ifndef MP_TRANSFER_MP_CONFIG_H_
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
''')
print('wrote src/mp_transfer/mp_config.h')

# ② tcp_receive.cpp 适配
p = os.path.join(MP, 'tcp_receive.cpp')
t = open(p, encoding='utf-8').read()
assert '#include "mtp_monitor/file_parse_manager.h"' in t
t = t.replace('#include "mtp_monitor/file_parse_manager.h"\n', '')
t = t.replace('#include "config.h"', '#include "mp_config.h"')
t = t.replace('auto file_info = FileParseManager::instance().parseFile(path);',
              'auto file_info = buildFileInfo(path);')
t = t.replace('auto file_info = FileParseManager::instance().parseFile(filepath);',
              'auto file_info = buildFileInfo(filepath);')
assert 'FileParseManager' not in t, '还有 FileParseManager 残留'

helper = '''#include <cctype>

// 原工程用 FileParseManager 解析媒体信息；我们只关心 路径/名字/类别/大小 -> 本地实现即可
static FileCategory categoryOf(const std::string& name) {
	size_t dot = name.find_last_of('.');
	std::string ext = (dot == std::string::npos) ? "" : name.substr(dot + 1);
	for (size_t i = 0; i < ext.size(); i++) ext[i] = (char)tolower((unsigned char)ext[i]);
	static const char* kPhoto[] = { "jpg", "jpeg", "png", "bmp", "gif", "webp" };
	static const char* kVideo[] = { "mp4", "avi", "mkv", "mov", "3gp", "ts", "flv" };
	for (size_t i = 0; i < sizeof(kPhoto) / sizeof(kPhoto[0]); i++) if (ext == kPhoto[i]) return FileCategory::PHOTO;
	for (size_t i = 0; i < sizeof(kVideo) / sizeof(kVideo[0]); i++) if (ext == kVideo[i]) return FileCategory::VIDEO;
	return ext.empty() ? FileCategory::UNKNOWN : FileCategory::UNSUPPORTED;
}

static TransferFileInfo buildFileInfo(const std::string& path, bool is_live = false) {
	TransferFileInfo info;
	info.path = path;
	size_t slash = path.find_last_of('/');
	info.name = (slash == std::string::npos) ? path : path.substr(slash + 1);
	info.category = categoryOf(info.name);
	struct stat st;
	if (stat(path.c_str(), &st) == 0) {
		info.size = (uint64_t)st.st_size;
		info.last_modified = (long)st.st_mtime;
	}
	info.is_live = is_live;
	return info;
}

void TcpReceiveTask::scanPath(const std::string& root_path) {'''
t = t.replace('void TcpReceiveTask::scanPath(const std::string& root_path) {', helper, 1)
open(p, 'w', encoding='utf-8').write(t)
print('patched src/mp_transfer/tcp_receive.cpp (FileParseManager -> buildFileInfo)')
