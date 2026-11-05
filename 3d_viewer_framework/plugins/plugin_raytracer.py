# -*- coding: utf-8 -*-
"""
=====================================================================
 实验四 · 编程任务1 —— 光线追踪插件（CPU Ray Tracer）
 《高级计算机图形学》电子科技大学计算机学院
=====================================================================
两种渲染模式：
  A) 参考场景（多物体多材质）：程序化房间场景（地面/三面墙/天花板
     面光源/镜面球/玻璃球/环境球/木箱），对应编程任务1"自行设置场景，
     多个不同形状的物体，设置不同材质特性"。
  B) 当前加载模型（进阶要求"为加载模型增加光线追踪"）：把左侧加载的
     OBJ 模型三角化并建立 BVH 加速结构，用 Möller–Trumbore 逐三角形
     求交，做真正的光线追踪渲染：
        - 漫反射(Lambert) + Blinn-Phong 高光 + 软阴影（对点光源多点抖动）；
        - 可选 镜面反射 / 玻璃折射（斯涅尔+Schlick 菲涅尔+全内反射）；
        - 光源位置/颜色/强度可调；可选地面与天空背景；
        - 直接使用模型当前的顶点法线 —— 若先用凹凸映射插件对模型做过
          法线扰动，光线追踪结果中即可看到凹凸细节（进阶：加载模型
          + 光线追踪 + 凹凸映射一体化）。
=====================================================================
"""
import math
import os
import random
import time
import vtk
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QSlider, QSpinBox, QComboBox,
                             QCheckBox, QGroupBox, QFrame, QDoubleSpinBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QColor
from plugins.base_plugin import Base3DPlugin

_PI = math.pi
_EPS = 1e-8


def _norm(v):
    l = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    return (v[0] / l, v[1] / l, v[2] / l) if l > _EPS else (0.0, 0.0, 1.0)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _sky(dir_):
    """程序化天空：顶部淡天蓝 → 地平线暖米白 → 下方渐暗（展示场景背景）"""
    d = _norm(dir_)
    t = max(d[1], 0.0)
    horizon = (0.86, 0.80, 0.72)   # 暖米色地平线
    zenith = (0.60, 0.76, 0.94)    # 淡天蓝
    ground = (0.20, 0.18, 0.16)
    if d[1] >= 0.0:
        k = math.pow(t, 0.45)
        return tuple(horizon[i] + (zenith[i] - horizon[i]) * k for i in range(3))
    k = min(-d[1], 1.0)
    return tuple(horizon[i] + (ground[i] - horizon[i]) * (0.5 * k) for i in range(3))


def _clamp01(v):
    return max(0.0, min(1.0, v))


# ==================================================================
# A) 参考场景（房间多物体）
# ==================================================================
class Sphere:
    def __init__(self, cx, cy, cz, r, mat, color):
        self.c = (cx, cy, cz); self.r = r
        self.mat = mat; self.color = color

    def hit(self, o, d, tmin, tmax):
        oc = _sub(o, self.c)
        b = _dot(oc, d)
        c = _dot(oc, oc) - self.r * self.r
        disc = b * b - c
        if disc < 0:
            return None
        sq = math.sqrt(disc)
        t = -b - sq
        if tmin < t < tmax:
            return t
        t = -b + sq
        return t if tmin < t < tmax else None

    def normal(self, p):
        return _norm(_sub(p, self.c))


class Plane:
    def __init__(self, n, d, mat, color):
        self.n = _norm(n); self.d = d
        self.mat = mat; self.color = color

    def hit(self, o, d, tmin, tmax):
        den = _dot(self.n, d)
        if abs(den) < _EPS:
            return None
        t = (self.d - _dot(self.n, o)) / den
        return t if tmin < t < tmax else None

    def normal(self, p):
        return self.n


class Box:
    def __init__(self, lo, hi, mat, color):
        self.lo = lo; self.hi = hi
        self.mat = mat; self.color = color

    def hit(self, o, d, tmin, tmax):
        t0, t1 = tmin, tmax
        for i in range(3):
            if abs(d[i]) < _EPS:
                if o[i] < self.lo[i] or o[i] > self.hi[i]:
                    return None
            else:
                inv = 1.0 / d[i]
                ta = (self.lo[i] - o[i]) * inv
                tb = (self.hi[i] - o[i]) * inv
                if ta > tb:
                    ta, tb = tb, ta
                t0 = max(t0, ta); t1 = min(t1, tb)
                if t0 > t1:
                    return None
        return t0 if tmin < t0 < tmax else None

    def normal(self, p):
        eps = 1e-4
        if abs(p[0] - self.lo[0]) < eps: return (-1, 0, 0)
        if abs(p[0] - self.hi[0]) < eps: return (1, 0, 0)
        if abs(p[1] - self.lo[1]) < eps: return (0, -1, 0)
        if abs(p[1] - self.hi[1]) < eps: return (0, 1, 0)
        if abs(p[2] - self.lo[2]) < eps: return (0, 0, -1)
        return (0, 0, 1)


