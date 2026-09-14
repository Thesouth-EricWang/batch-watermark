# -*- coding: utf-8 -*-
"""批量加水印 · 核心图像处理（无 GUI 依赖，可独立测试）

三层能力：
  1) 深浅自适应：标志拆成「校徽」「文字」，深色底时校徽垫圆底、文字反白。
  2) 描边：给标志可见像素外扩对比边（白/黑/双色），应对黑白错杂、杂彩底。
  3) 毛玻璃底板：标志下垫一块「背景模糊 + 薄白」的圆角板，边缘可淡出。

单位约定：
  · size_pct / margin_pct 	按图片「较短边」的百分比。
  · outline_w / plate_pad / plate_blur / plate_fade 	按「标志高度」的比例（0.1 = 10%）。
  · plate_radius 	按「底板高度」的比例，0~0.5（0.5 即胶囊形）。
  · plate_alpha 	白层不透明度，0~100 的百分比。
"""
from PIL import Image, ImageDraw, ImageFilter, ImageChops


# ---------------- 标志拆分 ----------------

def split_logo(logo):
    """把标志按最宽的内部空白拆成 (校徽, 文字)。找不到分界时返回 (None, logo)。"""
    W, H = logo.size
    alpha = logo.split()[3]
    ap = alpha.load()
    col = []
    for x in range(W):
        c = 0
        for y in range(H):
            if ap[x, y] > 16:
                c += 1
        col.append(c)
    gaps = []
    run = None
    for x in range(W):
        if col[x] <= 1:
            if run is None:
                run = x
        else:
            if run is not None:
                gaps.append((run, x, x - run))
                run = None
    if run is not None:
        gaps.append((run, W, W - run))
    inner = [g for g in gaps if g[0] > 0 and g[1] < W and g[2] > W * 0.03]
    if not inner:
        return None, logo
    g = max(inner, key=lambda t: t[2])
    left = logo.crop((0, 0, g[0], H))
    right = logo.crop((g[1], 0, W, H))
    lb, rb = left.getbbox(), right.getbbox()
    if not lb or not rb:
        return None, logo
    return left.crop(lb), right.crop(rb)


# ---------------- 圆底（深色底用） ----------------

