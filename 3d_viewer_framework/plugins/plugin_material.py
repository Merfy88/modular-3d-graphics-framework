# -*- coding: utf-8 -*-
"""
=====================================================================
 实验三 · 编程任务2 —— 光照与材质插件（多模型 + 任务1材质 + 真实材质）
 《高级计算机图形学》电子科技大学计算机学院
=====================================================================
功能说明：
  本插件挂载到 3d_viewer_framework（3D浏览器插件化框架）右侧扩展区，
  在"可以加载多个模型"的基础上，实现编程任务1的"光照与材质"，并覆盖
  进阶要求（不同模型表现其真实材质，如金属、木质等）。

  1) 多模型加载与管理
     框架内核每次加载 OBJ 都会 RemoveAllViewProps 只保留当前模型，
     本插件通过维护自己的"模型注册表"，在 on_model_loaded 钩子里把
     之前加载过的模型重新放回渲染器，从而实现"多个模型同屏显示"。
     右侧"模型列表"可勾选显示/隐藏、删除选中、清空全部，并可自动平铺
     各模型避免重叠。

  2) 编程任务1 的光照与材质
     - 材质预设："材质预设"页签提供任务1的 12 球材质矩阵对应样式
       （纯漫反射 / 镜面低高光 / 镜面亮高光 / 自发光 / 环境光 / 彩色环境光…），
       点击即应用到选中的模型。
     - 自定义材质：环境光、漫反射、镜面高光(RGB+强度)、高光系数 shininess、
       自发光(RGB+强度) 全部可调，随时应用到选中模型。
     - 灯光控制：光源位置 XYZ、颜色 RGB、强度、开关，对应任务1的
       "移动灯光位置 / 调节灯光颜色"要求（插件里用控件而非按键实现）。

  3) 真实材质（进阶要求）
     "材质预设"页签另提供 金属金/银/黄铜/铜、木质、塑料、橡胶、玻璃、
     陶瓷、玉石、哑光黑 等真实材质预设，一键让模型呈现接近真实的外观。

  4) 自发光（emission）实现说明
     VTK 经典材质模型（vtkProperty）没有原生"自发光"分量，本插件通过
     给每个 actor 的 vtkShaderProperty 注入一段自定义 fragment shader，
     在光照结果上叠加发射色 emiss，从而忠实还原任务1的"自发光"列。
     该方案经离屏渲染验证有效，且不影响经典 Blinn-Phong 的
     环境光/漫反射/镜面/高光系数语义。

  使用方法：
     1) 在 plugin_config.yaml 的 active_plugins 中加入 material_task2；
     2) 项目根目录运行  python main.py；
     3) 左侧文件树点击 OBJ 加载模型（可连续点击多个实现多模型）；
     4) 右侧面板：选模型 → 点材质预设 / 调自定义材质 / 调灯光。
=====================================================================
"""
import os
import vtk
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QFrame, QScrollArea,
    QDoubleSpinBox, QCheckBox, QGroupBox
)
from PyQt5.QtCore import Qt
from plugins.base_plugin import Base3DPlugin


# ------------------------------------------------------------------
# 小工具：把 0~255 的 RGB 转成 VTK 的 0~1 浮点
# ------------------------------------------------------------------
def _norm(rgb):
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


# ==================================================================
# 材质预设数据
# 每个预设 = {amb环境色, amb_i环境强度, dif漫反射色, dif_i漫强度,
#            spe镜面色, spe_i镜强度, shin高光系数, emi自发光色, emi_i自发强度}
# ==================================================================

# ---- 任务1 样式：12 球材质矩阵（蓝色系，与任务1保持一致） ----
TASK1_PRESETS = [
    {"name": "纯漫反射(无环境/镜面/自发光)",
     "amb": (0, 0, 0), "amb_i": 0.0, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+镜面·低高光",
     "amb": (0, 0, 0), "amb_i": 0.0, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (255, 255, 255), "spe_i": 0.8, "shin": 20.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+镜面·亮高光",
     "amb": (0, 0, 0), "amb_i": 0.0, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (255, 255, 255), "spe_i": 0.8, "shin": 128.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+自发光",
     "amb": (0, 0, 0), "amb_i": 0.0, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (70, 110, 255), "emi_i": 0.55},
    {"name": "漫反射+环境光",
     "amb": (35, 45, 55), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+环境光+镜面·低高光",
     "amb": (35, 45, 55), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (255, 255, 255), "spe_i": 0.8, "shin": 20.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+环境光+镜面·亮高光",
     "amb": (35, 45, 55), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (255, 255, 255), "spe_i": 0.8, "shin": 128.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "漫反射+环境光+自发光",
     "amb": (35, 45, 55), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (70, 110, 255), "emi_i": 0.55},
    {"name": "彩色环境光+漫反射",
     "amb": (60, 120, 110), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "彩色环境光+漫反射+镜面·亮高光",
     "amb": (60, 120, 110), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (255, 255, 255), "spe_i": 0.8, "shin": 128.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "彩色环境光+漫反射+自发光",
     "amb": (60, 120, 110), "amb_i": 0.30, "dif": (30, 50, 90), "dif_i": 0.9,
     "spe": (0, 0, 0), "spe_i": 0.0, "shin": 1.0, "emi": (70, 110, 255), "emi_i": 0.55},
]