class LightQuad:
    def __init__(self, cx, cz, hw, hd, y, color, intensity):
        self.cx = cx; self.cz = cz; self.hw = hw; self.hd = hd
        self.y = y; self.color = color; self.intensity = intensity

    def sample(self, rnd):
        return (self.cx + (rnd.random() * 2 - 1) * self.hw,
                self.y,
                self.cz + (rnd.random() * 2 - 1) * self.hd)

    def emi_color(self):
        return tuple(v * self.intensity for v in self.color)


class Scene:
    """参考场景：程序化房间 + 三球 + 木箱"""
    def __init__(self):
        self.objects = []
        self.light = LightQuad(0.0, 0.0, 2.6, 1.6, 4.0, (1.0, 0.95, 0.85), 2.6)
        self.exposure = 0.9
        self._build()

    def _build(self):
        self.objects.append(Plane((0, -1, 0), 0.0, "diffuse", (0.55, 0.38, 0.22)))
        self.objects.append(Plane((0, 1, 0), 4.0, "diffuse", (0.55, 0.55, 0.58)))
        self.objects.append(Plane((1, 0, 0), 3.0, "diffuse", (0.70, 0.16, 0.14)))
        self.objects.append(Plane((-1, 0, 0), 3.0, "diffuse", (0.16, 0.58, 0.18)))
        self.objects.append(Plane((0, 0, -1), 3.0, "diffuse", (0.90, 0.90, 0.88)))
        self.sphere_left = Sphere(-1.7, 0.45, 0.0, 1.0, "mirror", (0.6, 0.7, 0.8))
        self.sphere_mid = Sphere(0.0, 0.55, 0.0, 1.0, "glass", (0.75, 0.85, 0.95))
        self.sphere_right = Sphere(1.7, 0.6, 0.0, 1.0, "envsphere", (1, 1, 1))
        self.box = Box((-0.9, 0.0, 1.3), (-0.3, 0.8, 1.9), "diffuse", (0.62, 0.44, 0.22))
        self.objects += [self.sphere_left, self.sphere_mid, self.sphere_right, self.box]

    def set_mat(self, which, mat):
        m = {"sphere_left": self.sphere_left, "sphere_mid": self.sphere_mid,
             "sphere_right": self.sphere_right}[which]
        m.mat = mat

    def trace(self, o, d, tmin, tmax):
        best = None; bt = tmax
        for obj in self.objects:
            t = obj.hit(o, d, tmin, tmax)
            if t is not None and t < bt:
                bt = t; best = obj
        return best, bt

    def shade(self, o, d, hit, t, depth, rnd):
        p = tuple(o[i] + d[i] * t for i in range(3))
        n = hit.normal(p)
        if _dot(d, n) > 0:
            n = (-n[0], -n[1], -n[2])
        mat = hit.mat
        if mat == "envsphere":
            return _sky(n)
        if depth <= 0:
            return (0, 0, 0)
        if mat == "mirror":
            r = _reflect(d, n)
            return self._recurse(p, r, depth - 1, rnd)
        if mat == "glass":
            return self._glass(p, d, n, depth, rnd)
        return self._diffuse(p, n, d, hit.color, depth, rnd)

    def _recurse(self, p, r, depth, rnd):
        hit2, t2 = self.trace(p, r, _EPS, 1e9)
        return _sky(r) if hit2 is None else self.shade(p, r, hit2, t2, depth, rnd)

    def _diffuse(self, p, n, d, albedo, depth, rnd):
        color = [0.0, 0.0, 0.0]
        sky = _sky(n)
        for i in range(3):
            color[i] += 0.22 * albedo[i] * sky[i]
        for _ in range(self.light_samples):
            lp = self.light.sample(rnd)
            to_light = _sub(lp, p)
            dist = math.sqrt(_dot(to_light, to_light))
            L = (to_light[0] / dist, to_light[1] / dist, to_light[2] / dist)
            hit_s, ts = self.trace(p, L, 1e-3, dist - 1e-3)
            if hit_s is not None:
                continue
            ndl = max(_dot(n, L), 0.0)
            V = (-d[0], -d[1], -d[2])
            H = _norm((L[0] + V[0], L[1] + V[1], L[2] + V[2]))
            spec = math.pow(max(_dot(n, H), 0.0), 48.0)
            li = self.light.emi_color()
            for i in range(3):
                color[i] += li[i] * (albedo[i] * ndl * 0.85 + 0.55 * spec)
        return tuple(color)

    def _glass(self, p, d, n, depth, rnd):
        entering = _dot(d, n) < 0.0
        if entering:
            ni, nt, N = 1.0, 1.5, n
        else:
            ni, nt, N = 1.5, 1.0, (-n[0], -n[1], -n[2])
        cosi = -_dot(d, N)
        sin2t = (ni / nt) ** 2 * (1.0 - cosi * cosi)
        if sin2t >= 1.0:
            return self._recurse(p, _reflect(d, N), depth - 1, rnd)
        cos_t = math.sqrt(1.0 - sin2t)
        k = ni / nt
        tdir = _norm((d[0] * k + N[0] * (k * cosi - cos_t),
                      d[1] * k + N[1] * (k * cosi - cos_t),
                      d[2] * k + N[2] * (k * cosi - cos_t)))
        r0 = ((ni - nt) / (ni + nt)) ** 2
        fres = r0 + (1.0 - r0) * (1.0 - cosi) ** 5
        if rnd.random() < fres:
            return self._recurse(p, _reflect(d, N), depth - 1, rnd)
        return self._recurse(p, tdir, depth - 1, rnd)


