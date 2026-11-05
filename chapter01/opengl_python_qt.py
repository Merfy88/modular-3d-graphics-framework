"""
Simple_qt.py — Simple.cpp 的 PyQt5 + PyOpenGL 版本
在默认正交投影下，以原点为中心绘制一个边长为 1 的正方形。
不依赖 GLUT，改用 QOpenGLWidget 作为 Qt 界面。

Qt 事件驱动 + 虚函数回调
"""

import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication, QMainWindow, QOpenGLWidget

from OpenGL.GL import *


class GLWidget(QOpenGLWidget):
    """OpenGL 绘制控件，替代 GLUT 的窗口与回调机制"""

    def initializeGL(self):
        """对应 GLUT 初始化：设置清除色等 OpenGL 状态"""
        glClearColor(0.0, 0.0, 0.0, 1.0)

    def resizeGL(self, w, h):
        """对应默认正交投影：窗口尺寸变化时同步视口与投影矩阵"""
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        # GLUT 默认正交投影范围为 [-1, 1] × [-1, 1]
        glOrtho(-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    # 继承 + 虚函数机制(绘制图案)
    def paintGL(self):
        """显示回调（对应原 display()）"""
        glClear(GL_COLOR_BUFFER_BIT)
        glBegin(GL_TRIANGLES)
        glColor3f(1,0,0)
        glVertex2f(-0.5, -0.5)
        glColor3f(0,1,0)
        glVertex2f(0.5, -0.5)
        glColor3f(0,0,1)
        glVertex2f(0, 0.5)
        glEnd()

        # QOpenGLWidget 默认双缓冲，绘制完自动交换缓冲区，无需 glFlush


class MainWindow(QMainWindow):
    """主窗口，对应 glutCreateWindow / glutInitWindowSize / glutInitWindowPosition"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple")
        self.resize(500, 500)
        self.move(0, 0)
        self.setCentralWidget(GLWidget(self))


def main():
    # 使用传统固定管线（glBegin/glEnd），请求兼容性上下文避免 core profile 限制
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec_()  # app.exec_()启动 Qt 事件循环。对应 GLUT 的 glutMainLoop()


if __name__ == "__main__":
    main()
