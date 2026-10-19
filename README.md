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
| `config` | `cfg` | 查看/修改配置 |
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

配置文件为脚本同目录下的 `.td_config.json`（首次修改时自动生成）：

```bash
td cfg                    # 查看当前配置
td cfg set editor vim     # 修改编辑器
td cfg get editor         # 读取单项
```

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
