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
| `i <内容>` | `ai` | 后台交给大模型拆成多条任务 |
| `ai-status` | `is` | 查看后台解析进度与结果 |
| `ai-undo` | `ic` | 撤回上次 `td i` 添加的任务 |
| `alarm <操作>` | `al` | 闹钟与提醒管理 |
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
| `llm_auto_confirm` | 是 | 直接写入不询问；设为否则恢复确认（仅前台模式） |

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

把一段自然语言交给大模型，自动拆成多条待办。**解析在后台进行，命令立即返回**，你可以接着做别的事：

```
td i 明天交色彩作业，顺便买牛奶
```

```
已交给大模型后台解析，你可以继续做别的事。
  查看进度：td is
  撤回结果：td ic
```

稍后用 `td is` 看结果：

```
最近一次结果（2026-10-19 12:53:23）：
  ✓ 已添加 2 条：
    - 明天交色彩作业
    - 买牛奶
  （如需撤回：td ic）
```

失败也会记录在这里（含错误原因），不会静默丢失。

加错了就用 `td ic` 撤回刚才那一批：

```
td ic
```

```
已撤回 2 条任务：
  - 明天交色彩作业
  - 买牛奶
```

说明：
- 后台任务进行中时再次 `td i` 会被拒绝，避免叠加
- 撤回只对**最近一次** `td i` 有效，撤回后即清除
- 相关状态文件（`.td_pending.json`、`.td_last_result.json`、`.td_last_add.json`、`.td_last_run.log`）已在 `.gitignore` 中排除

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

## 日程识别与闹钟提醒

`td i` 不仅拆任务，还会提取**日期、时间、提醒时刻和任务类型**。模型返回结构化数据，写入 `tasks.json`：

```json
[
  {
    "title": "开组会",
    "done": false,
    "date": "2026-10-20",
    "time": "15:00",
    "remind": null,
    "type": "meeting"
  }
]
```

支持的 `type`：`work`（工作）/ `study`（学习）/ `life`（生活）/ `health`（健康）/ `meeting`（会议）/ `other`（其他）。

列表会显示时间与类型：

```
1. [✓] 色彩原理
2. [○] 开组会  (10-20 15:00, 会议)
3. [○] 吃药  (10-20 20:00, 健康)
```

### 闹钟命令

```
td alarm start          # 启动提醒守护进程（前台运行，Ctrl+C 退出）
td alarm auto on        # 开机自启（写注册表 Run 项）
td alarm auto off       # 关闭开机自启
td alarm status         # 查看状态与待提醒任务
td alarm test           # 发一条测试通知
```

`td alarm status` 示例：

```
开机自启：已开启
检查间隔：30 秒
提前提醒：10 分钟

待提醒任务（2 条）：
  10-20 14:50  开组会
  10-20 19:50  吃药
```

### 提醒方式

到点弹出 **Windows 系统通知（Toast）**，不打断当前操作。若系统通知不可用，会自动退回传统弹窗。

- 默认在任务时间前 10 分钟提醒，可用 `td cfg set remind_lead_minutes 5` 调整
- 模型若识别出明确的提醒时刻，会写入 `remind` 字段并优先生效
- 同一任务只提醒一次，记录在 `.td_alarm_state.json`（自动清理 7 天前记录）
- 错过超过 30 分钟的任务不会补弹，避免开机时被历史任务刷屏

开机自启动的命令形如：

```
"python.exe" "td.py" __daemon__
```

取消自启后该注册表项会被删除。

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
