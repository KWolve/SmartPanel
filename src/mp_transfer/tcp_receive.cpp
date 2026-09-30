/*
 * tcp_receive.cpp
 *
 *  Created on: 2026
 *      Author: asus
 */

#include "tcp_receive.h"

#include <algorithm>
#include <arpa/inet.h>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <exception>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <base/base.h>
#include <ctype.h>
#include <time.h>
#include "mp_config.h"
#include "utils/TimeHelper.h"

#define TCP_STATUS_READY        1
#define TCP_STATUS_OVER     0


namespace {

enum PacketType : uint8_t {
	TYPE_TEXT = 0,
	TYPE_IMAGE = 1,
	TYPE_VIDEO = 2,
	TYPE_LIVE = 3,
};

std::string socketErrnoText(int err) {
	if (err == 0) {
		return "none";
	}
	return std::string(strerror(err)) + "(" + std::to_string(err) + ")";
}

std::string recvFailReason(ssize_t n, int err) {
	if (n == 0) {
		return "peer closed";
	}
	if (err == EAGAIN || err == EWOULDBLOCK) {
		return "timeout";
	}
	return "recv errno " + socketErrnoText(err);
}

std::string sendFailReason(ssize_t n, int err) {
	if (n == 0) {
		return "send returned 0";
	}
	if (err == EAGAIN || err == EWOULDBLOCK) {
		return "timeout";
	}
	return "send errno " + socketErrnoText(err);
}

std::string makePeerText(const sockaddr_in& addr) {
	char ip[INET_ADDRSTRLEN] = {0};
	const char* res = inet_ntop(AF_INET, &addr.sin_addr, ip, sizeof(ip));
	if (res == nullptr) {
		snprintf(ip, sizeof(ip), "unknown");
	}
	return std::string(ip) + ":" + std::to_string(ntohs(addr.sin_port));
}

bool recvAll(int sock, void* buf, size_t len, const char* stage, const std::string& peer,
		bool log_peer_closed = true) {
	size_t received = 0;
	char* data = static_cast<char*>(buf);

	while (received < len) {
		ssize_t n = recv(sock, data + received, len - received, 0);
		if (n > 0) {
			received += static_cast<size_t>(n);
			continue;
		}
		if (n == 0) {
			if (!log_peer_closed) {
				LOGD("tcp receive: peer closed, peer=%s, stage=%s, progress=%zu/%zu",
						peer.c_str(), stage, received, len);
				return false;
			}
			LOGE_TRACE("tcp receive: recv failed, peer=%s, stage=%s, reason=%s, progress=%zu/%zu",
					peer.c_str(), stage, recvFailReason(n, 0).c_str(), received, len);
			return false;
		}
		if (errno == EINTR) {
			continue;
		}
		int err = errno;
		LOGE_TRACE("tcp receive: recv failed, peer=%s, stage=%s, reason=%s, progress=%zu/%zu",
				peer.c_str(), stage, recvFailReason(n, err).c_str(), received, len);
		return false;
	}
	return true;
}

bool sendAll(int sock, const void* buf, size_t len, const char* stage, const std::string& peer) {
	size_t sent = 0;
	const char* data = static_cast<const char*>(buf);

	while (sent < len) {
		int flags = 0;
#ifdef MSG_NOSIGNAL
		flags |= MSG_NOSIGNAL;
#endif
		ssize_t n = send(sock, data + sent, len - sent, flags);
		if (n > 0) {
			sent += static_cast<size_t>(n);
			continue;
		}
		if (n == 0) {
			LOGE_TRACE("tcp receive: send failed, peer=%s, stage=%s, reason=%s, progress=%zu/%zu",
					peer.c_str(), stage, sendFailReason(n, 0).c_str(), sent, len);
			return false;
		}
		if (errno == EINTR) {
			continue;
		}
		int err = errno;
		LOGE_TRACE("tcp receive: send failed, peer=%s, stage=%s, reason=%s, progress=%zu/%zu",
				peer.c_str(), stage, sendFailReason(n, err).c_str(), sent, len);
		return false;
	}
	return true;
}

bool sendPacketAck(int sock, uint32_t received, const std::string& peer) {
	char ack_buf[64] = {0};
	int ack_len = snprintf(ack_buf, sizeof(ack_buf), "ACK %u\n", received);
	if (ack_len <= 0) {
		return false;
	}
	return sendAll(sock, ack_buf, static_cast<size_t>(ack_len), "send packet ack", peer);
}

bool sendFinalOk(int sock, const std::string& peer) {
	static const char ok_buf[] = "OK\n";
	return sendAll(sock, ok_buf, sizeof(ok_buf) - 1, "send final ok", peer);
}

}  // namespace

