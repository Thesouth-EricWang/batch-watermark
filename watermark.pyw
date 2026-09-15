# -*- coding: utf-8 -*-
"""批量加水印 · 桌面版（CustomTkinter 界面）

给一个文件夹里的图片批量加水印。纯本地运行，不联网、不上传。
- 基础设置（位置/大小/深浅自适应）按文件夹保存，下次打开同一文件夹自动恢复。
- 描边 / 毛玻璃为「单张增强」，默认收起，仅对当前这张图开启，导出时逐张套用。
标志图：工具目录下的 logo.png（没有则用 logo_placeholder.png）。
配置文件与日志都在本工具目录（settings.json、logs/app.log）。
快捷键：← → 翻页；滚轮缩放、按住拖动、双击复原。
"""
import os
import sys
import math
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import customtkinter as ctk

import watermark_core as wc
import watermark_store as store

BASE = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else __file__))
BUNDLE = getattr(sys, "_MEIPASS", BASE)     # 打包后内置资源所在的解包目录
LOGO_CANDIDATES = ("logo.png", "logo_placeholder.png")   # 用户自备标志优先，其次占位图
SUPPORTED = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
PREVIEW_MAX = 1100
POPUP_MAX = 2200           # 查看原图窗口内部使用的最大边长（先降采样再合成，避免卡顿）
PANEL_W = 384              # 右侧参数面板固定宽度
OUT_SUBDIR = "已加水印"
VERSION = "1.1"
GITHUB_URL = "https://github.com/Thesouth-EricWang/batch-watermark"   # 关于窗口里的链接

C_BG = "#161b19"
C_PANEL = "#1f2724"
C_PANEL2 = "#273029"
C_LINE = "#33403a"
C_TEXT = "#e7e3d8"
C_MUTED = "#8f9a92"
C_ACCENT = "#4f8a68"
C_ACCENT_HOVER = "#5c9d78"
C_CANVAS = "#101413"

FONT = ("Microsoft YaHei UI", 13)
FONT_S = ("Microsoft YaHei UI", 12)
FONT_TITLE = ("Microsoft YaHei UI", 17, "bold")
FONT_H = ("Microsoft YaHei UI", 13, "bold")

# 单张增强的默认值
ENH_DEFAULT = dict(on=0, mode="follow", outline_style=0, outline_w=8,
                   plate=0, plate_alpha=20, plate_blur=2,
                   plate_pad=17, plate_radius=30, plate_fade=4)
ENH_KEYS = list(ENH_DEFAULT.keys())
MODE_LABELS = {"follow": "跟随全局", "auto": "自动", "light": "原色", "dark": "反白"}
LABEL_MODES = {v: k for k, v in MODE_LABELS.items()}


def resolve_logo_path(cfg=None):
    """标志图片位置：配置里指定的优先；其次 exe 旁 / data 目录 / 内置资源里的 logo。"""
    p = (cfg or {}).get("logo_path")
    if p and os.path.exists(p):
        return p
    for d in (BASE, getattr(store, "DATA_DIR", BASE), BUNDLE):
        for name in LOGO_CANDIDATES:
            fp = os.path.join(d, name)
            if os.path.exists(fp):
                return fp
    return None


def load_logo(path=None):
    if not path:
        path = resolve_logo_path()
    if not path or not os.path.exists(path):
        return None, None, None
    try:
        logo = Image.open(path).convert("RGBA")
    except Exception:
        return None, None, None
    seal, text = wc.split_logo(logo)
    if seal is None:
        return logo, None, None
    return logo, seal, text


class SliderRow(ctk.CTkFrame):
    """一行参数：标签 + 滑块 + 可输入数值框，双向联动。"""

    def __init__(self, parent, label, var, lo, hi, unit="", step=1, command=None):
        super().__init__(parent, fg_color="transparent")
        self.var = var
        self.lo, self.hi = lo, hi
        self.command = command
        self._guard = False

        ctk.CTkLabel(self, text=label, width=76, anchor="w",
                     font=FONT_S, text_color=C_TEXT).grid(row=0, column=0, sticky="w")
        self.slider = ctk.CTkSlider(
            self, from_=lo, to=hi, number_of_steps=int((hi - lo) / step),
            command=self._on_slide, height=18,
            fg_color=C_LINE, progress_color=C_ACCENT,
            button_color=C_ACCENT, button_hover_color=C_ACCENT_HOVER)
        self.slider.grid(row=0, column=1, sticky="ew", padx=(4, 8))
        self.grid_columnconfigure(1, weight=1)
        self.entry = ctk.CTkEntry(
            self, width=52, height=26, justify="center", font=FONT_S,
            fg_color=C_PANEL2, border_color=C_LINE, text_color=C_TEXT)
        self.entry.grid(row=0, column=2, sticky="e")
        self.entry.bind("<Return>", self._on_type)
        self.entry.bind("<FocusOut>", self._on_type)
        self.unit = ctk.CTkLabel(self, text=unit, width=16, anchor="w",
                                 font=FONT_S, text_color=C_MUTED)
        self.unit.grid(row=0, column=3, sticky="w")

        self.slider.set(var.get())
        self.entry.insert(0, str(var.get()))
        self.var.trace_add("write", self._on_var)

    def _on_var(self, *_):
        if self._guard:
            return
        self._guard = True
        v = self.var.get()
        self.slider.set(v)
        self.entry.delete(0, "end")
        self.entry.insert(0, str(v))
        self._guard = False

    def _on_slide(self, v):
        if self._guard:
            return
        self._guard = True
        iv = int(round(float(v)))
        self.var.set(iv)
        self.entry.delete(0, "end")
        self.entry.insert(0, str(iv))
        self._guard = False
        if self.command:
            self.command()

    def _on_type(self, _=None):
        if self._guard:
            return
        try:
            v = int(float(self.entry.get()))
        except Exception:
            v = self.var.get()
        v = max(self.lo, min(self.hi, v))
        self._guard = True
        self.var.set(v)
        self.slider.set(v)
        self.entry.delete(0, "end")
        self.entry.insert(0, str(v))
        self._guard = False
        if self.command:
            self.command()