def _reflect(d, n):
    nd = _dot(d, n)
    return (d[0] - 2 * nd * n[0], d[1] - 2 * nd * n[1], d[2] - 2 * nd * n[2])


# ==================================================================
# B) 加载模型：三角网格 + BVH 加速结构（Möller–Trumbore 求交）
# ==================================================================
class _BVHNode:
    __slots__ = ("lo", "hi", "left", "right", "tris")
    def __init__(self):
        self.lo = (1e30, 1e30, 1e30)
        self.hi = (-1e30, -1e30, -1e30)
        self.left = None
        self.right = None
        self.tris = None


class Mesh:
    """从 VTK polydata 构建的三角网格，自带 BVH。normal = 当前顶点法线
    （若凹凸映射插件已扰动法线，光线追踪会直接体现凹凸效果）。"""
    def __init__(self, polydata):
        self._build(polydata)

    def _build(self, pd):
        # 三角化（框架 OBJ 可能是多边形）
        tri = vtk.vtkTriangleFilter()
        tri.SetInputData(pd)
        tri.Update()
        out = tri.GetOutput()
        # 缺法线时计算平滑顶点法线
        if out.GetPointData().GetNormals() is None:
            nf = vtk.vtkPolyDataNormals()
            nf.SetInputData(out)
            nf.ComputePointNormalsOn()
            nf.ComputeCellNormalsOff()
            nf.SplittingOff()
            nf.AutoOrientNormalsOn()
            nf.Update()
            out = nf.GetOutput()
        pts = out.GetPoints()
        norms = out.GetPointData().GetNormals()
        self.pts = [tuple(pts.GetPoint(i)) for i in range(pts.GetNumberOfPoints())]
        self.norms = ([tuple(norms.GetTuple3(i)) for i in range(norms.GetNumberOfTuples())]
                      if norms is not None else None)
        # 提取三角形
        arr = out.GetPolys().GetData()
        k, N = 0, arr.GetNumberOfValues()
        tris = []
        while k < N:
            n = int(arr.GetValue(k)); k += 1
            ids = [int(arr.GetValue(k + j)) for j in range(n)]; k += n
            for j in range(1, n - 1):
                tris.append((ids[0], ids[j], ids[j + 1]))
        self.tris = tris
        self.n_tris = len(tris)
        self.root = self._build_bvh(tris)

    # ---------- BVH ----------
    def _tri_bbox(self, tri):
        i0, i1, i2 = tri
        p0, p1, p2 = self.pts[i0], self.pts[i1], self.pts[i2]
        lo = (min(p0[0], p1[0], p2[0]), min(p0[1], p1[1], p2[1]), min(p0[2], p1[2], p2[2]))
        hi = (max(p0[0], p1[0], p2[0]), max(p0[1], p1[1], p2[1]), max(p0[2], p1[2], p2[2]))
        return lo, hi

    def _build_bvh(self, tris):
        if not tris:
            return None
        node = _BVHNode()
        for tri in tris:
            lo, hi = self._tri_bbox(tri)
            node.lo = tuple(min(node.lo[i], lo[i]) for i in range(3))
            node.hi = tuple(max(node.hi[i], hi[i]) for i in range(3))
        if len(tris) <= 6:
            node.tris = tris
            return node
        # 沿最长轴按三角形质心中位切分
        ext = (node.hi[0] - node.lo[0], node.hi[1] - node.lo[1], node.hi[2] - node.lo[2])
        axis = 0 if ext[0] >= ext[1] and ext[0] >= ext[2] else (1 if ext[1] >= ext[2] else 2)
        tris = sorted(tris, key=lambda t: (self.pts[t[0]][axis] + self.pts[t[1]][axis] + self.pts[t[2]][axis]) / 3.0)
        mid = len(tris) // 2
        node.left = self._build_bvh(tris[:mid])
        node.right = self._build_bvh(tris[mid:])
        return node

    def _bbox_hit(self, node, o, d, tmin, tmax):
        t0, t1 = tmin, tmax
        for i in range(3):
            if abs(d[i]) < _EPS:
                if o[i] < node.lo[i] or o[i] > node.hi[i]:
                    return False
            else:
                inv = 1.0 / d[i]
                ta = (node.lo[i] - o[i]) * inv
                tb = (node.hi[i] - o[i]) * inv
                if ta > tb:
                    ta, tb = tb, ta
                t0 = max(t0, ta); t1 = min(t1, tb)
                if t0 > t1:
                    return False
        return True

    def hit(self, o, d, tmin, tmax):
        """返回 (t, u, v, tri) 或 None；u,v 为重心坐标，用于插值法线"""
        stack = [self.root]
        best = None
        bt = tmax
        while stack:
            node = stack.pop()
            if node is None or not self._bbox_hit(node, o, d, tmin, bt):
                continue
            if node.tris is not None:
                for tri in node.tris:
                    res = self._tri_hit(tri, o, d, tmin, bt)
                    if res is not None:
                        best = res; bt = res[0]
            else:
                stack.append(node.right)
                stack.append(node.left)
        return best

    def _tri_hit(self, tri, o, d, tmin, tmax):
        i0, i1, i2 = tri
        v0, v1, v2 = self.pts[i0], self.pts[i1], self.pts[i2]
        e1 = _sub(v1, v0)
        e2 = _sub(v2, v0)
        pvec = _cross(d, e2)
        det = _dot(e1, pvec)
        if abs(det) < _EPS:
            return None
        inv = 1.0 / det
        tvec = _sub(o, v0)
        u = _dot(tvec, pvec) * inv
        if u < 0.0 or u > 1.0:
            return None
        qvec = _cross(tvec, e1)
        v = _dot(d, qvec) * inv
        if v < 0.0 or u + v > 1.0:
            return None
        t = _dot(e2, qvec) * inv
        if t < tmin or t > tmax:
            return None
        return (t, u, v, tri)

    def normal_at(self, u, v, tri):
        """重心坐标插值顶点法线（可直接反映凹凸扰动后的法线）"""
        i0, i1, i2 = tri
        if self.norms is None:
            # 无顶点法线时退回几何法线
            v0, v1, v2 = self.pts[i0], self.pts[i1], self.pts[i2]
            return _norm(_cross(_sub(v1, v0), _sub(v2, v0)))
        n0, n1, n2 = self.norms[i0], self.norms[i1], self.norms[i2]
        w0, w1, w2 = 1.0 - u - v, u, v
        return _norm((n0[0] * w0 + n1[0] * w1 + n2[0] * w2,
                      n0[1] * w0 + n1[1] * w1 + n2[1] * w2,
                      n0[2] * w0 + n1[2] * w1 + n2[2] * w2))


