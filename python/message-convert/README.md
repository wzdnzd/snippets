# 聊天记录格式转换工具
> 请注意：⭐⭐⭐ 迁移前请做好数据备份，以防丢失 ⭐⭐⭐
> 
> 请注意：⭐⭐⭐ 迁移前请做好数据备份，以防丢失 ⭐⭐⭐
> 
> 请注意：⭐⭐⭐ 迁移前请做好数据备份，以防丢失 ⭐⭐⭐

这是一个用于在不同聊天记录格式之间进行转换的工具。目前支持以下三种格式：
- LobeChat（数据库格式）
- NextChat（JSON文件格式）
- Cherry Studio（JSON文件格式）

## 安装依赖

```bash
pip install psycopg2 tzlocal
```

## 使用方法

```bash
python chat_converter.py -s <源格式> -t <目标格式> [选项]
```

### 必需参数

- `-s, --source`: 源格式，可选值：`lobechat`、`nextchat`、`cherrystudio`
- `-t, --target`: 目标格式，可选值：`lobechat`、`nextchat`、`cherrystudio`

### 可选参数

- `-i, --input`: 输入文件路径（当源格式为 NextChat 或 Cherry Studio 时必需）
- `-o, --output`: 输出文件路径（当目标格式为 NextChat 或 Cherry Studio 时必需）
- `-d, --database-url`: LobeChat 数据库 URL（当源格式或目标格式为 LobeChat 时必需）
- `-u, --user-id`: 用户 ID（当源格式或目标格式为 LobeChat 时必需）
- `-w, --overwrite`: 覆盖现有数据而不是追加（默认为追加模式）

## 使用示例

1. 从 NextChat 转换到 LobeChat：
```bash
python chat_converter.py -s nextchat -t lobechat -i nextchat.json -d "postgresql://user:password@localhost:5432/dbname" -u "user_123"
```

2. 从 LobeChat 转换到 Cherry Studio：
```bash
python chat_converter.py -s lobechat -t cherrystudio -d "postgresql://user:password@localhost:5432/dbname" -u "user_123" -o cherry-studio.json
```

3. 从 Cherry Studio 转换到 NextChat（覆盖模式）：
```bash
python chat_converter.py -s cherrystudio -t nextchat -i cherry-studio.json -o nextchat.json -w
```

## 注意事项

1. 当使用 LobeChat 作为源或目标格式时：
   - 必须提供数据库 URL（`-d`）和用户 ID（`-u`）
   - 数据库 URL 格式：`postgresql://user:password@host:port/dbname`

2. 当使用 NextChat 或 Cherry Studio 作为源格式时：
   - 必须提供输入文件路径（`-i`）
   - 输入文件必须是有效的 JSON 格式

3. 当使用 NextChat 或 Cherry Studio 作为目标格式时：
   - 必须提供输出文件路径（`-o`）
   - 如果输出文件已存在：
     - 默认为追加模式，新数据会添加到现有数据中
     - 使用 `-w` 参数可以覆盖现有数据

4. 时区处理：
   - 工具会自动处理时区转换
   - LobeChat 数据库中的时间使用 UTC 时区
   - 输出的时间会根据本地时区进行调整

## 错误处理

- 如果提供的参数不完整或无效，工具会显示相应的错误信息
- 如果源数据为空，工具会跳过转换
- 如果在追加模式下输出路径不存在，工具会跳过转换
- 转换完成后会显示操作结果（追加或覆盖） 