std::vector<TransferFileInfo> TcpReceiveTask::getFileList(FileCategory category) {
	std::lock_guard<std::mutex> lock(mMutex);
	std::vector<TransferFileInfo> list;
	for (const auto& item : mFileCache) {
		if (item.category == category) {
			list.push_back(item);
		}
	}
	return list;
}

void TcpReceiveTask::refreshCache() {
	if (!base::exists(MP_PATH)) {
		base::mkdirs(MP_PATH, 0777);
	}
	cleanupTmpFiles(MP_PATH);
	scanPath(MP_PATH);
}

void TcpReceiveTask::removeCachedFiles(const std::vector<std::string>& filepaths) {
	if (filepaths.empty()) return;

	std::lock_guard<std::mutex> lock(mMutex);
	mFileCache.erase(
			std::remove_if(mFileCache.begin(), mFileCache.end(),
					[&filepaths](const TransferFileInfo& info) {
						return std::find(filepaths.begin(), filepaths.end(), info.path) != filepaths.end();
					}),
			mFileCache.end());
}

void TcpReceiveTask::addListener(TcpReceiveListener* listener) {
	std::lock_guard<std::mutex> lock(mListenerMutex);
	if (listener == nullptr) {
		return;
	}
	auto it = std::find(mListeners.begin(), mListeners.end(), listener);
	if (it == mListeners.end()) {
		mListeners.push_back(listener);
	}
}

void TcpReceiveTask::removeListener(TcpReceiveListener* listener) {
	std::lock_guard<std::mutex> lock(mListenerMutex);
	auto it = std::find(mListeners.begin(), mListeners.end(), listener);
	if (it != mListeners.end()) {
		mListeners.erase(it);
	}
}

void TcpReceiveTask::stop() {
	int server_fd = mServerFd.exchange(-1);
	if (server_fd >= 0) {
		LOGD("tcp receive: stop closing server socket, fd=%d", server_fd);
		shutdown(server_fd, SHUT_RDWR);
		close(server_fd);
	}

	int client_fd = mClientFd.exchange(-1);
	if (client_fd >= 0) {
		LOGD("tcp receive: stop closing client socket, fd=%d", client_fd);
		shutdown(client_fd, SHUT_RDWR);
		close(client_fd);
	}

	base::Task<TcpReceiveParams>::stop();
}

void TcpReceiveTask::beforeTask(const TcpReceiveParams& params) {
	(void)params;
	if (!base::exists(MP_PATH)) {
		base::mkdirs(MP_PATH, 0777);
	}
	mServerFd.store(-1);
	mClientFd.store(-1);
	clearCache();
}

