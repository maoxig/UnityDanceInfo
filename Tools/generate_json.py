import os
import hashlib
import json

# 配置
DANCES_FOLDER = r"./"  # 你的舞蹈文件夹
OUTPUT_FOLDER = r"./DanceInfo"  # JSON 输出目录

# 创建输出目录
os.makedirs(os.path.join(OUTPUT_FOLDER, "dances"), exist_ok=True)

index_data = {}

def compute_sha1(file_path):
    """计算文件的 SHA1 哈希（前 8 位即可）"""
    sha1 = hashlib.sha1()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(4096)
            if not chunk:
                break
            sha1.update(chunk)
    return sha1.hexdigest()[:8]


def walk_and_generate():
    """递归扫描 Dances 文件夹并生成 JSON 模板"""
    for root, dirs, files in os.walk(DANCES_FOLDER):
        for file in files:
            if file.endswith(".unity3d"):
                full_path = os.path.join(root, file)

                print(f"发现舞蹈文件: {full_path}")

                # 计算哈希
                hash_value = compute_sha1(full_path)
                json_filename = f"{hash_value}.json"

                # 单个舞蹈信息的模板数据
                dance_info = {
                    "name": file,       # 可手动改
                    "author": "",
                    "credits": [],
                    "description": "",
                    "sourceFile": file
                }

                # 写入 dances/<hash>.json
                with open(os.path.join(OUTPUT_FOLDER, "dances", json_filename), "w", encoding="utf-8") as f:
                    json.dump(dance_info, f, indent=4, ensure_ascii=False)

                # 同步到 dances.json 索引
                index_data[hash_value] = {
                    "name": file,
                    "author": "",
                    "credits": [],
                    "infoUrl": f"dances/{json_filename}",
                    "updated": ""
                }


def write_index():
    """写入 dances.json"""
    index_path = os.path.join(OUTPUT_FOLDER, "dances.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=4, ensure_ascii=False)
    print("已生成 dances.json")


if __name__ == "__main__":
    walk_and_generate()
    write_index()
    print("全部生成完成！")
