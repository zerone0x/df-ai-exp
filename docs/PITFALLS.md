# DF-AI Pitfalls & Lessons Learned

> 踩坑记录。每个坑都是真金白银（CPU 时间 + VPS 稳定性）换来的。

## 1. SDL2 不接收 xdotool 键盘/鼠标事件

**现象：** xdotool `key`/`click` 命令执行成功（rc=0），但 DF 完全无反应。

**原因：** SDL2 默认过滤 `XSendEvent` 合成事件（安全机制）。xdotool 的 `--window` 模式用的就是 XSendEvent。即使不加 `--window`，xdotool 的 XTEST 路径也可能因为 SDL2 内部事件循环的实现而被忽略。

**验证过程：**
- ❌ `xdotool key --window <id> Return` — 无效
- ❌ `xdotool key Return`（无 --window）— 无效
- ❌ `xdotool keydown/keyup` — 无效
- ❌ `xdotool click` — 无效
- ❌ `xdotool windowfocus --sync` + `key` — 无效
- ❌ 安装 openbox 窗口管理器后重试 — 无效
- ❌ python-xlib XTEST `fake_input` 发送 KeyPress/KeyRelease — 无效
- ✅ **python-xlib XTEST `fake_input` 发送鼠标事件（ButtonPress/ButtonRelease + MotionNotify）— 有效！**

**结论：** SDL2 Steam 版 DF 只响应 XTEST 鼠标事件，不响应键盘事件。可能是 SDL2 内部的键盘事件处理走了不同的路径（XIM/XKB）。

**解决方案：**
```python
from Xlib import X, display
from Xlib.ext import xtest

d = display.Display(":50")
root = d.screen().root

# 移动指针
root.warp_pointer(x, y)
d.sync()

# 点击
xtest.fake_input(d, X.ButtonPress, detail=1)
d.sync()
time.sleep(0.05)
xtest.fake_input(d, X.ButtonRelease, detail=1)
d.sync()
```

**适用范围：** DF Premium (Steam) v50+。Classic/终端版不受影响（不用 SDL2 图形窗口）。

---

## 2. DFHack Lua GUI 调用 Segfault

**现象：** `dfhack-run lua 'print(df.global.gametype)'` 等涉及 GUI 的 Lua 调用直接 SIGSEGV。

**有效的：**
- `dfhack-run help` ✅
- `dfhack-run ls` ✅
- `dfhack-run tags` ✅
- `dfhack-run lua 'print(1+1)'` ✅（简单表达式）

**会崩的：**
- `dfhack-run lua 'print(df.global.gametype)'` ❌ SIGSEGV
- `dfhack-run lua 'print(tostring(df.global.gametype))'` ❌ SIGSEGV
- `dfhack-run lua 'dfhack.gui.getCurFocus(true)'` ❌ SIGSEGV
- `dfhack-run lua 'dfhack.screen.readTile(0,0)'` ❌ SIGSEGV

**原因推测：** dfhack-run 是通过 RPC socket 执行命令的。GUI 相关的全局变量访问可能需要在 DF 主线程中执行，RPC 线程访问会竞态崩溃。

**影响：** 不能用 Lua API 查询游戏状态（gamemode/gametype/focus screen 等），只能用文件系统（save 目录）+ 截图来判断状态。

---

## 3. DF 窗口坐标偏移

**现象：** 点击截图中看到的按钮位置，点不到。

**原因：** DF 创建的窗口大小（1200×800）≠ Xvfb 屏幕大小（1280×720）。

**实际布局：**
```
Screen: 1280×720
Window: 1200×800, position at (40, -40)

窗口坐标 (wx, wy) → 屏幕坐标 (wx+40, wy-40)
屏幕坐标 (sx, sy) → 窗口坐标 (sx-40, sy+40)

窗口底部 80px 超出屏幕外（不可见/不可点击）
窗口左右各有 40px 的黑边
```

**坑：** scrot 截图捕获的是屏幕（1280×720），但鼠标事件坐标也是屏幕空间。所以截图中看到的位置可以直接用，但需要注意窗口起始偏移。

**解决：** 启动 Xvfb 时使用更大的屏幕分辨率（如 1280×800 或 1920×1080），让窗口完全可见。或者 `DF_DISPLAY_WIDTH`/`DF_DISPLAY_HEIGHT` 环境变量控制 DF 窗口大小。

---

## 4. DF 窗口没有 WM_NAME

**现象：** `xdotool search --name "Dwarf Fortress"` 找不到窗口。

**原因：** SDL2 创建的顶层窗口（0x2001d6）没有设置 `WM_NAME`。实际的 "Dwarf Fortress" 名字在子窗口（0x400008）上。

