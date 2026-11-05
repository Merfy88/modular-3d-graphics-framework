# -*- coding: utf-8 -*-
"""
读取文件生成纹理，实现纹理映射
 - 从 images 目录读取 6 张纹理（QImage 自动识别 BMP/JPG/PNG）
 - 立方体六个面分别映射不同纹理
 - 鼠标左/中/右键切换旋转轴（X/Y/Z）
 - 键盘 1 开启旋转，2 停止旋转
"""
import sys
import os
import warnings
# 忽略 SIP 弃用警告（不影响功能）
warnings.filterwarnings("ignore", category=DeprecationWarning)
from PyQt5.QtWidgets import QApplication, QOpenGLWidget
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QOpenGLTexture, QImage, QSurfaceFormat

class TextureCubeWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theta = [0.0, 0.0, 0.0]
        self.axis = 2
        self.textures = []
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.spin_cube)
        self.timer.start()
        self._cleaned = False  # 标记资源是否已经清理

    # ---------- OpenGL 生命周期 ----------
    def initializeGL(self):
        from OpenGL.GL import (glEnable, glClearColor,
                               GL_DEPTH_TEST, GL_TEXTURE_2D)
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_TEXTURE_2D)
        # 连接上下文销毁信号，在上下文失效前清理纹理
        self.context().aboutToBeDestroyed.connect(self.cleanup)
        self.load_textures()

    def load_textures(self):
        """加载 6 张纹理，销毁旧纹理【保证上下文激活】"""
        # 销毁旧纹理，必须先 makeCurrent
        if self.textures:
            self.makeCurrent()
            for tex in self.textures:
                if tex is not None and tex.isCreated():
                    tex.destroy()
            self.textures.clear()
            self.doneCurrent()

        for i in range(6):
            path = os.path.join("images", f"cube{i}.bmp")
            img = QImage(path)
            if img.isNull():
                print("加载失败:", path)
                self.textures.append(None)
                continue
            tex = QOpenGLTexture(img.mirrored())
            tex.setMinificationFilter(QOpenGLTexture.Linear)
            tex.setMagnificationFilter(QOpenGLTexture.Linear)
            tex.setWrapMode(QOpenGLTexture.Repeat)
            self.textures.append(tex)

    def cleanup(self):
        """在 OpenGL 上下文销毁前释放纹理资源"""
        if self._cleaned:
            return
        try:
            if not self.isValid():
                return
            self.makeCurrent()
            for tex in self.textures:
                if tex is not None and tex.isCreated():
                    tex.destroy()
            self.textures.clear()
            self.doneCurrent()
            self._cleaned = True
        except RuntimeError:
            pass

    def closeEvent(self, event):
        """窗口关闭兜底清理"""
        self.cleanup()
        super().closeEvent(event)

    def resizeGL(self, w, h):
        from OpenGL.GL import (glViewport, glMatrixMode, glLoadIdentity,
                               glOrtho, GL_PROJECTION, GL_MODELVIEW)
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if w <= h:
            glOrtho(-2.0, 2.0,
                    -2.0 * h / w, 2.0 * h / w,
                    -10.0, 10.0)
        else:
            glOrtho(-2.0 * w / h, 2.0 * w / h,
                    -2.0, 2.0,
                    -10.0, 10.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        from OpenGL.GL import (glClear, glLoadIdentity, glRotatef,
                               GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glRotatef(self.theta[0], 1.0, 0.0, 0.0)
        glRotatef(self.theta[1], 0.0, 1.0, 0.0)
        glRotatef(self.theta[2], 0.0, 0.0, 1.0)
        self.draw_cube()

    # ---------- 绘制 ----------
    def draw_cube(self):
        from OpenGL.GL import (glBegin, glEnd, glTexCoord2f,
                               glVertex3fv, GL_POLYGON)
        v = [
            [-1.0, -1.0, -1.0], [ 1.0, -1.0, -1.0],
            [ 1.0,  1.0, -1.0], [-1.0,  1.0, -1.0],
            [-1.0, -1.0,  1.0], [ 1.0, -1.0,  1.0],
            [ 1.0,  1.0,  1.0], [-1.0,  1.0,  1.0],
        ]
        faces = [
            (0, 3, 2, 1), (2, 3, 7, 6), (3, 0, 4, 7),
            (1, 2, 6, 5), (4, 5, 6, 7), (5, 4, 0, 1),
        ]
        for tex, (a, b, c, d) in zip(self.textures, faces):
            if tex is not None:
                tex.bind()
            glBegin(GL_POLYGON)
            glTexCoord2f(0.0, 0.0); glVertex3fv(v[a])
            glTexCoord2f(1.0, 0.0); glVertex3fv(v[b])
            glTexCoord2f(1.0, 1.0); glVertex3fv(v[c])
            glTexCoord2f(0.0, 1.0); glVertex3fv(v[d])
            glEnd()
            if tex is not None:
                tex.release()

    # ---------- 交互 ----------
    def spin_cube(self):
        self.theta[self.axis] += 0.2
        if self.theta[self.axis] > 360.0:
            self.theta[self.axis] -= 360.0
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.axis = 0
        elif e.button() == Qt.MidButton:
            self.axis = 1
        elif e.button() == Qt.RightButton:
            self.axis = 2

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_1:
            if not self.timer.isActive():
                self.timer.start()
        elif e.key() == Qt.Key_2:
            self.timer.stop()

def main():
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    widget = TextureCubeWidget()
    widget.setWindowTitle("Texture Cube")
    widget.resize(800, 800)
    widget.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
