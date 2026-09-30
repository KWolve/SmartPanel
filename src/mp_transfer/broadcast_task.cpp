/*
 * broadcast_task.cpp
 *
 *  Created on: 2026年5月8日
 *      Author: asus
 */

#include "broadcast_task.h"


#include <cstring>
#include <unistd.h>

void BroadcastTask::beforeTask(const BroadcastParams& params) {

	mSfd.store(-1);

	int fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0) {
		LOGE_TRACE("broadcast task : failed to init broadcast sfd");
		return;
	}

	int broadcast = 1;
	if (setsockopt(fd, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast)) != 0) {
		LOGE_TRACE("broadcast task : set broadcast mode failed");
		close(fd);
		return;
	}

	mSfd.store(fd);
}

void BroadcastTask::doTask(const BroadcastParams& params) {
	struct sockaddr_in addr = {0};
	addr.sin_family = AF_INET;
	addr.sin_port = htons(8899);
	addr.sin_addr.s_addr = inet_addr("255.255.255.255");

	int sfd = mSfd.load();
	if (sfd < 0) {
		LOGE_TRACE("broadcast task: invalid socket fd");
		return;
	}

	defer {
		int fd = mSfd.exchange(-1);
		if (fd >= 0) {
			close(fd);
		}
	};

	while (isRunning()) {
		// 暂不向小程序广播屏幕尺寸，保留原协议拼接方式便于后续恢复。
		// std::string whole_content = "zkswe:" + params.content + "-" +
		// 		std::to_string(params.width) + "-" + std::to_string(params.height);
		std::string whole_content = "zkswe:" + params.content;
		const char* msg = whole_content.c_str();
		ssize_t sent = sendto(sfd, msg, strlen(msg), 0, (struct sockaddr*)&addr, sizeof(addr));
		if (sent < 0) {
			if (!isRunning()) {
				break;
			}
			LOGE_TRACE("broadcast task failed");
		} else {
//			std::string text = base::this_thread::is_primary_thread()? "是主线程" : "不是";
//			text = to_string(base::this_thread::get_tid()) + " " + text;
//			LOGE_TRACE("broadcast task: %s----/n", text.c_str());
			LOGD_TRACE("UDP broadcast-----------------------------------------------");
		}

		// 每2秒广播一次
		for (int i = 0; i < 20 && isRunning(); ++i) {
			usleep(100 * 1000);
		}
	}
}

void BroadcastTask::addListener(BroadcastListener* listener) {
	std::lock_guard<std::mutex> lk(mListenerMutex);
	if (listener == nullptr) {
		return;
	}
	for (auto* item : mListeners) {
		if (item == listener) {
			return;
		}
	}
	mListeners.push_back(listener);
}

void BroadcastTask::removeListener(BroadcastListener* listener) {
	std::lock_guard<std::mutex> lk(mListenerMutex);
	auto iter = mListeners.begin();
	for (; iter != mListeners.end(); ++iter) {
		if (*iter == listener) {
			mListeners.erase(iter);
			break;
		}
	}
}