def render_model_image(polydata, width, height, spp, depth, ls, exposure,
                       mat, light_pos, light_color, light_int, show_ground,
                       light_auto=False):
    """对加载模型做光线追踪渲染（展示场景）。
    展示场景：天空渐变背景 + 带网格的展示台（尺度参照）
    + 半球环境光(天空/地面反弹) + 主光软阴影 + 反向补光（阴影不黑）。
    返回 (QImage, 统计文本)"""
    t0 = time.time()
    mesh = Mesh(polydata)
    build_t = time.time() - t0

    b = polydata.GetBounds()
    center = ((b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2)
    radius = max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-3) / 2.0
    ground_y = b[2] - radius * 0.4          # 展示台
    grid_sp = max(radius / 4.0, 1e-3)       # 网格间距（尺度参照）

    lcol = tuple(v / 255.0 for v in light_color)
    if light_auto:
        # 自动布光：随模型缩放的右上斜上方主光
        lpos = (center[0] - radius * 0.9, center[1] + radius * 2.2, center[2] + radius * 1.4)
    else:
        lpos = tuple(light_pos)
    fill_col = (0.55, 0.62, 0.72)           # 反向补光（冷调）

    rnd = random.Random(2026)
    aspect = width / height
    tan_half = math.tan(math.radians(40.0) / 2.0)

    # 相机：斜上 3/4 视角，模型居中偏上（观察展示台与投影）
    eye = (center[0] + radius * 1.35, center[1] + radius * 1.25, center[2] + radius * 2.05)
    target = (center[0], center[1] + radius * 0.15, center[2])
    fwd = _norm(_sub(target, eye))
    right = _norm(_cross(fwd, (0, 1, 0)))
    up = _cross(right, fwd)

    def tonemap(c):
        # Reinhard 色调映射 + gamma
        c = tuple(max(0.0, v) for v in c)
        c = tuple(v / (1.0 + v) * exposure * 1.5 for v in c)
        return (int(round(_clamp01(c[0]) ** (1 / 2.2) * 255)),
                int(round(_clamp01(c[1]) ** (1 / 2.2) * 255)),
                int(round(_clamp01(c[2]) ** (1 / 2.2) * 255)))

    img = QImage(width, height, QImage.Format_RGB888)
    spp_total = spp * spp

    def trace_world(o, d, tmin, tmax):
        best = mesh.hit(o, d, tmin, tmax)
        gt = None
        if show_ground and abs(d[1]) > _EPS:
            gt = (ground_y - o[1]) / d[1]
            if not (tmin < gt < tmax):
                gt = None
        if gt is not None and (best is None or gt < best[0]):
            return ("ground", gt)
        return best

    def ground_albedo(p):
        # 展示台：暖灰 + 细网格线（尺度参照）
        u = p[0] / grid_sp
        v = p[2] / grid_sp
        fu = u - math.floor(u)
        fv = v - math.floor(v)
        on_line = (min(fu, 1.0 - fu) < 0.06) or (min(fv, 1.0 - fv) < 0.06)
        return (0.40, 0.38, 0.35) if on_line else (0.60, 0.58, 0.54)

    def shade(o, d, hit, depth):
        if hit is None:
            return _sky(d)
        is_ground = isinstance(hit, tuple) and len(hit) == 2 and hit[0] == "ground"
        if is_ground:
            n = (0, 1, 0)
            p = (o[0] + d[0] * hit[1], o[1] + d[1] * hit[1], o[2] + d[2] * hit[1])
            albedo = ground_albedo(p)
            rough = 28.0
        else:
            t, u, v, tri = hit
            p = tuple(o[i] + d[i] * t for i in range(3))
            n = mesh.normal_at(u, v, tri)
            albedo = (0.82, 0.82, 0.84)
            rough = 60.0
        if _dot(d, n) > 0:
            n = (-n[0], -n[1], -n[2])

        # 材质（仅对模型网格生效，地面始终漫反射）
        if not is_ground and mat == "mirror" and depth > 0:
            rd = _reflect(d, n)
            return shade(p, rd, trace_world(p, rd, _EPS, 1e9), depth - 1)
        if not is_ground and mat == "glass" and depth > 0:
            return _glass_model(p, d, n, depth, trace_world, shade)

        # 半球环境光（天空 + 地面反弹）→ 让阴影不黑、四面都有底光
        ndu = n[1]
        sky_c = _sky(n)
        gnd_c = (0.36, 0.33, 0.30)
        amb = tuple(gnd_c[i] * (0.42 * (1.0 - ndu)) + sky_c[i] * (0.58 * ndu)
                    for i in range(3))
        color = [albedo[i] * (0.22 + 1.30 * amb[i]) for i in range(3)]

        V = (-d[0], -d[1], -d[2])
        # 主光（点光源 + 软阴影，对点光源方向轻微抖动模拟面积光）
        for _ in range(max(ls, 1)):
            jitter = (rnd.random() - 0.5) * radius * 0.10
            lp = (lpos[0] + jitter * 2, lpos[1] + jitter, lpos[2] + jitter)
            to_light = _sub(lp, p)
            dist = math.sqrt(_dot(to_light, to_light))
            L = (to_light[0] / dist, to_light[1] / dist, to_light[2] / dist)
            if trace_world(p, L, 1e-3, dist - 1e-3) is None:
                ndl = max(_dot(n, L), 0.0)
                H = _norm((L[0] + V[0], L[1] + V[1], L[2] + V[2]))
                spec = math.pow(max(_dot(n, H), 0.0), rough)
                for i in range(3):
                    color[i] += lcol[i] * light_int * (albedo[i] * ndl * 0.95 + 0.40 * spec)
        # 反向补光（无阴影，柔和提亮暗部，避免死黑）
        to_f = (-(lpos[0] - p[0]), -(lpos[1] - p[1]), -(lpos[2] - p[2]))
        df = math.sqrt(_dot(to_f, to_f))
        if df > 1e-6:
            Lf = (to_f[0] / df, to_f[1] / df, to_f[2] / df)
            ndlf = max(_dot(n, Lf), 0.0)
            for i in range(3):
                color[i] += fill_col[i] * 0.38 * light_int * albedo[i] * ndlf
        return tuple(color)

    def _glass_model(p, d, n, depth, trace_world, shade):
        entering = _dot(d, n) < 0.0
        if entering:
            ni, nt, N = 1.0, 1.5, n
        else:
            ni, nt, N = 1.5, 1.0, (-n[0], -n[1], -n[2])
        cosi = -_dot(d, N)
        sin2t = (ni / nt) ** 2 * (1.0 - cosi * cosi)
        if sin2t >= 1.0:
            rd = _reflect(d, N)
            return shade(p, rd, trace_world(p, rd, _EPS, 1e9), depth - 1)
        cos_t = math.sqrt(1.0 - sin2t)
        k = ni / nt
        td = _norm((d[0] * k + N[0] * (k * cosi - cos_t),
                    d[1] * k + N[1] * (k * cosi - cos_t),
                    d[2] * k + N[2] * (k * cosi - cos_t)))
        r0 = ((ni - nt) / (ni + nt)) ** 2
        fres = r0 + (1.0 - r0) * (1.0 - cosi) ** 5
        if rnd.random() < fres:
            rd = _reflect(d, N)
            return shade(p, rd, trace_world(p, rd, _EPS, 1e9), depth - 1)
        return shade(p, td, trace_world(p, td, _EPS, 1e9), depth - 1)

    for y in range(height):
        for x in range(width):
            acc = [0.0, 0.0, 0.0]
            for sy in range(spp):
                for sx in range(spp):
                    px = (x + (sx + rnd.random()) / spp) / width * 2.0 - 1.0
                    py = (y + (sy + rnd.random()) / spp) / height * 2.0 - 1.0
                    dirx = right[0] * px * tan_half * aspect + up[0] * py * tan_half + fwd[0]
                    diry = right[1] * px * tan_half * aspect + up[1] * py * tan_half + fwd[1]
                    dirz = right[2] * px * tan_half * aspect + up[2] * py * tan_half + fwd[2]
                    d = _norm((dirx, diry, dirz))
                    hit = trace_world(eye, d, 1e-3, 1e9)
                    c = shade(eye, d, hit, depth)
                    for i in range(3):
                        acc[i] += c[i]
            img.setPixelColor(x, y, QColor(*tonemap(tuple(v / spp_total for v in acc))))

    total_t = time.time() - t0
    info = ("模型光线追踪：%d 三角形（BVH %.1fs，渲染 %.1fs）"
            % (mesh.n_tris, build_t, total_t - build_t))
    return img, info


