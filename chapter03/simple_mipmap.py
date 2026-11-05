# -*- coding: utf-8 -*-
"""
Mipmap 效果对比演示（纯 PyQt 布局 + 两个独立 QOpenGLWidget）

左视图：GL_NEAREST + GL_NEAREST            （无 mipmap，远处摩尔纹、闪烁明显）
右视图：GL_LINEAR_MIPMAP_LINEAR + GL_LINEAR（三线性 mipmap，远处平滑）

操作：
  ← / →   绕 Y 轴旋转
  ↑ / ↓   前后移动
  Space   重置视角
"""

import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

from PyQt5.QtWidgets import (
    QApplication, QWidget, QOpenGLWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QSurfaceFormat, QFont

from OpenGL.GL import *
from OpenGL.GLU import *


# ---------------------------------------------------------------
# 全局状态（两个视图共享同一套旋转/位移）
# ---------------------------------------------------------------

angle = 0.0
z_position = 0.0

WIDTH = 128
HEIGHT = 128


# ---------------------------------------------------------------
# 生成彩色棋盘格纹理
# ---------------------------------------------------------------

def get_color_image():
    """构造四色棋盘格纹理，每色块 16x16 像素，RGB 顺序"""
    image = bytearray(WIDTH * HEIGHT * 3)
    for i in range(WIDTH):
        for j in range(HEIGHT):
            i_flag = (i & 0x10) == 0
            j_flag = (j & 0x10) == 0

            if i_flag and j_flag:
                r, g, b = 255, 40, 40       # 红
            elif i_flag and not j_flag:
                r, g, b = 40, 220, 40       # 绿
            elif (not i_flag) and j_flag:
                r, g, b = 40, 80, 255       # 蓝
            else:
                r, g, b = 255, 220, 40      # 黄

            index = (i * HEIGHT + j) * 3
            image[index + 0] = r
            image[index + 1] = g
            image[index + 2] = b
    return bytes(image)


# ---------------------------------------------------------------
# 单个 3D 视图
# ---------------------------------------------------------------

class FloorView(QOpenGLWidget):
    """
    一个独立的地板 3D 视图。
    每个实例有自己的纹理对象和过滤模式。
    """

    def __init__(self, min_filter, mag_filter, parent=None):
        super().__init__(parent)
        self.min_filter = min_filter
        self.mag_filter = mag_filter
        self.tex_id = 0
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- OpenGL 生命周期 ----------

    def initializeGL(self):
        glClearColor(0.05, 0.05, 0.08, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)

        # 生成纹理
        image = get_color_image()

        self.tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex_id)

        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, self.min_filter)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, self.mag_filter)

        glTexEnvf(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE)

        # 构建 mipmap 链（即使当前过滤模式不用 mipmap 也建好，保持纹理一致）
        gluBuild2DMipmaps(GL_TEXTURE_2D, 3, WIDTH, HEIGHT,
                          GL_RGB, GL_UNSIGNED_BYTE, image)

    def resizeGL(self, w, h):
        if h <= 0:
            h = 1
        glViewport(0, 0, w, h)

        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(60.5, w / h, 1.0, 200.0)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        glTranslatef(0.0, 0.0, z_position)
        glRotatef(angle, 0.0, 1.0, 0.0)

        glBindTexture(GL_TEXTURE_2D, self.tex_id)

        z = -80.0
        while z <= 0.0:
            glBegin(GL_QUADS)

            glTexCoord2f(0.0, 0.0)
            glVertex3f(-20.0, -10.0, z)

            glTexCoord2f(1.0, 0.0)
            glVertex3f(-20.0, -10.0, z + 10.0)

            glTexCoord2f(1.0, 1.0)
            glVertex3f(20.0, -10.0, z + 10.0)

            glTexCoord2f(0.0, 1.0)
            glVertex3f(20.0, -10.0, z)

            glEnd()
            z += 10.0

    # ---------- 键盘事件：交给主窗口统一处理 ----------

    def keyPressEvent(self, event):
        # 转发给父窗口，保证两个视图同步更新
        self.parent().keyPressEvent(event)