# ---- 真实材质（进阶要求）：金属、木质等 ----
REAL_PRESETS = [
    {"name": "金属·金", "amb": (40, 32, 12), "amb_i": 0.30, "dif": (118, 88, 32), "dif_i": 0.62,
     "spe": (255, 222, 150), "spe_i": 0.92, "shin": 90.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "金属·银", "amb": (42, 42, 48), "amb_i": 0.32, "dif": (178, 178, 190), "dif_i": 0.60,
     "spe": (255, 255, 255), "spe_i": 0.95, "shin": 115.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "黄铜", "amb": (42, 32, 12), "amb_i": 0.30, "dif": (150, 110, 40), "dif_i": 0.62,
     "spe": (255, 220, 128), "spe_i": 0.90, "shin": 80.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "铜", "amb": (42, 22, 12), "amb_i": 0.30, "dif": (172, 92, 45), "dif_i": 0.62,
     "spe": (255, 185, 122), "spe_i": 0.85, "shin": 70.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "木质", "amb": (42, 28, 12), "amb_i": 0.36, "dif": (150, 96, 46), "dif_i": 0.85,
     "spe": (82, 62, 42), "spe_i": 0.14, "shin": 12.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "塑料·红", "amb": (40, 10, 10), "amb_i": 0.30, "dif": (220, 42, 40), "dif_i": 0.72,
     "spe": (255, 255, 255), "spe_i": 0.55, "shin": 60.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "塑料·青", "amb": (10, 40, 40), "amb_i": 0.30, "dif": (40, 200, 200), "dif_i": 0.72,
     "spe": (255, 255, 255), "spe_i": 0.55, "shin": 60.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "橡胶", "amb": (12, 12, 14), "amb_i": 0.26, "dif": (42, 42, 48), "dif_i": 0.62,
     "spe": (85, 85, 90), "spe_i": 0.20, "shin": 15.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "玻璃", "amb": (32, 38, 44), "amb_i": 0.32, "dif": (120, 152, 172), "dif_i": 0.26,
     "spe": (255, 255, 255), "spe_i": 1.00, "shin": 128.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "陶瓷", "amb": (42, 42, 42), "amb_i": 0.32, "dif": (235, 235, 235), "dif_i": 0.80,
     "spe": (255, 255, 255), "spe_i": 0.42, "shin": 40.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "玉石", "amb": (32, 52, 38), "amb_i": 0.32, "dif": (102, 205, 132), "dif_i": 0.52,
     "spe": (222, 255, 232), "spe_i": 0.45, "shin": 50.0, "emi": (0, 0, 0), "emi_i": 0.0},
    {"name": "哑光黑", "amb": (10, 10, 10), "amb_i": 0.20, "dif": (26, 26, 26), "dif_i": 0.60,
     "spe": (32, 32, 32), "spe_i": 0.10, "shin": 10.0, "emi": (0, 0, 0), "emi_i": 0.0},
]

# 新加载模型的默认材质
DEFAULT_MAT = {"name": "默认", "amb": (26, 36, 46), "amb_i": 0.25, "dif": (150, 165, 190), "dif_i": 0.80,
               "spe": (255, 255, 255), "spe_i": 0.50, "shin": 50.0, "emi": (0, 0, 0), "emi_i": 0.0}


