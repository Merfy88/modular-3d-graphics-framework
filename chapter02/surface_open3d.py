'''
    基于Open3D的表面重建程序
'''
import sys
import os
import time
import numpy as np
import open3d as o3d

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSpinBox, QDoubleSpinBox,
    QTextEdit, QGroupBox, QFormLayout, QMessageBox, QComboBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


# ============================================================
# 常量配置
# ============================================================
# 重建方法: "poisson" 或 "ball_pivot"
RECONSTRUCTION_METHOD = "ball_pivot"


# ============================================================
# 后台重建线程
# ============================================================
class ReconstructionWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(object, object)  # (mesh, pcd)
    error_signal = pyqtSignal(str)

    def __init__(self, file_path, method, depth, knn, density_quantile, ball_radii):
        super().__init__()
        self.file_path = file_path
        self.method = method                # "poisson" 或 "ball_pivot"
        self.depth = depth
        self.knn = knn
        self.density_quantile = density_quantile
        self.ball_radii = ball_radii        # 滚球法半径列表

    # --------------------------------------------------------
    def _emit(self, msg):
        """同时输出到日志区和控制台"""
        print(msg, flush=True)
        self.log_signal.emit(msg)

    # --------------------------------------------------------
    def _load_point_cloud(self):
        """根据扩展名加载点云，统一返回 Open3D PointCloud"""
        ext = os.path.splitext(self.file_path)[1].lower()

        if ext == ".npy":
            self._emit(f"[1/4] 加载 .npy 点云: {os.path.basename(self.file_path)}")
            points = np.load(self.file_path)
            self._emit(f"      点云形状: {points.shape}, 数据类型: {points.dtype}")
            if points.shape[0] == 3 and points.shape[1] != 3:
                points = points.T
                self._emit(f"      已转置为: {points.shape}")
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
            return pcd

        if ext in (".ply", ".pcd"):
            self._emit(f"[1/4] 加载 {ext} 点云: {os.path.basename(self.file_path)}")
            pcd = o3d.io.read_point_cloud(self.file_path)
            if len(pcd.points) == 0:
                raise ValueError(f"点云为空或读取失败: {self.file_path}")
            self._emit(f"      点云信息: {pcd}")
            return pcd

        self._emit(f"[1/4] 尝试让 Open3D 加载: {self.file_path}")
        pcd = o3d.io.read_point_cloud(self.file_path)
        if len(pcd.points) == 0:
            raise ValueError(f"不支持或无法解析的文件格式: {ext}")
        return pcd

    # --------------------------------------------------------
    def _reconstruct_poisson(self, pcd):
        """Poisson 表面重建"""
        t0 = time.time()
        self._emit(f"[3/4] Poisson 表面重建 (depth={self.depth})...")
        self._emit("      (这一步通常最耗时，请耐心等待...)")
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=self.depth
        )
        self._emit(f"      Poisson 重建完成，耗时: {time.time() - t0:.3f} 秒")
        self._emit(
            f"      原始网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面"
        )

        # 密度裁剪
        t0 = time.time()
        self._emit(f"[4/4] 按密度分位数裁剪 (quantile={self.density_quantile})...")
        densities = np.asarray(densities)
        vertices_to_remove = densities < np.quantile(densities, self.density_quantile)
        mesh.remove_vertices_by_mask(vertices_to_remove)
        mesh.remove_unreferenced_vertices()
        self._emit(f"      裁剪完成，耗时: {time.time() - t0:.3f} 秒")

        return mesh

    # --------------------------------------------------------
    def _reconstruct_ball_pivot(self, pcd):
        """滚球法（Ball Pivoting）表面重建"""
        t0 = time.time()
        self._emit(f"[3/4] 滚球法表面重建 (radii={self.ball_radii})...")
        self._emit("      (这一步可能较耗时，请耐心等待...)")

        # 若点云范围未知，建议根据点云尺度自适应设置半径
        # 这里直接使用传入的半径列表
        radii = o3d.utility.DoubleVector(self.ball_radii)

        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, radii
        )
        self._emit(f"      滚球法重建完成，耗时: {time.time() - t0:.3f} 秒")
        self._emit(
            f"      原始网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面"
        )

        # 滚球法无需密度裁剪，直接清理未引用顶点
        t0 = time.time()
        self._emit("[4/4] 清理未引用顶点...")
        mesh.remove_unreferenced_vertices()
        self._emit(f"      清理完成，耗时: {time.time() - t0:.3f} 秒")

        return mesh

    # --------------------------------------------------------
    def run(self):
        try:
            t_total_start = time.time()
            self._emit("=" * 60)
            self._emit(f"🚀 开始重建任务: {os.path.basename(self.file_path)}")
            self._emit(f"   方法: {self.method}")
            if self.method == "poisson":
                self._emit(f"   参数: depth={self.depth}, knn={self.knn}, "
                           f"quantile={self.density_quantile}")
            else:
                self._emit(f"   参数: knn={self.knn}, radii={self.ball_radii}")
            self._emit("=" * 60)

            # ---------- 1. 加载点云 ----------
            t0 = time.time()
            pcd = self._load_point_cloud()
            n_points = len(pcd.points)
            self._emit(f"⏱ 加载点云耗时: {time.time() - t0:.3f} 秒 "
                       f"(共 {n_points} 个点)")

            # ---------- 2. 法线估计 ----------
            t0 = time.time()
            if pcd.has_normals():
                self._emit("[2/4] 点云已包含法线，跳过估计")
            else:
                self._emit(f"[2/4] 估计法线 (knn={self.knn})...")
                pcd.estimate_normals(
                    search_param=o3d.geometry.KDTreeSearchParamKNN(knn=self.knn)
                )
                self._emit(f"      法线估计完成，耗时: {time.time() - t0:.3f} 秒")

            t0 = time.time()
            self._emit("      统一法线朝向...")
            pcd.orient_normals_consistent_tangent_plane(k=self.knn)
            self._emit(f"      法线定向完成，耗时: {time.time() - t0:.3f} 秒")

            # ---------- 3 & 4. 重建 + 后处理 ----------
            if self.method == "poisson":
                mesh = self._reconstruct_poisson(pcd)
            elif self.method == "ball_pivot":
                mesh = self._reconstruct_ball_pivot(pcd)
            else:
                raise ValueError(f"未知的重建方法: {self.method}")

            mesh.compute_vertex_normals()
            mesh.paint_uniform_color([0.75, 0.75, 0.75])
            self._emit(
                f"      最终网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面"
            )

            # ---------- 5. 保存 mesh（文件名带方法名） ----------
            t0 = time.time()
            obj_dir = os.path.join(os.getcwd(), "obj")
            os.makedirs(obj_dir, exist_ok=True)
            base_name = os.path.splitext(os.path.basename(self.file_path))[0]
            obj_path = os.path.join(obj_dir, f"{base_name}_{self.method}.obj")
            o3d.io.write_triangle_mesh(obj_path, mesh)
            self._emit(f"💾 网格已保存: {obj_path} (耗时: {time.time() - t0:.3f} 秒)")

            self._emit("=" * 60)
            self._emit(f"✅ 重建完成！总耗时: {time.time() - t_total_start:.3f} 秒")
            self._emit("=" * 60)

            self.finished_signal.emit(mesh, pcd)

        except Exception as e:
            import traceback
            err = f"❌ 错误: {str(e)}\n{traceback.format_exc()}"
            print(err, flush=True)
            self.error_signal.emit(err)


