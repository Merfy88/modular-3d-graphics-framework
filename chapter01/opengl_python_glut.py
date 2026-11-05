from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

def display():
    glClear(GL_COLOR_BUFFER_BIT)
    glBegin(GL_TRIANGLES)
    glColor3f(1,0,0)
    glVertex2f(-0.5, -0.5)
    glColor3f(0,1,0)
    glVertex2f(0.5, -0.5)
    glColor3f(0,0,1)
    glVertex2f(0, 0.5)
    glEnd()
    glutSwapBuffers()

if __name__ == "__main__":
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB)
    glutInitWindowSize(600, 400)
    glutCreateWindow("Python GLUT Demo".encode('utf-8'))
    glClearColor(0,0,0,1)
    glutDisplayFunc(display)
    glutMainLoop()