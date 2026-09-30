/*
 * tcp_receive.h
 *
 *  Created on: 2026
 *      Author: asus
 */

#ifndef MP_TRANSFER_TCP_RECEIVE_H_
#define MP_TRANSFER_TCP_RECEIVE_H_

#include <cstdint>
#include <atomic>
#include <mutex>
#include <string>
#include <vector>
#include <base/task.h>
#include "system/transfer_type_and_data.h"

struct TcpReceiveParams {
	int listen_port = 9000;
	int socket_timeout_ms = 2000;
	uint32_t max_file_size = 500 * 1024 * 1024;
	int packet_size = 32 * 1024;
};

class TcpReceiveTask : public base::Task<TcpReceiveParams> {
	DISALLOW_COPY_AND_ASSIGN_METHOD(TcpReceiveTask);
	DECLARE_SINGLETON_PATTERN(TcpReceiveTask);

public:
	class TcpReceiveListener {
	public:
		virtual ~TcpReceiveListener() = default;

		virtual void onScanFinished(const std::vector<TransferFileInfo>& fileList) = 0;
		virtual void onFileAdded(const TransferFileInfo& info) = 0;
		virtual void onTcpStateChanged(int state) = 0;
	};

	std::vector<TransferFileInfo> getFileList(FileCategory category);
	bool isClientConnected() const { return mClientFd.load() >= 0; }
	void refreshCache();
	void removeCachedFiles(const std::vector<std::string>& filepaths);

	void addListener(TcpReceiveListener* listener);
	void removeListener(TcpReceiveListener* listener);
	void stop() override;

protected:
	void beforeTask(const TcpReceiveParams& params) override;
	void doTask(const TcpReceiveParams& params) override;

private:
	void scanPath(const std::string& root_path);
	void clearCache();
	void cleanupTmpFiles(const std::string& root_path);
	void updateCacheWithFile(const std::string& filepath, bool is_live = false);
	void handleClient(int client_fd, const TcpReceiveParams& params, const std::string& peer);
	void setActiveTmpPath(const std::string& path);
	void clearActiveTmpPath(const std::string& path);
	std::string getActiveTmpPath() const;

	bool isValidFilename(const std::string& filename) const;
	bool isTmpFile(const std::string& filename) const;
	void configureClientSocket(int client_fd, int timeout_ms) const;

private:
	mutable std::mutex mMutex;
	std::vector<TransferFileInfo> mFileCache;

	std::mutex mListenerMutex;
	std::vector<TcpReceiveListener*> mListeners;

	mutable std::mutex mTmpMutex;
	std::string mActiveTmpPath;

	std::atomic<int> mServerFd{-1};
	std::atomic<int> mClientFd{-1};
};

#endif /* MP_TRANSFER_TCP_RECEIVE_H_ */
