import sys
import json
import time
import subprocess
from pathlib import Path

import llm

VERSION = "1.2.0"

# 路径全部基于脚本所在目录，避免受"当前工作目录"影响
BASE_DIR    = Path(__file__).resolve().parent
FILE_PATH   = BASE_DIR / "tasks.json"
CONFIG_PATH = BASE_DIR / ".td_config.json"
ENV_PATH    = BASE_DIR / ".env"
UNDO_PATH   = BASE_DIR / ".td_last_add.json"

TASKS = []
CONFIG = {}

DEFAULT_CONFIG = {
    # 仅支持 Windows，编辑器直接用 notepad
    "editor": "notepad",
    # 下面三项：命令执行后是否自动把 `td l` 的内容再打印一遍
    "show_list_after_add": False,     # td a 之后
    "show_list_after_delete": False,  # td x 之后
    "show_list_after_done": True,     # td d 之后
    # 输入归一化：命令名大小写不敏感 + 任务名连续空格合并
    "normalize_input": True,
    # ---- 大模型接口（td @ 内容 用，仅 OpenAI 兼容格式）----
    "llm_url": "",                          # 例如 https://api.deepseek.com
    "llm_model": "",                        # 例如 deepseek-chat
    "llm_apikey": "",                       # 一般不填，放 .env 的 TD_LLM_APIKEY
    "llm_timeout": 60,                      # 请求超时秒数
    "llm_auto_confirm": True,               # 默认直接写入，不询问；设否可恢复确认
}

# 布尔配置项的友好写法
TRUE_WORDS = {"1", "true", "yes", "y", "on", "是", "开", "启用"}
FALSE_WORDS = {"0", "false", "no", "n", "off", "否", "关", "禁用"}

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
    "v": "version",
    "i": "ai",
    "ic": "ai-undo",
    "@": "ai",
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


# ---------- 撤销快照 ----------
def record_added(titles):
    """记下本次新增了哪些任务，供 td ic 撤回"""
    snapshot = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "titles": list(titles),
    }
    try:
        with open(UNDO_PATH, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"警告：撤销记录写入失败（{exc}），本次无法用 td ic 撤回。")


