# -*- coding: utf-8 -*-
"""
=====================================================================
 实验菜单宿主插件 —— 把四个实验以"折叠分组"整合进 3D 浏览器框架
 《高级计算机图形学》电子科技大学计算机学院
=====================================================================
UI 形态（对应需求："UI 上看到折叠的实验一二三四，展开后有这些实验"）：
  ▶ 实验一：颜色应用
      └ 任务1 彩色三角形 / 任务2 RGB立方体（HSV↔RGB 双显示区）
  ▶ 实验二：纹理映射
      └ 任务1 纹理映射 / 任务2 环境映射（天球/球体采样/立方体反射）
  ▶ 实验三：光照与材质
      └ 任务1 光照控制 / 任务2 多模型加载 + 材质（含真实材质进阶）
  ▶ 实验四：光线追踪与凹凸映射
      └ 任务1 CPU光线追踪 / 任务2 凹凸映射（法线贴图）

本插件是右侧面板唯一入口（yaml 只注册 experiment_hub），
它以懒加载方式把各实验的子插件创建出来并挂到对应分组里；
只有展开某实验时才会创建/激活该实验的子插件（减少冲突、省资源）。
生命周期钩子(on_model_loaded / on_window_resize / on_destroy)
由本宿主统一转发给已创建的子插件。

说明：四个实验共享同一个 3D 视窗，若同时展开多个实验，它们的
场景可能互相叠加/覆盖。建议一次只展开一个实验，效果最佳。
=====================================================================
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QToolButton, QScrollArea, QFrame)
from PyQt5.QtCore import Qt
from plugins.base_plugin import Base3DPlugin

# 各实验的子插件（懒加载）
from plugins.plugin_color_experiment import ColorExperimentPlugin
from plugins.plugin_texture import TexturePlugin
from plugins.plugin_environment import EnvironmentMappingPlugin
from plugins.plugin_light import LightPlugin
from plugins.plugin_material import MaterialTask2Plugin
from plugins.plugin_raytracer import RaytracerPlugin
from plugins.plugin_bump import BumpPlugin


def _collapsible_header(text):
    """返回一个可折叠分组头（▶/▼ 切换）"""
    btn = QToolButton()
    btn.setText("▶ " + text)
    btn.setCheckable(True)
    btn.setChecked(False)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setAutoRaise(True)
    btn.setStyleSheet("""
        QToolButton { text-align:left; font-weight:bold; font-size:13px;
                       padding:6px; background:#eef2f7; border:1px solid #c8d3e0;
                       border-radius:4px; color:#14365c; }
        QToolButton:hover { background:#dfe8f3; }
    """)
    return btn


class _ExperimentSection:
    """一个折叠的实验分组：头 + 内容（懒创建子插件）"""
    def __init__(self, hub, header_text, task_label, child_classes):
        self.hub = hub
        self.header = _collapsible_header(header_text)
        self.content = QWidget()
        self.lay = QVBoxLayout(self.content)
        self.lay.setSpacing(4)
        self.lay.setContentsMargins(10, 2, 4, 6)
        # 任务摘要
        if task_label:
            t = QLabel(task_label)
            t.setWordWrap(True)
            t.setStyleSheet("color:#666; font-size:11px; padding:2px 0;")
            self.lay.addWidget(t)
        self.child_classes = list(child_classes)
        self.children = []          # 已创建的子插件实例
        self.created = False
        self.header.toggled.connect(self.on_toggle)

    def on_toggle(self, checked):
        self.header.setText(("▼ " if checked else "▶ ") + self.header.text()[2:])
        self.content.setVisible(checked)
        if checked and not self.created:
            self._create_children()
        # 展开/收起时激活或停用有 set_active 的子插件（颜色/环境映射）
        for ch in self.children:
            if hasattr(ch, "set_active"):
                try:
                    ch.set_active(checked)
                except Exception as e:  # noqa
                    print("experiment set_active error:", e)

    def _create_children(self):
        self.created = True
        for cls in self.child_classes:
            try:
                inst = cls(self.hub.ctx)
                panel = inst.create_ui()
                self.children.append(inst)
                if panel is not None:
                    self.lay.addWidget(panel)
            except Exception as e:  # noqa
                self.lay.addWidget(QLabel(f"<font color=red>插件加载失败：{cls.__name__}</font>"))
                print(f"[experiment] {cls.__name__} 加载失败：", e)

    def forward(self, method, *args):
        for ch in self.children:
            fn = getattr(ch, method, None)
            if fn is not None:
                try:
                    fn(*args)
                except Exception as e:  # noqa
                    print(f"[experiment] {method} 转发失败：", e)


class ExperimentMenuPlugin(Base3DPlugin):
    plugin_cls_name = "experiment_hub"
    plugin_name = "experiment_hub"
    plugin_desc = "实验一/二/三/四 折叠菜单（整合四个实验）"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        self.sections = []

    def create_ui(self):
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(6)
        outer.setContentsMargins(6, 6, 6, 6)

        title = QLabel("实验菜单（点击展开/收起）")
        title.setStyleSheet("font-weight:bold; font-size:14px; color:#1a5fb4;")
        outer.addWidget(title)

        note = QLabel("把四个实验以插件形式整合进框架。\n"
                      "建议一次只展开一个实验，避免共享视窗场景叠加。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#888; font-size:11px;")
        outer.addWidget(note)

        # 折叠分组容器（放入滚动区，内容多时可滚动）
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setSpacing(8)
        body_lay.setContentsMargins(0, 0, 0, 0)

        self.sections.append(_ExperimentSection(
            self, "实验一：颜色应用",
            "任务1 彩色三角形（HSV↔RGB 双显示区） / 任务2 RGB立方体",
            [ColorExperimentPlugin]))
        self.sections.append(_ExperimentSection(
            self, "实验二：纹理映射",
            "任务1 纹理映射（2D贴图） / 任务2 环境映射（天球/球体采样/立方体反射）",
            [TexturePlugin, EnvironmentMappingPlugin]))
        self.sections.append(_ExperimentSection(
            self, "实验三：光照与材质",
            "任务1 光照控制 / 任务2 多模型加载 + 光照材质（含真实材质进阶）",
            [LightPlugin, MaterialTask2Plugin]))
        self.sections.append(_ExperimentSection(
            self, "实验四：光线追踪与凹凸映射",
            "任务1 CPU光线追踪（参考场景/加载模型·BVH加速） / "
            "任务2 凹凸映射（法线贴图，缺UV自动补算）\n"
            "★ 进阶：加载模型 + 光线追踪 + 凹凸映射一体化",
            [RaytracerPlugin, BumpPlugin]))

        for sec in self.sections:
            body_lay.addWidget(sec.header)
            body_lay.addWidget(sec.content)
        body_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)
        return self.plugin_panel

    # ----------------------------------------------------------
    # 生命周期钩子：转发给已创建的子插件
    # ----------------------------------------------------------
    def on_model_loaded(self, obj_path, actor, polydata):
        for sec in self.sections:
            sec.forward("on_model_loaded", obj_path, actor, polydata)

    def on_window_resize(self):
        for sec in self.sections:
            sec.forward("on_window_resize")

    def on_destroy(self):
        for sec in self.sections:
            sec.forward("on_destroy")
