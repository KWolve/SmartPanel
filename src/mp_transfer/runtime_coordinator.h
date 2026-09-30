#ifndef MP_TRANSFER_RUNTIME_COORDINATOR_H_
#define MP_TRANSFER_RUNTIME_COORDINATOR_H_

#include "broadcast_task.h"
#include "tcp_receive.h"
// 暂不读取广播所需的屏幕尺寸，后续恢复宽高广播时重新启用。
// #include "utils/ScreenHelper.h"

#include <mutex>
#include <set>
#include <string>

class MpTransferRuntimeCoordinator {
public:
	static MpTransferRuntimeCoordinator& instance() {
		static MpTransferRuntimeCoordinator inst;
		return inst;
	}

	void retain(const std::string& owner, const std::string& broadcast_name) {
		if (owner.empty()) return;

		std::lock_guard<std::mutex> lk(mMutex);
		mOwners.insert(owner);

		std::string next_name = broadcast_name.empty() ? "Frame" : broadcast_name;
		const bool need_restart = !mRunning || (next_name != mBroadcastName);
		mBroadcastName = next_name;

		if (!need_restart) return;
		stopLocked();
		startLocked();
	}

	void release(const std::string& owner) {
		if (owner.empty()) return;

		std::lock_guard<std::mutex> lk(mMutex);
		mOwners.erase(owner);
		if (!mOwners.empty()) return;
		stopLocked();
	}

private:
	MpTransferRuntimeCoordinator() = default;
	MpTransferRuntimeCoordinator(const MpTransferRuntimeCoordinator&) = delete;
	MpTransferRuntimeCoordinator& operator=(const MpTransferRuntimeCoordinator&) = delete;

	void startLocked() {
		// int width = ScreenHelper::getScreenWidth();
		// int height = ScreenHelper::getScreenHeight();
		// BroadcastTask::instance().start(BroadcastParams{
		// 		mBroadcastName.empty() ? "Frame" : mBroadcastName, width, height});
		BroadcastTask::instance().start(BroadcastParams{mBroadcastName.empty() ? "Frame" : mBroadcastName});
		TcpReceiveTask::instance().start(TcpReceiveParams{});
		mRunning = true;
	}

	void stopLocked() {
		BroadcastTask::instance().stop();
		TcpReceiveTask::instance().stop();
		mRunning = false;
	}

private:
	std::mutex mMutex;
	std::set<std::string> mOwners;
	std::string mBroadcastName;
	bool mRunning = false;
};

#endif /* MP_TRANSFER_RUNTIME_COORDINATOR_H_ */