class MaterialTask2Plugin(Base3DPlugin):
    """任务2插件：多模型加载 + 任务1光照与材质 + 真实材质"""

    # YAML 配置唯一标识
    plugin_cls_name = "material_task2"
    plugin_name = "material_task2"
    plugin_desc = "任务2：多模型加载 + 光照材质 + 真实材质"

    def __init__(self, viewer_ctx):
        super().__init__(viewer_ctx)
        # ---- 模型注册表（多模型同屏的核心） ----
        # 每条 = {"path","actor","polydata","visible","mat","extent"}
        self.models = []
        self.current = -1                 # 当前选中的模型下标
        self.axes = None                  # 单根坐标轴（避免每个模型各加一根）
        self.scene_light = None           # 场景光源

        # ---- 控件引用 ----
        self.model_list = None
        self._updating_list = False
        self.chk_autolayout = None
        self.lbl_current = None

        # 自定义材质控件
        self.sb_amb = []                  # [r,g,b,强度]
        self.sb_dif = []
        self.sb_spe = []
        self.sb_shin = None
        self.sb_emi = []

        # 灯光控件
        self.sb_light_pos = []            # [x,y,z]
        self.sb_light_rgb = []            # [r,g,b]
        self.sb_light_int = None
        self.chk_light_on = None

        # 初始光源参数（默认在右上前方）
        self.light_pos = (5.0, 6.0, 7.0)
        self.light_rgb = (255, 255, 255)
        self.light_int = 0.9
        self.light_on = True

        # ---- 鼠标点击选中模型（点击=选中，拖拽=旋转，两者同时可用） ----
        self.picker = None            # vtkPropPicker 拾取器
        self._press_pos = None        # 左键按下时的屏幕坐标（区分"点击/拖拽"）
        self._pick_threshold = 5.0    # 位移小于该像素视为"点击选中"，否则为旋转拖拽

    # ==================================================================
    # create_ui：构建右侧插件面板（三个页签）
    # ==================================================================
    def create_ui(self):
        self.plugin_panel = QFrame()
        self.plugin_panel.setFrameShape(QFrame.StyledPanel)
        outer = QVBoxLayout(self.plugin_panel)
        outer.setSpacing(6)
        outer.setContentsMargins(8, 8, 8, 8)

        title = QLabel("任务2：光照与材质（多模型）")
        title.setStyleSheet("font-weight:bold; font-size:13px; color:#1a5fb4;")
        outer.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_model_tab(), "模型与预设")
        tabs.addTab(self._build_custom_tab(), "自定义材质")
        tabs.addTab(self._build_light_tab(), "灯光控制")
        outer.addWidget(tabs, stretch=1)

        # 创建场景光源 + 单根坐标轴
        self.create_light()
        self.create_axes()

        # 挂"鼠标点击选中"观察者（点击=选中，拖拽=旋转，两者同时可用）
        self._setup_picking()
        return self.plugin_panel

    # ---------- 页签1：模型管理与材质预设 ----------
    def _build_model_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(6)
        lay.setContentsMargins(6, 6, 6, 6)

        lay.addWidget(QLabel("模型列表（点击左侧OBJ加载，可加载多个）："))

        self.model_list = QListWidget()
        self.model_list.setMaximumHeight(130)
        self.model_list.currentRowChanged.connect(self.on_current_changed)
        self.model_list.itemChanged.connect(self.on_list_item_changed)
        lay.addWidget(self.model_list)

        # 模型操作按钮行
        row = QHBoxLayout()
        self.chk_autolayout = QCheckBox("自动平铺")
        self.chk_autolayout.setChecked(True)
        self.chk_autolayout.stateChanged.connect(self.on_autolayout_toggle)
        btn_hide = QPushButton("显/隐")
        btn_del = QPushButton("删除")
        btn_clear = QPushButton("清空")
        btn_hide.clicked.connect(self.on_toggle_visibility)
        btn_del.clicked.connect(self.on_delete_selected)
        btn_clear.clicked.connect(self.on_clear_all)
        row.addWidget(self.chk_autolayout)
        row.addWidget(btn_hide)
        row.addWidget(btn_del)
        row.addWidget(btn_clear)
        lay.addLayout(row)

        self.lbl_current = QLabel("当前：未加载模型")
        self.lbl_current.setStyleSheet("color:#666;")
        lay.addWidget(self.lbl_current)

        # ---------- 一键分配不同真实材质（进阶要求：不同模型表现真实材质） ----------
        btn_distinct = QPushButton("一键分配不同真实材质（金属/木质/塑料…）")
        btn_distinct.setToolTip("把加载的所有模型按顺序自动分配不同的真实材质："
                                "第1个→金属金、第2个→木质、第3个→塑料…\n"
                                "一次性让每个模型表现各自的真实材质。")
        btn_distinct.setStyleSheet(
            "font-weight:bold; background:#2e7d32; color:#fff; padding:6px;")
        btn_distinct.clicked.connect(self.assign_distinct_materials)
        lay.addWidget(btn_distinct)

        # ---------- 材质预设（任务1 + 真实材质） ----------
        lay.addWidget(QLabel("材质预设（点击应用到选中模型）："))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(6)
        grid.setContentsMargins(2, 2, 2, 2)

        def add_group(grid, row, title, presets):
            lab = QLabel(title)
            lab.setStyleSheet("font-weight:bold; color:#2e7d32;")
            grid.addWidget(lab, row, 0, 1, 2)
            row += 1
            for i, p in enumerate(presets):
                r = row + i // 2
                c = i % 2
                btn = QPushButton(p["name"])
                btn.setToolTip(self._preset_desc(p))
                btn.setStyleSheet("text-align:left; padding:3px;")
                btn.clicked.connect(lambda ch, m=p: self.apply_preset(m))
                grid.addWidget(btn, r, c)

        r = 0
        add_group(grid, r, "— 任务1 样式（12球材质矩阵） —", TASK1_PRESETS)
        r += (len(TASK1_PRESETS) + 1) // 2 + 1
        add_group(grid, r, "— 真实材质（进阶：金属/木质等） —", REAL_PRESETS)

        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(container)
        lay.addWidget(scroll, stretch=1)
        return page

    # ---------- 页签2：自定义材质 ----------
    def _make_spin(self, lo, hi, step, dec, val):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(dec)
        sp.setValue(val)
        return sp

    def _add_mat_row(self, lay, label, spin_list, shin_spin=None):
        """一行 = 颜色名 + R G B 强度，可选追加高光系数"""
        row = QHBoxLayout()
        if label:
            row.addWidget(QLabel(label))
        for _ in range(4):          # R,G,B,强度
            sp = self._make_spin(0, 255, 1, 0, 0) if len(spin_list) < 3 else \
                self._make_spin(0.0, 2.0, 0.05, 2, 0.0)
            spin_list.append(sp)
            sp.setMaximumWidth(64)
            row.addWidget(sp)
        if shin_spin is not None:
            row.addWidget(QLabel("高光"))
            shin_spin.setMaximumWidth(64)
            row.addWidget(shin_spin)
        lay.addLayout(row)

    def _build_custom_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(8)
        lay.setContentsMargins(6, 6, 6, 6)

        self.sb_amb = []
        self.sb_dif = []
        self.sb_spe = []
        self.sb_emi = []
        self.sb_shin = self._make_spin(1, 256, 5, 0, 50)

        lay.addWidget(QLabel("环境光 ambient  [R G B] 强度:"))
        self._add_mat_row(lay, "", self.sb_amb)
        lay.addWidget(QLabel("漫反射 diffuse  [R G B] 强度:"))
        self._add_mat_row(lay, "", self.sb_dif)
        lay.addWidget(QLabel("镜面高光 specular  [R G B] 强度:"))
        self._add_mat_row(lay, "", self.sb_spe, self.sb_shin)
        lay.addWidget(QLabel("自发光 emission  [R G B] 强度:"))
        self._add_mat_row(lay, "", self.sb_emi)

        # 从当前模型读取参数到控件
        btn_read = QPushButton("读取当前材质")
        btn_read.clicked.connect(self.read_current_to_controls)
        lay.addWidget(btn_read)

        btn_apply = QPushButton("应用到选中模型")
        btn_apply.setStyleSheet("font-weight:bold;")
        btn_apply.clicked.connect(self.apply_custom)
        lay.addWidget(btn_apply)

        note = QLabel("说明：自发光通过注入 fragment shader 实现，\n"
                      "环境光/漫反射/镜面/高光为经典 Blinn-Phong。")
        note.setStyleSheet("color:#999; font-size:11px;")
        lay.addWidget(note)
        lay.addStretch(1)
        return page

    # ---------- 页签3：灯光控制 ----------
    def _build_light_tab(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(8)
        lay.setContentsMargins(6, 6, 6, 6)

        self.chk_light_on = QCheckBox("启用光源")
        self.chk_light_on.setChecked(self.light_on)
        self.chk_light_on.stateChanged.connect(self.on_light_toggle)
        lay.addWidget(self.chk_light_on)

        lay.addWidget(QLabel("光源位置 X Y Z："))
        self.sb_light_pos = []
        row = QHBoxLayout()
        for v in self.light_pos:
            sp = self._make_spin(-30, 30, 0.5, 1, v)
            sp.setMaximumWidth(70)
            self.sb_light_pos.append(sp)
            row.addWidget(sp)
        lay.addLayout(row)

        lay.addWidget(QLabel("光源颜色 R G B (0~255)："))
        self.sb_light_rgb = []
        row = QHBoxLayout()
        for v in self.light_rgb:
            sp = self._make_spin(0, 255, 1, 0, v)
            sp.setMaximumWidth(70)
            self.sb_light_rgb.append(sp)
            row.addWidget(sp)
        lay.addLayout(row)

        lay.addWidget(QLabel("光源强度 (0~2)："))
        self.sb_light_int = self._make_spin(0.0, 2.0, 0.05, 2, self.light_int)
        lay.addWidget(self.sb_light_int)

        btn = QPushButton("应用灯光")
        btn.setStyleSheet("font-weight:bold;")
        btn.clicked.connect(self.apply_light)
        lay.addWidget(btn)

        note = QLabel("说明：对应任务1\"移动灯光位置 / 调节灯光颜色\"，\n"
                      "这里用控件调节（WASD/QRGB 改为滑块+数值）。")
        note.setStyleSheet("color:#999; font-size:11px;")
        lay.addWidget(note)
        lay.addStretch(1)
        return page

    # ==================================================================
    # 场景光源
    # ==================================================================
    def create_light(self):
        self.scene_light = vtk.vtkLight()
        self.scene_light.SetLightTypeToSceneLight()   # 场景光：固定在世界坐标
        self.scene_light.SetPosition(*self.light_pos)
        self.scene_light.SetFocalPoint(0, 0, 0)
        self.scene_light.SetColor(*_norm(self.light_rgb))
        self.scene_light.SetIntensity(self.light_int)
        self.scene_light.SetSwitch(self.light_on)
        self.ctx.vtk_renderer.AddLight(self.scene_light)

    def apply_light(self):
        """读取灯光控件 → 更新光源"""
        self.light_pos = tuple(s.value() for s in self.sb_light_pos)
        self.light_rgb = tuple(int(s.value()) for s in self.sb_light_rgb)
        self.light_int = self.sb_light_int.value()
        self.light_on = self.chk_light_on.isChecked()
        self.scene_light.SetPosition(*self.light_pos)
        self.scene_light.SetColor(*_norm(self.light_rgb))
        self.scene_light.SetIntensity(self.light_int)
        self.scene_light.SetSwitch(self.light_on)
        self._render()
        self.ctx.info_display.append(
            f"灯光更新：位置{tuple(round(x,1) for x in self.light_pos)} "
            f"RGB{self.light_rgb} 强度{self.light_int:.2f} 开关{'开' if self.light_on else '关'}")

    def on_light_toggle(self):
        self.apply_light()

    # ==================================================================
    # 坐标轴（整个场景只保留一根，避免每模型一根）
    # ==================================================================
    def create_axes(self):
        self.axes = vtk.vtkAxesActor()
        self.axes.SetTotalLength(2.5, 2.5, 2.5)
        x_c = self.axes.GetXAxisCaptionActor2D()
        y_c = self.axes.GetYAxisCaptionActor2D()
        z_c = self.axes.GetZAxisCaptionActor2D()
        x_c.GetCaptionTextProperty().SetColor(1, 0, 0)
        y_c.GetCaptionTextProperty().SetColor(0, 1, 0)
        z_c.GetCaptionTextProperty().SetColor(0, 0, 1)
        for cap in (x_c, y_c, z_c):
            cap.GetCaptionTextProperty().SetFontSize(10)

    # ==================================================================
    # 渲染辅助
    # ==================================================================
    def _render(self):
        self.ctx.vtk_widget.GetRenderWindow().Render()

    # ==================================================================
    # 鼠标点击选中：点击=选中模型，拖拽=旋转视角（两者同时可用）
    # ==================================================================
    def _setup_picking(self):
        """给交互器挂按下/松开观察者：位移小=点击选中，位移大=拖拽旋转(默认样式处理)"""
        self.picker = vtk.vtkPropPicker()
        self.iren = self.ctx.vtk_widget   # QVTKRenderWindowInteractor 即 vtkRenderWindowInteractor
        self.iren.AddObserver("LeftButtonPressEvent", self._on_pick_press)
        self.iren.AddObserver("LeftButtonReleaseEvent", self._on_pick_release)

    def _on_pick_press(self, obj, event):
        self._press_pos = obj.GetEventPosition()

    def _on_pick_release(self, obj, event):
        if self._press_pos is None:
            return
        x, y = obj.GetEventPosition()
        dx = x - self._press_pos[0]
        dy = y - self._press_pos[1]
        self._press_pos = None
        # 位移超过阈值 = 拖拽旋转（由默认 Trackball 样式处理），不拾取；
        # 只有真正"点击"（位移很小）才选中模型
        if (dx * dx + dy * dy) > self._pick_threshold * self._pick_threshold:
            return
        self._pick_model(x, y)

    def _pick_model(self, x, y):
        """在屏幕坐标(x,y)处拾取，若命中已加载模型则设为当前选中"""
        if not self.models:
            return
        self.picker.Pick(x, y, 0, self.ctx.vtk_renderer)
        picked = self.picker.GetViewProp()
        if picked is None:
            return
        # 用底层 C++ 地址比较命中 actor：VTK 的 Python 包装对象用 `is` 可能匹配不上
        # （同一 C++ 对象每次可能生成不同的 Python 包装），按地址比对才能保证命中
        picked_addr = picked.GetAddressAsString("vtkActor")
        for i, m in enumerate(self.models):
            if m["actor"].GetAddressAsString("vtkActor") == picked_addr:
                self._set_current(i)
                return
        # 点击到空白/坐标轴：不做改变，保持当前选中

    def _set_current(self, idx):
        """把第 idx 个模型设为当前选中（高亮描边 + 同步右侧列表与标签）"""
        self.current = idx
        if self.model_list:
            self.model_list.setCurrentRow(idx)   # 触发 on_current_changed → 同步标签/自定义面板
        self._refresh_current_label()
        self._update_selection_highlight()
        self._render()
        self.ctx.info_display.append(
            f"点击选中模型：{os.path.basename(self.models[idx]['path'])}  "
            f"[{self.models[idx]['mat']['name']}]")

    def _update_selection_highlight(self):
        """当前选中模型加金黄色描边高亮，其余关闭描边（不动表面材质）"""
        for i, m in enumerate(self.models):
            prop = m["actor"].GetProperty()
            if i == self.current:
                prop.SetEdgeVisibility(1)
                prop.SetEdgeColor(1.0, 0.84, 0.0)   # 金黄描边
                prop.SetLineWidth(2)
            else:
                prop.SetEdgeVisibility(0)

    # ==================================================================
    # 生命周期钩子：模型加载完成
    # ==================================================================
    def on_model_loaded(self, obj_path, actor, polydata):
        # 关闭顶点色（内核给模型设了纯白顶点色，会让材质颜色失效）
        mapper = actor.GetMapper()
        if mapper:
            mapper.ScalarVisibilityOff()

        # 计算该模型原始包围盒范围（用于自动平铺间距）
        b = polydata.GetBounds()
        extent = max((b[1] - b[0]), (b[3] - b[2]), (b[5] - b[4]), 1e-3)

        # 若同一路径已加载，替换其 actor（保留顺序、材质）
        for i, m in enumerate(self.models):
            if m["path"] == obj_path:
                self.models[i]["actor"] = actor
                self.models[i]["polydata"] = polydata
                self.models[i]["extent"] = extent
                self._apply_mat_to_actor(actor, self.models[i]["mat"])
                self.current = i
                self._rebuild_scene()
                self._rebuild_list()
                return

        # 否则新增一个模型
        mat = dict(DEFAULT_MAT)
        self.models.append({"path": obj_path, "actor": actor, "polydata": polydata,
                            "visible": True, "mat": mat, "extent": extent})
        self._apply_mat_to_actor(actor, mat)
        self.current = len(self.models) - 1
        self._rebuild_scene()
        self._rebuild_list()
        self.ctx.info_display.append(f"已加载模型：{os.path.basename(obj_path)}"
                                     f"（当前共 {len(self.models)} 个）")

    # ==================================================================
    # 场景重建：把注册表里所有可见模型放回渲染器
    # ==================================================================
    def _rebuild_scene(self):
        renderer = self.ctx.vtk_renderer
        renderer.RemoveAllViewProps()
        for m in self.models:
            if m["visible"]:
                renderer.AddActor(m["actor"])
        if self.axes:
            renderer.AddActor(self.axes)
        if self.chk_autolayout and self.chk_autolayout.isChecked():
            self._place_models()
        else:
            self._reset_model_positions()
        self._update_selection_highlight()
        renderer.ResetCamera()
        self._render()

    # ---------- 自动平铺：先归一化到统一尺寸，再按网格排布 ----------
    # 目标：所有模型"最长边≈NORMAL_SIZE"，间距由其决定，模型不重叠且大小可比
    NORMAL_SIZE = 2.0
    NORMAL_SPACING = 1.7
    LAYOUT_COLS = 4

    def _place_models(self):
        if not self.models:
            return
        sx = self.NORMAL_SIZE * self.NORMAL_SPACING
        for i, m in enumerate(self.models):
            r = i // self.LAYOUT_COLS
            c = i % self.LAYOUT_COLS
            # 归一化缩放：最长边缩放到 NORMAL_SIZE
            scale = self.NORMAL_SIZE / m["extent"]
            actor = m["actor"]
            actor.SetScale(scale, scale, scale)
            # 取模型局部中心，把中心对齐到网格点（(c+1) 留出原点给坐标轴）
            b = m["polydata"].GetBounds()
            cx = (b[0] + b[1]) / 2.0
            cy = (b[2] + b[3]) / 2.0
            cz = (b[4] + b[5]) / 2.0
            actor.SetPosition((c + 1) * sx - cx * scale,
                              0.0 - cy * scale,
                              (r + 1) * sx - cz * scale)

    def _reset_model_positions(self):
        for m in self.models:
            m["actor"].SetScale(1, 1, 1)
            m["actor"].SetPosition(0, 0, 0)

    def on_autolayout_toggle(self):
        self._rebuild_scene()

    # ==================================================================
    # 模型列表 UI
    # ==================================================================
    def _rebuild_list(self):
        self._updating_list = True
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for m in self.models:
            item = QListWidgetItem(os.path.basename(m["path"]))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if m["visible"] else Qt.Unchecked)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        self._updating_list = False
        if 0 <= self.current < len(self.models):
            self.model_list.setCurrentRow(self.current)
        self._refresh_current_label()

    def on_current_changed(self, row):
        self.current = row
        self._refresh_current_label()
        # 选中模型时，自动把它的材质同步到自定义面板，便于微调
        if self.sb_amb and 0 <= row < len(self.models):
            self._sync_controls(self.models[row]["mat"])
        # 列表选中时同步更新 3D 视窗里的选中高亮
        self._update_selection_highlight()
        self._render()

    def on_list_item_changed(self, item):
        if self._updating_list:
            return
        row = self.model_list.row(item)
        if 0 <= row < len(self.models):
            self.models[row]["visible"] = (item.checkState() == Qt.Checked)
            self._rebuild_scene()

    def _refresh_current_label(self):
        if 0 <= self.current < len(self.models):
            m = self.models[self.current]
            self.lbl_current.setText(f"当前：{os.path.basename(m['path'])}  "
                                     f"[{m['mat']['name']}]")
        else:
            self.lbl_current.setText("当前：未加载模型")

    # ---------- 模型操作 ----------
    def on_toggle_visibility(self):
        if 0 <= self.current < len(self.models):
            self.models[self.current]["visible"] = not self.models[self.current]["visible"]
            self._rebuild_list()
            self._rebuild_scene()

    def on_delete_selected(self):
        if 0 <= self.current < len(self.models):
            path = self.models[self.current]["path"]
            self.models.pop(self.current)
            self.current = min(self.current, len(self.models) - 1)
            self._rebuild_list()
            self._rebuild_scene()
            self.ctx.info_display.append(f"已删除模型：{os.path.basename(path)}")

    def on_clear_all(self):
        if not self.models:
            return
        self.models.clear()
        self.current = -1
        self._rebuild_list()
        self._rebuild_scene()
        self.ctx.info_display.append("已清空全部模型")

    # ==================================================================
    # 材质应用
    # ==================================================================
    def _preset_desc(self, p):
        return (f"ambient:{p['amb_i']} {p['amb']}\n"
                f"diffuse:{p['dif_i']} {p['dif']}\n"
                f"specular:{p['spe_i']} {p['spe']} shin:{p['shin']}\n"
                f"emission:{p['emi_i']} {p['emi']}")

    def apply_preset(self, preset):
        if not (0 <= self.current < len(self.models)):
            self.ctx.info_display.append("提示：请先在左侧加载并选中一个模型")
            return
        m = self.models[self.current]
        m["mat"] = dict(preset)
        self._apply_mat_to_actor(m["actor"], m["mat"])
        self._refresh_current_label()
        self.ctx.info_display.append(
            f"已应用材质「{preset['name']}」到 {os.path.basename(m['path'])}")

    def assign_distinct_materials(self):
        """一键给所有模型按顺序分配不同的真实材质，让每个模型表现各自的真实材质。

        实现"进阶要求：不同模型表现出其真实的材质（金属、木质等）"——
        加载多个模型后点击该按钮，模型0→金属金、模型1→木质、模型2→塑料……
        每个模型拿到不同的 REAL_PRESETS，同屏即可直观对比不同真实材质。
        """
        if not self.models:
            self.ctx.info_display.append("提示：请先在左侧加载模型（至少1个）")
            return
        n = len(REAL_PRESETS)
        for i, m in enumerate(self.models):
            preset = REAL_PRESETS[i % n]       # 按顺序取不同真实材质
            m["mat"] = dict(preset)
            self._apply_mat_to_actor(m["actor"], m["mat"])
        self._refresh_current_label()
        summary = " / ".join(
            f"{os.path.basename(m['path'])}→{m['mat']['name']}" for m in self.models)
        self.ctx.info_display.append(
            f"已为 {len(self.models)} 个模型分配不同的真实材质：{summary}")

    def apply_custom(self):
        if not (0 <= self.current < len(self.models)):
            self.ctx.info_display.append("提示：请先在左侧加载并选中一个模型")
            return
        m = self.models[self.current]
        m["mat"] = {
            "name": "自定义",
            "amb": (int(self.sb_amb[0].value()), int(self.sb_amb[1].value()), int(self.sb_amb[2].value())),
            "amb_i": self.sb_amb[3].value(),
            "dif": (int(self.sb_dif[0].value()), int(self.sb_dif[1].value()), int(self.sb_dif[2].value())),
            "dif_i": self.sb_dif[3].value(),
            "spe": (int(self.sb_spe[0].value()), int(self.sb_spe[1].value()), int(self.sb_spe[2].value())),
            "spe_i": self.sb_spe[3].value(),
            "shin": self.sb_shin.value(),
            "emi": (int(self.sb_emi[0].value()), int(self.sb_emi[1].value()), int(self.sb_emi[2].value())),
            "emi_i": self.sb_emi[3].value(),
        }
        self._apply_mat_to_actor(m["actor"], m["mat"])
        self._refresh_current_label()
        self.ctx.info_display.append(f"已应用自定义材质到 {os.path.basename(m['path'])}")

    def _sync_controls(self, mat):
        """把一份材质写进自定义控件（不产生日志）"""
        for key, spins in (("amb", self.sb_amb), ("dif", self.sb_dif),
                           ("spe", self.sb_spe), ("emi", self.sb_emi)):
            color = mat[key]
            for k in range(3):
                spins[k].setValue(color[k])
            spins[3].setValue(mat[key + "_i"])
        self.sb_shin.setValue(mat["shin"])

    def read_current_to_controls(self):
        """把当前模型的材质读回自定义控件，便于微调"""
        if not (0 <= self.current < len(self.models)):
            self.ctx.info_display.append("提示：请先加载并选中一个模型")
            return
        self._sync_controls(self.models[self.current]["mat"])
        self.ctx.info_display.append("已读取当前模型材质到自定义面板")

    # ---------- 核心：把材质写到 actor 的 vtkProperty + shader ----------
    def _apply_mat_to_actor(self, actor, mat):
        prop = actor.GetProperty()
        prop.SetInterpolationToPhong()               # 镜面高光需要 Phong 插值
        # 环境光
        prop.SetAmbient(mat["amb_i"])
        prop.SetAmbientColor(*_norm(mat["amb"]))
        # 漫反射
        prop.SetDiffuse(mat["dif_i"])
        prop.SetDiffuseColor(*_norm(mat["dif"]))
        # 镜面 + 高光系数
        prop.SetSpecular(mat["spe_i"])
        prop.SetSpecularColor(*_norm(mat["spe"]))
        prop.SetSpecularPower(mat["shin"])
        # 自发光：注入 fragment shader
        self._apply_emission(actor, mat["emi"], mat["emi_i"])
        mapper = actor.GetMapper()
        if mapper:
            mapper.ScalarVisibilityOff()
        self._render()

    def _apply_emission(self, actor, rgb, intensity):
        """通过自定义 fragment shader 实现自发光（VTK 经典材质无原生 emission）"""
        shader = actor.GetShaderProperty()
        shader.ClearAllFragmentShaderReplacements()
        if intensity <= 0.0 or (rgb[0] == 0 and rgb[1] == 0 and rgb[2] == 0):
            return  # 无自发光
        er = rgb[0] / 255.0 * intensity
        eg = rgb[1] / 255.0 * intensity
        eb = rgb[2] / 255.0 * intensity
        glsl = ("//VTK::Light::Impl\n"
                f"vec3 emiss = vec3({er:.4f}, {eg:.4f}, {eb:.4f});\n"
                "fragOutput0 = vec4(fragOutput0.rgb + emiss, fragOutput0.a);\n")
        shader.AddShaderReplacement(vtk.vtkShader.Fragment, "//VTK::Light::Impl",
                                    True, glsl, True)

    # ==================================================================
    # 其它钩子（本插件无特殊资源需释放）
    # ==================================================================
    def on_window_resize(self):
        pass

    def on_destroy(self):
        pass