def load_last_add():
    """读取上一次新增快照，没有则返回 None"""
    if not UNDO_PATH.exists():
        return None
    try:
        with open(UNDO_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not data.get("titles"):
        return None
    return data


def cmd_undo():
    """td ic：撤回上一次添加的任务"""
    snapshot = load_last_add()
    if not snapshot:
        print("没有可撤回的记录。")
        return

    titles = snapshot["titles"]
    remaining = list(titles)
    removed = []

    # 从后往前按标题匹配删除，保证同名任务只删一次
    for title in remaining:
        for idx in range(len(TASKS) - 1, -1, -1):
            if TASKS[idx]["title"] == title:
                TASKS.pop(idx)
                removed.append(title)
                break

    if not removed:
        print(f"撤回失败：列表里找不到上次添加的任务（{snapshot.get('time', '未知时间')}）。")
        UNDO_PATH.unlink(missing_ok=True)
        return

    save_tasks()
    UNDO_PATH.unlink(missing_ok=True)

    print(f"已撤回 {len(removed)} 条任务：")
    for t in removed:
        print(f"  - {t}")
    missing = [t for t in titles if t not in removed]
    if missing:
        print(f"\n有 {len(missing)} 条已被手动改动，未能撤回：")
        for t in missing:
            print(f"  - {t}")


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


def open_config():
    """用配置里的编辑器打开配置文件；不存在则先按默认值创建"""
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        save_config()
        print(f"已生成默认配置文件：{config_path}")

    editor = CONFIG.get("editor", "notepad")
    print(f"用 {editor} 打开：{config_path}")
    try:
        subprocess.Popen([editor, str(config_path)])
    except FileNotFoundError:
        print(f"错误：找不到编辑器 {editor}，用 `td cfg set editor <名字>` 修改。")


def parse_bool(value):
    """把用户输入的开关值转成 bool，无法识别返回 None"""
    text = str(value).strip().lower()
    if text in TRUE_WORDS:
        return True
    if text in FALSE_WORDS:
        return False
    return None


def parse_index(value):
    """把命令行里的编号转成 int；非法输入给出友好提示后退出"""
    try:
        return int(value)
    except (TypeError, ValueError):
        print(f"错误：编号必须是数字，收到的是「{value}」")
        sys.exit(1)


def cmd_config(args):
    if not args:
        # 无参数：直接用编辑器打开配置文件
        open_config()
        return

    sub = args[0]
    if sub == "set" and len(args) >= 3:
        key, value = args[1], " ".join(args[2:])
        if key not in CONFIG:
            print(f"未知配置项：{key}（可用：{', '.join(CONFIG.keys())}）")
            return
        # 布尔项统一转成 true/false 存储，避免 true/false/是/否 混用
        if isinstance(DEFAULT_CONFIG.get(key), bool):
            parsed = parse_bool(value)
            if parsed is None:
                print(f"错误：{key} 只接受 是/否（或 true/false/on/off/1/0）")
                return
            CONFIG[key] = parsed
            save_config()
            print(f"已设置 {key} = {'是' if parsed else '否'}")
            return
        CONFIG[key] = value
        save_config()
        print(f"已设置 {key} = {value}")
    elif sub == "get" and len(args) == 2:
        key = args[1]
        if key not in CONFIG:
            print(f"未知配置项：{key}")
            return
        val = CONFIG[key]
        print(f"{key} = {'是' if val else '否'}" if isinstance(val, bool) else f"{key} = {val}")
    elif sub in ("show", "list"):
        # 不打开文件，只打印当前配置
        print("当前配置：")
        for k, v in CONFIG.items():
            shown = f"是" if v is True else ("否" if v is False else v)
            print(f"  {k} = {shown}")
        print(f"\n配置文件：{CONFIG_PATH}")
    elif sub in ("path", "edit", "open"):
        open_config()
    else:
        print("用法：\n"
              "  td cfg                    打开配置文件\n"
              "  td cfg show               查看当前配置（不打开文件）\n"
              "  td cfg set <键> <值>      修改配置\n"
              "  td cfg get <键>           读取单项\n"
              "\n可配置项：\n"
              "  editor                 用于打开脚本/配置文件的编辑器\n"
              "  show_list_after_add    td a 后是否自动显示列表（默认 否）\n"
              "  show_list_after_delete td x 后是否自动显示列表（默认 否）\n"
              "  show_list_after_done   td d 后是否自动显示列表（默认 是）\n"
              "  normalize_input        命令大小写不敏感、任务名空格合并（默认 是）\n"
              "  llm_url                大模型接口地址，如 https://api.deepseek.com\n"
              "  llm_model              模型名，如 deepseek-chat\n"
              "  llm_apikey             apikey，建议放 .env 的 TD_LLM_APIKEY\n"
              "  llm_timeout            请求超时秒数（默认 60）\n"
              "  llm_auto_confirm       是否直接写入不询问（默认 是）")


def cmd_at(text):
    """td @ 内容：交给大模型拆成若干任务"""
    if not text or not text.strip():
        print("错误：@ 或 i 后面要跟内容，例如 td i 明天交报告然后买牛奶")
        sys.exit(1)

    print("正在交给大模型解析…")
    try:
        titles = llm.generate_titles(text, CONFIG, ENV_PATH)
    except llm.LLMError as exc:
        print(f"错误：{exc}")
        print("\n配置提示（括号内为当前值）：")
        print(f"  llm_url       = {CONFIG.get('llm_url') or '（空）'}")
        print(f"  llm_model     = {CONFIG.get('llm_model') or '（空）'}")
        print(f"  apikey        = {'已配置' if llm.resolve_api_key(CONFIG, ENV_PATH) else '未配置'}")
        print(f"\n设置示例：\n"
              f"  td cfg set llm_url https://api.deepseek.com\n"
              f"  td cfg set llm_model deepseek-chat\n"
              f"  然后在 {ENV_PATH} 写入：TD_LLM_APIKEY=sk-xxx")
        sys.exit(1)

    if not titles:
        print("模型没有生成任何任务。")
        return

    print(f"\n解析出 {len(titles)} 条任务：")
    for i, t in enumerate(titles, 1):
        print(f"  {i}. {t}")

    # 默认自动添加；只有 llm_auto_confirm 显式设为「否」才询问
    if CONFIG.get("llm_auto_confirm") is False:
        try:
            answer = input("\n确认添加？(Y/n) ").strip().lower()
        except EOFError:
            answer = "n"
        if answer in ("n", "no", "否"):
            print("已取消。")
            return
    for t in titles:
        TASKS.append({"title": t, "done": False})
    save_tasks()
    record_added(titles)
    print(f"\n已添加 {len(titles)} 条任务。（如需撤回：td ic）")

    if CONFIG.get("show_list_after_add"):
        print()
        list_tasks()


def show_version():
    """打印版本与运行环境"""
    print(f"td {VERSION}")
    print(f"Python {sys.version.split()[0]}")
    print(f"脚本：{Path(__file__).resolve()}")
    print(f"数据：{FILE_PATH}")
    print(f"配置：{CONFIG_PATH}")


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
version                      v       显示版本信息
ai <内容>                    i       交给大模型拆成多条任务
ai-undo                      ic      撤回上次 ai 添加的任务
help                         h       显示帮助

示例：
  td a 买牛奶
  td l
  td d 1
  td t 2
  td x 1
""")


# ---------- 入口 ----------
def normalize_title(parts):
    """把任务名的多个参数拼成一条，连续空白合并为单个空格，首尾去空白"""
    text = " ".join(parts)
    return " ".join(text.split())


def resolve(cmd: str) -> str:
    """命令名归一化：大小写不敏感、去掉首尾空白"""
    if not CONFIG.get("normalize_input", True):
        return ALIASES.get(cmd, cmd)
    key = cmd.strip().lower()
    return ALIASES.get(key, key)


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

    if cmd == "ai":
        cmd_at(" ".join(args))
    elif cmd == "ai-undo":
        cmd_undo()
    elif cmd == "add":
        if not args:
            print("错误：add 需要任务名，例如 td add 买牛奶")
            sys.exit(1)
        title = normalize_title(args) if CONFIG.get("normalize_input", True) else " ".join(args)
        if not title:
            print("错误：任务名不能为空。")
            sys.exit(1)
        add_task(title)
        if CONFIG.get("show_list_after_add"):
            print()
            list_tasks()
    elif cmd == "list":
        list_tasks()
    elif cmd == "done":
        if not args:
            print("错误：done 需要编号，例如 td done 1")
            sys.exit(1)
        mark_done(parse_index(args[0]))
        if CONFIG.get("show_list_after_done"):
            print()
            list_tasks()
    elif cmd == "toggle":
        if not args:
            print("错误：toggle 需要编号")
            sys.exit(1)
        toggle_task(parse_index(args[0]))
    elif cmd == "delete":
        if not args:
            print("错误：delete 需要编号")
            sys.exit(1)
        delete_task(parse_index(args[0]))
        if CONFIG.get("show_list_after_delete"):
            print()
            list_tasks()
    elif cmd == "clear":
        clear_tasks()
    elif cmd == "self":
        open_self()
    elif cmd == "config":
        cmd_config(args)
    elif cmd == "help":
        show_help()
    elif cmd == "version":
        show_version()
    else:
        print(f"未知命令：{sys.argv[1]}\n")
        show_help()
        sys.exit(1)


if __name__ == "__main__":
    main()