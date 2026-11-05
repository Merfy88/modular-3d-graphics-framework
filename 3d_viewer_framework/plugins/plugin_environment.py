# -*- coding: utf-8 -*-
"""
=====================================================================
 实验二 · 编程任务2 —— 环境映射插件（天球 / 球体全景采样 / 立方体反射）
 《高级计算机图形学》电子科技大学计算机学院
=====================================================================
功能说明（对应 task2_environment_mapping / task2.cpp）：
  1. 天球背景：把等距柱状(equirectangular)全景图采样到一圈大球上，
     作为环境本身（背景就是那张全景图）。
  2. 球体：按球面方向(经纬度)换算成全景图的 (u,v)，把全景图直接采样
     到球面 —— 即题目要求"将全景图用采样的方式采到球里面"。
  3. 立方体：反射映射 —— 对每个顶点计算"视线关于表面法线的反射方向"，
     再按该反射方向去采样全景图，从而在立方体表面"反射"出环境。

  环境映射 vs 普通纹理映射的区别：
    普通纹理映射(任务1)纹理坐标由几何体自带(顶点 u/v)；环境映射纹理
    坐标由"观察方向 / 表面法线动态生成"，反映周围环境在物体上的样子。

本插件由"实验菜单"宿主以"实验二"分组挂载；展开时 set_active(True)
把环境映射场景加入主渲染器，收起时 set_active(False) 移除并还原视角。
=====================================================================
"""
import math
import os
import vtk
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton,
                             QCheckBox, QGroupBox, QFrame)
from plugins.base_plugin import Base3DPlugin


