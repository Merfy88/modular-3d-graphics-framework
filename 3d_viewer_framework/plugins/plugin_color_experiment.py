import colorsys
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
                             QSlider, QSpinBox, QPushButton, QGroupBox,
                             QGridLayout, QRadioButton, QButtonGroup, QToolButton)
from PyQt5.QtCore import Qt
import vtk
from plugins.base_plugin import Base3DPlugin


# ★ 自定义交互样式：滚轮缩放相机；左键拾取到目标 actor 时旋转该 actor，否则旋转相机
class _CubeActorStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, target_actor, renderer, parent=None):
        super().__init__()
        self._target = target_actor
        self._ren = renderer
        self._parent = parent
        self._rotating_actor = False

    def OnLeftButtonDown(self):
        pos = self.GetInteractor().GetEventPosition()
        picker = vtk.vtkPropPicker()
        picker.Pick(pos[0], pos[1], 0, self._ren)
        actor = picker.GetActor()
        # 拾取到 assembly 内部的叶子 actor 也算命中（marker 或 cube）
        hit = False
        if actor is not None and self._target is not None:
            if actor is self._target:
                hit = True
            else:
                # 检查该 actor 是否是 assembly 的部件
                parts = self._target.GetParts()
                parts.InitTraversal()
                for _ in range(parts.GetNumberOfItems()):
                    p = parts.GetNextProp()
                    if p is actor:
                        hit = True
                        break
        if hit:
            self._rotating_actor = True
            # 用 TrackballActor 的旋转逻辑手动处理
            self._start_actor_rotate()
        else:
            self._rotating_actor = False
            super().OnLeftButtonDown()

    def _start_actor_rotate(self):
        # 使用 vtkInteractorStyleTrackballActor 的旋转实现需要切换 style，
        # 这里直接用 Rotate 宏不方便，改为手动实现：记录起点，MouseMove 中旋转
        self.GetInteractor().GetRenderWindow().Render()

    def OnLeftButtonUp(self):
        if self._rotating_actor:
            self._rotating_actor = False
        else:
            super().OnLeftButtonUp()

    def OnMouseMove(self):
        if self._rotating_actor and self.GetState() == vtk.VTKIS_ROTATE:
            # 使用父类 TrackballCamera 的旋转不行（那是相机），这里手动旋转 actor
            self._rotate_target()
            return
        if self._rotating_actor:
            # 第一次按下后进入旋转状态
            self.StartState(vtk.VTKIS_ROTATE)
            self._rotate_target()
            return
        super().OnMouseMove()

    def _rotate_target(self):
        if self._target is None:
            return
        rwi = self.GetInteractor()
        last = rwi.GetLastEventPosition()
        cur = rwi.GetEventPosition()
        dx = cur[0] - last[0]
        dy = cur[1] - last[1]
        # 用 vtkTransform 绕屏幕轴旋转
        center = self._target.GetCenter()
        transform = vtk.vtkTransform()
        transform.Identity()
        # 绕 Y 轴（水平拖动），绕 X 轴（垂直拖动）
        t1 = vtk.vtkTransform()
        t1.Translate(center)
        t2 = vtk.vtkTransform()
        t2.RotateWXYZ(dy * 0.5, 1, 0, 0)
        t3 = vtk.vtkTransform()
        t3.RotateWXYZ(dx * 0.5, 0, 1, 0)
        t4 = vtk.vtkTransform()
        t4.Translate(-center[0], -center[1], -center[2])
        transform.Concatenate(t4)
        transform.Concatenate(t3)
        transform.Concatenate(t2)
        transform.Concatenate(t1)
        self._target.SetUserTransform(transform)
        rwi.GetRenderWindow().Render()

    def OnMouseWheelForward(self):
        self._dolly(1.1)

    def OnMouseWheelBackward(self):
        self._dolly(1.0 / 1.1)

    def _dolly(self, factor):
        cam = self._ren.GetActiveCamera()
        if cam.GetParallelProjection():
            cam.SetParallelScale(cam.GetParallelScale() / factor)
        else:
            cam.Dolly(factor)
        self._ren.ResetCameraClippingRange()
        self.GetInteractor().GetRenderWindow().Render()
        if self._parent is not None:
            self._parent.sync_marker_with_cube()


