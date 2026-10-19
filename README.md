# todo-cli

一个极简的命令行待办工具，单文件实现，数据存本地 JSON，不依赖数据库和网络。

## 特性

- 单文件 `td.py`，无第三方依赖，只用标准库
- 任务数据存为 `tasks.json`，纯文本、可版本管理、可手改
- 命令支持短别名（`a` / `l` / `d` / `t` / `x` / `c` / `s` / `h` / `cfg`）
- 无参数运行时直接列出任务，不会报错
- 用 `td self` 可一键用编辑器打开源码

## 环境要求

- Python 3.8+
- 可选：Windows 下直接用 `td.bat` 启动（内部调用 `uv run`，也可换成 `python`）

## 安装

把仓库克隆到任意目录即可，无需 `pip install`：

```bash
git clone <你的仓库地址> todo-cli
cd todo-cli
```

运行时用：

```bash
python td.py <命令> [参数]
```

Windows 下也可以用 `td.bat`（等价于 `uv run td.py`）。想全局使用，可把该目录加入 `PATH`，之后直接敲 `td`。

## 命令

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| `add <任务>` | `a` | 添加任务 |
| `list` | `l` | 列出任务 |
| `done <编号>` | `d` | 标记完成 |
| `toggle <编号>` | `t` | 切换完成状态 |
| `delete <编号>` | `x` | 删除任务 |
| `clear` | `c` | 清空全部（需确认） |
| `self` | `s` | 用编辑器打开源文件 |
| `config` | `cfg` | 打开配置文件（`cfg show` 查看当前值） |
| `version` | `v` | 显示版本信息 |
| `@ <内容>` | `ai` | 交给大模型拆成多条任务 |
| `help` | `h` | 显示帮助 |

示例：

```bash
td a 买牛奶
td l
td d 1
td t 2
td x 1
```

## 配置

配置文件为脚本同目录下的 `.td_config.json`（首次 `td cfg` 或修改时自动生成）。

```bash
td cfg                    # 用编辑器打开配置文件
td cfg show               # 只在终端查看当前配置
td cfg set editor vim     # 修改编辑器
td cfg get editor         # 读取单项
```

可配置项：

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `editor` | `notepad`（Windows）/ `$EDITOR` | 打开脚本和配置文件用的编辑器 |
| `show_list_after_add` | 否 | `td a` 之后是否自动显示列表 |
| `show_list_after_delete` | 否 | `td x` 之后是否自动显示列表 |
| `show_list_after_done` | 是 | `td d` 之后是否自动显示列表 |
| `normalize_input` | 是 | 命令名大小写不敏感、任务名连续空格合并为单个 |
| `llm_url` | 空 | 大模型接口地址 |
| `llm_model` | 空 | 模型名称 |
| `llm_apikey` | 空 | apikey，建议留空改放 `.env` |
| `llm_timeout` | 60 | 请求超时秒数 |
| `llm_auto_confirm` | 否 | 生成后免确认直接写入 |

开关类配置接受 `是/否`、`true/false`、`on/off`、`1/0` 等写法，统一以布尔值存储：

```bash
td cfg set show_list_after_add 是
td cfg set show_list_after_done false
```

## 输入容错

开启 `normalize_input`（默认）时：

```bash
td ADD 买牛奶        # 等价于 td add，命令大小写不敏感
td   a   "写   报告"  # 任务名连续空格合并为「写 报告」
```

任务名允许重复，同名任务会各自占用一个编号。

## 用大模型生成任务：`td @`

把一段自然语言交给大模型，自动拆成多条待办：

```bash
td @ 明天交色彩作业，顺便买牛奶
```

```
正在交给大模型解析…

解析出 2 条任务：
  1. 明天交色彩作业
  2. 买牛奶

确认添加？(Y/n)
```

### 1. 准备密钥

复制 `.env.example` 为 `.env`，填入 apikey：

```bash
TD_LLM_APIKEY=sk-your-key-here
```

`.env` 已在 `.gitignore` 中排除，不会被提交。也支持用 `td cfg set llm_apikey env:MY_OTHER_KEY` 间接引用其他环境变量。

### 2. 配置接口

```bash
td cfg set llm_url https://api.deepseek.com
td cfg set llm_model deepseek-chat
```

只支持 OpenAI 兼容接口（`/v1/chat/completions`）。`llm_url` 填 base 地址即可，程序会自动补路径；如果填的是完整地址则原样使用。

常见服务商：

| 服务商 | `llm_url` | `llm_model` 示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.openai.com` | `gpt-4o-mini` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode` | `qwen-plus` |
| 月之暗面 | `https://api.moonshot.cn` | `moonshot-v1-8k` |
| Ollama（本地） | `http://localhost:11434` | `qwen2.5` |

### 3. 其他说明

- 依赖：`requests`、`python-dotenv`
- 本地模型（Ollama / LM Studio）把 `llm_url` 设为 `http://localhost:11434`，apikey 可留空
- `llm_auto_confirm` 设为 `是` 可跳过确认直接写入
- 模型输出即使被 markdown 代码块包裹、或夹带说明文字，也会被自动提取成任务列表
- 单元测试：`python test_llm.py`（自带本地 mock 服务，不消耗真实额度）

## 数据存储

所有任务保存在脚本同目录的 `tasks.json`，结构为：

```json
[
  { "title": "买牛奶", "done": false }
]
```

`tasks.json` 和 `.td_config.json` 已在 `.gitignore` 中排除，属于本地数据，不会提交到仓库。

## License

MIT