def _tex_dir(ctx):
    """定位 data/texture 目录（相对项目根）"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "texture")


def _dir_to_equirect(x, y, z):
    """方向向量 -> 等距柱状 (u,v)，与 task2.cpp 的 dirToEquirect 一致"""
    lon = math.atan2(x, z)
    lat = math.asin(max(-1.0, min(1.0, y)))
    u = 0.5 + lon / (2.0 * math.pi)
    v = 0.5 - lat / math.pi
    return u, v


class EnvironmentMappingPlugin(Base3DPlugin):
    plugin_cls_name = "environment_mapping"
    plugin_name = "environment_mapping"
    plugin_desc = "实验二任务2：环境映射（天球/球体全景采样/立方体反射）"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        self.active = False
        # 场景对象
        self.sky_actor = None
        self.sphere_actor = None
        self.cube_actor = None
        self.cube_tex_coords = None     # vtkFloatArray（立方体逐点反射 UV）
        self.pano_tex = None
        # 控件
        self.chk_cube = None
        self.chk_sphere_env = None
        self.chk_wire = None
        # 相机
        self.cam_pos = None
        self._inter_obs = None
        self._last_cam_key = None

    # ----------------------------------------------------------
    # 全景图纹理
    # ----------------------------------------------------------
    def _load_pano(self):
        if self.pano_tex is not None:
            return self.pano_tex
        path = os.path.join(_tex_dir(self.ctx), "panorama.bmp")
        reader = vtk.vtkBMPReader()
        reader.SetFileName(path)
        reader.Update()
        tex = vtk.vtkTexture()
        tex.SetInputConnection(reader.GetOutputPort())
        tex.InterpolateOn()
        tex.RepeatOff()
        self.pano_tex = tex
        return tex

    # ----------------------------------------------------------
    # 天球背景（大球 + 等距柱状全景采样）
    # ----------------------------------------------------------
    def _build_sky(self):
        src = vtk.vtkSphereSource()
        src.SetRadius(80.0)
        src.SetThetaResolution(96)
        src.SetPhiResolution(48)
        src.Update()
        # 反转朝向：相机在球内，需要看到内表面且纹理朝向正确
        rev = vtk.vtkReverseSense()
        rev.SetInputConnection(src.GetOutputPort())
        rev.ReverseCellsOn()
        rev.ReverseNormalsOn()
        rev.Update()
        tmapper = vtk.vtkTextureMapToSphere()
        tmapper.SetInputConnection(rev.GetOutputPort())
        tmapper.PreventSeamOn()
        tmapper.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tmapper.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetTexture(self._load_pano())
        prop = actor.GetProperty()
        prop.LightingOff()                       # 天球只负责把全景图采上来，不光照
        prop.SetAmbient(1.0); prop.SetDiffuse(0.0); prop.SetSpecular(0.0)
        actor.SetPickable(False)
        return actor

    # ----------------------------------------------------------
    # 球体：等距柱状直接采样全景图（任务要求：把全景图采到球里面）
    # ----------------------------------------------------------
    def _build_sphere(self):
        src = vtk.vtkSphereSource()
        src.SetRadius(2.4)
        src.SetThetaResolution(72)
        src.SetPhiResolution(48)
        src.Update()
        tmapper = vtk.vtkTextureMapToSphere()
        tmapper.SetInputConnection(src.GetOutputPort())
        tmapper.PreventSeamOn()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tmapper.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetTexture(self._load_pano())
        prop = actor.GetProperty()
        prop.LightingOff()                       # GL_DECAL：全景原样可见，不被光照压暗
        prop.SetAmbient(1.0); prop.SetDiffuse(0.0); prop.SetSpecular(0.0)
        actor.SetPosition(-1.8, 0.0, 0.0)
        return actor

    # ----------------------------------------------------------
    # 立方体：反射映射（按视线反射方向采样环境）
    # ----------------------------------------------------------
    def _build_cube(self):
        src = vtk.vtkCubeSource()
        src.SetXLength(1.8); src.SetYLength(1.8); src.SetZLength(1.8)
        src.Update()
        pd = vtk.vtkPolyData()
        pd.DeepCopy(src.GetOutput())
        # 每点初始 UV 占位
        n = pd.GetPoints().GetNumberOfPoints()
        self.cube_tex_coords = vtk.vtkFloatArray()
        self.cube_tex_coords.SetNumberOfComponents(2)
        self.cube_tex_coords.SetNumberOfTuples(n)
        pd.GetPointData().SetTCoords(self.cube_tex_coords)
        self.cube_pd = pd

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetTexture(self._load_pano())
        prop = actor.GetProperty()
        prop.LightingOff()                       # GL_DECAL：反射到的环境原样显示
        prop.SetAmbient(1.0); prop.SetDiffuse(0.0); prop.SetSpecular(0.0)
        actor.SetPosition(2.0, 0.0, 0.0)
        # 初始按一个默认视角算一次 UV
        self._update_cube_reflection((0.0, 9.0, 12.0))
        return actor

    def _update_cube_reflection(self, eye):
        """按相机位置 eye 重算立方体各顶点 UV = 视线关于法线的反射方向 -> 全景 UV"""
        if self.cube_pd is None:
            return
        pts = self.cube_pd.GetPoints()
        normals = self.cube_pd.GetPointData().GetNormals()
        n = pts.GetNumberOfPoints()
        for i in range(n):
            P = pts.GetPoint(i)
            N = normals.GetTuple3(i)
            Vx, Vy, Vz = eye[0] - P[0], eye[1] - P[1], eye[2] - P[2]
            vl = math.sqrt(Vx * Vx + Vy * Vy + Vz * Vz)
            if vl < 1e-8:
                vl = 1.0
            Vx, Vy, Vz = Vx / vl, Vy / vl, Vz / vl
            dot = Vx * N[0] + Vy * N[1] + Vz * N[2]
            Rx = Vx - 2.0 * dot * N[0]
            Ry = Vy - 2.0 * dot * N[1]
            Rz = Vz - 2.0 * dot * N[2]
            u, v = _dir_to_equirect(Rx, Ry, Rz)
            self.cube_tex_coords.SetTuple2(i, u, v)
        self.cube_pd.GetPointData().Modified()
        self.cube_pd.Modified()

    # ----------------------------------------------------------
    # UI
    # ----------------------------------------------------------
    def create_ui(self):
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(6)
        outer.setContentsMargins(6, 6, 6, 6)

        title = QLabel("任务2：环境映射（天球 / 球体采样 / 立方体反射）")
        title.setStyleSheet("font-weight:bold; font-size:12px; color:#1a5fb4;")
        outer.addWidget(title)

        box = QGroupBox("场景开关")
        lay = QVBoxLayout(box)
        self.chk_sphere_env = QCheckBox("球体：全景图采样（等距柱状）")
        self.chk_sphere_env.setChecked(True)
        self.chk_sphere_env.toggled.connect(self.on_sphere_env)
        self.chk_cube = QCheckBox("立方体：反射映射（视线反射方向采样）")
        self.chk_cube.setChecked(True)
        self.chk_cube.toggled.connect(self.on_cube_toggle)
        self.chk_wire = QCheckBox("线框模式")
        self.chk_wire.setChecked(False)
        self.chk_wire.toggled.connect(self.on_wire)
        lay.addWidget(self.chk_sphere_env)
        lay.addWidget(self.chk_cube)
        lay.addWidget(self.chk_wire)
        outer.addWidget(box)

        btn_reset = QPushButton("复位视角")
        btn_reset.clicked.connect(self.reset_view)
        outer.addWidget(btn_reset)

        tip = QLabel(
            "背景=把全景图采样到天球(环境本身)；球体=直接采样全景图；\n"
            "立方体=按视线反射方向采样全景图，实现反射。\n"
            "对比任务1普通纹理映射：这里纹理坐标由方向动态生成。\n"
            "操作：拖拽旋转视角，滚轮缩放。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; font-size:11px;")
        outer.addWidget(tip)
        outer.addStretch(1)

        # 挂交互事件：视角变化时刷新立方体反射 UV
        self._hook_interaction()
        return self.plugin_panel

    def _hook_interaction(self):
        iren = self.ctx.vtk_widget.GetRenderWindow().GetInteractor()
        if iren is None:
            return
        self._inter_obs = iren.AddObserver("InteractionEvent", self._on_interaction)

    def _on_interaction(self, obj, event):
        if not self.active or self.cube_actor is None:
            return
        cam = self.ctx.vtk_renderer.GetActiveCamera()
        self._refresh_cube(cam)

    def _refresh_cube(self, cam):
        self._update_cube_reflection(tuple(cam.GetPosition()))
        self.ctx.vtk_widget.GetRenderWindow().Render()

    # ----------------------------------------------------------
    # 场景挂载 / 卸载（由宿主实验菜单调用）
    # ----------------------------------------------------------
    def set_active(self, checked):
        self.active = checked
        ren = self.ctx.vtk_renderer
        rw = self.ctx.vtk_widget.GetRenderWindow()
        if checked:
            if self.sky_actor is None:
                self.sky_actor = self._build_sky()
                self.sphere_actor = self._build_sphere()
                self.cube_actor = self._build_cube()
            ren.AddActor(self.sky_actor)
            ren.AddActor(self.sphere_actor)
            ren.AddActor(self.cube_actor)
            self.reset_view()
        else:
            for a in (self.sky_actor, self.sphere_actor, self.cube_actor):
                if a is not None:
                    ren.RemoveActor(a)
            ren.ResetCamera()
        rw.Render()

    def reset_view(self):
        ren = self.ctx.vtk_renderer
        cam = ren.GetActiveCamera()
        cam.SetPosition(7.0, 2.5, 10.5)     # 与 task2 初始视角相当
        cam.SetFocalPoint(0, 0, 0)
        cam.SetViewUp(0, 1, 0)
        cam.SetViewAngle(60)
        cam.SetClippingRange(0.5, 500.0)
        ren.ResetCameraClippingRange()
        self._refresh_cube(cam)
        self.ctx.vtk_widget.GetRenderWindow().Render()

    # ----------------------------------------------------------
    # 控件回调
    # ----------------------------------------------------------
    def on_sphere_env(self, on):
        if self.sphere_actor is None:
            return
        self.sphere_actor.SetVisibility(on)
        self._render()

    def on_cube_toggle(self, on):
        if self.cube_actor is None:
            return
        self.cube_actor.SetVisibility(on)
        self._render()

    def on_wire(self, on):
        for a in (self.sky_actor, self.sphere_actor, self.cube_actor):
            if a is not None:
                a.GetProperty().SetRepresentationToWireframe() if on \
                    else a.GetProperty().SetRepresentationToSurface()
        self._render()

    def _render(self):
        self.ctx.vtk_widget.GetRenderWindow().Render()

    # ----------------------------------------------------------
    # 生命周期
    # ----------------------------------------------------------
    def on_model_loaded(self, obj_path, actor, polydata):
        pass

    def on_window_resize(self):
        pass

    def on_destroy(self):
        self.set_active(False)
        iren = self.ctx.vtk_widget.GetRenderWindow().GetInteractor()
        if iren is not None and self._inter_obs is not None:
            iren.RemoveObserver(self._inter_obs)
            self._inter_obs = None
