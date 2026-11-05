# -*- coding: utf-8 -*-
"""
=====================================================================
 实验四 · 编程任务2 —— 凹凸映射插件（Bump / Normal Mapping）
 《高级计算机图形学》电子科技大学计算机学院
=====================================================================
功能说明（对应 任务2 bump_mapping）：
  使用混凝土铺路砖贴图对当前加载模型做凹凸映射：
    - 漫反射(Albedo)：interlocking_concrete_pavers_diff（bump_diffuse.jpg）
    - 法线贴图：interlocking_concrete_pavers_nor_gl（bump_normal.png）
  核心算法（在插件内用 CPU 按顶点实现，等价于着色器里的 TBN 扰动）：
    1) 对每个顶点用几何法线 N 建立正交切向基 T,B（右手系，B=cross(N,T)）；
    2) 按顶点 UV 采样法线贴图 nm∈[-1,1]；
    3) 扰动法线 surfN = normalize(T*nm.x + B*nm.y + N*nm.z)；
    4) 把扰动后的法线写回模型点数据，VTK 用其做光照着色，
       在表面呈现铺路砖的沟槽浮雕明暗层次。
  支持：凹凸强度滑块、凹凸开关（对比效果）、一键生成带 UV 的演示球体，
  保证在没有合适模型时也能直观看到凹凸映射效果。
=====================================================================
"""
import ctypes
import os
import vtk
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QSlider, QCheckBox, QGroupBox, QFrame)
from PyQt5.QtCore import Qt
from plugins.base_plugin import Base3DPlugin


def _norm(v):
    l = (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) ** 0.5
    return (v[0] / l, v[1] / l, v[2] / l) if l > 1e-12 else (0.0, 0.0, 1.0)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _perturb_normal(n, nm, strength):
    """TBN 扰动：N 几何法线 + nm 切线空间法线 -> 世界法线"""
    N = _norm(n)
    # 选一条与 N 不近平行的参考轴，构造正交基
    if abs(N[1]) < 0.999:
        ref = (0.0, 1.0, 0.0)
    else:
        ref = (1.0, 0.0, 0.0)
    T = _norm(_cross(ref, N))
    B = _cross(N, T)
    sx = nm[0] * strength
    sy = nm[1] * strength
    sz = nm[2]
    return _norm((T[0] * sx + B[0] * sy + N[0] * sz,
                  T[1] * sx + B[1] * sy + N[1] * sz,
                  T[2] * sx + B[2] * sy + N[2] * sz))


def _tex_dir(ctx):
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "texture")


