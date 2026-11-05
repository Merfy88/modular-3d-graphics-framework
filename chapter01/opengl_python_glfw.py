import glfw
from OpenGL.GL import *
from OpenGL.GLU import *

# 窗口尺寸
WIDTH = 600
HEIGHT = 400

def render_scene():
    # 清空颜色缓冲，对应原代码 glClear(GL_COLOR_BUFFER_BIT)
    glClear(GL_COLOR_BUFFER_BIT)

    # 老式固定管线绘制三角形，和原GLUT代码完全一致
    glBegin(GL_TRIANGLES)
    glColor3f(1.0, 0.0, 0.0)
    glVertex2f(-0.5, -0.5)

    glColor3f(0.0, 1.0, 0.0)
    glVertex2f(0.5, -0.5)

    glColor3f(0.0, 0.0, 1.0)
    glVertex2f(0.0, 0.5)
    glEnd()

def main():
    # 初始化glfw
    if not glfw.init():
        raise Exception("GLFW 初始化失败")

    # 配置OpenGL上下文（兼容固定管线，不用core profile）
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_ANY_PROFILE)

    # 创建窗口
    window = glfw.create_window(WIDTH, HEIGHT, "PyOpenGL + GLFW Demo", None, None)
    if not window:
        glfw.terminate()
        raise Exception("窗口创建失败")
    glfw.make_context_current(window)

    # 设置清屏底色，和原代码一致
    glClearColor(0.0, 0.0, 0.0, 1.0)

    # 主渲染循环（替代glutMainLoop）
    while not glfw.window_should_close(window):
        render_scene()

        # 交换双缓冲，对应 glutSwapBuffers()
        glfw.swap_buffers(window)
        # 处理窗口、键盘鼠标事件
        glfw.poll_events()

    # 释放资源
    glfw.terminate()

if __name__ == "__main__":
    main()