**解决：** 用 `xwininfo -root -children` 或 python-xlib 遍历窗口树，按几何大小（1200×800 或 1280×720）找 DF 窗口，而不是按名字。

---

## 5. 多 DF 实例 = VPS 崩溃

**现象：** 开发过程中启动多个 DF 实例忘记清理，VPS load 飙到 36，内存/swap 全满。

**原因：** 每个 DF 实例：~100% CPU + ~300MB RAM。4 核 3.8G VPS 同时跑 2 个就很勉强，3 个直接挂。

**预防：**
```bash
# 每次启动前必须执行
scripts/df_safety.sh killall

# 开发时跑 guard
scripts/df_safety.sh guard &
```

**Guard 自动杀 DF 的条件：**
- 多于 1 个 DF 实例
- 系统 load > 3
- 可用内存 < 200MB

---

## 6. Xvfb 残留和 Auth 文件

**现象：** `/tmp/xvfb-run.*` 目录越积越多，每次 `xvfb-run` 都留一个。

**影响：** `find_active_session()` 找到错误的 auth 文件，连不上正确的 X session。

**预防：** 
- 不用 `xvfb-run`，直接 `Xvfb :50 -ac` 启动（更可控）
- 定期清理：`rm -rf /tmp/xvfb-run.*`
- 用固定 display number（:50-:59），不用 `-a` 自动分配

---

## 7. Shell 退出杀死后台进程

**现象：** `Xvfb :50 & ... && ...` 在一个 exec 命令中运行，shell 退出时 Xvfb 被杀。

**解决：** 用 `nohup` 启动持久进程：
```bash
nohup Xvfb :50 -screen 0 1280x800x24 -ac &>/tmp/xvfb.log &
```

---

## 8. Classic vs Premium 版本差异

**Classic（终端/curses）：**
- 纯文本界面，不用 SDL2
- DFHack 直接控制终端输入
- 键盘输入走标准 stdin
- 适合 headless 自动化

**Premium（Steam/图形）：**
- SDL2 图形窗口
- 鼠标驱动的 UI
- XSendEvent 被过滤
- 需要 XTEST 鼠标注入
- DFHack Lua GUI 调用 segfault

**建议：** 自动化优先用 Classic 版。Premium 只在需要图形交互（如截图验证）时用。

---

## 9. scrot 截图是假的（SDL2 GPU 渲染）

**现象：** scrot 截到的图看起来是 DF 画面，但像素分析发现大片区域是纯色填充（如 `(255,225,17)` 黄色），没有实际 UI 元素渲染。Vision model 对这些截图的描述是**幻觉**——它根据 DF 的常识脑补了按钮和文字。

**原因：** DF Premium 用 SDL2 + GPU 渲染（通过 DMA buffer），画面直接写入 GPU framebuffer。scrot 从 X11 buffer 读取的是过时或不完整的数据。

**验证：** `ls -la /proc/<df_pid>/fd` 显示 `dmabuf` 和 `udmabuf` 句柄，确认 GPU 渲染路径。

**影响：**
- 不能用截图做坐标定位或状态判断
- Vision model 对 VPS 截图的分析不可信
- macOS 截图工具不受影响（走 WindowServer compositing）

**解决方案：**
- 用文件系统检查代替截图（`data/save/region*` 目录）
- 用 DFHack 命令输出代替 GUI 状态查询
- 或者换 Classic 版（纯终端，不用 SDL2）

---

## Quick Reference: 什么能用什么不能用

| 方法 | 状态 | 备注 |
|------|------|------|
| `dfhack-run ls/help/tags` | ✅ | 纯 DFHack 命令 |
| `dfhack-run lua 'print(1+1)'` | ✅ | 简单 Lua |
| `dfhack-run lua 'df.global.*'` | ❌ | Segfault |
| `xdotool key` | ❌ | SDL2 过滤 |
| `xdotool click` | ❌ | SDL2 过滤 |
| python-xlib XTEST 鼠标 | ✅ | 唯一可靠的 UI 控制 |
| python-xlib XTEST 键盘 | ❌ | SDL2 不处理 |
| scrot 截图 | ⚠️ | Premium: GPU 渲染导致截图可能是脏数据 |
| 文件系统检查 (save/) | ✅ | worldgen 完成检测 |
| TEXT 模式 (PRINT_MODE:TEXT) | ✅ | 不需要 Xvfb，用 PTY 即可 |
| quickfort (蓝图) | ✅ | 堡垒模式下可用，dfhack-run 执行 |
| dig-now | ✅ | 堡垒模式下可用（主菜单报 "Map not available"）|
| dfhack lua (TEXT 模式) | ❌ | 仍然 segfault（不是 SDL2 的问题）|