void TcpReceiveTask::doTask(const TcpReceiveParams& params) {
try {
	LOGD("tcp receive task started");

	cleanupTmpFiles(MP_PATH);
	scanPath(MP_PATH);

	int server_fd = socket(AF_INET, SOCK_STREAM, 0);
	if (server_fd < 0) {
		LOGE_TRACE("tcp receive: socket create failed");
		return;
	}
	mServerFd.store(server_fd);

	defer {
		int fd = mServerFd.exchange(-1);
		if (fd >= 0) {
			close(fd);
		}
		cleanupTmpFiles(MP_PATH);
		clearCache();
		LOGD("tcp receive task exited");
	};

	int opt = 1;
	setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
#ifdef SO_REUSEPORT
	setsockopt(server_fd, SOL_SOCKET, SO_REUSEPORT, &opt, sizeof(opt));
#endif

	struct sockaddr_in addr = {0};
	addr.sin_family = AF_INET;
	addr.sin_addr.s_addr = INADDR_ANY;
	addr.sin_port = htons(params.listen_port);

	if (bind(server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
		LOGE_TRACE("tcp receive: bind failed");
		return;
	}

	if (listen(server_fd, 8) < 0) {
		LOGE_TRACE("tcp receive: listen failed");
		return;
	}

	while (isStarted()) {
		int current_server_fd = mServerFd.load();
		if (current_server_fd < 0) {
			break;
		}

		struct sockaddr_in client_addr = {0};
		socklen_t client_addr_len = sizeof(client_addr);
		int client_fd = accept(current_server_fd, (struct sockaddr*)&client_addr, &client_addr_len);
		if (client_fd < 0) {
			if (!isStarted() || mServerFd.load() < 0) {
				break;
			}
			if (errno == EINTR) {
				continue;
			}
			LOGE_TRACE("tcp receive: accept failed, errno=%s", socketErrnoText(errno).c_str());
			continue;
		}
		const std::string peer = makePeerText(client_addr);
		LOGD("tcp receive: client accepted, peer=%s, fd=%d", peer.c_str(), client_fd);

		try {
			configureClientSocket(client_fd, params.socket_timeout_ms);
			mClientFd.store(client_fd);
			{
				std::lock_guard<std::mutex> lk(mListenerMutex);
				for(auto listener : mListeners){
					try {
						listener->onTcpStateChanged(TCP_STATUS_READY);
					} catch (const std::exception& e) {
						LOGE_TRACE("tcp receive: state listener exception: %s", e.what());
					} catch (...) {
						LOGE_TRACE("tcp receive: unknown state listener exception");
					}
				}
			}
			handleClient(client_fd, params, peer);
		} catch (const std::exception& e) {
			LOGE_TRACE("tcp receive: client handling exception, peer=%s, error=%s", peer.c_str(), e.what());
			setActiveTmpPath("");
			int fd = mClientFd.exchange(-1);
			if (fd >= 0) {
				shutdown(fd, SHUT_RDWR);
				close(fd);
			}
			cleanupTmpFiles(MP_PATH);
		} catch (...) {
			LOGE_TRACE("tcp receive: unknown client handling exception, peer=%s", peer.c_str());
			setActiveTmpPath("");
			int fd = mClientFd.exchange(-1);
			if (fd >= 0) {
				shutdown(fd, SHUT_RDWR);
				close(fd);
			}
			cleanupTmpFiles(MP_PATH);
		}
	}
} catch (const std::exception& e) {
	LOGE_TRACE("tcp receive task exception: %s", e.what());
} catch (...) {
	LOGE_TRACE("tcp receive task unknown exception");
}
}

#include <cctype>

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

void TcpReceiveTask::scanPath(const std::string& root_path) {
	std::vector<TransferFileInfo> scanned_list;
	auto file_list = base::listFiles(root_path);

	for (const auto& file : file_list) {
		std::string path = file.string();
		if (isTmpFile(path)) {
			continue;
		}
		auto file_info = buildFileInfo(path);
		scanned_list.push_back(file_info);
	}

	{
		std::lock_guard<std::mutex> lock(mMutex);
		mFileCache = scanned_list;
	}
	{
		std::lock_guard<std::mutex> lock(mListenerMutex);
		for (auto listener : mListeners) {
			try {
				listener->onScanFinished(scanned_list);
			} catch (const std::exception& e) {
				LOGE_TRACE("tcp receive: scan listener exception: %s", e.what());
			} catch (...) {
				LOGE_TRACE("tcp receive: unknown scan listener exception");
			}
		}
	}
}

void TcpReceiveTask::clearCache() {
	std::lock_guard<std::mutex> lock(mMutex);
	mFileCache.clear();
}

void TcpReceiveTask::cleanupTmpFiles(const std::string& root_path) {
	std::string active_tmp_path = getActiveTmpPath();
	auto file_list = base::listFiles(root_path);
	for (const auto& file : file_list) {
		std::string path = file.string();
		if (!isTmpFile(path)) {
			continue;
		}
		if (!active_tmp_path.empty() && path == active_tmp_path) {
			LOGD("tcp receive: skip active tmp file cleanup, path=%s", path.c_str());
			continue;
		}
		if (std::remove(path.c_str()) != 0) {
			LOGE_TRACE("tcp receive: remove tmp file failed, path=%s, errno=%s",
					path.c_str(), socketErrnoText(errno).c_str());
		}
	}
}

void TcpReceiveTask::updateCacheWithFile(const std::string& filepath, bool is_live) {
	if (filepath.empty() || isTmpFile(filepath)) {
		return;
	}

	auto file_info = buildFileInfo(filepath);
	file_info.is_live = is_live;
	{
		std::lock_guard<std::mutex> lock(mMutex);
		auto iter = std::find_if(mFileCache.begin(), mFileCache.end(),
				[&filepath](const TransferFileInfo& info) { return info.path == filepath; });
		if (iter != mFileCache.end()) {
			*iter = file_info;
		} else {
			mFileCache.push_back(file_info);
		}
	}
	{
		std::lock_guard<std::mutex> lock(mListenerMutex);
		for (auto listener : mListeners) {
			try {
				listener->onFileAdded(file_info);
			} catch (const std::exception& e) {
				LOGE_TRACE("tcp receive: file listener exception: %s", e.what());
			} catch (...) {
				LOGE_TRACE("tcp receive: unknown file listener exception");
			}
		}
	}
}

void TcpReceiveTask::setActiveTmpPath(const std::string& path) {
	std::lock_guard<std::mutex> lock(mTmpMutex);
	mActiveTmpPath = path;
}

void TcpReceiveTask::clearActiveTmpPath(const std::string& path) {
	std::lock_guard<std::mutex> lock(mTmpMutex);
	if (mActiveTmpPath == path) {
		mActiveTmpPath.clear();
	}
}

std::string TcpReceiveTask::getActiveTmpPath() const {
	std::lock_guard<std::mutex> lock(mTmpMutex);
	return mActiveTmpPath;
}

void TcpReceiveTask::handleClient(int client_fd, const TcpReceiveParams& params, const std::string& peer) {
	LOGD("tcp receive: client connected, peer=%s", peer.c_str());

	defer {
		int fd = mClientFd.exchange(-1);
		{
			std::lock_guard<std::mutex> lock(mListenerMutex);
			for (auto listener : mListeners) {
				try {
					listener->onTcpStateChanged(TCP_STATUS_OVER);
				} catch (const std::exception& e) {
					LOGE_TRACE("tcp receive: state listener exception: %s", e.what());
				} catch (...) {
					LOGE_TRACE("tcp receive: unknown state listener exception");
				}
			}
		}
		if (fd >= 0) {
			close(fd);
		}
		cleanupTmpFiles(MP_PATH);
		LOGD("tcp receive: client disconnected, peer=%s", peer.c_str());
	};

	while (isStarted()) {
		uint8_t type = 0;
		uint32_t len = 0;

		if (!recvAll(client_fd, &type, sizeof(type), "read packet type", peer, false)) {
			break;
		}

		LOGI_TRACE("[mp_transfer] type: %u", (unsigned int)type);

		if (!recvAll(client_fd, &len, sizeof(len), "read payload length", peer)) {
			break;
		}

		len = ntohl(len);
		if (len == 0 || len > params.max_file_size) {
			LOGE_TRACE("tcp receive: invalid payload size, peer=%s, type=%u, len=%u, max=%u",
					peer.c_str(), type, len, params.max_file_size);
			break;
		}

		if (type == TYPE_TEXT) {
			std::vector<char> data(len + 1, 0);
			if (!recvAll(client_fd, data.data(), len, "read text payload", peer)) {
				break;
			}
			if (!sendFinalOk(client_fd, peer)) {
				break;
			}
			continue;
		}

		if (type != TYPE_IMAGE && type != TYPE_VIDEO && type != TYPE_LIVE) {
			LOGE_TRACE("tcp receive: unsupported packet type, peer=%s, type=%u", peer.c_str(), type);
			break;
		}
		const bool is_live_packet = (type == TYPE_LIVE);

		uint16_t name_len = 0;
		if (!recvAll(client_fd, &name_len, sizeof(name_len), "read filename length", peer)) {
			break;
		}
		name_len = ntohs(name_len);
		if (name_len == 0 || name_len > 256) {
			LOGE_TRACE("tcp receive: invalid file name length, peer=%s, name_len=%u",
					peer.c_str(), name_len);
			break;
		}

		std::string filename(name_len, '\0');
		if (!recvAll(client_fd, &filename[0], name_len, "read filename", peer)) {
			break;
		}
		if (!isValidFilename(filename)) {
			LOGE_TRACE("tcp receive: invalid file name, peer=%s, filename=%s",
					peer.c_str(), filename.c_str());
			break;
		}

		// 落盘改名（钟工 2026-09-25 17:15）：小程序发来的原名不友好 -> 统一命名为
		// 小程序_YYMMDD_HHMMSS.<ext>；同一秒多个文件加 _1/_2 后缀；扩展名沿用原文件名（小写）
		std::string ext;
		{
			size_t dot = filename.rfind('.');
			if (dot != std::string::npos) {
				ext = filename.substr(dot);
				for (size_t e = 0; e < ext.size(); e++) {
					ext[e] = static_cast<char>(tolower(static_cast<unsigned char>(ext[e])));
				}
			}
		}
		std::string stamp;
		{
			struct tm* tmv = TimeHelper::getDateTime();
			char sb[32];
			if (tmv != nullptr) {
				snprintf(sb, sizeof(sb), "%02d%02d%02d_%02d%02d%02d",
						(tmv->tm_year + 1900) % 100, tmv->tm_mon + 1, tmv->tm_mday,
						tmv->tm_hour, tmv->tm_min, tmv->tm_sec);
			} else {
				snprintf(sb, sizeof(sb), "%ld", static_cast<long>(time(nullptr)));
			}
			stamp = sb;
		}
		std::string final_path;
		{
			char pb[384];
			snprintf(pb, sizeof(pb), "%s小程序_%s%s", MP_PATH, stamp.c_str(), ext.c_str());
			final_path = pb;
			struct stat st0 = {0};
			for (int n = 1; n < 100 && stat(final_path.c_str(), &st0) == 0; n++) {
				snprintf(pb, sizeof(pb), "%s小程序_%s_%d%s", MP_PATH, stamp.c_str(), n, ext.c_str());
				final_path = pb;
			}
		}
		std::string tmp_path = final_path;
		size_t last_slash = tmp_path.rfind('/');
		size_t last_dot = tmp_path.rfind('.');
		bool has_dot_after_slash = (last_dot != std::string::npos) &&
				(last_slash == std::string::npos || last_dot > last_slash);
		if (has_dot_after_slash) {
			tmp_path = tmp_path.substr(0, last_dot) + ".tmp";
		} else {
			tmp_path += ".tmp";
		}

		FILE* fp = fopen(tmp_path.c_str(), "wb");
		if (fp == nullptr) {
			LOGE_TRACE("tcp receive: open temp file failed, peer=%s, path=%s, errno=%s",
					peer.c_str(), tmp_path.c_str(), socketErrnoText(errno).c_str());
			break;
		}
		setActiveTmpPath(tmp_path);

		uint32_t received = 0;
		bool ok = true;
		std::vector<char> buf(static_cast<size_t>(params.packet_size));
		LOGD("tcp receive: file receive begin, peer=%s, filename=%s, type=%u, len=%u, packet_size=%d",
				peer.c_str(), filename.c_str(), type, len, params.packet_size);

		while (received < len && isStarted()) {
			uint32_t remain = len - received;
			size_t need = std::min(static_cast<size_t>(remain), buf.size());
			if (!recvAll(client_fd, buf.data(), need, "read file chunk", peer)) {
				ok = false;
				break;
			}

			size_t written = fwrite(buf.data(), 1, need, fp);
			if (written != need) {
				LOGE_TRACE("tcp receive: write temp file failed, peer=%s, filename=%s, written=%zu/%zu, received=%u/%u, errno=%s",
						peer.c_str(), filename.c_str(), written, need, received, len, socketErrnoText(errno).c_str());
				ok = false;
				break;
			}

			received += static_cast<uint32_t>(need);
			if (received < len && !sendPacketAck(client_fd, received, peer)) {
				LOGE_TRACE("tcp receive: send ack failed, peer=%s, filename=%s, received=%u/%u",
						peer.c_str(), filename.c_str(), received, len);
				ok = false;
				break;
			}
		}

		fflush(fp);
		fclose(fp);

		if (!ok || received != len) {
			clearActiveTmpPath(tmp_path);
			LOGE_TRACE("tcp receive: file receive incomplete, peer=%s, filename=%s, received=%u/%u, started=%d, temp file kept",
					peer.c_str(), filename.c_str(), received, len, isStarted());
			break;
		}

		struct stat st = {0};
		int stat_res = stat(tmp_path.c_str(), &st);
		long long stat_size = (stat_res == 0) ? static_cast<long long>(st.st_size) : -1LL;
		if (stat_res != 0 || static_cast<uint64_t>(st.st_size) != len) {
			clearActiveTmpPath(tmp_path);
			LOGE_TRACE("tcp receive: temp file size verify failed, peer=%s, filename=%s, path=%s, expected=%u, stat_size=%lld, errno=%s",
					peer.c_str(), filename.c_str(), tmp_path.c_str(), len, stat_size, socketErrnoText(errno).c_str());
			break;
		}

		if (rename(tmp_path.c_str(), final_path.c_str()) != 0) {
			clearActiveTmpPath(tmp_path);
			LOGE_TRACE("tcp receive: rename temp file failed, peer=%s, filename=%s, tmp=%s, final=%s, errno=%s",
					peer.c_str(), filename.c_str(), tmp_path.c_str(), final_path.c_str(), socketErrnoText(errno).c_str());
			break;
		}
		clearActiveTmpPath(tmp_path);

		updateCacheWithFile(final_path, is_live_packet);

		if (!sendFinalOk(client_fd, peer)) {
			break;
		}
		LOGD("tcp receive: file receive success, peer=%s, filename=%s, len=%u",
				peer.c_str(), filename.c_str(), len);
	}
}

bool TcpReceiveTask::isValidFilename(const std::string& filename) const {
	if (filename.empty()) {
		return false;
	}
	if (filename.find("..") != std::string::npos) {
		return false;
	}
	if (filename.find('/') != std::string::npos || filename.find('\\') != std::string::npos) {
		return false;
	}
	return true;
}

bool TcpReceiveTask::isTmpFile(const std::string& filename) const {
	static const std::string suffix = ".tmp";
	if (filename.size() < suffix.size()) {
		return false;
	}
	return filename.compare(filename.size() - suffix.size(), suffix.size(), suffix) == 0;
}

void TcpReceiveTask::configureClientSocket(int client_fd, int timeout_ms) const {
	struct timeval tv = {timeout_ms / 1000, (timeout_ms % 1000) * 1000};
	setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
	setsockopt(client_fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));
}
