#!/usr/bin/env python3
"""生成应用图标 app.ico（纯标准库，PNG 压缩 ICO）。"""
import struct, zlib, os

S = 256
px = [[(0, 0, 0, 0)] * S for _ in range(S)]


def put(x, y, c):
    if 0 <= x < S and 0 <= y < S:
        px[y][x] = c


def blend(x, y, c):
    r, g, b, a = c
    if 0 <= x < S and 0 <= y < S:
        pr, pg, pb, pa = px[y][x]
        na = a + pa * (255 - a) // 255
        if na:
            nr = (r * a + pr * pa * (255 - a) // 255) // na
            ng = (g * a + pg * pa * (255 - a) // 255) // na
            nb = (b * a + pb * pa * (255 - a) // 255) // na
        else:
            nr = ng = nb = 0
        px[y][x] = (nr, ng, nb, na)


def rounded_rect(x0, y0, x1, y1, rad, c):
    for y in range(y0, y1):
        for x in range(x0, x1):
            dx = max(x0 + rad - x, x - (x1 - 1 - rad), 0)
            dy = max(y0 + rad - y, y - (y1 - 1 - rad), 0)
            if dx * dx + dy * dy <= rad * rad:
                blend(x, y, c)


def circle_fill(cx, cy, r, c):
    for y in range(int(cy - r) - 1, int(cy + r) + 2):
        for x in range(int(cx - r) - 1, int(cx + r) + 2):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 <= r * r:
                blend(x, y, c)
            elif d2 <= (r + 1.2) ** 2:  # 抗锯齿边缘
                aa = max(0, int((1 - (d2 ** 0.5 - r)) * 255))
                if aa:
                    blend(x, y, (c[0], c[1], c[2], aa))


def triangle(p0, p1, p2, c):
    xs = [p[0] for p in (p0, p1, p2)]
    ys = [p[1] for p in (p0, p1, p2)]

    def sign(a, b, p):
        return (p[0] - b[0]) * (a[1] - b[1]) - (a[0] - b[0]) * (p[1] - b[1])

    for y in range(min(ys), max(ys) + 1):
        for x in range(min(xs), max(xs) + 1):
            p = (x + 0.5, y + 0.5)
            d1, d2, d3 = sign(p0, p1, p), sign(p1, p2, p), sign(p2, p0, p)
            neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
            pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
            if not (neg and pos):
                blend(x, y, c)


BLUE = (43, 122, 255, 255)
BLUE_D = (28, 90, 210, 255)
WHITE = (245, 248, 255, 255)

# 圆角方块背景（上浅下深渐变）
for y in range(S):
    t = y / S
    col = (int(48 + t * -14), int(120 + t * -18), int(255 + t * -35), 255)
    for x in range(S):
        dx = max(24 - x, x - 231, 0)
        dy = max(24 - y, y - 231, 0)
        if dx * dx + dy * dy <= 24 * 24:
            blend(x, y, col)

# 交换箭头（上箭头向右偏、下箭头向左偏，表示 IP 切换/交换）
# 上箭头（指上）
triangle((162, 52), (122, 52), (142, 88), WHITE)
for y in range(84, 118):
    for x in range(134, 151):
        blend(x, y, WHITE)
# 下箭头（指下）
triangle((94, 204), (134, 204), (114, 168), WHITE)
for y in range(138, 172):
    for x in range(106, 123):
        blend(x, y, WHITE)
# 连接横杠
for y in range(64, 80):
    for x in range(146, 190):
        blend(x, y, (245, 248, 255, 230))
for y in range(176, 192):
    for x in range(66, 110):
        blend(x, y, (245, 248, 255, 230))

# 中央小圆点（网络节点意象）
circle_fill(128, 128, 10, BLUE_D)

# 转 PNG
rows = []
for y in range(S):
    row = bytearray([0])
    for x in range(S):
        row += bytes(px[y][x])
    rows.append(bytes(row))


def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


png = (b"\x89PNG\r\n\x1a\n"
       + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 6, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
       + chunk(b"IEND", b""))

# 包成 ICO（单条 256px PNG 条目）
ico = struct.pack("<HHH", 0, 1, 1)
ico += struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 6 + 16)
ico += png

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
with open(out, "wb") as f:
    f.write(ico)
print("saved", out, len(ico))