# ---------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------

class MipmapCompareWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Mipmap对比")
        self.resize(1000, 640)

        # ---- 两个 3D 视图 ----
        self.left_view = FloorView(GL_NEAREST, GL_NEAREST)
        self.right_view = FloorView(GL_LINEAR_MIPMAP_LINEAR, GL_LINEAR)

        for v in (self.left_view, self.right_view):
            v.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            v.setMinimumSize(200, 150)

        # ---- 每个视图下方的文字区 ----
        left_title = QLabel("无mipmap")
        left_title.setAlignment(Qt.AlignHCenter)
        f = QFont("Microsoft YaHei", 11)
        f.setBold(True)
        left_title.setFont(f)
        left_title.setStyleSheet("color: #ff7878;")

        left_info = QLabel("MIN_FILTER = GL_NEAREST\nMAG_FILTER = GL_NEAREST")
        left_info.setAlignment(Qt.AlignHCenter)
        left_info.setFont(QFont("Consolas", 9))
        left_info.setStyleSheet("color: #dcdcdc;")

        right_title = QLabel("三线性mipmap")
        right_title.setAlignment(Qt.AlignHCenter)
        right_title.setFont(f)
        right_title.setStyleSheet("color: #78dc78;")

        right_info = QLabel("MIN_FILTER = GL_LINEAR_MIPMAP_LINEAR\nMAG_FILTER = GL_LINEAR")
        right_info.setAlignment(Qt.AlignHCenter)
        right_info.setFont(QFont("Consolas", 9))
        right_info.setStyleSheet("color: #dcdcdc;")

        # ---- 左列（视图 + 文字）----
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(4)
        left_col.addWidget(self.left_view, stretch=1)
        left_col.addWidget(left_title)
        left_col.addWidget(left_info)

        # ---- 右列（视图 + 文字）----
        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(4)
        right_col.addWidget(self.right_view, stretch=1)
        right_col.addWidget(right_title)
        right_col.addWidget(right_info)

        # ---- 中间间隔（用一条带背景色的竖线/空白实现）----
        gap = QFrame()
        gap.setFrameShape(QFrame.NoFrame)
        gap.setFixedWidth(16)
        gap.setStyleSheet("background-color: #0d0d14;")

        # ---- 水平布局：左列 | 间隔 | 右列 ----
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(0)
        h_layout.addLayout(left_col, stretch=1)
        h_layout.addWidget(gap)
        h_layout.addLayout(right_col, stretch=1)

        # ---- 底部提示 ----
        hint = QLabel("← → 旋转   ↑ ↓ 前后移动   Space 重置")
        hint.setAlignment(Qt.AlignCenter)
        hint.setFont(QFont("Microsoft YaHei", 10))
        hint.setStyleSheet("color: #a0a0a0; padding: 6px;")

        # ---- 总布局 ----
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(h_layout, stretch=1)
        root.addWidget(hint)

        # 设一个深色背景，让间隔和文字区看起来协调
        self.setStyleSheet("background-color: #0d0d14;")

        # 让窗口能接收键盘事件
        self.setFocusPolicy(Qt.StrongFocus)

    # ---------- 键盘事件：统一更新两个视图 ----------

    def keyPressEvent(self, event):
        global angle, z_position

        k = event.key()

        if k == Qt.Key_Up:
            z_position += 1.0
        elif k == Qt.Key_Down:
            z_position -= 1.0
        elif k == Qt.Key_Left:
            angle += 1.0
        elif k == Qt.Key_Right:
            angle -= 1.0
        elif k == Qt.Key_Space:
            angle = 0.0
            z_position = 0.0
        else:
            super().keyPressEvent(event)
            return

        if angle > 360.0:
            angle -= 360.0
        elif angle < 0.0:
            angle += 360.0

        # 两个视图都刷新
        self.left_view.update()
        self.right_view.update()


# ---------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------

def main():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    win = MipmapCompareWindow()
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()