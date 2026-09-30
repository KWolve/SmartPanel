/*
 * broadcast_task.h
 *
 *  Created on: 2026年5月8日
 *      Author: asus
 */

#ifndef MP_TRANSFER_BROADCAST_TASK_H_
#define MP_TRANSFER_BROADCAST_TASK_H_

#include <arpa/inet.h>
#include <atomic>
#include <mutex>
#include <string>
#include <vector>
#include <base/base.h>
#include <base/task.h>

struct BroadcastParams {
	// 广播内容：当前设备名称
	std::string content;
	// 暂不广播屏幕尺寸，保留字段便于后续恢复。
	// int width;
	// int height;
};

class BroadcastTask : public base::Task<BroadcastParams> {
	DISALLOW_COPY_AND_ASSIGN_METHOD(BroadcastTask);
	DECLARE_SINGLETON_PATTERN(BroadcastTask);

public:
	class BroadcastListener {
	public:
		virtual ~BroadcastListener() = default;
	};

	void addListener(BroadcastListener* listener);
	void removeListener(BroadcastListener* listener);

protected:
	void beforeTask(const BroadcastParams& params) override;
	void doTask(const BroadcastParams& params) override;

private:
	std::vector<BroadcastListener*> mListeners;
	std::mutex mListenerMutex;
	std::atomic<int> mSfd{-1};
};

#endif /* MP_TRANSFER_BROADCAST_TASK_H_ */