class PreviewView:
    """画布上的可缩放/平移图像视图。
    用「视口裁剪」渲染：无论放大到多少倍，只把可见的那一块缩放到窗口尺寸，
    所以放大不会额外占内存、也不会因为图大而变慢；放大超过 1:1 时用最近邻，
    能直接看到像素感。
    """

    def __init__(self, canvas, max_zoom=32, native_cap=False):
        self.canvas = canvas
        self.img = None
        self.zoom = 1.0
        self.pan = [0.0, 0.0]
        self.max_zoom = max_zoom
        self.native_cap = native_cap      # True 时最多放到 1:1，不超原像素
        self._photo = None
        self._drag = None

    def set_image(self, im):
        if im is not self.img:
            self.img = im
            self._photo = None

    def _fit(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if self.img is None or cw < 4 or ch < 4:
            return None
        BW, BH = self.img.size
        f = min((cw - 6) / BW, (ch - 6) / BH)
        return f, cw, ch, BW, BH

    def _max_allowed(self):
        r = self._fit()
        if r is None:
            return self.max_zoom
        f = r[0]
        hi = self.max_zoom
        if self.native_cap and f > 0:
            hi = min(hi, 1.0 / f)
        return max(1.0, hi)

    def clamp_pan(self):
        r = self._fit()
        if r is None:
            return
        f, cw, ch, BW, BH = r
        s = f * self.zoom
        mx = max(0.0, (BW * s - cw) / 2)
        my = max(0.0, (BH * s - ch) / 2)
        self.pan[0] = max(-mx, min(mx, self.pan[0]))
        self.pan[1] = max(-my, min(my, self.pan[1]))

    def zoom_at(self, factor, cx=None, cy=None):
        """以 (cx,cy) 为中心缩放；返回是否发生变化。"""
        r = self._fit()
        if r is None:
            return False
        f, cw, ch, BW, BH = r
        if cx is None:
            cx, cy = cw / 2, ch / 2
        old = self.zoom
        new = max(1.0, min(self._max_allowed(), old * factor))
        if abs(new - old) < 1e-9:
            return False
        s_old, s_new = f * old, f * new
        ox = cw / 2 - BW * s_old / 2 + self.pan[0]
        oy = ch / 2 - BH * s_old / 2 + self.pan[1]
        ix = (cx - ox) / s_old
        iy = (cy - oy) / s_old
        self.pan[0] = cx - ix * s_new - (cw / 2 - BW * s_new / 2)
        self.pan[1] = cy - iy * s_new - (ch / 2 - BH * s_new / 2)
        self.zoom = new
        self.clamp_pan()
        return True

    def zoom_step(self, factor):
        return self.zoom_at(factor)

    def zoom_actual(self):
        """缩放到 1:1（只在图大于窗口时有意义）。"""
        r = self._fit()
        if r is None:
            return False
        f = r[0]
        target = max(1.0, 1.0 / f)
        self.zoom = min(target, self._max_allowed())
        self.pan = [0.0, 0.0]
        return True

    def reset(self):
        self.zoom = 1.0
        self.pan = [0.0, 0.0]

    def drag_start(self, x, y):
        self._drag = (x, y)

    def drag_move(self, x, y):
        if self._drag is None:
            return False
        r = self._fit()
        if r is None:
            return False
        f, cw, ch, BW, BH = r
        s = f * self.zoom
        if BW * s <= cw and BH * s <= ch:
            self._drag = (x, y)
            return False
        dx = x - self._drag[0]
        dy = y - self._drag[1]
        self._drag = (x, y)
        self.pan[0] += dx
        self.pan[1] += dy
        self.clamp_pan()
        return True

    def drag_end(self):
        self._drag = None

    def draw(self):
        self.canvas.delete("all")
        r = self._fit()
        if r is None:
            return
        f, cw, ch, BW, BH = r
        s = f * self.zoom
        DW, DH = BW * s, BH * s
        ox = cw / 2 - DW / 2 + self.pan[0]
        oy = ch / 2 - DH / 2 + self.pan[1]
        # 可见区域（图坐标）
        bx0 = max(0.0, (0 - ox) / s)
        by0 = max(0.0, (0 - oy) / s)
        bx1 = min(float(BW), (cw - ox) / s)
        by1 = min(float(BH), (ch - oy) / s)
        if bx1 <= bx0 or by1 <= by0:
            return
        ix0, iy0 = int(bx0), int(by0)
        ix1, iy1 = min(int(math.ceil(bx1)), BW), min(int(math.ceil(by1)), BH)
        crop = self.img.crop((ix0, iy0, ix1, iy1))
        tw = max(1, int(round((ix1 - ix0) * s)))
        th = max(1, int(round((iy1 - iy0) * s)))
        # 放大过 1:1 用最近邻，像素感更直白；缩小用平滑
        resample = Image.NEAREST if s >= 1.0 else Image.LANCZOS
        disp = crop.resize((tw, th), resample)
        sx = int(round(ox + ix0 * s))
        sy = int(round(oy + iy0 * s))
        if (self._photo is not None and self._photo.width() == tw
                and self._photo.height() == th):
            self._photo.paste(disp)          # 同尺寸时复用，拖动更顺
        else:
            self._photo = ImageTk.PhotoImage(disp)
        self.canvas.create_image(sx, sy, image=self._photo, anchor="nw")
        # 图小于窗口时补个底色框，便于定位
        if DW < cw and DH < ch:
            self.canvas.create_rectangle(ox, oy, ox + DW, oy + DH,
                                         outline="#3a4a41", width=1)


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"批量加水印 v{VERSION}")
        root.geometry("1200x760")
        root.minsize(1000, 640)
        root.configure(fg_color=C_BG)

        self.cfg = store.load_config()
        self.logo_full, self.seal, self.text = load_logo(resolve_logo_path(self.cfg))
        self.files = []
        self.idx = -1
        self.folder = None
        self.preview_img = None
        self.orig_size = None        # 当前图原图尺寸
        self._composed = None        # 缩略图上已叠加水印的成品（预览用）
        self._composed_key = None
        self._repaint_job = None
        self._save_job = None
        self._preview_serial = 0
        self._thumb_cache = {}
        self._thumb_lock = threading.Lock()
        self._loading = False
        self._popup = None
        self._popup_queue = queue.Queue()
        self._alive = True

        # 基础参数（按文件夹保存）
        self.corner = tk.StringVar(value="tl")
        self.mode = tk.StringVar(value="auto")
        self.size_pct = tk.IntVar(value=20)
        self.margin_pct = tk.IntVar(value=4)
        self.opacity_pct = tk.IntVar(value=100)
        self.disc_alpha = tk.IntVar(value=92)
        self.disc_pad = tk.IntVar(value=2)
        self.dark_threshold = tk.IntVar(value=148)
        # 单张增强（仅当前图片）
        self.enh_store = {}          # {文件名: 增强参数字典}
        self.folder_enh = None       # 本文件夹的增强默认（None 则用全局 ENH_DEFAULT）
        self.enh_on = tk.IntVar(value=0)
        self.enh_mode = tk.StringVar(value="follow")   # 本张水印黑白：follow/auto/light/dark
        self.outline_style = tk.IntVar(value=0)
        self.outline_w = tk.IntVar(value=8)
        self.plate = tk.IntVar(value=0)
        self.plate_alpha = tk.IntVar(value=20)
        self.plate_blur = tk.IntVar(value=2)
        self.plate_pad = tk.IntVar(value=17)
        self.plate_radius = tk.IntVar(value=30)
        self.plate_fade = tk.IntVar(value=4)
        self.output_dir = None
        # 导出格式与质量
        self.export_format = tk.StringVar(value="keep")   # keep / jpeg / png / webp
        self.export_quality = tk.IntVar(value=92)         # JPEG / WebP 质量

        self._enh_vars = {
            "on": self.enh_on, "mode": self.enh_mode,
            "outline_style": self.outline_style,
            "outline_w": self.outline_w, "plate": self.plate,
            "plate_alpha": self.plate_alpha, "plate_blur": self.plate_blur,
            "plate_pad": self.plate_pad, "plate_radius": self.plate_radius,
            "plate_fade": self.plate_fade,
        }
        # 基础参数变化时也要存配置
        for v in (self.corner, self.mode, self.size_pct, self.margin_pct,
                  self.opacity_pct, self.disc_alpha, self.disc_pad, self.dark_threshold,
                  self.export_format, self.export_quality):
            v.trace_add("write", lambda *_: self._schedule_save())

        self._build_ui()
        self._build_menu()
        self.view = PreviewView(self.canvas, max_zoom=32, native_cap=False)
        self.root.after(120, self._poll_popup)
        if self.seal is None:
            messagebox.showwarning(
                "缺标志", "没找到可用的标志图片。请把标志图放到工具目录下的 logo.png，\n"
                "或用菜单 设置 → 更换标志图片… 选一张。")

        root.bind("<Left>", lambda e: self.prev())
        root.bind("<Right>", lambda e: self.next())
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        store.log("程序启动")
        self._refresh_enh_ui()

    # ---------------- 界面 ----------------
    def _build_ui(self):
        root = self.root
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=3)
        root.grid_columnconfigure(1, weight=0)

        top = ctk.CTkFrame(root, fg_color=C_PANEL, corner_radius=0, height=56)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(4, weight=1)

        # 应用内自绘菜单：不用系统菜单条（那条是 Windows 画的，改不了色），
        # 这样才能保证顶栏配色和界面一致；下拉菜单保持系统默认色。
        menuf = ctk.CTkFrame(top, fg_color="transparent")
        menuf.grid(row=0, column=0, padx=(10, 6), pady=12)
        self._make_menu_button(menuf, "文件", self._menu_file)
        self._make_menu_button(menuf, "设置", self._menu_set)
        self._make_menu_button(menuf, "关于", self._menu_about)

        ctk.CTkLabel(top, text="批量加水印", font=FONT_TITLE, text_color=C_TEXT).grid(
            row=0, column=1, padx=(6, 8), pady=12)
        ctk.CTkLabel(top, text=f"v{VERSION} · 纯本地运行", font=FONT_S,
                     text_color=C_MUTED).grid(row=0, column=2, padx=(0, 18))
        self.folder_lb = ctk.CTkLabel(top, text="", font=FONT_S, text_color=C_MUTED)
        self.folder_lb.grid(row=0, column=4, padx=(0, 10), sticky="e")
        ctk.CTkButton(top, text="选择文件夹", width=110, height=32, font=FONT_S,
                      fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, corner_radius=8,
                      command=self.pick_folder).grid(row=0, column=5, padx=(6, 6))
        self.export_btn = ctk.CTkButton(
            top, text="导出全部", width=110, height=32, font=FONT_S,
            fg_color="#3a4a41", hover_color=C_ACCENT, corner_radius=8,
            state="disabled", command=self.export)
        self.export_btn.grid(row=0, column=6, padx=(0, 16))

        # 左：预览
        left = ctk.CTkFrame(root, fg_color=C_PANEL, corner_radius=12)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=12)
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(left, bg=C_CANVAS, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.canvas.bind("<Configure>", lambda e: self._draw_view())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.view.drag_start(e.x, e.y))
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.view.drag_end())
        self.canvas.bind("<Double-Button-1>", lambda e: self._reset_view())

        bottom = ctk.CTkFrame(left, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ctk.CTkButton(bottom, text="← 上一张", width=88, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self.prev).pack(side="left")
        ctk.CTkButton(bottom, text="下一张 →", width=88, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self.next).pack(side="left", padx=(8, 14))
        ctk.CTkButton(bottom, text="−", width=34, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self._zoom_out).pack(side="left")
        ctk.CTkButton(bottom, text="＋", width=34, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self._zoom_in).pack(side="left", padx=(6, 0))
        ctk.CTkButton(bottom, text="恢复", width=52, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self._reset_view).pack(side="left", padx=(6, 14))
        ctk.CTkButton(bottom, text="查看原图", width=84, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=self.view_original).pack(side="left", padx=(0, 14))
        self.status = ctk.CTkLabel(bottom, text="请选择图片文件夹", font=FONT_S,
                                   text_color=C_MUTED, anchor="w")
        self.status.pack(side="left")
        self.nav_lb = ctk.CTkLabel(bottom, text="", font=FONT_S, text_color=C_MUTED)
        self.nav_lb.pack(side="right")

        # 右：参数面板（外层容器固定宽度，避免内容变化时整栏横向挪动）
        root.grid_columnconfigure(0, weight=1, minsize=520)
        root.grid_columnconfigure(1, weight=0, minsize=PANEL_W)
        panel_wrap = ctk.CTkFrame(root, fg_color="transparent", width=PANEL_W)
        panel_wrap.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=12)
        panel_wrap.grid_propagate(False)
        right = ctk.CTkScrollableFrame(panel_wrap, fg_color=C_PANEL, corner_radius=12)
        right.pack(fill="both", expand=True)
        right.grid_columnconfigure(0, weight=1)
        self.right = right

        # 位置
        self._section(right, "水印位置")
        posf = ctk.CTkFrame(right, fg_color="transparent")
        posf.pack(fill="x", padx=12, pady=(0, 8))
        self._corner_btns = {}
        for i, (txt, val) in enumerate([("左上", "tl"), ("右上", "tr"), ("左下", "bl"), ("右下", "br")]):
            b = ctk.CTkButton(posf, text=txt, width=68, height=32, font=FONT_S,
                              corner_radius=8,
                              fg_color=C_ACCENT if val == "tl" else C_PANEL2,
                              hover_color=C_ACCENT_HOVER,
                              command=lambda v=val: self._set_corner(v))
            b.grid(row=i // 2, column=i % 2, padx=4, pady=4, sticky="ew")
            posf.grid_columnconfigure(i % 2, weight=1)
            self._corner_btns[val] = b

        # 大小
        self._section(right, "大小与留白")
        self.row_size = SliderRow(right, "标志宽度", self.size_pct, 6, 45, "%", 1, self._schedule_repaint)
        self.row_size.pack(fill="x", padx=12, pady=3)
        self.row_margin = SliderRow(right, "留白", self.margin_pct, 1, 15, "%", 1, self._schedule_repaint)
        self.row_margin.pack(fill="x", padx=12, pady=3)
        self.row_opacity = SliderRow(right, "不透明度", self.opacity_pct, 10, 100, "%", 1, self._schedule_repaint)
        self.row_opacity.pack(fill="x", padx=12, pady=3)

        # 深色底适配
        self._section(right, "深色底适配")
        seg = ctk.CTkSegmentedButton(
            right, values=["自动", "原色", "反白"], font=FONT_S,
            command=self._set_mode,
            selected_color=C_ACCENT, selected_hover_color=C_ACCENT_HOVER,
            unselected_color=C_PANEL2, unselected_hover_color=C_LINE,
            text_color=C_TEXT, height=32)
        seg.set("自动")
        seg.pack(fill="x", padx=12, pady=(0, 6))
        self.mode_seg = seg
        self.row_disc_a = SliderRow(right, "圆底浓度", self.disc_alpha, 0, 100, "%", 1, self._schedule_repaint)
        self.row_disc_a.pack(fill="x", padx=12, pady=3)
        self.row_disc_p = SliderRow(right, "圆底大小", self.disc_pad, -15, 20, "%", 1, self._schedule_repaint)
        self.row_disc_p.pack(fill="x", padx=12, pady=3)
        self.row_dark_th = SliderRow(right, "深浅判定", self.dark_threshold, 60, 220, "", 1, self._schedule_repaint)
        self.row_dark_th.pack(fill="x", padx=12, pady=3)
        ctk.CTkLabel(right, text="深色底上：校徽垫圆底、文字反白；浅色底保持原色。\n"
                                 "圆底大小为 0 刚好贴校徽外径，负值收在校徽内部。\n"
                                 "深浅判定：数值越高，越多图片按深色底处理。",
                     font=FONT_S, text_color=C_MUTED, justify="left", anchor="w").pack(
            fill="x", padx=12, pady=(6, 4))

        # ---- 单张增强（仅当前图片）----
        self._section(right, "单张增强 · 仅当前图片")

        # 本张水印黑白（独立于增强开关，随时可设）
        self.enh_mode_row = ctk.CTkFrame(right, fg_color="transparent")
        self.enh_mode_row.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(self.enh_mode_row, text="水印黑白", font=FONT_S,
                     text_color=C_TEXT, anchor="w").pack(fill="x")
        mrow = ctk.CTkFrame(self.enh_mode_row, fg_color="transparent")
        mrow.pack(fill="x", pady=(2, 0))
        self._enh_mode_btns = {}
        for i, (txt, code) in enumerate([("跟随", "follow"), ("自动", "auto"),
                                         ("原色", "light"), ("反白", "dark")]):
            b = ctk.CTkButton(mrow, text=txt, width=64, height=30, font=FONT_S,
                              corner_radius=8,
                              fg_color=C_ACCENT if code == "follow" else C_PANEL2,
                              hover_color=C_ACCENT_HOVER,
                              command=lambda c=code: self._set_enh_mode_code(c))
            b.grid(row=0, column=i, padx=3, sticky="ew")
            mrow.grid_columnconfigure(i, weight=1)
            self._enh_mode_btns[code] = b

        self.enh_head = ctk.CTkFrame(right, fg_color="transparent")
        self.enh_head.pack(fill="x", padx=12, pady=(0, 4))
        self.enh_switch = ctk.CTkSwitch(
            self.enh_head, text="启用（描边 / 毛玻璃）", font=FONT_S,
            text_color=C_TEXT, progress_color=C_ACCENT,
            variable=self.enh_on, onvalue=1, offvalue=0,
            command=self._toggle_enh)
        self.enh_switch.pack(side="left")
        self.enh_hint = ctk.CTkLabel(
            right, text="水印黑白随时可设，只作用本张；描边/毛玻璃默认不启用，开启后也只作用本张。\n"
                        "没有单独设过的图，用本文件夹默认（可在下方保存）。",
            font=FONT_S, text_color=C_MUTED, justify="left", anchor="w", wraplength=286)
        self.enh_hint.pack(fill="x", padx=12, pady=(0, 4))

        # 详情容器（开启后显示）
        self.enh_box = ctk.CTkFrame(right, fg_color=C_PANEL2, corner_radius=10)

        # 描边
        self.lbl_ol = ctk.CTkLabel(self.enh_box, text="描边样式", font=FONT_S,
                                   text_color=C_TEXT, anchor="w")
        self.outline_seg = ctk.CTkSegmentedButton(
            self.enh_box, values=["无", "白", "黑", "双色"], font=FONT_S,
            command=self._set_outline,
            selected_color=C_ACCENT, selected_hover_color=C_ACCENT_HOVER,
            unselected_color=C_PANEL, unselected_hover_color=C_LINE,
            text_color=C_TEXT, height=30)
        self.row_ow = SliderRow(self.enh_box, "描边宽度", self.outline_w, 2, 40, "", 1, self._on_enh_change)
        # 毛玻璃
        self.lbl_pl = ctk.CTkLabel(self.enh_box, text="毛玻璃底板", font=FONT_S,
                                   text_color=C_TEXT, anchor="w")
        self.plate_seg = ctk.CTkSegmentedButton(
            self.enh_box, values=["关", "开"], font=FONT_S,
            command=self._set_plate,
            selected_color=C_ACCENT, selected_hover_color=C_ACCENT_HOVER,
            unselected_color=C_PANEL, unselected_hover_color=C_LINE,
            text_color=C_TEXT, height=30)
        self.row_pa = SliderRow(self.enh_box, "雾面浓度", self.plate_alpha, 0, 100, "%", 1, self._on_enh_change)
        self.row_pb = SliderRow(self.enh_box, "模糊强度", self.plate_blur, 0, 40, "", 1, self._on_enh_change)
        self.row_pp = SliderRow(self.enh_box, "内边距", self.plate_pad, 0, 60, "", 1, self._on_enh_change)
        self.row_pr = SliderRow(self.enh_box, "圆角", self.plate_radius, 0, 50, "", 1, self._on_enh_change)
        self.row_pf = SliderRow(self.enh_box, "边缘淡出", self.plate_fade, 0, 40, "", 1, self._on_enh_change)
        self.apply_all_btn = ctk.CTkButton(
            self.enh_box, text="把当前增强套用到全部图片", font=FONT_S, height=30,
            fg_color=C_PANEL, hover_color=C_ACCENT, corner_radius=8,
            command=self._apply_enh_to_all)
        self.save_def_btn = ctk.CTkButton(
            self.enh_box, text="存为本文件夹默认（新图也用它）", font=FONT_S, height=30,
            fg_color=C_PANEL, hover_color=C_ACCENT, corner_radius=8,
            command=self._save_folder_enh_default)

        ctk.CTkLabel(right, text="预览：滚轮或 −/＋ 缩放（只看缩略图，不卡）；\n"
                                 "看真实效果点「查看原图」，新窗口后台渲染。",
                     font=FONT_S, text_color=C_MUTED, anchor="w",
                     justify="left", wraplength=286).pack(fill="x", padx=12, pady=(14, 14))

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=FONT_H,
                     text_color=C_ACCENT, anchor="w").pack(fill="x", padx=12, pady=(12, 4))

    # ---------------- 顶栏菜单（自绘，下拉用系统默认配色）----------------
    def _build_menu(self):
        self.root.bind("<Control-o>", lambda e: self.pick_folder())
        self.root.bind("<Control-O>", lambda e: self.pick_folder())

    def _make_menu_button(self, parent, label, builder):
        btn = ctk.CTkButton(parent, text=label, width=52, height=30, font=FONT_S,
                            fg_color="transparent", hover_color=C_PANEL2,
                            text_color=C_TEXT, corner_radius=8)
        btn.pack(side="left", padx=1)
        menu = tk.Menu(self.root, tearoff=0)     # 不做自定义，保持系统默认色
        builder(menu)

        def popup():
            try:
                menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
            finally:
                menu.grab_release()

        btn.configure(command=popup)
        return btn

    def _menu_file(self, m):
        m.add_command(label="打开图片文件夹…", accelerator="Ctrl+O", command=self.pick_folder)
        m.add_command(label="打开输出文件夹", command=self._open_output_dir)
        m.add_separator()
        m.add_command(label="退出", command=self._on_close)

    def _menu_set(self, m):
        m.add_command(label="更换标志图片…", command=self._change_logo)
        m.add_command(label="输出位置与导出格式…", command=self._export_dialog)
        m.add_command(label="清除本文件夹的增强默认", command=self._clear_folder_enh_default)

    def _menu_about(self, m):
        m.add_command(label="关于本工具…", command=self._show_about)
        m.add_command(label="打开配置与日志目录", command=self._open_log)

    def _change_logo(self):
        """更换默认标志图片：拷到工具目录下的 logo.png，并记住。"""
        p = filedialog.askopenfilename(
            title="选择标志图片（建议透明底 PNG）",
            filetypes=[("图片", "*.png *.webp *.bmp"), ("所有文件", "*.*")])
        if not p:
            return
        try:
            im = Image.open(p).convert("RGBA")
        except Exception as e:
            messagebox.showerror("无法读取", str(e))
            return
        dst = os.path.join(BASE, "logo.png")
        try:
            im.save(dst, "PNG")
        except Exception:
            dst = os.path.join(store.DATA_DIR, "logo.png")
            try:
                im.save(dst, "PNG")
            except Exception as e:
                messagebox.showerror("保存失败", str(e))
                return
        self.cfg["logo_path"] = dst
        store.save_config(self.cfg)
        self.logo_full, self.seal, self.text = load_logo(dst)
        if self.seal is None:
            messagebox.showwarning("标志不可用",
                                   "这张图无法拆分成校徽与文字两部分，请换一张。")
        else:
            store.log(f"更换标志：{p} -> {dst}")
        # 标志换了，预览要重算
        self._composed_key = None
        self._schedule_repaint()

    def _open_output_dir(self):
        d = self._resolve_out_dir()
        if not d:
            return
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as e:
            messagebox.showinfo("输出文件夹", f"{d}\n\n{e}")

    def _clear_folder_enh_default(self):
        self.folder_enh = None
        self._schedule_save()
        store.log(f"清除文件夹增强默认：{self.folder}")
        messagebox.showinfo("已清除", "本文件夹的增强默认已清除，将使用全局默认值。")

    def _show_about(self):
        win = ctk.CTkToplevel(self.root)
        win.title("关于 批量加水印")
        win.geometry("470x340")
        win.configure(fg_color=C_BG)
        try:
            win.transient(self.root)
        except Exception:
            pass

        ctk.CTkLabel(win, text="批量加水印", font=FONT_TITLE,
                     text_color=C_TEXT).pack(anchor="w", padx=24, pady=(22, 2))
        ctk.CTkLabel(win, text=f"版本 {VERSION}", font=FONT_S,
                     text_color=C_MUTED).pack(anchor="w", padx=24)
        ctk.CTkLabel(win, text="给一个文件夹里的图片批量加水印的桌面工具。",
                     font=FONT_S, text_color=C_TEXT, justify="left",
                     anchor="w").pack(anchor="w", padx=24, pady=(12, 2))
        ctk.CTkLabel(win, text="纯本地运行，不联网、不上传图片。", font=FONT_S,
                     text_color=C_TEXT, justify="left",
                     anchor="w").pack(anchor="w", padx=24)
        ctk.CTkLabel(win, text="Python · Pillow · CustomTkinter", font=FONT_S,
                     text_color=C_MUTED).pack(anchor="w", padx=24, pady=(10, 0))
        ctk.CTkLabel(win, text="MIT License  ·  Copyright (c) 2026 Thesouth",
                     font=FONT_S, text_color=C_MUTED).pack(anchor="w", padx=24, pady=(2, 12))
        ctk.CTkButton(win, text="打开项目主页", width=170, height=32, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=lambda: webbrowser.open(GITHUB_URL)).pack(anchor="w", padx=24)
        ctk.CTkLabel(win, text=GITHUB_URL, font=FONT_S, text_color=C_MUTED,
                     anchor="w").pack(anchor="w", padx=24, pady=(4, 0))
        ctk.CTkButton(win, text="关闭", width=90, height=30, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_LINE, corner_radius=8,
                      command=win.destroy).pack(anchor="e", padx=24, pady=(14, 16))

    # ---------------- 交互：基础参数 ----------------
    def _set_corner(self, val):
        self.corner.set(val)
        for k, b in self._corner_btns.items():
            b.configure(fg_color=C_ACCENT if k == val else C_PANEL2)
        self._schedule_repaint()

    def _set_mode(self, label):
        self.mode.set({"自动": "auto", "原色": "light", "反白": "dark"}[label])
        self._schedule_repaint()

    def _set_fmt(self, label):
        self.export_format.set({"原格式": "keep", "JPEG": "jpeg",
                                "PNG": "png", "WebP": "webp"}[label])
        self._schedule_save()

    def _open_log(self):
        p = store.log_path()
        try:
            if not os.path.exists(p):
                store.log("（用户打开日志，文件尚未创建）")
            os.startfile(os.path.dirname(p))
        except Exception as e:
            messagebox.showinfo("日志位置", f"日志文件：\n{p}\n\n{e}")

    # ---------------- 单张增强 ----------------
    def _current_key(self):
        if 0 <= self.idx < len(self.files):
            return os.path.basename(self.files[self.idx])
        return None

    def _enh_default(self):
        """本文件夹的增强默认；没有则退回全局默认。"""
        return self.folder_enh if self.folder_enh else ENH_DEFAULT

    def _enh_dict_from_vars(self):
        return {k: self._enh_vars[k].get() for k in ENH_KEYS}

    def _set_vars_from_enh(self, d):
        self._loading = True
        for k in ENH_KEYS:
            v = d.get(k, ENH_DEFAULT[k])
            if k == "mode":
                self._enh_vars[k].set(str(v))
            else:
                self._enh_vars[k].set(int(v))
        self._loading = False
        try:
            self.outline_seg.set({0: "无", 1: "白", 2: "黑", 3: "双色"}[self.outline_style.get()])
            self.plate_seg.set("开" if self.plate.get() else "关")
            self._sync_enh_mode_btns()
        except Exception:
            pass

    def _load_enh_for_current(self):
        key = self._current_key()
        if key is None:
            self._set_vars_from_enh(self._enh_default())
        else:
            self._set_vars_from_enh(self.enh_store.get(key, self._enh_default()))
        self._refresh_enh_ui()

    def _toggle_enh(self):
        if self._current_key() is None:
            self.enh_on.set(0)
            return
        self._on_enh_change()

    def _on_enh_change(self):
        if self._loading:
            return
        key = self._current_key()
        if key is not None:
            self.enh_store[key] = self._enh_dict_from_vars()
        self._refresh_enh_ui()
        self._schedule_save()
        self._schedule_repaint()

    def _set_outline(self, label):
        self.outline_style.set({"无": 0, "白": 1, "黑": 2, "双色": 3}[label])
        self._on_enh_change()

    def _set_enh_mode(self, label):
        self.enh_mode.set(LABEL_MODES.get(label, "follow"))
        self._sync_enh_mode_btns()
        self._on_enh_change()

    def _set_enh_mode_code(self, code):
        self.enh_mode.set(code)
        self._sync_enh_mode_btns()
        self._on_enh_change()

    def _sync_enh_mode_btns(self):
        cur = self.enh_mode.get()
        for code, b in self._enh_mode_btns.items():
            try:
                b.configure(fg_color=C_ACCENT if code == cur else C_PANEL2)
            except Exception:
                pass

    def _set_plate(self, label):
        self.plate.set(1 if label == "开" else 0)
        self._on_enh_change()

    def _save_folder_enh_default(self):
        """把当前增强设置存为本文件夹的默认（没单独设过的图都用它）。"""
        if self._current_key() is None:
            return
        self.folder_enh = self._enh_dict_from_vars()
        self._schedule_save()
        store.log(f"保存文件夹增强默认：{self.folder}")
        messagebox.showinfo("已保存", "当前增强设置已存为本文件夹的默认；\n"
                                      "本文件夹中没有单独设置的图片都会用它。")

    def _apply_enh_to_all(self):
        if self._current_key() is None:
            return
        d = self._enh_dict_from_vars()
        for f in self.files:
            self.enh_store[os.path.basename(f)] = dict(d)
        self._schedule_save()
        store.log(f"增强套用到全部 {len(self.files)} 张")
        messagebox.showinfo("已套用", f"当前增强设置已套用到全部 {len(self.files)} 张图片。")

    def _relayout_enh(self):
        sig = (self.outline_style.get() != 0, self.plate.get() == 1)
        if sig == getattr(self, "_relayout_sig", None):
            return
        self._relayout_sig = sig
        for w in self.enh_box.winfo_children():
            w.pack_forget()
        p = dict(fill="x", padx=10, pady=4)
        self.lbl_ol.pack(**p)
        self.outline_seg.pack(**p)
        if self.outline_style.get() != 0:
            self.row_ow.pack(**p)
        self.lbl_pl.pack(**p)
        self.plate_seg.pack(**p)
        if self.plate.get() == 1:
            for r in (self.row_pa, self.row_pb, self.row_pp, self.row_pr, self.row_pf):
                r.pack(**p)
        self.apply_all_btn.pack(**dict(fill="x", padx=10, pady=(8, 4)))
        self.save_def_btn.pack(**dict(fill="x", padx=10, pady=(0, 10)))

    def _refresh_enh_ui(self):
        """根据是否有图、是否启用，显示/隐藏增强控件。"""
        has_img = self._current_key() is not None
        want = "normal" if has_img else "disabled"
        # 只在状态真的变化时改，避免每次拖动都触发重建导致跳动
        if want != getattr(self, "_enh_state", None):
            self._enh_state = want
            try:
                self.enh_switch.configure(state=want)
            except Exception:
                pass
            for b in self._enh_mode_btns.values():
                try:
                    b.configure(state=want)
                except Exception:
                    pass
        if self.enh_on.get() == 1 and has_img:
            if not self.enh_box.winfo_manager():
                self.enh_box.pack(fill="x", padx=12, pady=(2, 6))
            self._relayout_enh()
        else:
            if self.enh_box.winfo_manager():
                self.enh_box.pack_forget()

    # ---------------- 文件夹 ----------------
    def pick_folder(self):
        d = filedialog.askdirectory()
        if not d:
            return
        self._open_folder(d)

    def _open_folder(self, d):
        # 切换文件夹前，先把上一个文件夹的待保存落下（否则会写到新文件夹名下）
        if self._save_job:
            self.root.after_cancel(self._save_job)
            self._save_job = None
        self._save_now()
        files = sorted(
            os.path.join(d, f) for f in os.listdir(d)
            if f.lower().endswith(SUPPORTED) and os.path.isfile(os.path.join(d, f)))
        if not files:
            self.folder_lb.configure(text="该文件夹里没有图片")
            return
        self.folder = d
        self.files = files
        self.idx = 0
        with self._thumb_lock:
            self._thumb_cache.clear()
        self._composed_key = None
        self.folder_lb.configure(text=f"{os.path.basename(d)} / {len(files)} 张")
        self.export_btn.configure(state="normal", fg_color=C_ACCENT)

        # 载入该文件夹的配置
        saved = store.get_folder_cfg(self.cfg, d)
        self.enh_store = {}
        if saved:
            base = saved.get("base") or {}
            self._loading = True
            try:
                self.corner.set(base.get("corner", "tl"))
                self.mode.set(base.get("mode", "auto"))
                self.size_pct.set(int(base.get("size_pct", 20)))
                self.margin_pct.set(int(base.get("margin_pct", 4)))
                self.opacity_pct.set(int(base.get("opacity_pct", 100)))
                self.disc_alpha.set(int(base.get("disc_alpha", 92)))
                self.disc_pad.set(int(base.get("disc_pad", 2)))
                self.dark_threshold.set(int(base.get("dark_threshold", 148)))
                self.export_format.set(base.get("export_format", "keep"))
                self.export_quality.set(int(base.get("export_quality", 92)))
            finally:
                self._loading = False
            self._sync_corner_btns()
            self._sync_mode_seg()
            fd = saved.get("enh_default")
            self.folder_enh = dict(ENH_DEFAULT, **fd) if fd else None
            self.enh_store = {k: dict(self._enh_default(), **v)
                              for k, v in (saved.get("enh") or {}).items()}
            self.output_dir = saved.get("output_dir")
            store.log(f"打开文件夹 {d}（{len(files)} 张，已载入配置）")
        else:
            self.folder_enh = None
            self.output_dir = None
            store.log(f"打开文件夹 {d}（{len(files)} 张，无历史配置）")

        self._load_preview(0)

    def _sync_corner_btns(self):
        cur = self.corner.get()
        for k, b in self._corner_btns.items():
            b.configure(fg_color=C_ACCENT if k == cur else C_PANEL2)

    def _sync_mode_seg(self):
        self.mode_seg.set({"auto": "自动", "light": "原色", "dark": "反白"}[self.mode.get()])

    def _resolve_out_dir(self):
        if self.output_dir:
            return self.output_dir
        if self.files:
            return os.path.join(os.path.dirname(self.files[0]), OUT_SUBDIR)
        return None

    def prev(self):
        if self.files:
            self.idx = (self.idx - 1) % len(self.files)
            self._load_preview(self.idx)

    def next(self):
        if self.files:
            self.idx = (self.idx + 1) % len(self.files)
            self._load_preview(self.idx)

    # ---------------- 配置保存 ----------------
    def _schedule_save(self):
        if self._save_job:
            self.root.after_cancel(self._save_job)
        self._save_job = self.root.after(700, self._save_now)

    def _save_now(self):
        self._save_job = None
        if not self.folder:
            return
        data = {
            "base": {
                "corner": self.corner.get(), "mode": self.mode.get(),
                "size_pct": self.size_pct.get(), "margin_pct": self.margin_pct.get(),
                "opacity_pct": self.opacity_pct.get(),
                "disc_alpha": self.disc_alpha.get(), "disc_pad": self.disc_pad.get(),
                "dark_threshold": self.dark_threshold.get(),
                "export_format": self.export_format.get(),
                "export_quality": self.export_quality.get(),
            },
            "enh": self.enh_store,
            "enh_default": self.folder_enh,
            "output_dir": self.output_dir,
        }
        ok = store.set_folder_cfg(self.cfg, self.folder, data)
        if not ok:
            store.log(f"保存配置未成功：{self.folder}")

    # ---------------- 预览 ----------------
    def _load_preview(self, idx):
        p = self.files[idx]
        with self._thumb_lock:
            cached = self._thumb_cache.get(idx)
        if cached is not None:
            im, (full_w, full_h) = cached
        else:
            im, full_w, full_h = self._decode_thumb(p)
            if im is None:
                self.status.configure(text="无法打开该图片")
                store.log(f"无法打开 {p}")
                return
            with self._thumb_lock:
                self._thumb_cache[idx] = (im, (full_w, full_h))
                self._trim_cache_locked()
        self.preview_img = im
        self.orig_size = (full_w, full_h)
        self._preview_serial += 1
        if hasattr(self, "view"):
            self.view.reset()
        self.status.configure(text=f"{os.path.basename(p)} · {full_w}×{full_h}")
        self.nav_lb.configure(text=f"{idx + 1} / {len(self.files)}")
        self._load_enh_for_current()
        self._schedule_repaint()
        self._preload_neighbors()

    def _decode_thumb(self, p):
        try:
            img = Image.open(p)
            full_w, full_h = img.size
            try:
                img.draft("RGB", (PREVIEW_MAX, PREVIEW_MAX))
            except Exception:
                pass
            im = img.convert("RGBA")
            im.thumbnail((PREVIEW_MAX, PREVIEW_MAX), Image.LANCZOS)
            return im, full_w, full_h
        except Exception:
            return None, 0, 0

    def _trim_cache_locked(self):
        if len(self._thumb_cache) <= 6:
            return
        keys = sorted(self._thumb_cache.keys(),
                      key=lambda k: abs(k - self.idx), reverse=True)
        for k in keys[6:]:
            self._thumb_cache.pop(k, None)

    def _preload_neighbors(self):
        for di in (1, -1, 2, -2):
            j = self.idx + di
            if 0 <= j < len(self.files):
                with self._thumb_lock:
                    if j in self._thumb_cache:
                        continue
                threading.Thread(target=self._preload_one, args=(j,), daemon=True).start()

    def _preload_one(self, j):
        im, w, h = self._decode_thumb(self.files[j])
        if im is None:
            return
        with self._thumb_lock:
            if j not in self._thumb_cache:
                self._thumb_cache[j] = (im, (w, h))

    # ---------------- 渲染 ----------------
    def _kwargs_from_enh(self, enh):
        on = int(enh.get("on", 0))
        em = enh.get("mode", "follow")
        eff_mode = self.mode.get() if em in ("follow", None, "") else em
        return dict(
            size_pct=self.size_pct.get(), margin_pct=self.margin_pct.get(),
            opacity_pct=self.opacity_pct.get(), corner=self.corner.get(),
            mode=eff_mode,
            disc_alpha=int(self.disc_alpha.get() * 255 / 100),
            disc_pad=self.disc_pad.get() / 100.0,
            dark_threshold=self.dark_threshold.get(),
            outline_style=(enh.get("outline_style", 0) if on else 0),
            outline_w=enh.get("outline_w", 8) / 100.0,
            plate=(enh.get("plate", 0) if on else 0),
            plate_alpha=enh.get("plate_alpha", 20),
            plate_blur=enh.get("plate_blur", 2) / 100.0,
            plate_pad=enh.get("plate_pad", 17) / 100.0,
            plate_radius=enh.get("plate_radius", 30) / 100.0,
            plate_fade=enh.get("plate_fade", 4) / 100.0)

    def _current_enh(self):
        key = self._current_key()
        if key is None:
            return self._enh_dict_from_vars()
        return self.enh_store.get(key, self._enh_dict_from_vars())

    def _schedule_repaint(self):
        if self._repaint_job:
            self.root.after_cancel(self._repaint_job)
        self._repaint_job = self.root.after(40, self._repaint)

    def _ensure_composed(self):
        """在缩略图上叠加水印，得到预览成品（缓存，参数不变则复用）。"""
        if self.preview_img is None:
            self._composed = None
            self._used_mode = None
            return
        enh = self._current_enh()
        key = (self._preview_serial, id(self.preview_img), tuple(sorted(enh.items())),
               self.corner.get(), self.mode.get(), self.size_pct.get(),
               self.margin_pct.get(), self.opacity_pct.get(),
               self.disc_alpha.get(), self.disc_pad.get(), self.dark_threshold.get())
        if key == self._composed_key and self._composed is not None:
            return
        if self.seal is not None:
            im, used = wc.render(self.preview_img, self.seal, self.text,
                                 **self._kwargs_from_enh(enh))
        else:
            im, used = self.preview_img, None
        self._composed = im
        self._composed_key = key
        self._used_mode = used

    def _repaint(self):
        self._repaint_job = None
        if self.preview_img is None:
            return
        self._ensure_composed()
        self.view.set_image(self._composed)
        self._draw_view()

    def _draw_view(self):
        if self.view.img is None:
            return
        self.view.clamp_pan()
        self.view.draw()
        tag = f"{self.idx + 1} / {len(self.files)}"
        if getattr(self, "_used_mode", None):
            tag += f" · {self._used_mode}"
        if self.enh_on.get() == 1 and self._current_key():
            tag += " · 增强"
        tag += f" · {int(round(self.view.zoom * 100))}%"
        self.nav_lb.configure(text=tag)

    # ---------- 预览缩放 / 拖动 ----------
    def _zoom_in(self):
        if self.view.zoom_step(1.25):
            self._draw_view()

    def _zoom_out(self):
        if self.view.zoom_step(1 / 1.25):
            self._draw_view()

    def _reset_view(self):
        self.view.reset()
        self._draw_view()

    def _on_wheel(self, event):
        if self.view.zoom_at(1.15 if event.delta > 0 else 1 / 1.15, event.x, event.y):
            self._draw_view()

    def _on_drag(self, event):
        if self.view.drag_move(event.x, event.y):
            self._draw_view()

    # ---------- 查看原图（后台渲染，不阻塞主界面）----------
    def view_original(self):
        if not self.files or self.seal is None:
            return
        path = self.files[self.idx]
        kwargs = self._kwargs_from_enh(self._current_enh())
        orig_size = self.orig_size
        win = ctk.CTkToplevel(self.root)
        win.title("原图效果预览 · " + os.path.basename(path))
        win.geometry("1060x760")
        win.configure(fg_color=C_CANVAS)
        lbl = ctk.CTkLabel(win, text="正在后台渲染原图，主界面可继续操作…",
                           text_color=C_TEXT, font=FONT)
        lbl.pack(expand=True)
        store.log(f"查看原图：{path}")

        def work():
            try:
                img = Image.open(path)
                try:
                    img.draft("RGB", (POPUP_MAX, POPUP_MAX))
                except Exception:
                    pass
                if max(img.size) > POPUP_MAX:
                    img.thumbnail((POPUP_MAX, POPUP_MAX), Image.LANCZOS)
                im = img.convert("RGBA")
                out, _ = wc.render(im, self.seal, self.text, **kwargs)
                self._popup_queue.put(("ok", win, (out, orig_size)))
            except Exception as e:
                store.log(f"原图渲染失败 {path}: {e}")
                self._popup_queue.put(("err", win, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _poll_popup(self):
        """主线程轮询后台渲染结果（跨线程只通过队列传递，不直接碰界面）。"""
        if not self._alive:
            return
        try:
            while True:
                kind, win, payload = self._popup_queue.get_nowait()
                if not win.winfo_exists():
                    continue
                if kind == "ok":
                    self._build_popup(win, payload)
                else:
                    for ch in win.winfo_children():
                        if isinstance(ch, tk.Label):
                            ch.configure(text="渲染失败：" + payload)
        except queue.Empty:
            pass
        except Exception as e:
            store.log(f"弹窗处理异常: {e}")
        finally:
            try:
                self.root.after(120, self._poll_popup)
            except Exception:
                pass

    def _build_popup(self, win, payload):
        if not win.winfo_exists():
            return
        img, orig_size = payload
        for w in win.winfo_children():
            w.destroy()
        bar = ctk.CTkFrame(win, fg_color=C_PANEL, corner_radius=0)
        bar.pack(side="bottom", fill="x")
        info = ctk.CTkLabel(bar, text="", text_color=C_MUTED, font=FONT_S, anchor="w")
        info.pack(side="left", padx=10, pady=6)
        canvas = tk.Canvas(win, bg=C_CANVAS, highlightthickness=0, bd=0)
        canvas.pack(side="top", fill="both", expand=True)
        view = PreviewView(canvas, max_zoom=12, native_cap=True)
        ow, oh = orig_size if orig_size else img.size

        def upd(*_):
            view.clamp_pan()
            view.draw()
            info.configure(text=f"原图 {ow}×{oh}  ·  内部预览 {img.size[0]}×{img.size[1]}"
                                f"（已降采样，不卡）  ·  {int(round(view.zoom * 100))}%")

        for txt, cmd in [("适应", lambda: (view.reset(), upd())),
                         ("100%", lambda: (view.zoom_actual(), upd())),
                         ("放大", lambda: (view.zoom_step(1.25), upd())),
                         ("缩小", lambda: (view.zoom_step(1 / 1.25), upd()))]:
            ctk.CTkButton(bar, text=txt, width=56, height=28, font=FONT_S,
                          fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                          command=cmd).pack(side="right", padx=(0, 6), pady=4)

        canvas.bind("<MouseWheel>", lambda e: (view.zoom_at(1.15 if e.delta > 0 else 1 / 1.15,
                                                           e.x, e.y) and upd()))
        canvas.bind("<ButtonPress-1>", lambda e: view.drag_start(e.x, e.y))
        canvas.bind("<B1-Motion>", lambda e: (view.drag_move(e.x, e.y) and upd()))
        canvas.bind("<ButtonRelease-1>", lambda e: view.drag_end())
        canvas.bind("<Double-Button-1>", lambda e: (view.reset(), upd()))
        canvas.bind("<Configure>", upd)
        view.set_image(img)
        upd()

    def _on_close(self):
        self._alive = False
        try:
            if self._save_job:
                self.root.after_cancel(self._save_job)
                self._save_job = None
            self._save_now()          # 关窗前强制落盘
        except Exception as e:
            store.log(f"关窗前保存失败: {e!r}")
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- 导出 ----------------
    def _save_one(self, out, out_dir, base, orig_ext):
        """按导出格式设置保存一张图。"""
        fmt = self.export_format.get()
        q = int(self.export_quality.get())
        if fmt == "jpeg":
            out.convert("RGB").save(os.path.join(out_dir, base + ".jpg"), "JPEG", quality=q)
        elif fmt == "png":
            out.convert("RGBA").save(os.path.join(out_dir, base + ".png"), "PNG")
        elif fmt == "webp":
            out.convert("RGBA").save(os.path.join(out_dir, base + ".webp"), "WEBP", quality=q)
        else:  # 跟随原格式
            if orig_ext == ".png":
                out.convert("RGBA").save(os.path.join(out_dir, base + ".png"), "PNG")
            elif orig_ext == ".bmp":
                out.convert("RGB").save(os.path.join(out_dir, base + ".bmp"), "BMP")
            elif orig_ext == ".webp":
                out.convert("RGBA").save(os.path.join(out_dir, base + ".webp"), "WEBP", quality=q)
            else:
                out.convert("RGB").save(os.path.join(out_dir, base + ".jpg"), "JPEG", quality=q)

    def export(self):
        """点「导出全部」：弹出导出设置窗口。"""
        if not self.files:
            return
        if self.seal is None:
            messagebox.showerror("错误", "缺少标志图片：请用菜单 设置 → 更换标志图片… 选一张。")
            return
        self._export_dialog()

    def _out_dir_text(self):
        return self.output_dir if self.output_dir else "原文件夹内的「已加水印」"

    def _export_summary(self):
        fmt = {"keep": "跟随原格式", "jpeg": "JPEG", "png": "PNG",
               "webp": "WebP"}.get(self.export_format.get(), "跟随原格式")
        n = len(self.files)
        if self.export_format.get() == "png":
            return f"共 {n} 张，输出为 {fmt}（无损）→ {self._resolve_out_dir()}"
        return f"共 {n} 张，输出为 {fmt}（质量 {self.export_quality.get()}）→ {self._resolve_out_dir()}"

    def _export_dialog(self):
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("导出设置")
        dlg.geometry("500x460")
        dlg.configure(fg_color=C_BG)
        try:
            dlg.transient(self.root)
        except Exception:
            pass

        ctk.CTkLabel(dlg, text="导出设置", font=FONT_TITLE, text_color=C_TEXT).pack(
            anchor="w", padx=18, pady=(16, 4))

        # 输出位置
        ctk.CTkLabel(dlg, text="输出位置", font=FONT_H, text_color=C_ACCENT,
                     anchor="w").pack(fill="x", padx=18, pady=(10, 2))
        dir_lb = ctk.CTkLabel(dlg, text=self._out_dir_text(), font=FONT_S,
                              text_color=C_TEXT if self.output_dir else C_MUTED,
                              justify="left", anchor="w", wraplength=450)
        dir_lb.pack(fill="x", padx=18)
        dirrow = ctk.CTkFrame(dlg, fg_color="transparent")
        dirrow.pack(fill="x", padx=18, pady=(4, 6))

        def choose_dir():
            p = filedialog.askdirectory(title="选择输出文件夹")
            if p:
                self.output_dir = p
                dir_lb.configure(text=p, text_color=C_TEXT)
                self._schedule_save()
                info.configure(text=self._export_summary())

        def reset_dir():
            self.output_dir = None
            dir_lb.configure(text="原文件夹内的「已加水印」", text_color=C_MUTED)
            self._schedule_save()
            info.configure(text=self._export_summary())

        ctk.CTkButton(dirrow, text="更改位置", width=100, height=28, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=choose_dir).pack(side="left")
        ctk.CTkButton(dirrow, text="恢复默认", width=100, height=28, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_ACCENT, corner_radius=8,
                      command=reset_dir).pack(side="left", padx=(8, 0))

        # 图片格式
        ctk.CTkLabel(dlg, text="图片格式", font=FONT_H, text_color=C_ACCENT,
                     anchor="w").pack(fill="x", padx=18, pady=(10, 2))
        seg = ctk.CTkSegmentedButton(
            dlg, values=["原格式", "JPEG", "PNG", "WebP"], font=FONT_S,
            command=self._set_fmt,
            selected_color=C_ACCENT, selected_hover_color=C_ACCENT_HOVER,
            unselected_color=C_PANEL2, unselected_hover_color=C_LINE,
            text_color=C_TEXT, height=30)
        seg.set({"keep": "原格式", "jpeg": "JPEG", "png": "PNG",
                 "webp": "WebP"}.get(self.export_format.get(), "原格式"))
        seg.pack(fill="x", padx=18, pady=(2, 6))

        # 质量
        SliderRow(dlg, "质量", self.export_quality, 50, 100, "%", 1,
                  self._schedule_save).pack(fill="x", padx=18, pady=3)
        ctk.CTkLabel(dlg, text="质量用于 JPEG / WebP；PNG 无损。", font=FONT_S,
                     text_color=C_MUTED, anchor="w").pack(fill="x", padx=18, pady=(0, 4))

        info = ctk.CTkLabel(dlg, text=self._export_summary(), font=FONT_S,
                            text_color=C_MUTED, anchor="w", justify="left", wraplength=450)
        info.pack(fill="x", padx=18, pady=(8, 4))
        for v in (self.export_format, self.export_quality):
            v.trace_add("write", lambda *_: info.configure(text=self._export_summary()))

        btns = ctk.CTkFrame(dlg, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(6, 16), side="bottom")
        ctk.CTkButton(btns, text="开始导出", height=34, font=FONT_S,
                      fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, corner_radius=8,
                      command=lambda: (dlg.destroy(), self._run_export())).pack(side="right")
        ctk.CTkButton(btns, text="取消", width=84, height=34, font=FONT_S,
                      fg_color=C_PANEL2, hover_color=C_LINE, corner_radius=8,
                      command=dlg.destroy).pack(side="right", padx=(0, 8))

    def _run_export(self):
        if not self.files:
            return
        if self.seal is None:
            messagebox.showerror("错误", "缺少标志图片：请用菜单 设置 → 更换标志图片… 选一张。")
            return
        out_dir = self._resolve_out_dir()
        if not out_dir:
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出文件夹：{e}")
            return

        self._save_now()          # 导出前落盘配置
        import time
        t0 = time.time()
        store.log(f"开始导出：{len(self.files)} 张 → {out_dir}，格式={self.export_format.get()}，质量={self.export_quality.get()}")
        done = failed = 0
        n = len(self.files)
        for i, p in enumerate(self.files):
            self.status.configure(text=f"导出中 {i + 1}/{n} …")
            self.root.update_idletasks()
            try:
                key = os.path.basename(p)
                enh = self.enh_store.get(key, self._enh_default())
                im = Image.open(p).convert("RGBA")
                out, _ = wc.render(im, self.seal, self.text, **self._kwargs_from_enh(enh))
                base, _ = os.path.splitext(key)
                self._save_one(out, out_dir, base, os.path.splitext(p)[1].lower())
                done += 1
            except Exception as e:
                failed += 1
                store.log(f"导出失败 {os.path.basename(p)}: {e}")
                print(f"[失败] {os.path.basename(p)}: {e}")

        dt = time.time() - t0
        msg = f"完成：{done} 张 → {out_dir}（{dt:.1f}s）"
        if failed:
            msg += f"（失败 {failed} 张）"
        store.log(f"导出结束：成功 {done}，失败 {failed}，用时 {dt:.1f}s")
        self.status.configure(text=msg)
        messagebox.showinfo("完成", msg)


def main():
    ctk.set_appearance_mode("dark")
    try:
        ctk.set_default_color_theme("green")
    except Exception:
        pass
    root = ctk.CTk()
    App(root)
    root.mainloop()


def _run():
    try:
        main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            store.log("程序异常：\n" + tb)
        except Exception:
            pass
        try:
            with open(os.path.join(BASE, "启动错误.log"), "w", encoding="utf-8") as f:
                f.write(tb)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    _run()