# ============================================================
# 简单加载点云的辅助函数（用于"查看点云"按钮）
# ============================================================
def load_point_cloud_direct(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".npy":
        points = np.load(file_path)
        if points.shape[0] == 3 and points.shape[1] != 3:
            points = points.T
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points.astype(np.float64))
        return pcd
    pcd = o3d.io.read_point_cloud(file_path)
    return pcd


# ============================================================
# 主窗口
# ============================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Open3D 表面重建演示")
        self.resize(1024, 768)

        self.file_path = None
        self.mesh = None
        self.pcd = None
        self.worker = None

        self._build_ui()
        self._apply_adaptive_size()
        self._update_param_state()

    # --------------------------------------------------------
    def _apply_adaptive_size(self):
        """根据屏幕可用区域自适应窗口大小"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()   # 不含任务栏
        w = int(avail.width() * 0.9)
        h = int(avail.height() * 0.9)
        # 保证不小于初始 size，也不超过可用区域
        w = max(w, 1024)
        h = max(h, 768)
        w = min(w, avail.width())
        h = min(h, avail.height())

        self.resize(w, h)
        # 居中
        self.move(
            avail.left() + (avail.width() - w) // 2,
            avail.top() + (avail.height() - h) // 2,
        )

    # --------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ----- 文件选择区 -----
        file_group = QGroupBox("1. 选择点云文件")
        file_layout = QHBoxLayout()
        self.file_label = QLabel("未选择文件")
        self.file_label.setStyleSheet("color: gray;")
        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self.on_browse)
        file_layout.addWidget(self.file_label, stretch=1)
        file_layout.addWidget(btn_browse)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # ----- 参数区 -----
        param_group = QGroupBox("2. 重建参数")
        form = QFormLayout()

        # 方法选择（默认使用常量 RECONSTRUCTION_METHOD）
        self.combo_method = QComboBox()
        self.combo_method.addItem("Poisson", "poisson")
        self.combo_method.addItem("Ball Pivoting (滚球法)", "ball_pivot")
        idx = self.combo_method.findData(RECONSTRUCTION_METHOD)
        if idx >= 0:
            self.combo_method.setCurrentIndex(idx)
        self.combo_method.currentIndexChanged.connect(self._update_param_state)
        form.addRow("重建方法:", self.combo_method)

        self.spin_depth = QSpinBox()
        self.spin_depth.setRange(6, 12)
        self.spin_depth.setValue(9)
        form.addRow("Poisson depth:", self.spin_depth)

        self.spin_knn = QSpinBox()
        self.spin_knn.setRange(5, 100)
        self.spin_knn.setValue(30)
        form.addRow("法线估计 KNN:", self.spin_knn)

        self.spin_quantile = QDoubleSpinBox()
        self.spin_quantile.setRange(0.0, 0.1)
        self.spin_quantile.setSingleStep(0.005)
        self.spin_quantile.setDecimals(3)
        self.spin_quantile.setValue(0.01)
        form.addRow("密度裁剪分位数:", self.spin_quantile)

        # 滚球法半径列表（逗号分隔）
        from PyQt5.QtWidgets import QLineEdit
        self.edit_ball_radii = QLineEdit("0.005, 0.01, 0.02, 0.04")
        form.addRow("滚球法半径列表:", self.edit_ball_radii)

        param_group.setLayout(form)
        main_layout.addWidget(param_group)

        # ----- 按钮区 -----
        btn_layout = QHBoxLayout()

        self.btn_show_pcd = QPushButton("👁 查看点云")
        self.btn_show_pcd.clicked.connect(self.on_show_pcd)
        self.btn_show_pcd.setEnabled(False)

        self.btn_show_mesh = QPushButton("👁 查看网格")
        self.btn_show_mesh.clicked.connect(self.on_show_mesh)
        self.btn_show_mesh.setEnabled(False)

        self.btn_reconstruct = QPushButton("🚀 开始重建")
        self.btn_reconstruct.clicked.connect(self.on_reconstruct)
        self.btn_reconstruct.setEnabled(False)

        btn_layout.addWidget(self.btn_show_pcd)
        btn_layout.addWidget(self.btn_show_mesh)
        btn_layout.addWidget(self.btn_reconstruct)
        main_layout.addLayout(btn_layout)

        # ----- 日志区 -----
        log_group = QGroupBox("3. 运行日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 24px;")
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group, stretch=1)

    # --------------------------------------------------------
    def _update_param_state(self):
        """根据所选方法启用/禁用相关参数控件"""
        method = self.combo_method.currentData()
        is_poisson = (method == "poisson")

        self.spin_depth.setEnabled(is_poisson)
        self.spin_quantile.setEnabled(is_poisson)
        self.edit_ball_radii.setEnabled(not is_poisson)
        # KNN 两种方法都需要
        self.spin_knn.setEnabled(True)

    # --------------------------------------------------------
    def log(self, msg):
        self.log_text.append(msg)

    # --------------------------------------------------------
    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择点云文件", "",
            "点云文件 (*.ply *.pcd *.npy);;PLY (*.ply);;PCD (*.pcd);;Numpy (*.npy);;所有文件 (*)"
        )
        if path:
            self.file_path = path
            self.mesh = None
            self.pcd = None
            self.file_label.setText(path)
            self.file_label.setStyleSheet("color: black;")
            # 选中文件后即可查看点云、开始重建；网格按钮重置为禁用
            self.btn_show_pcd.setEnabled(True)
            self.btn_reconstruct.setEnabled(True)
            self.btn_show_mesh.setEnabled(False)
            self.log(f"📂 已选择: {path}")

    # --------------------------------------------------------
    def _parse_ball_radii(self):
        """从输入框解析半径列表"""
        text = self.edit_ball_radii.text().strip()
        if not text:
            raise ValueError("滚球法半径列表不能为空")
        parts = [p.strip() for p in text.split(",") if p.strip()]
        try:
            radii = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"滚球法半径解析失败: {text}")
        if not radii:
            raise ValueError("滚球法半径列表为空")
        return radii

    # --------------------------------------------------------
    def on_reconstruct(self):
        if not self.file_path:
            QMessageBox.warning(self, "提示", "请先选择点云文件！")
            return

        method = self.combo_method.currentData()

        try:
            ball_radii = self._parse_ball_radii()
        except ValueError as e:
            QMessageBox.warning(self, "参数错误", str(e))
            return

        self.btn_reconstruct.setEnabled(False)
        self.btn_show_mesh.setEnabled(False)
        self.btn_show_pcd.setEnabled(False)
        self.log_text.clear()

        self.worker = ReconstructionWorker(
            self.file_path,
            method,
            self.spin_depth.value(),
            self.spin_knn.value(),
            self.spin_quantile.value(),
            ball_radii,
        )
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.error_signal.connect(self.on_error)
        self.worker.start()

    # --------------------------------------------------------
    def on_finished(self, mesh, pcd):
        self.mesh = mesh
        self.pcd = pcd
        # 重建结束：恢复三个按钮
        self.btn_reconstruct.setEnabled(True)
        self.btn_show_mesh.setEnabled(True)
        self.btn_show_pcd.setEnabled(True)

    # --------------------------------------------------------
    def on_error(self, msg):
        self.log(msg)
        # 出错后：重建按钮恢复，网格按钮保持禁用（没有有效 mesh）
        self.btn_reconstruct.setEnabled(True)
        self.btn_show_mesh.setEnabled(False)
        self.btn_show_pcd.setEnabled(True if self.file_path else False)
        QMessageBox.critical(self, "重建失败", msg)

    # --------------------------------------------------------
    def on_show_mesh(self):
        if self.mesh is None:
            QMessageBox.information(self, "提示", "请先完成重建再查看网格。")
            return
        self.log("👁 打开网格可视化窗口...")
        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=0.5, origin=[0, 0, 0]
        )
        o3d.visualization.draw_geometries(
            [self.mesh, coord],
            window_name="表面重建结果 (Mesh)",
            width=1024, height=768,
        )

    # --------------------------------------------------------
    def on_show_pcd(self):
        """查看点云：若内存中没有，就现场加载"""
        if self.pcd is None:
            if not self.file_path:
                QMessageBox.information(self, "提示", "请先选择点云文件。")
                return
            try:
                self.log(f"👁 加载点云用于预览: {os.path.basename(self.file_path)}")
                self.pcd = load_point_cloud_direct(self.file_path)
            except Exception as e:
                QMessageBox.critical(self, "加载失败", str(e))
                return

        self.log("👁 打开点云可视化窗口...")
        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=0.5, origin=[0, 0, 0]
        )
        o3d.visualization.draw_geometries(
            [self.pcd, coord],
            window_name="输入点云 (Point Cloud)",
            width=1024, height=768,
        )


# ============================================================
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()