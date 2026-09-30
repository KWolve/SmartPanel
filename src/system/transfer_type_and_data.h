/*
 * transfer_type_and_data.h
 *
 *  Created on: 2026年5月9日
 *      Author: asus
 */

#ifndef TRANSFER_TYPE_AND_DATA_H_
#define TRANSFER_TYPE_AND_DATA_H_

#include <string>
#include <vector>


enum class TransferType {
	NONE = 0,
	PC,
	MINI_PROGRAM //小程序
};


enum class FileCategory {
	PHOTO,
	VIDEO,
	UNSUPPORTED,
	UNKNOWN,
};

struct TransferFileInfo {
	std::string path;
	std::string name;
	FileCategory category;
	uint64_t size;
	int width = 0;
	int height = 0;
	int duration = 0;
	long last_modified = 0;
	bool is_live = false;
};



#endif /* TRANSFER_TYPE_AND_DATA_H_ */