class BumpPlugin(Base3DPlugin):
    plugin_cls_name = "bump_mapping"
    plugin_name = "bump_mapping"
    plugin_desc = "实验四任务2：凹凸映射（混凝土铺路砖法线贴图）"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        self.diff_tex = None
        self.normal_img = None          # vtkImageData（法线贴图）
        self.orig_normals = None        # vtkFloatArray（应用凹凸前备份）
        self.cur_actor = None
        self.cur_pd = None
        self.diffuse_tex_tex = None     # vtkTexture
        self.applied = False
        # 控件
        self.chk_on = None
        self.sl_strength = None
        self.btn_apply = None
        self.btn_off = None
        self.btn_demo = None
        self.lbl_status = None
        self.demo_actor = None

    # ----------------------------------------------------------
    # 贴图加载
    # ----------------------------------------------------------
    def _load_textures(self):
        d = _tex_dir(self.ctx)
        # 漫反射纹理
        if self.diff_tex is None:
            r = vtk.vtkJPEGReader()
            r.SetFileName(os.path.join(d, "bump_diffuse.jpg"))
            r.Update()
            self.diff_tex = vtk.vtkTexture()
            self.diff_tex.SetInputConnection(r.GetOutputPort())
            self.diff_tex.InterpolateOn()
            self.diff_tex.RepeatOn()
        # 法线贴图图像
        if self.normal_img is None:
            r = vtk.vtkPNGReader()
            r.SetFileName(os.path.join(d, "bump_normal.png"))
            r.Update()
            self.normal_img = r.GetOutput()
            # 转为内存缓冲直读，避免大数据集模型逐顶点调用 VTK 接口过慢
            sc = self.normal_img.GetPointData().GetScalars()
            self.nm_ncomp = sc.GetNumberOfComponents()
            self.nm_w = self.normal_img.GetDimensions()[0]
            self.nm_h = self.normal_img.GetDimensions()[1]
            ptr = str(sc.GetVoidPointer(0))
            import re
            m = re.search(r"_([0-9a-fA-F]+)_", ptr)
            addr = int(m.group(1), 16) if m else int(ptr, 16)
            self.nm_buf = (ctypes.c_ubyte *
                           (self.nm_w * self.nm_h * self.nm_ncomp)).from_address(addr)

    def _sample_normal(self, u, v):
        """按 UV 采样法线贴图 -> (nx,ny,nz)∈[-1,1]（bump_normal 的 RGB）"""
        W, H = self.nm_w, self.nm_h
        x = int(max(0, min(W - 1, int(u * (W - 1)))))
        y = int(max(0, min(H - 1, int((1.0 - v) * (H - 1)))))
        k = (y * W + x) * self.nm_ncomp
        return (self.nm_buf[k] / 127.5 - 1.0,
                self.nm_buf[k + 1] / 127.5 - 1.0,
                self.nm_buf[k + 2] / 127.5 - 1.0)

    # ----------------------------------------------------------
    # 数据准备：确保模型有法线与 UV（框架 OBJ 普遍缺少两者）
    # ----------------------------------------------------------
    def _ensure_normals(self, pd):
        """缺法线时用 vtkPolyDataNormals 计算平滑顶点法线"""
        if pd.GetPointData().GetNormals() is not None:
            return False
        nf = vtk.vtkPolyDataNormals()
        nf.SetInputData(pd)
        nf.ComputePointNormalsOn()
        nf.ComputeCellNormalsOff()
        nf.SplittingOff()
        nf.AutoOrientNormalsOn()
        nf.Update()
        pd.ShallowCopy(nf.GetOutput())
        return True

    def _ensure_uvs(self, pd):
        """缺 UV 时按法线主轴向做盒式投影生成纹理坐标（任意外形通用）"""
        if pd.GetPointData().GetTCoords() is not None:
            return False
        norms = pd.GetPointData().GetNormals()
        if norms is None:
            return False
        b = pd.GetBounds()
        sx = (b[1] - b[0]) or 1e-6
        sy = (b[3] - b[2]) or 1e-6
        sz = (b[5] - b[4]) or 1e-6
        n = pd.GetPoints().GetNumberOfPoints()
        tco = vtk.vtkFloatArray()
        tco.SetNumberOfComponents(2)
        tco.SetNumberOfTuples(n)
        for i in range(n):
            nrm = norms.GetTuple3(i)
            ax = 0
            if abs(nrm[1]) > abs(nrm[0]):
                ax = 1
            if abs(nrm[2]) > abs(nrm[0]) and abs(nrm[2]) > abs(nrm[1]):
                ax = 2
            p = pd.GetPoints().GetPoint(i)
            if ax == 0:      # 法线沿 X：投影到 YZ
                u = (p[2] - b[4]) / sz
                v = (p[1] - b[2]) / sy
            elif ax == 1:    # 法线沿 Y：投影到 XZ
                u = (p[0] - b[0]) / sx
                v = (p[2] - b[4]) / sz
            else:            # 法线沿 Z：投影到 XY
                u = (p[0] - b[0]) / sx
                v = (p[1] - b[2]) / sy
            tco.SetTuple2(i, u, v)
        pd.GetPointData().SetTCoords(tco)
        return True

    # ----------------------------------------------------------
    # 核心：对 polydata 应用凹凸映射
    # ----------------------------------------------------------
    def _apply_bump_to(self, pd, strength):
        tco = pd.GetPointData().GetTCoords()
        norms = pd.GetPointData().GetNormals()
        pts = pd.GetPoints()
        n = pts.GetNumberOfPoints()
        if tco is None or norms is None:
            return False
        new_norms = vtk.vtkFloatArray()
        new_norms.SetNumberOfComponents(3)
        new_norms.SetName("Normals")
        new_norms.SetNumberOfTuples(n)
        for i in range(n):
            uv = tco.GetTuple2(i)
            nm = self._sample_normal(uv[0], uv[1])
            N = norms.GetTuple3(i)
            new_norms.SetTuple3(i, *_perturb_normal(N, nm, strength))
        pd.GetPointData().SetNormals(new_norms)
        pd.GetPointData().Modified()
        pd.Modified()
        return True

    def _restore_bump(self):
        if self.cur_pd is not None and self.orig_normals is not None:
            self.cur_pd.GetPointData().SetNormals(self.orig_normals)
            self.cur_pd.GetPointData().Modified()
            self.cur_pd.Modified()

    def _render(self):
        self.ctx.vtk_widget.GetRenderWindow().Render()

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------
    def create_ui(self):
        self._load_textures()
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(6)
        outer.setContentsMargins(6, 6, 6, 6)

        title = QLabel("任务2：凹凸映射（混凝土铺路砖法线贴图）")
        title.setStyleSheet("font-weight:bold; font-size:12px; color:#1a5fb4;")
        outer.addWidget(title)

        box = QGroupBox("凹凸映射")
        lay = QVBoxLayout(box)
        self.chk_on = QCheckBox("启用凹凸映射")
        self.chk_on.setChecked(True)
        self.chk_on.toggled.connect(self.on_toggle)
        lay.addWidget(self.chk_on)

        row = QHBoxLayout()
        row.addWidget(QLabel("凹凸强度"))
        self.sl_strength = QSlider(Qt.Horizontal)
        self.sl_strength.setRange(0, 200)
        self.sl_strength.setValue(100)
        self.sl_strength.valueChanged.connect(self.on_strength)
        row.addWidget(self.sl_strength)
        lay.addLayout(row)
        outer.addWidget(box)

        btn_row = QVBoxLayout()
        self.btn_apply = QPushButton("应用到当前模型")
        self.btn_apply.setStyleSheet("font-weight:bold;")
        self.btn_apply.clicked.connect(self.on_apply)
        self.btn_off = QPushButton("关闭凹凸（恢复原法线）")
        self.btn_off.clicked.connect(self.on_restore)
        self.btn_demo = QPushButton("生成演示球体（带UV，直接演示）")
        self.btn_demo.setStyleSheet("background:#2e7d32; color:#fff;")
        self.btn_demo.clicked.connect(self.on_demo)
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_off)
        btn_row.addWidget(self.btn_demo)
        outer.addLayout(btn_row)

        self.lbl_status = QLabel("请在左侧加载一个 OBJ 模型（需含 UV 与法线）。\n"
                                 "或点击「生成演示球体」直接查看凹凸映射效果。")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color:#666; font-size:11px;")
        outer.addWidget(self.lbl_status)
        outer.addStretch(1)
        return self.plugin_panel

    # ----------------------------------------------------------
    # 应用到当前模型（框架加载的 actor）
    # ----------------------------------------------------------
    def on_apply(self):
        ren = self.ctx.vtk_renderer
        actor = self.ctx.current_actor if hasattr(self.ctx, "current_actor") else None
        if actor is None:
            self.lbl_status.setText("未检测到当前模型：请先在左侧加载 OBJ，或点击演示球体。")
            return
        pd = actor.GetMapper().GetInput()
        # 数据准备：缺法线/UV 时自动补算（框架 OBJ 普遍缺少两者）
        fixed_n = self._ensure_normals(pd)
        fixed_uv = self._ensure_uvs(pd)
        # 补算之后再备份，保证"关闭凹凸"能恢复到无凹凸的平滑法线
        self._capture(actor, pd)
        if not self._apply_bump_to(self.cur_pd, self._strength()):
            self.lbl_status.setText("当前模型无法凹凸映射（无法取得法线/UV）。可点击演示球体。")
            return
        # 贴上混凝土漫反射贴图，并关掉顶点色（白顶点色会冲掉贴图）
        actor.SetTexture(self.diff_tex)
        mapper = actor.GetMapper()
        mapper.ScalarVisibilityOff()
        mapper.Update()
        self._render()
        self.applied = True
        extra = ""
        if fixed_n or fixed_uv:
            extra = "（已自动补算法线/UV：%s%s）" % (
                "平滑法线" if fixed_n else "",
                "盒式投影UV" if fixed_uv else "")
        self.lbl_status.setText("已对当前模型应用凹凸映射（强度 %.2f）%s"
                                % (self._strength(), extra))

    # 演示球体：自带 UV + 法线，直接演示
    def on_demo(self):
        ren = self.ctx.vtk_renderer
        if self.demo_actor is None:
            src = vtk.vtkSphereSource()
            src.SetThetaResolution(96)
            src.SetPhiResolution(64)
            # 生成纹理坐标（vtkSphereSource 默认不带 UV，需映射到球面）
            tm = vtk.vtkTextureMapToSphere()
            tm.SetInputConnection(src.GetOutputPort())
            tm.PreventSeamOn()
            tm.Update()
            pd = vtk.vtkPolyData()
            pd.DeepCopy(tm.GetOutput())
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputData(pd)
            self.demo_actor = vtk.vtkActor()
            self.demo_actor.SetMapper(mapper)
            self.demo_actor.SetTexture(self.diff_tex)
            self.demo_actor.GetProperty().SetSpecular(0.4)
            self.demo_actor.GetProperty().SetSpecularPower(20)
            ren.AddActor(self.demo_actor)
        self._capture(self.demo_actor, self.demo_actor.GetMapper().GetInput())
        if self._apply_bump_to(self.cur_pd, self._strength()):
            self.demo_actor.GetMapper().Update()
        ren.ResetCamera()
        self._render()
        self.applied = True
        self.lbl_status.setText("已生成演示球体并应用凹凸映射（强度 %.2f）。"
                                % self._strength())

    def _capture(self, actor, pd):
        """备份当前 actor/polydata 与原始法线"""
        self.cur_actor = actor
        self.cur_pd = pd
        norms = pd.GetPointData().GetNormals()
        if norms is not None:
            self.orig_normals = vtk.vtkFloatArray()
            self.orig_normals.DeepCopy(norms)

    def _strength(self):
        return self.sl_strength.value() / 100.0

    # ----------------------------------------------------------
    # 开关 / 强度回调
    # ----------------------------------------------------------
    def on_toggle(self, on):
        if self.cur_pd is None:
            return
        if on:
            if not self.applied:
                self.on_apply()
            else:
                self._apply_bump_to(self.cur_pd, self._strength())
        else:
            self._restore_bump()
        if self.cur_actor:
            self.cur_actor.GetMapper().Update()
        self._render()

    def on_strength(self, _v):
        if self.chk_on.isChecked() and self.cur_pd is not None:
            self._apply_bump_to(self.cur_pd, self._strength())
            if self.cur_actor:
                self.cur_actor.GetMapper().Update()
            self._render()

    def on_restore(self):
        if self.cur_pd is None:
            return
        self._restore_bump()
        if self.cur_actor:
            self.cur_actor.GetMapper().Update()
        self._render()
        self.applied = False
        self.lbl_status.setText("已恢复原始法线（关闭凹凸映射）。")

    # ----------------------------------------------------------
    # 生命周期
    # ----------------------------------------------------------
    def on_model_loaded(self, obj_path, actor, polydata):
        # 新加载模型后，若凹凸处于启用状态，自动补齐 UV/法线并应用（保持演示连贯）
        if self.chk_on and self.chk_on.isChecked():
            if self.normal_img is None:
                self._load_textures()
            self._ensure_normals(polydata)
            self._ensure_uvs(polydata)
            self._capture(actor, polydata)
            self._apply_bump_to(self.cur_pd, self._strength())
            actor.GetMapper().Update()

    def on_window_resize(self):
        pass

    def on_destroy(self):
        pass