class ColorExperimentPlugin(Base3DPlugin):
    plugin_cls_name = "color_experiment"
    plugin_name = "color_experiment"
    plugin_desc = "实验一：颜色应用（HSV/RGB转换、双显示窗口、RGB立方体）"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        self._updating = False
        self.rgb = (255, 255, 255)
        self.hsv = (0, 0, 100)

        self.content_widget = None
        self.middle_active = False
        self.triangle_on = True
        self.cube_on = False

        self.hsv_ren = None
        self.rgb_ren = None
        self.hsv_tri_actor = None
        self.rgb_tri_actor = None
        self.cube_actor = None
        self.cube_assembly = None
        self.cube_marker = None
        self.hsv_label = None
        self.rgb_label = None
        self.hsv_axes = None
        self.rgb_axes = None

        self._default_style = None
        self._cube_style = None

        self.header_btn = None
        self.sp_h = self.sp_s = self.sp_v = None
        self.sp_r = self.sp_g = self.sp_b = None
        self.color_btn = None
        self.rb_triangle = None
        self.rb_cube = None
        self._task_group = None

    # ---------- 颜色转换 ----------
    @staticmethod
    def hsv_to_rgb(h, s, v):
        r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
        return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))

    @staticmethod
    def rgb_to_hsv(r, g, b):
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        return int(round(h * 360)), int(round(s * 100)), int(round(v * 100))

    # ---------- UI ----------
    def create_ui(self):
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(4)
        outer.setContentsMargins(6, 6, 6, 6)

        # 本插件由"实验菜单"宿主插件以"实验一"分组统一挂载，
        # 不再自带折叠头：展开实验一时宿主调用 set_active(True)，收起时 set_active(False)。
        self.content_widget = QWidget()
        lay = QVBoxLayout(self.content_widget)
        lay.setSpacing(6)
        lay.setContentsMargins(6, 2, 6, 2)

        task_box = QGroupBox("任务选择")
        task_lay = QHBoxLayout(task_box)
        self.rb_triangle = QRadioButton("任务1：彩色三角形")
        self.rb_cube = QRadioButton("任务2：RGB立方体")
        self.rb_triangle.setChecked(True)
        self._task_group = QButtonGroup(self.plugin_panel)
        self._task_group.addButton(self.rb_triangle, 1)
        self._task_group.addButton(self.rb_cube, 2)
        self._task_group.buttonClicked.connect(self.on_task_changed)
        task_lay.addWidget(self.rb_triangle)
        task_lay.addWidget(self.rb_cube)
        lay.addWidget(task_box)

        hsv_box = QGroupBox("HSV 控制区")
        hsv_lay = QGridLayout(hsv_box)
        self.s_h, self.sp_h = self._add_row(hsv_lay, "H", 0, 0, 360, "hsv")
        self.s_s, self.sp_s = self._add_row(hsv_lay, "S", 1, 0, 100, "hsv")
        self.s_v, self.sp_v = self._add_row(hsv_lay, "V", 2, 0, 100, "hsv")
        lay.addWidget(hsv_box)

        rgb_box = QGroupBox("RGB 控制区")
        rgb_lay = QGridLayout(rgb_box)
        self.s_r, self.sp_r = self._add_row(rgb_lay, "R", 0, 0, 255, "rgb")
        self.s_g, self.sp_g = self._add_row(rgb_lay, "G", 1, 0, 255, "rgb")
        self.s_b, self.sp_b = self._add_row(rgb_lay, "B", 2, 0, 255, "rgb")
        lay.addWidget(rgb_box)

        self.color_btn = QPushButton("当前颜色（点击重置为红色）")
        self.color_btn.setFixedHeight(32)
        self.color_btn.clicked.connect(self.reset_color)
        lay.addWidget(self.color_btn)

        tip = QLabel("任务1：拖动滑块观察两个显示区三角形颜色同步变化。\n"
                     "任务2：勾选后右侧显示RGB立方体，鼠标滚轮缩放，\n"
                     "左键拖拽立方体旋转（标记球随立方体一起旋转）。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(tip)

        outer.addWidget(self.content_widget)
        # 内容常显（折叠/展开由宿主"实验菜单"控制）
        self.content_widget.setVisible(True)

        self._updating = True
        self._init_from_rgb(255, 0, 0)
        self._updating = False
        self.triangle_on = True
        self.cube_on = False
        self.sync_color_btn()
        return self.plugin_panel

    def _add_row(self, grid, label, row, vmin, vmax, channel):
        lab = QLabel(label)
        lab.setFixedWidth(18)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(vmin, vmax)
        slider.setFixedHeight(20)
        spin = QSpinBox()
        spin.setRange(vmin, vmax)
        spin.setFixedWidth(54)
        grid.addWidget(lab, row, 0)
        grid.addWidget(slider, row, 1)
        grid.addWidget(spin, row, 2)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        handler = self.on_hsv_change if channel == "hsv" else self.on_rgb_change
        slider.valueChanged.connect(handler)
        spin.valueChanged.connect(handler)
        return slider, spin

    # ---------- 入口展开/收起 ----------
    def on_entry_toggled(self, checked):
        # 兼容旧版独立折叠头（宿主挂载模式下不调用此方法）
        if self.header_btn is not None:
            self.header_btn.setText(("▼ " if checked else "▶ ") + "实验一：颜色应用（HSV↔RGB）")
        self.set_active(checked)

    def set_active(self, checked):
        """宿主实验菜单在展开/收起"实验一"分组时调用。"""
        if self.content_widget:
            self.content_widget.setVisible(checked)
        self.middle_active = checked
        if checked:
            self.activate_middle()
        else:
            self.deactivate_middle()
        self._append_info("实验一设置面板：%s" % ("展开" if checked else "收起"))

    # ---------- 数值联动 ----------
    def _init_from_rgb(self, r, g, b):
        self.rgb = (r, g, b)
        h, s, v = self.rgb_to_hsv(r, g, b)
        self.hsv = (h, s, v)
        self.sp_h.setValue(h); self.sp_s.setValue(s); self.sp_v.setValue(v)
        self.sp_r.setValue(r); self.sp_g.setValue(g); self.sp_b.setValue(b)

    def on_hsv_change(self, *_):
        if self._updating:
            return
        self._updating = True
        h, s, v = self.sp_h.value(), self.sp_s.value(), self.sp_v.value()
        self.hsv = (h, s, v)
        r, g, b = self.hsv_to_rgb(h, s, v)
        self.rgb = (r, g, b)
        self.sp_r.setValue(r); self.sp_g.setValue(g); self.sp_b.setValue(b)
        self._updating = False
        self.apply_color_to_scene()
        self.sync_color_btn()

    def on_rgb_change(self, *_):
        if self._updating:
            return
        self._updating = True
        r, g, b = self.sp_r.value(), self.sp_g.value(), self.sp_b.value()
        self.rgb = (r, g, b)
        h, s, v = self.rgb_to_hsv(r, g, b)
        self.hsv = (h, s, v)
        self.sp_h.setValue(h); self.sp_s.setValue(s); self.sp_v.setValue(v)
        self._updating = False
        self.apply_color_to_scene()
        self.sync_color_btn()

    def reset_color(self):
        self._updating = True
        self._init_from_rgb(255, 0, 0)
        self._updating = False
        self.apply_color_to_scene()
        self.sync_color_btn()
        self._append_info("颜色已重置为红色")

    def sync_color_btn(self):
        r, g, b = self.rgb
        self.color_btn.setStyleSheet(
            "background-color: rgb(%d,%d,%d); color: rgb(%d,%d,%d);"
            " border:1px solid #888; font-weight:bold;"
            % (r, g, b, 255 - r, 255 - g, 255 - b))

    def _append_info(self, text):
        if self.ctx.info_display:
            self.ctx.info_display.append(text)

    # ---------- 中间双视口 ----------
    def ensure_renderers(self):
        if self.hsv_ren is not None:
            return
        self.hsv_ren = vtk.vtkRenderer()
        self.hsv_ren.SetViewport(0.0, 0.0, 0.5, 1.0)
        self.hsv_ren.SetBackground(0.86, 0.88, 0.92)
        self.rgb_ren = vtk.vtkRenderer()
        self.rgb_ren.SetViewport(0.5, 0.0, 1.0, 1.0)
        self.rgb_ren.SetBackground(0.93, 0.89, 0.85)

        self.hsv_tri_actor = self.build_triangle()
        self.rgb_tri_actor = self.build_triangle()

        self.cube_actor = self.build_color_cube()
        self.cube_marker = self.build_marker()
        self.cube_assembly = vtk.vtkAssembly()
        self.cube_assembly.AddPart(self.cube_actor)
        self.cube_assembly.AddPart(self.cube_marker)

        self.hsv_label = self.build_label("HSV 显示区")
        self.rgb_label = self.build_label("RGB 显示区")

        self.hsv_ren.AddActor(self.hsv_tri_actor)
        self.hsv_ren.AddActor(self.hsv_label)
        self.rgb_ren.AddActor(self.rgb_tri_actor)
        self.rgb_ren.AddActor(self.rgb_label)

        self.hsv_axes = self._make_axes_widget(self.hsv_ren)
        self.rgb_axes = self._make_axes_widget(self.rgb_ren)

        self.apply_color_to_scene()

    def _make_axes_widget(self, renderer):
        axes = vtk.vtkAxesActor()
        axes.SetXAxisLabelText("X"); axes.SetYAxisLabelText("Y"); axes.SetZAxisLabelText("Z")
        widget = vtk.vtkOrientationMarkerWidget()
        widget.SetOrientationMarker(axes)
        widget.SetInteractor(self.ctx.vtk_widget.GetRenderWindow().GetInteractor())
        widget.SetViewport(0.0, 0.0, 0.18, 0.22)
        widget.SetEnabled(1)
        widget.InteractiveOff()
        return widget

    def activate_middle(self):
        self.ensure_renderers()
        rw = self.ctx.vtk_widget.GetRenderWindow()
        rws = list(rw.GetRenderers())
        if self.hsv_ren not in rws:
            rw.AddRenderer(self.hsv_ren)
        if self.rgb_ren not in rws:
            rw.AddRenderer(self.rgb_ren)
        self.apply_display_content()
        for ren in (self.hsv_ren, self.rgb_ren):
            ren.ResetCamera()
        if self.cube_on:
            self._set_cube_camera()
        rw.Render()
        self.update_interactor_style()

    def deactivate_middle(self):
        if self.hsv_ren is None:
            return
        if self.hsv_axes:
            self.hsv_axes.SetEnabled(0)
        if self.rgb_axes:
            self.rgb_axes.SetEnabled(0)
        rw = self.ctx.vtk_widget.GetRenderWindow()
        rws = list(rw.GetRenderers())
        if self.hsv_ren in rws:
            rw.RemoveRenderer(self.hsv_ren)
        if self.rgb_ren in rws:
            rw.RemoveRenderer(self.rgb_ren)
        rw.Render()
        self.update_interactor_style()

    # ★ 用 GetViewProps 判断（GetActors 不会返回 assembly 本身）
    def _has_prop(self, renderer, prop):
        props = renderer.GetViewProps()
        props.InitTraversal()
        for _ in range(props.GetNumberOfItems()):
            if props.GetNextProp() is prop:
                return True
        return False

    def apply_display_content(self):
        if self.rgb_ren is None:
            return
        if self.cube_on:
            # 移除三角形
            if self._has_prop(self.rgb_ren, self.rgb_tri_actor):
                self.rgb_ren.RemoveActor(self.rgb_tri_actor)
            # 添加 assembly（若未添加）
            if not self._has_prop(self.rgb_ren, self.cube_assembly):
                self.rgb_ren.AddActor(self.cube_assembly)
        else:
            # 移除 assembly
            if self._has_prop(self.rgb_ren, self.cube_assembly):
                self.rgb_ren.RemoveActor(self.cube_assembly)
            # 添加三角形
            if not self._has_prop(self.rgb_ren, self.rgb_tri_actor):
                self.rgb_ren.AddActor(self.rgb_tri_actor)

    # ---------- 场景对象 ----------
    def build_triangle(self):
        pts = vtk.vtkPoints()
        pts.InsertNextPoint(-0.8, -0.45, 0.0)
        pts.InsertNextPoint(0.8, -0.45, 0.0)
        pts.InsertNextPoint(0.0, 0.45, 0.0)
        cells = vtk.vtkCellArray()
        tri = vtk.vtkTriangle()
        tri.GetPointIds().SetId(0, 0)
        tri.GetPointIds().SetId(1, 1)
        tri.GetPointIds().SetId(2, 2)
        cells.InsertNextCell(tri)
        pd = vtk.vtkPolyData()
        pd.SetPoints(pts)
        pd.SetPolys(cells)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(1.0, 1.0, 1.0)
        prop.SetEdgeVisibility(1)
        prop.SetEdgeColor(0, 0, 0)
        prop.SetLineWidth(2)
        return actor

    def build_color_cube(self):
        cube = vtk.vtkCubeSource()
        cube.SetXLength(0.7); cube.SetYLength(0.7); cube.SetZLength(0.7)
        cube.Update()
        pd = cube.GetOutput()
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)
        colors.SetName("Colors")
        for i in range(pd.GetPoints().GetNumberOfPoints()):
            x, y, z = pd.GetPoints().GetPoint(i)
            colors.InsertNextTuple3(int(round((x / 0.7 + 0.5) * 255)),
                                    int(round((y / 0.7 + 0.5) * 255)),
                                    int(round((z / 0.7 + 0.5) * 255)))
        pd.GetPointData().SetScalars(colors)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        mapper.SetScalarModeToUsePointData()
        mapper.InterpolateScalarsBeforeMappingOn()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.LightingOff()
        prop.SetEdgeVisibility(1)
        prop.SetEdgeColor(0, 0, 0)
        # ★ 关键修复1：立方体半透明，内部标记球可见
        prop.SetOpacity(0.35)
        prop.BackfaceCullingOff()
        return actor

    def build_marker(self):
        sphere = vtk.vtkSphereSource()
        sphere.SetRadius(0.05)
        sphere.SetThetaResolution(24)
        sphere.SetPhiResolution(24)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(1.0, 1.0, 1.0)
        # 标记球不透明，且关闭光照以保持纯色可见
        actor.GetProperty().LightingOff()
        actor.GetProperty().SetOpacity(1.0)
        return actor

    def build_label(self, text):
        ta = vtk.vtkTextActor()
        ta.SetInput(text)
        ta.GetTextProperty().SetFontSize(22)
        ta.GetTextProperty().SetColor(0, 0, 0)
        ta.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
        ta.GetPositionCoordinate().SetValue(0.05, 0.9)
        return ta

    # ---------- 颜色应用 ----------
    def apply_color_to_scene(self):
        r, g, b = self.rgb
        nr, ng, nb = r / 255.0, g / 255.0, b / 255.0
        for t in (self.hsv_tri_actor, self.rgb_tri_actor):
            if t is not None:
                t.GetProperty().SetColor(nr, ng, nb)
        if self.cube_marker is not None:
            self.cube_marker.GetProperty().SetColor(nr, ng, nb)
            # 标记球放在立方体内部，位置对应颜色坐标（归一化到 -0.35~0.35）
            self.cube_marker.SetPosition((nr - 0.5) * 0.7,
                                         (ng - 0.5) * 0.7,
                                         (nb - 0.5) * 0.7)
        if self.ctx.vtk_widget:
            self.ctx.vtk_widget.GetRenderWindow().Render()

    # ---------- 交互样式 ----------
    def update_interactor_style(self):
        inter = self.ctx.vtk_widget.GetRenderWindow().GetInteractor()
        if not inter:
            return
        if self.middle_active and self.cube_on:
            self._cube_style = _CubeActorStyle(self.cube_assembly, self.rgb_ren, self)
            inter.SetInteractorStyle(self._cube_style)
        else:
            if self._default_style is None:
                self._default_style = vtk.vtkInteractorStyleTrackballCamera()
            inter.SetInteractorStyle(self._default_style)

    def sync_marker_with_cube(self):
        pass

    # ---------- 任务切换（互斥） ----------
    def on_task_changed(self, btn):
        if btn is self.rb_triangle:
            self.triangle_on = True
            self.cube_on = False
        else:
            self.triangle_on = False
            self.cube_on = True
        if self.middle_active:
            self.apply_display_content()
            if self.cube_on:
                self._set_cube_camera()
            else:
                self.rgb_ren.ResetCamera()
            self.ctx.vtk_widget.GetRenderWindow().Render()
            self.update_interactor_style()
        if self.cube_on:
            self.apply_color_to_scene()
        self._append_info("切换任务：%s" % ("任务1 彩色三角形" if self.triangle_on else "任务2 RGB立方体"))

    def _set_cube_camera(self):
        cam = self.rgb_ren.GetActiveCamera()
        cam.SetPosition(2.2, 1.6, 1.8)
        cam.SetFocalPoint(0, 0, 0)
        cam.SetViewUp(0, 0, 1)
        cam.SetViewAngle(30)
        self.rgb_ren.ResetCameraClippingRange()

    # ---------- 生命周期 ----------
    def on_model_loaded(self, obj_path, actor, polydata):
        if self.middle_active:
            self.apply_color_to_scene()

    def on_window_resize(self):
        pass

    def on_destroy(self):
        if self.hsv_ren is not None:
            if self.hsv_axes:
                self.hsv_axes.SetEnabled(0)
            if self.rgb_axes:
                self.rgb_axes.SetEnabled(0)
            rw = self.ctx.vtk_widget.GetRenderWindow()
            rws = list(rw.GetRenderers())
            if self.hsv_ren in rws:
                rw.RemoveRenderer(self.hsv_ren)
            if self.rgb_ren in rws:
                rw.RemoveRenderer(self.rgb_ren)
        inter = self.ctx.vtk_widget.GetRenderWindow().GetInteractor()
        if inter and self._default_style is not None:
            inter.SetInteractorStyle(self._default_style)