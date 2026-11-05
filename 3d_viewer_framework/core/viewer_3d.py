'''
框架内核：基础3D查看器底座，仅保留纯基础功能，所有扩展通过插件实现
作者：蔡洪斌
2026-06-24
'''
import sys
import os
import vtk
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
                             QFileDialog, QPushButton, QTextEdit, QTreeView, QFileSystemModel, QSplitter,
                             QMenuBar, QMenu, QAction, QFrame)
from PyQt5.QtCore import QDir, Qt

class ViewerContext:
    """全局上下文，插件共享状态，避免各自重复存储变量"""
    def __init__(self):
        self.main_window = None
        self.vtk_renderer = None
        self.vtk_widget = None
        self.info_display = None
        self.right_extension_panel = None  # 插件面板挂载容器
        self.current_obj_path = None
        self.current_actor = None
        self.current_polydata = None
        self.plugins = []  # 已加载插件实例列表

class VTKViewerCore(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Model Viewer Framework")
        self.setGeometry(100, 100, 1600, 800)

        # 全局上下文
        self.ctx = ViewerContext()
        self.ctx.main_window = self

        # 插件管理器
        self.plugin_instances = []

        self.create_menu()
        self.build_base_layout()
        self.init_vtk()

    def register_plugin(self, plugin_cls):
        """外部注册插件，入口main.py调用"""
        plugin = plugin_cls(self.ctx)
        self.plugin_instances.append(plugin)
        self.ctx.plugins.append(plugin)
        # 创建插件UI并挂载到右侧扩展面板
        panel = plugin.create_ui()
        if panel:
            self.ctx.right_extension_layout.addWidget(panel)

    def build_base_layout(self):
        """基础布局：文件树 | VTK窗口 | 右侧插件垂直容器"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_v_layout = QVBoxLayout(central_widget)
        main_v_layout.setSpacing(4)

        top_h_splitter = QSplitter(Qt.Horizontal)
        main_v_layout.addWidget(top_h_splitter, stretch=8)

        # 底部信息栏
        self.ctx.info_display = QTextEdit()
        self.ctx.info_display.setReadOnly(True)
        self.ctx.info_display.setMaximumHeight(160)
        main_v_layout.addWidget(self.ctx.info_display, stretch=1)

        # 左侧文件树
        self.tree_view = QTreeView()
        self.file_model = QFileSystemModel()
        self.file_model.setFilter(QDir.NoDotAndDotDot | QDir.AllDirs | QDir.Files)
        self.file_model.setNameFilters(["*.obj"])
        self.file_model.setNameFilterDisables(False)
        self.tree_view.setModel(self.file_model)
        self.tree_view.clicked.connect(self.on_tree_item_clicked)
        for col in range(1, self.file_model.columnCount()):
            self.tree_view.hideColumn(col)
        self.file_model.setRootPath("")
        self.tree_view.setRootIndex(self.file_model.index(""))
        top_h_splitter.addWidget(self.tree_view)

        # 中间VTK窗口
        self.ctx.vtk_widget = QVTKRenderWindowInteractor(self)
        self.ctx.vtk_renderer = vtk.vtkRenderer()
        self.ctx.vtk_widget.GetRenderWindow().AddRenderer(self.ctx.vtk_renderer)
        top_h_splitter.addWidget(self.ctx.vtk_widget)

        # 右侧：插件统一挂载容器
        right_container = QWidget()
        self.ctx.right_extension_layout = QVBoxLayout(right_container)
        self.ctx.right_extension_layout.setSpacing(8)
        self.ctx.right_extension_layout.setContentsMargins(0,0,0,0)
        self.ctx.right_extension_panel = right_container
        top_h_splitter.addWidget(right_container)

        top_h_splitter.setSizes([int(0.3*self.width()), int(0.5*self.width()), int(0.2*self.width())])
        top_h_splitter.setStretchFactor(1, 6)
        top_h_splitter.setStretchFactor(2, 4)

    def init_vtk(self):
        self.ctx.vtk_widget.Initialize()
        self.ctx.vtk_widget.Start()

    def create_menu(self):
        menubar = self.menuBar()
        file_menu = QMenu("File", self)
        open_folder_action = QAction("Open Folder", self)
        open_folder_action.triggered.connect(self.open_folder)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(open_folder_action)
        file_menu.addAction(exit_action)
        menubar.addMenu(file_menu)

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", "")
        if folder:
            self.file_model.setRootPath(folder)
            self.tree_view.setRootIndex(self.file_model.index(folder))

    def on_tree_item_clicked(self, index):
        file_path = self.file_model.filePath(index)
        if os.path.isfile(file_path) and file_path.endswith(".obj"):
            self.load_model(file_path)

    def load_model(self, file_name):
        """基础OBJ加载逻辑，纯白模型，加载完成分发插件钩子"""
        vtk.vtkObject.GlobalWarningDisplayOff()
        reader = vtk.vtkOBJReader()
        reader.SetFileName(file_name)
        reader.Update()
        polydata = reader.GetOutput()
        num_points = polydata.GetPoints().GetNumberOfPoints()
        num_faces = polydata.GetNumberOfCells()

        # 纯白顶点色
        color_array = vtk.vtkUnsignedCharArray()
        color_array.SetNumberOfComponents(3)
        color_array.SetName("VertexColors")
        for i in range(num_points):
            color_array.InsertNextTuple3(255,255,255)
        polydata.GetPointData().SetScalars(color_array)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        # 更新全局上下文
        self.ctx.current_obj_path = file_name
        self.ctx.current_actor = actor
        self.ctx.current_polydata = polydata

        self.ctx.vtk_renderer.RemoveAllViewProps()
        self.ctx.vtk_renderer.AddActor(actor)
        self.add_axes(polydata)
        self.ctx.vtk_renderer.ResetCamera()
        self.ctx.vtk_widget.GetRenderWindow().Render()

        self.update_info(file_name, num_points, num_faces)

        # 分发插件钩子：模型加载完成
        for plugin in self.plugin_instances:
            plugin.on_model_loaded(file_name, actor, polydata)
        return True

    def add_axes(self, polydata):
        """基础坐标轴，全局统一"""
        centroid = polydata.GetCenter()
        axes_actor = vtk.vtkAxesActor()
        axes_actor.SetTotalLength(15,15,15)
        x_c = axes_actor.GetXAxisCaptionActor2D()
        y_c = axes_actor.GetYAxisCaptionActor2D()
        z_c = axes_actor.GetZAxisCaptionActor2D()
        x_c.GetCaptionTextProperty().SetColor(1,0,0)
        y_c.GetCaptionTextProperty().SetColor(0,1,0)
        z_c.GetCaptionTextProperty().SetColor(0,0,1)
        x_c.GetCaptionTextProperty().SetFontSize(10)
        y_c.GetCaptionTextProperty().SetFontSize(10)
        z_c.GetCaptionTextProperty().SetFontSize(10)
        offset = 24
        x_c.SetAttachmentPoint(centroid[0]+offset, centroid[1], centroid[2])
        y_c.SetAttachmentPoint(centroid[0], centroid[1]+offset, centroid[2])
        z_c.SetAttachmentPoint(centroid[0], centroid[1], centroid[2]+offset)
        trans = vtk.vtkTransform()
        trans.Translate(centroid[0], centroid[1], centroid[2]+10)
        axes_actor.SetUserTransform(trans)
        self.ctx.vtk_renderer.AddActor(axes_actor)

    def update_info(self, obj_file, pts, faces):
        text = f"OBJ File: {obj_file}\nVertices: {pts}\nFaces: {faces}\n"
        self.ctx.info_display.setPlainText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 窗口缩放分发插件钩子
        for plugin in self.plugin_instances:
            plugin.on_window_resize()

    def closeEvent(self, event):
        # 程序关闭释放插件资源
        for plugin in self.plugin_instances:
            plugin.on_destroy()
        event.accept()