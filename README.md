# todo-cli

一个极简的命令行待办工具，单文件实现，数据存本地 JSON，不依赖数据库。

**仅支持 Windows。**

## 特性

- 单文件 `td.py`，只用标准库（大模型功能额外需要 `requests`、`python-dotenv`）
- 任务数据存为 `tasks.json`，纯文本、可手改
- 命令支持短别名（`a` / `l` / `d` / `t` / `x` / `c` / `s` / `h` / `cfg` / `v`）
- 无参数运行时直接列出任务
- 支持 `td i 内容` 让大模型把一段话拆成多条任务

## 环境要求

- Windows + Python 3.8+
- `requests`、`python-dotenv`（仅 `td i` 用到）：
  ```
  pip install requests python-dotenv
  ```

## 安装

把仓库克隆或下载到任意目录，无需 `pip install`：

```
git clone <仓库地址> todo-cli
cd todo-cli
```

运行方式二选一：

```
python td.py <命令> [参数]
td.bat <命令> [参数]
```

想把 `td` 当全局命令用，把该目录加入系统环境变量 `PATH` 即可。

## 命令

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| `add <任务>` | `a` | 添加任务 |
| `list` | `l` | 列出任务 |
| `done <编号>` | `d` | 标记完成 |
| `toggle <编号>` | `t` | 切换完成状态 |
| `delete <编号>` | `x` | 删除任务 |
| `clear` | `c` | 清空全部（需确认） |
| `self` | `s` | 用记事本打开源文件 |
| `config` | `cfg` | 打开配置文件（`cfg show` 查看当前值） |
| `version` | `v` | 显示版本信息 |
| `i <内容>` | `ai` | 交给大模型拆成多条任务 |
| `ai-undo` | `ic` | 撤回上次 `td i` 添加的任务 |
| `help` | `h` | 显示帮助 |

示例：

```
td a 买牛奶
td l
td d 1
td t 2
td x 1
```

## 配置

配置文件为脚本同目录下的 `.td_config.json`（首次 `td cfg` 或修改时自动生成）。

```
td cfg                    # 用记事本打开配置文件
td cfg show               # 只在终端查看当前配置
td cfg set editor vim     # 修改编辑器
td cfg get editor         # 读取单项
```

可配置项：

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `editor` | `notepad` | 打开脚本和配置文件用的编辑器 |
| `show_list_after_add` | 否 | `td a` 之后是否自动显示列表 |
| `show_list_after_delete` | 否 | `td x` 之后是否自动显示列表 |
| `show_list_after_done` | 是 | `td d` 之后是否自动显示列表 |
| `normalize_input` | 是 | 命令名大小写不敏感、任务名连续空格合并为单个 |
| `llm_url` | 空 | 大模型接口地址 |
| `llm_model` | 空 | 模型名称 |
| `llm_apikey` | 空 | apikey，建议留空改放 `.env` |
| `llm_timeout` | 60 | 请求超时秒数 |
| `llm_auto_confirm` | 是 | 直接写入不询问；设为否则恢复确认 |

开关类配置接受 `是/否`、`true/false`、`on/off`、`1/0` 等写法，统一以布尔值存储：

```
td cfg set show_list_after_add 是
td cfg set show_list_after_done false
```

## 输入容错

开启 `normalize_input`（默认）时：

```
td ADD 买牛奶        # 等价于 td add，命令大小写不敏感
td a "写   报告"      # 任务名连续空格合并为「写 报告」
```

任务名允许重复，同名任务会各自占用一个编号。

## 用大模型生成任务：`td i`

把一段自然语言交给大模型，自动拆成多条待办：

```
td i 明天交色彩作业，顺便买牛奶
```

```
正在交给大模型解析…

解析出 2 条任务：
  1. 明天交色彩作业
  2. 买牛奶

已添加 2 条任务。（如需撤回：td ic）
```

默认直接写入，不询问。加错了就用 `td ic` 撤回刚才那一批：

```
td ic
```

```
已撤回 2 条任务：
  - 明天交色彩作业
  - 买牛奶
```

撤回记录保存在 `.td_last_add.json`（已在 `.gitignore` 中排除），只对**最近一次** `td i` 有效，撤回后即清除。

### 1. 准备密钥

复制 `.env.example` 为 `.env`，填入 apikey：

```
TD_LLM_APIKEY=sk-your-key-here
```

`.env` 已在 `.gitignore` 中排除，不会被提交。也可以在配置里写 `td cfg set llm_apikey env:MY_OTHER_KEY` 引用其他环境变量。

### 2. 配置接口

```
td cfg set llm_url https://api.deepseek.com
td cfg set llm_model deepseek-chat
```

只支持 OpenAI 兼容接口（`/v1/chat/completions`）。`llm_url` 填 base 地址即可，程序自动补路径；填完整地址则原样使用。

常见服务商：

| 服务商 | `llm_url` | `llm_model` 示例 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| OpenAI | `https://api.openai.com` | `gpt-4o-mini` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode` | `qwen-plus` |
| 月之暗面 | `https://api.moonshot.cn` | `moonshot-v1-8k` |
| Ollama（本地） | `http://localhost:11434` | `qwen2.5` |

### 3. 其他说明

- 本地模型（Ollama）apikey 可留空
- `llm_auto_confirm` 默认为 `是`（直接写入）；设为 `否` 会恢复“确认添加？(Y/n)”询问
- 模型输出即使被 markdown 代码块包裹、或夹带说明文字，也会被自动提取成任务列表
- 单元测试：`python test_llm.py`（自带临时 HTTP 服务，不消耗真实额度）

## 数据存储

所有任务保存在脚本同目录的 `tasks.json`，结构为：

```json
[
  { "title": "买牛奶", "done": false }
]
```

`tasks.json`、`.td_config.json`、`.env` 已在 `.gitignore` 中排除，不会提交到仓库。

## License

MIT
