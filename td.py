import sys
import json
import os
import subprocess
from pathlib import Path

# 路径全部基于脚本所在目录，避免受"当前工作目录"影响
BASE_DIR    = Path(__file__).resolve().parent
FILE_PATH   = BASE_DIR / "tasks.json"
CONFIG_PATH = BASE_DIR / ".td_config.json"

TASKS = []
CONFIG = {}

DEFAULT_CONFIG = {
    "editor": "notepad" if os.name == "nt" else os.environ.get("EDITOR", "nano"),
}

# 命令别名映射：左边是短命令，右边是完整命令
ALIASES = {
    "a": "add",
    "l": "list",
    "d": "done",
    "t": "toggle",
    "x": "delete",
    "c": "clear",
    "s": "self",
    "h": "help",
    "cfg": "config",
}


# ---------- 配置 ----------
def load_config():
    global CONFIG
    CONFIG = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                CONFIG.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            print("警告：配置文件损坏，使用默认配置。")


def save_config():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)


# ---------- 任务读写 ----------
def load_tasks():
    global TASKS
    if not FILE_PATH.exists():
        TASKS = []
        return
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            TASKS = json.load(f)
    except json.JSONDecodeError:
        print("警告：数据文件损坏，将重新初始化。")
        TASKS = []


def save_tasks():
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(TASKS, f, ensure_ascii=False, indent=2)


# ---------- 各命令实现 ----------
def add_task(title):
    TASKS.append({"title": title, "done": False})
    save_tasks()
    print(f"已添加：{title}")


def list_tasks():
    if not TASKS:
        print("暂无待办事项。")
        return
    for i, t in enumerate(TASKS, 1):
        status = "✓" if t["done"] else "○"
        print(f"{i}. [{status}] {t['title']}")


def mark_done(index):
    try:
        task = TASKS[index - 1]
        task["done"] = True
        save_tasks()
        print(f"已完成：{task['title']}")
    except IndexError:
        print(f"错误：编号 {index} 不存在。")


def toggle_task(index):
    try:
        task = TASKS[index - 1]
        task["done"] = not task["done"]
        save_tasks()
        print(f"{task['title']} → {'已完成' if task['done'] else '未完成'}")
    except IndexError:
        print(f"错误：编号 {index} 不存在。")


def delete_task(index):
    try:
        task = TASKS.pop(index - 1)
        save_tasks()
        print(f"已删除：{task['title']}")
    except IndexError:
        print(f"错误：编号 {index} 不存在。")


def clear_tasks():
    if not TASKS:
        print("没有可清除的任务。")
        return
    confirm = input(f"确定清除全部 {len(TASKS)} 个任务？(y/N) ").strip().lower()
    if confirm == "y":
        TASKS.clear()
        save_tasks()
        print("已清空。")
    else:
        print("已取消。")


def open_self():
    """用配置里的编辑器打开本脚本"""
    script = Path(__file__).resolve()
    editor = CONFIG.get("editor", "notepad")
    print(f"用 {editor} 打开：{script}")
    try:
        subprocess.Popen([editor, str(script)])
    except FileNotFoundError:
        print(f"错误：找不到编辑器 {editor}，用 `td cfg set editor <名字>` 修改。")


def cmd_config(args):
    if not args:
        print("当前配置：")
        for k, v in CONFIG.items():
            print(f"  {k} = {v}")
        print(f"\n配置文件：{CONFIG_PATH}")
        return

    sub = args[0]
    if sub == "set" and len(args) >= 3:
        key, value = args[1], " ".join(args[2:])
        if key not in CONFIG:
            print(f"未知配置项：{key}（可用：{', '.join(CONFIG.keys())}）")
            return
        CONFIG[key] = value
        save_config()
        print(f"已设置 {key} = {value}")
    elif sub == "get" and len(args) == 2:
        key = args[1]
        print(CONFIG[key] if key in CONFIG else f"未知配置项：{key}")
    else:
        print("用法：td cfg | td cfg set <键> <值> | td cfg get <键>")


def show_help():
    print("""用法：td <命令> [参数]

命令                        别名    说明
─────────────────────────────────────────────
add <任务>                   a       添加任务
list                         l       列出任务
done <编号>                  d       标记完成
toggle <编号>                t       切换完成状态
delete <编号>                x       删除任务
clear                        c       清空全部（需确认）
self                         s       打开脚本源文件
config                       cfg     查看/修改配置
help                         h       显示帮助

示例：
  td a 买牛奶
  td l
  td d 1
  td t 2
  td x 1
""")


# ---------- 入口 ----------
def resolve(cmd: str) -> str:
    return ALIASES.get(cmd, cmd)


def main():
    load_config()
    load_tasks()

    # 无参数时直接展示列表，比报错更友好
    if len(sys.argv) < 2:
        list_tasks()
        print("\n提示：用 `td h` 查看全部命令。")
        return

    cmd  = resolve(sys.argv[1])
    args = sys.argv[2:]

    if cmd == "add":
        if not args:
            print("错误：add 需要任务名，例如 td add 买牛奶")
            sys.exit(1)
        add_task(" ".join(args))
    elif cmd == "list":
        list_tasks()
    elif cmd == "done":
        if not args:
            print("错误：done 需要编号，例如 td done 1")
            sys.exit(1)
        mark_done(int(args[0]))
    elif cmd == "toggle":
        if not args:
            print("错误：toggle 需要编号")
            sys.exit(1)
        toggle_task(int(args[0]))
    elif cmd == "delete":
        if not args:
            print("错误：delete 需要编号")
            sys.exit(1)
        delete_task(int(args[0]))
    elif cmd == "clear":
        clear_tasks()
    elif cmd == "self":
        open_self()
    elif cmd == "config":
        cmd_config(args)
    elif cmd == "help":
        show_help()
    else:
        print(f"未知命令：{sys.argv[1]}\n")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()