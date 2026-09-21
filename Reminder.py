import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading
import ctypes
import sys
import os
import json
from datetime import date, datetime


class RestReminder:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("休息提醒 & 日程(by Donald J.Trump,20260920)")
        self.root.geometry("550x680")
        self.root.minsize(460, 680)
        self.root.resizable(True, True)

        # ---------- 数据文件路径 ----------
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(base_dir, "schedule.json")

        # ---------- 日程数据 ----------
        self.tasks = []
        self.last_task_check = None
        self.is_topmost = False
        # 到点提醒状态（每天重置）
        self._reminded_date = None
        self._reminded_ids = set()
        self.load_data()

        # ---------- 图标 ----------
        icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        # ---------- 计时状态 ----------
        self.is_running = False
        self.work_timer = None
        self.phase = "idle"
        self.phase_start_time = 0
        self.phase_end_time = 0
        self.work_seconds = 0
        self.rest_seconds = 0
        self.work_start_time = 0
        self.last_sleep_time = 0

        self.setup_sleep_detection()
        self.create_ui()

        # ---------- 首次刷新 + 启动每分钟循环 ----------
        self.refresh_tasks()
        self.daily_task_check()
        self.check_timed_tasks()
        self.root.after(60000, self.periodic_tick)

    # ==================================================
    #  UI
    # ==================================================
    def create_ui(self):
        # ---------- 统一调大 ttk 组件字体 ----------
        style = ttk.Style()
        base_font = ("Microsoft YaHei", 12)
        style.configure("TLabel", font=base_font)
        style.configure("TButton", font=base_font)
        style.configure("TEntry", font=base_font)
        style.configure("TSpinbox", font=base_font)
        style.configure("TCheckbutton", font=base_font)
        style.configure("TLabelframe.Label",
                        font=("Microsoft YaHei", 12, "bold"))

        # ---------- 标题栏（标题 + 置顶按钮） ----------
        title_bar = tk.Frame(self.root)
        title_bar.pack(fill="x", pady=(8, 2))

        tk.Label(
            title_bar,
            text="休息提醒 & 日程",
            font=("Microsoft YaHei", 15, "bold")
        ).pack()

        topmost_frame = tk.Frame(self.root)
        topmost_frame.place(relx=1.0, rely=0, anchor="ne", x=-12, y=10)

        self.topmost_btn = tk.Button(
            topmost_frame,
            text="置顶",
            command=self.toggle_topmost,
            font=("Microsoft YaHei", 10),
            relief="flat",
            bd=0,
            bg="#f0f0f0",
            fg="#666666",
            activebackground="#e0e0e0",
            activeforeground="#333333",
            cursor="hand2",
            padx=10,
            pady=1
        )
        self.topmost_btn.pack()

        # 状态
        self.status_var = tk.StringVar(value="程序未启动")
        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Microsoft YaHei", 13),
            fg="blue"
        ).pack(pady=2)

        # 计时大字
        self.timer_var = tk.StringVar(value="00:00:00")
        tk.Label(
            self.root,
            textvariable=self.timer_var,
            font=("Microsoft YaHei", 30, "bold"),
            fg="green"
        ).pack(pady=4)

        # 控制按钮
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=4)

        self.start_btn = ttk.Button(
            button_frame, text="开始计时", command=self.start_timer
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(
            button_frame, text="停止计时",
            command=self.stop_timer, state="disabled"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 设置区
        settings_frame = ttk.LabelFrame(self.root, text="计时设置", padding=8)
        settings_frame.pack(fill="x", padx=20, pady=6)

        row = ttk.Frame(settings_frame)
        row.pack(fill="x", pady=3)

        ttk.Label(row, text="工作(分):").pack(side=tk.LEFT)
        self.work_time_var = tk.StringVar(value="40")
        ttk.Spinbox(
            row, from_=5, to=120,
            textvariable=self.work_time_var, width=6
        ).pack(side=tk.LEFT, padx=(2, 12))

        ttk.Label(row, text="休息(分):").pack(side=tk.LEFT)
        self.rest_time_var = tk.StringVar(value="10")
        ttk.Spinbox(
            row, from_=1, to=30,
            textvariable=self.rest_time_var, width=6
        ).pack(side=tk.LEFT, padx=2)

        self.daily_reminder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            settings_frame,
            text="启用每日开机提醒",
            variable=self.daily_reminder_var
        ).pack(anchor="w", pady=(2, 0))

        # ==================================================
        #  日程面板
        # ==================================================
        task_frame = ttk.LabelFrame(self.root, text="事件 / ddl", padding=8)
        task_frame.pack(fill="both", expand=True, padx=20, pady=6)

        # ---- 输入行 1：任务名 ----
        input_row = ttk.Frame(task_frame)
        input_row.pack(fill="x", pady=(0, 4))

        self.task_name_var = tk.StringVar()
        self.name_entry = ttk.Entry(
            input_row, textvariable=self.task_name_var
        )
        self.name_entry.pack(side=tk.LEFT, fill="x", expand=True)

        # ---- 输入行 2：日期(可选) + 时间(可选) + 重要 + 添加 ----
        opt_row = ttk.Frame(task_frame)
        opt_row.pack(fill="x", pady=(0, 6))

        self.task_date_var = tk.StringVar()
        self.task_time_var = tk.StringVar()
        self.task_important_var = tk.BooleanVar(value=False)

        ttk.Label(opt_row, text="日期:").pack(side=tk.LEFT)
        self.date_entry = ttk.Entry(
            opt_row, textvariable=self.task_date_var, width=10
        )
        self.date_entry.pack(side=tk.LEFT, padx=(2, 8))

        ttk.Label(opt_row, text="时间:").pack(side=tk.LEFT)
        self.time_entry = ttk.Entry(
            opt_row, textvariable=self.task_time_var, width=6
        )
        self.time_entry.pack(side=tk.LEFT, padx=(2, 8))

        ttk.Checkbutton(
            opt_row, text="重要", variable=self.task_important_var
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            opt_row, text="添加", width=6, command=self.add_task
        ).pack(side=tk.LEFT)

        self.name_entry.bind("<Return>", lambda e: self.add_task())
        self.date_entry.bind("<Return>", lambda e: self.add_task())
        self.time_entry.bind("<Return>", lambda e: self.add_task())

        # 滚动列表
        list_wrap = ttk.Frame(task_frame)
        list_wrap.pack(fill="both", expand=True)

        self.task_canvas = tk.Canvas(
            list_wrap, highlightthickness=0, bg="white", height=150
        )
        sb = ttk.Scrollbar(
            list_wrap, orient="vertical", command=self.task_canvas.yview
        )
        self.task_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.task_canvas.pack(side="left", fill="both", expand=True)

        self.task_inner = tk.Frame(self.task_canvas, bg="white")
        self.task_window = self.task_canvas.create_window(
            (0, 0), window=self.task_inner, anchor="nw"
        )

        self.task_inner.bind(
            "<Configure>",
            lambda e: self.task_canvas.configure(
                scrollregion=self.task_canvas.bbox("all")
            )
        )
        self.task_canvas.bind(
            "<Configure>",
            lambda e: self.task_canvas.itemconfig(
                self.task_window, width=e.width
            )
        )

        def _on_wheel(event):
            self.task_canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units"
            )

        self.task_canvas.bind(
            "<Enter>",
            lambda e: self.task_canvas.bind_all("<MouseWheel>", _on_wheel)
        )
        self.task_canvas.bind(
            "<Leave>",
            lambda e: self.task_canvas.unbind_all("<MouseWheel>")
        )

        # 日志
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=4)
        log_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.log_text = tk.Text(
            log_frame, height=4, width=50,
            font=("Microsoft YaHei", 11)
        )
        log_sb = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_sb.pack(side="right", fill="y")

        self.log("程序已启动，点击“开始计时”来启动提醒")
        self.log("日程：日期/时间均可留空；留空日期请勾选「重要」")

    # ==================================================
    #  日程：数据读写
    # ==================================================
    def load_data(self):
        self.tasks = []
        self.last_task_check = None
        if not os.path.exists(self.data_file):
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.tasks = data.get("tasks", []) or []
                self.is_topmost = bool(data.get("topmost", False))
                lc = data.get("last_check")
                if lc:
                    try:
                        self.last_task_check = date.fromisoformat(lc)
                    except Exception:
                        self.last_task_check = None
            elif isinstance(data, list):
                self.tasks = data
        except Exception as e:
            print(f"加载日程失败: {e}")

    def save_data(self):
        try:
            data = {
                "last_check": (
                    self.last_task_check.isoformat()
                    if self.last_task_check else None
                ),
                "topmost": self.is_topmost,
                "tasks": self.tasks,
            }
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"保存日程失败: {e}")

    # ==================================================
    #  日程：日期 / 时间解析
    # ==================================================
    @staticmethod
    def parse_date(s):
        """支持：9.26 / 9-26 / 09/26 / 2026.9.26 / 9月26日 等"""
        raw = (s or "").strip()
        if not raw:
            raise ValueError("空日期")
        for ch in "年月日/.\\":
            raw = raw.replace(ch, "-")
        parts = [p for p in raw.split("-") if p.strip()]
        nums = []
        for p in parts:
            nums.append(int(p))

        today = date.today()

        if len(nums) == 3:
            y, m, d = nums
            if y < 100:
                y += 2000
            return date(y, m, d)

        if len(nums) == 2:
            m, d = nums
            y = today.year
            cand = date(y, m, d)
            # 如果已经过去，算明年
            if cand < today:
                y += 1
            return date(y, m, d)

        raise ValueError("日期格式不正确")

    @staticmethod
    def parse_time(s):
        """解析具体时刻，返回 'HH:MM'。
        支持：23:59 / 23：59 / 9:5 / 2359 / 930 / 23 / 9点30 / 23时59分
        输入为空返回 None
        """
        raw = (s or "").strip()
        if not raw:
            return None
        raw = (raw.replace("：", ":")
                  .replace("时", ":")
                  .replace("点", ":")
                  .replace("分", "")
                  .strip(": "))

        if ":" in raw:
            parts = [p.strip() for p in raw.split(":") if p.strip() != ""]
            if len(parts) != 2:
                raise ValueError("时间格式不正确")
            h, m = int(parts[0]), int(parts[1])
        else:
            if not raw.isdigit():
                raise ValueError("时间格式不正确")
            if len(raw) <= 2:
                h, m = int(raw), 0
            elif len(raw) == 3:
                h, m = int(raw[0]), int(raw[1:])
            elif len(raw) == 4:
                h, m = int(raw[:2]), int(raw[2:])
            else:
                raise ValueError("时间格式不正确")

        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("时间超出范围")
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def fmt_due(due):
        today = date.today()
        if due.year == today.year:
            return f"{due.month}.{due.day}"
        return f"{due.year}.{due.month}.{due.day}"

    # ==================================================
    #  日程：增删
    # ==================================================
    def add_task(self):
        name = self.task_name_var.get().strip()
        ds = self.task_date_var.get().strip()
        ts = self.task_time_var.get().strip()
        important = bool(self.task_important_var.get())

        if not name:
            self.log("请输入任务名称")
            self.name_entry.focus_set()
            return

        # ---- 日期（可选） ----
        due = None
        if ds:
            try:
                due = self.parse_date(ds)
            except Exception:
                self.log(f"无法识别的日期：{ds}")
                self.date_entry.focus_set()
                return

        # ---- 时间（可选，必须先有日期） ----
        t = None
        if ts:
            if due is None:
                self.log("填写具体时间前，请先填写日期")
                self.date_entry.focus_set()
                return
            try:
                t = self.parse_time(ts)
            except Exception:
                self.log(f"无法识别的时间：{ts}")
                self.time_entry.focus_set()
                return

        self.tasks.append({
            "id": f"{int(time.time() * 1000)}-{len(self.tasks)}",
            "name": name,
            "due": due.isoformat() if due else None,
            "time": t,
            "important": important,
        })

        self.task_name_var.set("")
        self.task_date_var.set("")
        self.task_time_var.set("")
        self.task_important_var.set(False)
        self.name_entry.focus_set()

        self.save_data()
        self.refresh_tasks()

        if due:
            desc = self.fmt_due(due) + (f" {t}" if t else "")
        else:
            desc = "无期限"
        if important:
            desc += " ★"
        self.log(f"已添加日程：{desc} {name}")

    def delete_task(self, tid):
        task = next((t for t in self.tasks if t.get("id") == tid), None)
        if not task:
            return
        if not messagebox.askyesno(
            "删除日程", f"确定删除「{task['name']}」？"
        ):
            return
        self.tasks = [t for t in self.tasks if t.get("id") != tid]
        self.save_data()
        self.refresh_tasks()
        self.log(f"已删除日程：{task['name']}")

    # ==================================================
    #  日程：刷新显示
    # ==================================================
    def refresh_tasks(self):
        try:
            pos = self.task_canvas.yview()[0]
        except Exception:
            pos = 0.0

        for w in self.task_inner.winfo_children():
            w.destroy()

        today = date.today()

        items = []
        for t in self.tasks:
            due = None
            if t.get("due"):
                try:
                    due = date.fromisoformat(t["due"])
                except Exception:
                    due = None
            items.append((due, t))

        # 有日期的按日期升序；无日期的排最后（其中重要的靠前）
        def sort_key(item):
            d, t = item
            imp = 0 if t.get("important") else 1
            if d is None:
                return (2, date.max, imp)
            return (1, d, imp)

        items.sort(key=sort_key)

        if not items:
            tk.Label(
                self.task_inner,
                text="暂无日程，输入「任务名 + 日期」后回车添加",
                fg="#999", bg="white",
                font=("Microsoft YaHei", 11)
            ).pack(pady=24)
            return

        for due, t in items:
            important = bool(t.get("important"))
            timestr = t.get("time") or ""

            if due is None:
                date_text = "—"
                if important:
                    bg, fg = "#f3e8ff", "#6b21a8"
                    remain = "重要"
                else:
                    bg, fg = "#f7f7f7", "#888888"
                    remain = "无期限"
            else:
                d = (due - today).days
                date_text = self.fmt_due(due)

                if d < 0:
                    bg, fg = "#ffe5e5", "#c0392b"
                    remain = f"已过期 {-d} 天"
                elif d == 0:
                    bg, fg = "#ffe0cc", "#d35400"
                    remain = "今天截止"
                elif d == 1:
                    bg, fg = "#fff1cc", "#b8860b"
                    remain = "明天截止"
                elif d <= 3:
                    bg, fg = "#fff8e1", "#a67c00"
                    remain = f"还有 {d} 天"
                else:
                    bg, fg = "#ffffff", "#333333"
                    remain = f"还有 {d} 天"

                if important and d > 3:
                    bg = "#faf5ff"
                    fg = "#6b21a8"

            row = tk.Frame(self.task_inner, bg=bg)
            row.pack(fill="x", padx=2, pady=1)
            row.grid_columnconfigure(1, weight=1)

            tk.Label(
                row, text=date_text, bg=bg, fg=fg,
                width=9, anchor="w",
                font=("Microsoft YaHei", 12, "bold")
            ).grid(row=0, column=0, sticky="w", padx=(4, 2), pady=4)

            display_name = t["name"]
            if important:
                display_name = "★ " + display_name
            if len(display_name) > 22:
                display_name = display_name[:21] + "…"

            tk.Label(
                row, text=display_name, bg=bg, fg=fg,
                anchor="w",
                font=("Microsoft YaHei", 12,
                      "bold" if important else "normal")
            ).grid(row=0, column=1, sticky="we", padx=4)

            tk.Label(
                row, text=timestr, bg=bg, fg=fg, width=6,
                font=("Microsoft YaHei", 11, "bold")
            ).grid(row=0, column=2, padx=2)

            tk.Label(
                row, text=remain, bg=bg, fg=fg,
                font=("Microsoft YaHei", 12, "bold")
            ).grid(row=0, column=3, padx=6)

            del_lbl = tk.Label(
                row, text="×", bg=bg, fg="#999",
                cursor="hand2", width=2,
                font=("Microsoft YaHei", 14)
            )
            del_lbl.grid(row=0, column=4, padx=(0, 4))
            del_lbl.bind(
                "<Button-1>",
                lambda e, tid=t.get("id"): self.delete_task(tid)
            )

        self.task_canvas.after_idle(
            lambda p=pos: self.task_canvas.yview_moveto(p)
        )

    # ==================================================
    #  日程：每日提醒
    # ==================================================
    def daily_task_check(self):
        today = date.today()
        if self.last_task_check == today:
            return
        self.last_task_check = today
        self.save_data()

        urgent = []
        important_undated = []

        for t in self.tasks:
            due = None
            if t.get("due"):
                try:
                    due = date.fromisoformat(t["due"])
                except Exception:
                    due = None

            if due is None:
                if t.get("important"):
                    important_undated.append(t["name"])
                continue

            d = (due - today).days
            timestr = f" {t['time']}" if t.get("time") else ""

            if d < 0:
                urgent.append((d, f"「{t['name']}」已过期 {-d} 天"))
            elif d == 0:
                urgent.append((d, f"「{t['name']}」今天{timestr}截止"))
            elif d == 1:
                urgent.append((d, f"「{t['name']}」明天{timestr}截止"))

        urgent.sort(key=lambda x: x[0])

        lines = [x[1] for x in urgent]
        if important_undated:
            if lines:
                lines.append("")
            lines.append("重要事项（无截止日期）：")
            lines.extend(f"· {n}" for n in important_undated)

        if not lines:
            return

        self.show_notification("日程提醒", "\n".join(lines))
        self.log(
            f"日程提醒：{len(urgent)} 项临近或已过期，"
            f"{len(important_undated)} 项重要事项"
        )

    def check_timed_tasks(self):
        """每分钟检查：今天带具体时间的日程，到点前 10 分钟提醒一次"""
        now = datetime.now()
        if self._reminded_date != now.date():
            self._reminded_date = now.date()
            self._reminded_ids = set()

        for t in self.tasks:
            if not t.get("time") or not t.get("due"):
                continue
            tid = t.get("id")
            if tid in self._reminded_ids:
                continue

            try:
                due = date.fromisoformat(t["due"])
                hh, mm = t["time"].split(":")
                due_dt = datetime(
                    due.year, due.month, due.day, int(hh), int(mm)
                )
            except Exception:
                continue

            # 只处理今天的日程
            if due_dt.date() != now.date():
                continue

            delta = (due_dt - now).total_seconds()
            if delta > 600:          # 还没进入 10 分钟窗口
                continue

            self._reminded_ids.add(tid)

            if delta > 60:
                msg = (
                    f"「{t['name']}」将于 {t['time']} 截止，"
                    f"还有约 {int(delta // 60)} 分钟。"
                )
            elif delta > 0:
                msg = f"「{t['name']}」马上就要到截止时间 {t['time']} 了！"
            else:
                msg = f"「{t['name']}」已过截止时间 {t['time']}，请尽快处理！"

            self.show_notification("日程到点提醒", msg)
            self.log(f"到点提醒：{t['name']} ({t['time']})")

    def periodic_tick(self):
        """每分钟刷新一次剩余天数，并在跨天时做每日提醒"""
        try:
            self.refresh_tasks()
            self.daily_task_check()
            self.check_timed_tasks()
        except Exception as e:
            self.log(f"日程刷新失败: {e}")
        finally:
            self.root.after(60000, self.periodic_tick)

    # ==================================================
    #  窗口置顶（类似微信的置顶按钮）
    # ==================================================
    def apply_topmost(self):
        """把当前置顶状态应用到窗口和按钮外观"""
        try:
            self.root.attributes("-topmost", self.is_topmost)
        except Exception:
            pass

        if self.is_topmost:
            self.topmost_btn.config(
                text="已置顶",
                bg="#07c160", fg="white",
                activebackground="#06ad56", activeforeground="white"
            )
        else:
            self.topmost_btn.config(
                text="置顶",
                bg="#f0f0f0", fg="#666666",
                activebackground="#e0e0e0", activeforeground="#333333"
            )

    def toggle_topmost(self):
        """切换窗口永久置顶"""
        self.is_topmost = not self.is_topmost
        self.apply_topmost()
        self.save_data()
        if self.is_topmost:
            self.log("窗口已置顶，将始终显示在其他窗口前面")
        else:
            self.log("已取消窗口置顶")

    # ==================================================
    #  系统休眠检测
    # ==================================================
    def setup_sleep_detection(self):
        try:
            self.kernel32 = ctypes.windll.kernel32
            self.advapi32 = ctypes.windll.advapi32
            self.power_event = self.kernel32.CreateEventW(
                None, False, False, None
            )
        except Exception as e:
            self.log(f"休眠检测设置失败: {e}")

    # ==================================================
    #  日志
    # ==================================================
    def log(self, message):
        if not hasattr(self, "log_text"):
            print(message)
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    # ==================================================
    #  计时相关
    # ==================================================
    def format_seconds(self, seconds):
        seconds = int(max(0, seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start_timer(self):
        if self.is_running:
            return
        try:
            work_minutes = int(self.work_time_var.get())
            rest_minutes = int(self.rest_time_var.get())
        except ValueError:
            self.log("设置无效，请输入整数分钟")
            return

        self.work_seconds = work_minutes * 60
        self.rest_seconds = rest_minutes * 60

        self.is_running = True
        self.phase = "work"

        now = time.time()
        self.work_start_time = now
        self.phase_start_time = now
        self.phase_end_time = now + self.work_seconds

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_var.set(
            f"工作中... 剩余 {self.format_seconds(self.work_seconds)}"
        )
        self.timer_var.set("00:00:00")

        self.work_timer = threading.Thread(
            target=self.timer_worker, daemon=True
        )
        self.work_timer.start()

        self.log(
            f"计时器已启动：工作 {work_minutes} 分钟，休息 {rest_minutes} 分钟"
        )

        if self.daily_reminder_var.get():
            self.show_daily_reminder()

    def stop_timer(self):
        if not self.is_running:
            return
        self.is_running = False
        self.phase = "idle"
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("程序已停止")
        self.timer_var.set("00:00:00")
        self.log("计时器已停止")

    def timer_worker(self):
        while self.is_running:
            try:
                now = time.time()

                if self.phase == "work":
                    elapsed = now - self.phase_start_time
                    remain = max(0, self.phase_end_time - now)

                    time_str = self.format_seconds(elapsed)
                    status = f"工作中... 剩余 {self.format_seconds(remain)}"

                    self.root.after(
                        0, lambda s=time_str: self.timer_var.set(s)
                    )
                    self.root.after(
                        0, lambda s=status: self.status_var.set(s)
                    )

                    if now >= self.phase_end_time:
                        self.phase = "rest"
                        self.phase_start_time = now
                        self.phase_end_time = now + self.rest_seconds

                        rest_minutes = self.rest_seconds // 60
                        self.root.after(
                            0,
                            lambda rs=self.rest_seconds:
                            self.status_var.set(
                                f"休息中... 剩余 {self.format_seconds(rs)}"
                            )
                        )
                        self.show_rest_reminder(rest_minutes)
                        self.root.after(
                            0,
                            lambda rm=rest_minutes:
                            self.log(f"工作时间结束，开始 {rm} 分钟休息")
                        )

                elif self.phase == "rest":
                    remain = max(0, self.phase_end_time - now)
                    time_str = self.format_seconds(remain)
                    status = f"休息中... 剩余 {self.format_seconds(remain)}"

                    self.root.after(
                        0, lambda s=time_str: self.timer_var.set(s)
                    )
                    self.root.after(
                        0, lambda s=status: self.status_var.set(s)
                    )

                    if now >= self.phase_end_time:
                        self.phase = "work"
                        self.phase_start_time = now
                        self.phase_end_time = now + self.work_seconds

                        work_minutes = self.work_seconds // 60
                        self.root.after(
                            0,
                            lambda ws=self.work_seconds:
                            self.status_var.set(
                                f"工作中... 剩余 {self.format_seconds(ws)}"
                            )
                        )
                        self.show_work_reminder()
                        self.root.after(
                            0,
                            lambda wm=work_minutes:
                            self.log(
                                f"休息时间结束，开始新的工作周期（{wm} 分钟）"
                            )
                        )
                else:
                    break

                time.sleep(0.5)

            except Exception as e:
                self.root.after(
                    0, lambda err=e: self.log(f"计时器错误: {err}")
                )
                self.root.after(0, self.stop_timer)
                break

    def show_daily_reminder(self):
        message = (
            "早上好！\n\n"
            "新的一天开始了，请注意合理安排工作时间，"
            "保持健康的工作习惯。\n记得定时休息哦！"
        )
        self.show_notification("每日提醒", message)

    def show_rest_reminder(self, rest_minutes):
        message = (
            f"您已经连续工作 {self.work_seconds // 60} 分钟了！\n\n"
            f"建议休息 {rest_minutes} 分钟。\n"
            "站起来走动一下，看看远方，放松眼睛。"
        )
        self.show_notification("该休息了！", message)

    def show_work_reminder(self):
        message = (
            f"休息时间结束！\n\n"
            f"开始新的工作周期 ({self.work_seconds // 60} 分钟)。\n"
            "保持专注，高效工作！"
        )
        self.show_notification("该工作了！", message)

    def show_notification(self, title, message):
        """非阻塞弹窗，10 秒自动关闭"""
        def _show():
            try:
                win = tk.Toplevel(self.root)
                win.title(title)
                win.geometry("400x240")
                win.resizable(False, False)
                win.attributes("-topmost", True)

                win.update_idletasks()
                x = (win.winfo_screenwidth() - 400) // 2
                y = (win.winfo_screenheight() - 240) // 2
                win.geometry(f"+{x}+{y}")

                tk.Label(
                    win, text=title, font=("Arial", 14, "bold")
                ).pack(pady=(12, 4))

                text_wrap = tk.Text(
                    win, height=7, wrap="word",
                    relief="flat", bg=win.cget("bg"),
                    font=("Arial", 11)
                )
                text_wrap.insert("1.0", message)
                text_wrap.configure(state="disabled")
                text_wrap.pack(padx=16, pady=4, fill="both", expand=True)

                def close():
                    try:
                        if win.winfo_exists():
                            win.destroy()
                    except tk.TclError:
                        pass

                ttk.Button(win, text="知道了", command=close).pack(pady=8)
                win.after(10000, close)
                win.focus_force()

            except Exception as e:
                self.log(f"显示通知失败: {e}")

        self.root.after(0, _show)

    # ==================================================
    #  退出
    # ==================================================
    def on_closing(self):
        self.is_running = False
        try:
            self.save_data()
        except Exception:
            pass
        if hasattr(self, 'power_event'):
            try:
                self.kernel32.CloseHandle(self.power_event)
            except Exception:
                pass
        self.root.destroy()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()


def create_startup_shortcut():
    try:
        if getattr(sys, 'frozen', False):
            application_path = sys.executable
        else:
            application_path = os.path.abspath(__file__)

        startup_folder = os.path.join(
            os.path.expanduser("~"),
            "AppData", "Roaming", "Microsoft",
            "Windows", "Start Menu", "Programs", "Startup"
        )
        print(f"可以将程序快捷方式放到: {startup_folder}")
        print(f"程序路径: {application_path}")
    except Exception as e:
        print(f"创建启动项失败: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        app = RestReminder()
        app.run()
    elif sys.argv[1] == "--setup-startup":
        create_startup_shortcut()
