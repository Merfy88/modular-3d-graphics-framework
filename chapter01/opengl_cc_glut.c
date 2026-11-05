// opengl_cc_glut.c :
//

#ifdef __APPLE__
#include <GLUT/glut.h>
#else
#include <GL/glut.h>
#endif

void display()
{
    glClear(GL_COLOR_BUFFER_BIT);
    glBegin(GL_TRIANGLES);
		glColor3f(1,0,0);
		glVertex2f(-0.5, -0.5);
		glColor3f(0,1,0);
		glVertex2f(0.5, -0.5);
		glColor3f(0,0,1);
		glVertex2f(0, 0.5);
    glEnd();

	glFlush();
}


int main(int argc, char* argv[])
{
	 
    glutInit(&argc, argv);

	glutInitDisplayMode(GLUT_SINGLE | GLUT_RGB);
    glutInitWindowSize(500, 500);
	glutInitWindowPosition(0, 0);
	glutCreateWindow("OpenGL CC GLUT");

	glutDisplayFunc(display);
    
	glutMainLoop();

	return 0;
}