# ==================================================================
# 通用渲染线程
# ==================================================================
class RenderThread(QThread):
    done = pyqtSignal(object)

    def __init__(self, job):
        super().__init__()
        self.job = job

    def run(self):
        try:
            self.done.emit(self.job())
        except Exception as e:  # noqa
            print("raytracer error:", e)
            self.done.emit(None)


# ==================================================================
# 插件
# ==================================================================
class RaytracerPlugin(Base3DPlugin):
    plugin_cls_name = "raytracer"
    plugin_name = "raytracer"
    plugin_desc = "实验四任务1：光线追踪（参考场景 / 进阶：加载模型）"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        self.scene = Scene()
        self.thread = None
        self.img_label = None
        self.btn_render = None
        self.lbl_status = None
        self.combo_res = None
        self.combo_mode = None
        self.sp_spp = None
        self.sp_depth = None
        self.sp_ls = None
        self.s_exp = None
        self.chk_mirror = None
        self.chk_glass = None
        self.chk_env = None
        # 模型模式控件
        self.model_group = None
        self.combo_mat = None
        self.sp_light_pos = []
        self.sp_light_rgb = []
        self.sp_light_int = None
        self.chk_ground = None
        self.chk_auto_light = None

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------
    def create_ui(self):
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(6)
        outer.setContentsMargins(6, 6, 6, 6)

        title = QLabel("任务1：CPU 光线追踪（纯 Python 渲染）")
        title.setStyleSheet("font-weight:bold; font-size:12px; color:#1a5fb4;")
        outer.addWidget(title)

        # 渲染对象模式
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("渲染对象："))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("参考场景（多物体多材质）", "scene")
        self.combo_mode.addItem("当前加载模型（展示场景：天空+展示台）", "model")
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        row_mode.addWidget(self.combo_mode, stretch=1)
        outer.addLayout(row_mode)

        # 图像显示区
        self.img_label = QLabel("点击「渲染」生成光线追踪图像…")
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumHeight(170)
        self.img_label.setStyleSheet("border:1px solid #aaa; background:#222; color:#ccc;")
        self.img_label.setWordWrap(True)
        outer.addWidget(self.img_label)

        # ---- 参考场景材质开关 ----
        self.scene_group = QGroupBox("参考场景材质")
        mlay = QVBoxLayout(self.scene_group)
        self.chk_mirror = QCheckBox("左球：镜面反射")
        self.chk_mirror.setChecked(True)
        self.chk_glass = QCheckBox("中球：玻璃折射")
        self.chk_glass.setChecked(True)
        self.chk_env = QCheckBox("右球：环境球")
        self.chk_env.setChecked(True)
        for c in (self.chk_mirror, self.chk_glass, self.chk_env):
            c.stateChanged.connect(self._apply_scene_mats)
            mlay.addWidget(c)
        outer.addWidget(self.scene_group)

        # ---- 模型模式（进阶） ----
        self.model_group = QGroupBox("加载模型·光线追踪参数")
        mgl = QVBoxLayout(self.model_group)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("模型材质："))
        self.combo_mat = QComboBox()
        self.combo_mat.addItem("漫反射（Lambert+高光）", "diffuse")
        self.combo_mat.addItem("镜面反射（金属感）", "mirror")
        self.combo_mat.addItem("玻璃折射", "glass")
        r1.addWidget(self.combo_mat, stretch=1)
        mgl.addLayout(r1)

        mgl.addWidget(QLabel("光源位置 X Y Z："))
        r2 = QHBoxLayout()
        self.sp_light_pos = []
        for v in (3.0, 6.0, 5.0):
            sp = self._dspin(-50, 50, 0.5, 1, v)
            sp.setMaximumWidth(70)
            self.sp_light_pos.append(sp)
            r2.addWidget(sp)
        mgl.addLayout(r2)

        self.chk_auto_light = QCheckBox("自动布光（主光随模型缩放，最省事）")
        self.chk_auto_light.setChecked(True)
        self.chk_auto_light.toggled.connect(self._on_auto_light)
        mgl.addWidget(self.chk_auto_light)

        mgl.addWidget(QLabel("光源颜色 R G B (0~255)："))
        r3 = QHBoxLayout()
        self.sp_light_rgb = []
        for v in (255, 245, 220):
            sp = self._dspin(0, 255, 1, 0, v)
            sp.setMaximumWidth(70)
            self.sp_light_rgb.append(sp)
            r3.addWidget(sp)
        mgl.addLayout(r3)

        mgl.addWidget(QLabel("光源强度 (0~3)："))
        self.sp_light_int = self._dspin(0.0, 3.0, 0.1, 2, 1.2)
        mgl.addWidget(self.sp_light_int)

        self.chk_ground = QCheckBox("显示展示台（暖灰地面+网格尺度参照）")
        self.chk_ground.setChecked(True)
        mgl.addWidget(self.chk_ground)

        note_m = QLabel("展示场景：天空渐变背景 + 半球环境光 + 主光/补光，\n"
                        "模型投影在带网格的展示台上，便于观察轮廓与尺度。\n"
                        "先用任务2凹凸映射扰动法线，再渲染当前模型，\n"
                        "光线追踪结果中会直接体现凹凸细节（进阶一体化）。")
        note_m.setWordWrap(True)
        note_m.setStyleSheet("color:#2e7d32; font-size:11px;")
        mgl.addWidget(note_m)
        outer.addWidget(self.model_group)

        # ---- 算法参数 ----
        box = QGroupBox("算法参数（两模式共用）")
        lay = QVBoxLayout(box)
        lay.addWidget(QLabel("分辨率："))
        self.combo_res = QComboBox()
        self.combo_res.addItem("小  (320 × 240)", (320, 240))
        self.combo_res.addItem("中  (360 × 270)", (360, 270))
        self.combo_res.addItem("大  (480 × 360)", (480, 360))
        # 默认"小"：加载模型 CPU 求交量大，保证默认即可接受的速度
        self.combo_res.setCurrentIndex(0)
        lay.addWidget(self.combo_res)
        self.sp_spp = self._spin_row(lay, "超采样 spp（每边）", 1, 4, 2)
        self.sp_depth = self._spin_row(lay, "递归深度", 1, 10, 6)
        self.sp_ls = self._spin_row(lay, "软阴影采样数", 1, 24, 8)
        self.s_exp = self._spin_row(lay, "曝光（×0.1）", 1, 30, 9)
        outer.addWidget(box)

        # 渲染按钮
        self.btn_render = QPushButton("渲 染")
        self.btn_render.setStyleSheet("font-weight:bold; background:#2e7d32; color:#fff; padding:8px;")
        self.btn_render.clicked.connect(self.on_render)
        outer.addWidget(self.btn_render)

        self.lbl_status = QLabel("就绪。选择渲染对象并调整参数后点击渲染。")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#666; font-size:11px;")
        outer.addWidget(self.lbl_status)
        outer.addStretch(1)

        self._on_auto_light(True)   # 自动布光默认开启，禁用光源位置框
        self.on_mode_changed()
        return self.plugin_panel

    def _dspin(self, lo, hi, step, dec, val):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(dec)
        sp.setValue(val)
        return sp

    def _spin_row(self, lay, label, lo, hi, val):
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(val)
        sp.setMaximumWidth(64)
        row.addWidget(sp)
        row.addStretch(1)
        lay.addLayout(row)
        return sp

    def _on_auto_light(self, on):
        for s in self.sp_light_pos:
            s.setEnabled(not on)

    def on_mode_changed(self, *_):
        is_model = (self.combo_mode.currentData() == "model")
        self.scene_group.setVisible(not is_model)
        self.model_group.setVisible(is_model)
        # 各模式独立的默认渲染参数：模型模式 CPU 求交量大，默认偏低保证速度
        if is_model:
            if self.sp_spp.value() == 2:
                self.sp_spp.setValue(1)
            if self.sp_ls.value() == 8:
                self.sp_ls.setValue(6)
            self.lbl_status.setText("模型模式：请在左侧加载 OBJ，默认自动布光+展示台。\n"
                                    "先用凹凸映射扰动法线，可在结果中看到凹凸细节。")
        else:
            if self.sp_spp.value() == 1:
                self.sp_spp.setValue(2)
            if self.sp_ls.value() == 6:
                self.sp_ls.setValue(8)

    # ----------------------------------------------------------
    # 参考场景材质
    # ----------------------------------------------------------
    def _apply_scene_mats(self, *_):
        self.scene.sphere_left.mat = "mirror" if self.chk_mirror.isChecked() else "diffuse"
        self.scene.sphere_mid.mat = "glass" if self.chk_glass.isChecked() else "diffuse"
        self.scene.sphere_right.mat = "envsphere" if self.chk_env.isChecked() else "diffuse"

    # ----------------------------------------------------------
    # 渲染
    # ----------------------------------------------------------
    def on_render(self):
        if self.thread is not None and self.thread.isRunning():
            self.lbl_status.setText("正在渲染…请稍候")
            return
        w, h = self.combo_res.currentData()
        self._apply_scene_mats()
        self.btn_render.setEnabled(False)

        if self.combo_mode.currentData() == "model":
            pd = getattr(self.ctx, "current_polydata", None)
            if pd is None or pd.GetPoints() is None or pd.GetPoints().GetNumberOfPoints() == 0:
                self.btn_render.setEnabled(True)
                self.lbl_status.setText("请先在左侧文件树加载一个 OBJ 模型。")
                return
            cells = pd.GetNumberOfCells()
            if cells > 60000:
                self.lbl_status.setText(
                    "警告：模型三角形较多（%d 个），纯 CPU 求交耗时较长。\n"
                    "建议使用小分辨率、spp=1、阴影采样数调低；仍可渲染。"
                    % cells)
            pd_ref = pd
            job = lambda: render_model_image(
                pd_ref, w, h,
                self.sp_spp.value(), self.sp_depth.value(), self.sp_ls.value(),
                self.s_exp.value() / 10.0,
                self.combo_mat.currentData(),
                tuple(s.value() for s in self.sp_light_pos),
                tuple(int(s.value()) for s in self.sp_light_rgb),
                self.sp_light_int.value(),
                self.chk_ground.isChecked(),
                self.chk_auto_light.isChecked())
            self.lbl_status.setText("模型光线追踪中…（BVH构建+逐像素求交，稍候）")
        else:
            job = lambda: (render_scene_image(
                self.scene, w, h,
                self.sp_spp.value(), self.sp_depth.value(), self.sp_ls.value(),
                self.s_exp.value() / 10.0), None)
            self.lbl_status.setText("参考场景渲染中…")

        self.thread = RenderThread(job)
        self.thread.done.connect(self._on_done)
        self.thread.start()

    def _on_done(self, result):
        self.btn_render.setEnabled(True)
        if result is None:
            self.lbl_status.setText("渲染失败（详见控制台）")
            return
        img, info = result
        pix = QPixmap.fromImage(img)
        self.img_label.setPixmap(pix.scaled(self.img_label.width() or 320,
                                            self.img_label.height() or 240,
                                            Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.img_label.setAlignment(Qt.AlignCenter)
        extra = ("  " + info) if info else ""
        self.lbl_status.setText(
            "渲染完成 %d×%d  spp=%d 深度=%d  阴影采样=%d  曝光=%.2f%s"
            % (img.width(), img.height(), self.sp_spp.value(), self.sp_depth.value(),
               self.sp_ls.value(), self.s_exp.value() / 10.0, extra))

    def save_png(self, path):
        if self.img_label and self.img_label.pixmap():
            return self.img_label.pixmap().toImage().save(path)
        return False

    # ----------------------------------------------------------
    # 生命周期
    # ----------------------------------------------------------
    def on_model_loaded(self, obj_path, actor, polydata):
        if self.combo_mode is not None and self.combo_mode.currentData() == "model":
            self.lbl_status.setText("已加载模型 %s。可调整材质/光源后渲染。"
                                    % os.path.basename(obj_path))

    def on_window_resize(self):
        pass

    def on_destroy(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.requestInterruption()
            self.thread.quit()


# 保留原参考场景渲染入口
def render_scene_image(scene, width, height, spp, depth, ls, exposure):
    rnd = random.Random(2026)
    scene.light_samples = ls
    scene.exposure = exposure
    aspect = width / height
    tan_half = math.tan(math.radians(60.0) / 2.0)
    eye = (0.0, 1.2, 5.6)
    fwd = _norm((-eye[0], -eye[1], -eye[2]))
    right = (1.0, 0.0, 0.0)
    up = (0.0, 1.0, 0.0)
    img = QImage(width, height, QImage.Format_RGB888)
    spp_total = spp * spp
    for y in range(height):
        for x in range(width):
            acc = [0.0, 0.0, 0.0]
            for sy in range(spp):
                for sx in range(spp):
                    px = (x + (sx + rnd.random()) / spp) / width * 2.0 - 1.0
                    py = (y + (sy + rnd.random()) / spp) / height * 2.0 - 1.0
                    dirx = right[0] * px * tan_half * aspect + up[0] * py * tan_half + fwd[0]
                    diry = right[1] * px * tan_half * aspect + up[1] * py * tan_half + fwd[1]
                    dirz = right[2] * px * tan_half * aspect + up[2] * py * tan_half + fwd[2]
                    d = _norm((dirx, diry, dirz))
                    hit, t = scene.trace(eye, d, 1e-3, 1e9)
                    c = _sky(d) if hit is None else scene.shade(eye, d, hit, t, depth, rnd)
                    for i in range(3):
                        acc[i] += c[i]
            col = tuple(v / spp_total for v in acc)
            img.setPixelColor(x, y, QColor(*tonemap_rgb(col, exposure)))
    return img


def tonemap_rgb(c, exposure):
    c = tuple(_clamp01(max(0.0, v) / (1.0 + max(0.0, v)) * exposure * 1.6) for v in c)
    return (int(round(_clamp01(c[0]) ** (1 / 2.2) * 255)),
            int(round(_clamp01(c[1]) ** (1 / 2.2) * 255)),
            int(round(_clamp01(c[2]) ** (1 / 2.2) * 255)))