def _seal_with_disc(seal, pad_ratio, disc_color):
    """给校徽加圆形底衬。pad_ratio 可正可负：正=外扩白边，0=贴合，负=收在内。"""
    sw, sh = seal.size
    base = max(sw, sh)
    d = max(1, int(base + base * pad_ratio * 2))
    size = max(sw, sh, d)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r = d // 2
    c = size // 2
    ImageDraw.Draw(canvas).ellipse([c - r, c - r, c + r, c + r], fill=disc_color)
    canvas.alpha_composite(seal, ((size - sw) // 2, (size - sh) // 2))
    return canvas


# ---------------- 描边 ----------------

def _dilate(alpha, px):
    """把 alpha 形状向外膨胀 px 像素。"""
    img = alpha
    remaining = int(round(px))
    while remaining > 0:
        k = min(9, remaining * 2 + 1)
        if k % 2 == 0:
            k += 1
        img = img.filter(ImageFilter.MaxFilter(k))
        remaining -= (k - 1) // 2
    return img


def add_outline(mark, width_px, color):
    if width_px <= 0:
        return mark
    a = mark.split()[3]
    dil = _dilate(a, width_px)
    ring = ImageChops.subtract(dil, a)
    stroke = Image.new("RGBA", mark.size, tuple(color[:3]) + (0,))
    stroke.putalpha(ring)
    out = Image.new("RGBA", mark.size, (0, 0, 0, 0))
    out.alpha_composite(stroke)
    out.alpha_composite(mark)
    return out


OUTLINE_STYLES = {
    0: None,
    1: [(255, 255, 255)],
    2: [(17, 17, 17)],
    3: [(255, 255, 255), (17, 17, 17)],
}


def _apply_outline(mark, style, width_px):
    colors = OUTLINE_STYLES.get(style)
    if not colors or width_px <= 0:
        return mark
    out = mark
    for i, c in enumerate(colors):
        out = add_outline(out, width_px if i == 0 else max(1, int(width_px * 0.7)), c)
    return out


# ---------------- 组装标志 ----------------

_MARK_CACHE = {}


def _assemble(seal, text, dark_mode, disc_alpha, disc_pad, disc_color, gap_ratio,
              outline_style, outline_w_px):
    if dark_mode:
        s = _seal_with_disc(seal, disc_pad, tuple(disc_color[:3]) + (int(disc_alpha),))
        t = Image.new("RGBA", text.size, (255, 255, 255, 0))
        t.putalpha(text.split()[3])
    else:
        s, t = seal, text
    H = s.height
    gap = int(H * gap_ratio)
    out = Image.new("RGBA", (s.width + gap + t.width, H), (0, 0, 0, 0))
    out.alpha_composite(s, (0, 0))
    out.alpha_composite(t, (s.width + gap, (H - t.height) // 2))
    if outline_style and outline_w_px > 0:
        out = _apply_outline(out, outline_style, outline_w_px)
    return out


def mark_ratio(seal, text, dark_mode, disc_pad=0.02, gap_ratio=0.09):
    """不实际组装，只算组装后标志的 高/宽 比。"""
    sw, sh = seal.size
    tw, th = text.size
    if dark_mode:
        side = max(sw, sh) * (1 + 2 * disc_pad)
        H, W = side, side
    else:
        H, W = sh, sw
    total_w = W + H * gap_ratio + tw
    return (H / total_w) if total_w else 1.0


def build_mark(seal, text, dark_mode, disc_alpha=235, disc_pad=0.02,
               disc_color=(255, 255, 255), gap_ratio=0.09,
               outline_style=0, outline_w_px=0, target_w=None, target_h=None):
    """组装标志。若给了 target_w/target_h，先把部件缩到目标分辨率再组装
    （描边也就在目标像素尺度上做，既准又快）。"""
    key = (id(seal), id(text), bool(dark_mode), int(disc_alpha),
           round(float(disc_pad), 4), tuple(disc_color[:3]), round(float(gap_ratio), 4),
           int(outline_style), int(outline_w_px),
           int(target_w or 0), int(target_h or 0))
    hit = _MARK_CACHE.get(key)
    if hit is not None:
        return hit

    s_src, t_src = seal, text
    if target_h:
        if dark_mode:
            natural_h = max(seal.size) * (1 + 2 * disc_pad)
        else:
            natural_h = seal.size[1]
        sc = (target_h / natural_h) if natural_h else 1.0
        if abs(sc - 1.0) > 5e-3:
            sw, sh = seal.size
            tw, th = text.size
            s_src = seal.resize((max(1, round(sw * sc)), max(1, round(sh * sc))), Image.LANCZOS)
            t_src = text.resize((max(1, round(tw * sc)), max(1, round(th * sc))), Image.LANCZOS)

    content = _assemble(s_src, t_src, dark_mode, disc_alpha, disc_pad, disc_color,
                        gap_ratio, 0, 0)
    if outline_style and outline_w_px > 0:
        # 画布四周留出描边宽度，否则外圈描边会被画布边界裁掉
        pad = int(outline_w_px)
        canvas = Image.new("RGBA", (content.width + pad * 2, content.height + pad * 2),
                           (0, 0, 0, 0))
        canvas.alpha_composite(content, (pad, pad))
        out = _apply_outline(canvas, outline_style, outline_w_px)
    else:
        out = content
    if len(_MARK_CACHE) > 64:
        _MARK_CACHE.clear()
    _MARK_CACHE[key] = out
    return out


# ---------------- 明暗检测 ----------------

def region_luminance(im, corner, size_pct, margin_pct):
    W, H = im.size
    short = min(W, H)
    lw = max(1, int(short * size_pct / 100))
    m = max(0, int(short * margin_pct / 100))
    x0 = m if "l" in corner else max(0, W - lw - m)
    y0 = m if "t" in corner else max(0, H - lw - m)
    x1 = min(W, x0 + lw)
    y1 = min(H, y0 + max(1, int(lw * 0.42)))
    crop = im.crop((x0, y0, x1, y1)).convert("RGB")
    crop.thumbnail((48, 48))
    px = crop.load()
    tot = n = 0
    for yy in range(crop.height):
        for xx in range(crop.width):
            r, g, b = px[xx, yy]
            tot += 0.299 * r + 0.587 * g + 0.114 * b
            n += 1
    return tot / max(1, n)


def is_dark_region(im, corner, size_pct, margin_pct, threshold=148):
    return region_luminance(im, corner, size_pct, margin_pct) < threshold


# ---------------- 毛玻璃底板 ----------------

def _glass_plate(base, x0, y0, x1, y1, radius_px, fade_px, blur_px, alpha):
    """把 (x0,y0,x1,y1) 区域做成毛玻璃圆角底板，边缘 fade 淡出。就地修改 base。"""
    f = int(max(0, fade_px)) + 1
    rx0 = max(0, x0 - f)
    ry0 = max(0, y0 - f)
    rx1 = min(base.width, x1 + f)
    ry1 = min(base.height, y1 + f)
    if rx1 <= rx0 or ry1 <= ry0:
        return
    region = base.crop((rx0, ry0, rx1, ry1))
    blurred = region.filter(ImageFilter.GaussianBlur(max(0.1, blur_px)))
    white = Image.new("RGBA", region.size, (255, 255, 255, int(alpha)))
    glass = Image.alpha_composite(blurred, white)

    mask = Image.new("L", region.size, 0)
    mx0 = x0 - rx0
    my0 = y0 - ry0
    mx1 = mx0 + (x1 - x0) - 1
    my1 = my0 + (y1 - y0) - 1
    ImageDraw.Draw(mask).rounded_rectangle([mx0, my0, mx1, my1],
                                           radius=max(0, int(radius_px)), fill=255)
    if fade_px > 0.5:
        mask = mask.filter(ImageFilter.GaussianBlur(fade_px))
    base.paste(glass, (rx0, ry0), mask)


# ---------------- 渲染 ----------------

_PLACE_CACHE = {}


def _prepare_mark(mark, lw, lh, opacity_pct):
    ckey = (id(mark), mark.size, lw, lh)
    lg0 = _PLACE_CACHE.get(ckey)
    if lg0 is None:
        lg0 = mark.resize((lw, lh), Image.LANCZOS)
        if len(_PLACE_CACHE) > 24:
            _PLACE_CACHE.clear()
        _PLACE_CACHE[ckey] = lg0
    lg = lg0
    if opacity_pct < 100:
        lg = lg.copy()
        a = lg.split()[3].point(lambda v: int(v * opacity_pct / 100))
        lg.putalpha(a)
    return lg


def render(im, seal, text, size_pct=18, margin_pct=4, opacity_pct=100, corner="tl",
           mode="auto", disc_alpha=235, disc_pad=0.02, disc_color=(255, 255, 255),
           dark_threshold=148,
           outline_style=0, outline_w=0.08,
           plate=0, plate_alpha=20, plate_blur=0.02, plate_pad=0.17,
           plate_radius=0.30, plate_fade=0.04):
    """返回 (结果图, 使用的模式)。"""
    if seal is None or text is None:
        return im, "none"

    if mode == "auto":
        use_dark = is_dark_region(im, corner, size_pct, margin_pct, dark_threshold)
    elif mode == "dark":
        use_dark = True
    else:
        use_dark = False

    W, H = im.size
    short = min(W, H)
    lw = max(1, int(short * size_pct / 100))
    lh = max(1, int(lw * mark_ratio(seal, text, use_dark, disc_pad)))
    # 小尺寸时超采样组装（ImageDraw 本身不抗锯齿）；大尺寸像素已够密。
    ss = 2 if max(lw, lh) < 700 else 1
    work_w, work_h = lw * ss, lh * ss
    outline_w = min(max(float(outline_w or 0.0), 0.0), 0.5)   # 钳制，避免荒谬取值拖死
    ow_final = max(0, int(round(lh * outline_w))) if outline_style else 0
    mark = build_mark(seal, text, use_dark, disc_alpha, disc_pad, disc_color,
                      outline_style=outline_style, outline_w_px=ow_final * ss,
                      target_w=work_w, target_h=work_h)

    m = int(short * margin_pct / 100)
    if corner == "tr":
        x, y = W - lw - m, m
    elif corner == "bl":
        x, y = m, H - lh - m
    elif corner == "br":
        x, y = W - lw - m, H - lh - m
    else:
        x, y = m, m

    out = im.copy()

    if plate == 1:
        pad = int(lh * plate_pad)
        board_h = lh + pad * 2
        rad = int(board_h * min(max(plate_radius, 0.0), 0.5))
        fade = lh * plate_fade
        blur = max(0.1, lh * plate_blur)
        _glass_plate(out, x - pad - ow_final, y - pad - ow_final,
                     x + lw + pad + ow_final, y + lh + pad + ow_final,
                     rad, fade, blur, int(plate_alpha * 255 / 100))

    # 描边使标志外扩 ow_final，合成时相应偏移，保持内容位置不变
    lg = _prepare_mark(mark, lw + ow_final * 2, lh + ow_final * 2, opacity_pct)
    out.alpha_composite(lg, (x - ow_final, y - ow_final))
    return out, ("dark" if use_dark else "light")
