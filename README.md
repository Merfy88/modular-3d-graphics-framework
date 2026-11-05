# computer_graphics

#### 介绍
计算机图形课程配套源代码，其中3d_viewer_framework是一个完整的3d浏览器，它使用插件化开发方法，可以在学习过程中不断增加有关图形处理的新功能，可以逐步完善成为一个有实用价值的小型软件。开发方法见3d_viewer_framework/3D浏览器插件化开发手册.md

#### 数据集
课程涉及三维建模、纹理映射、光照、可编程着色器等，配套使用以下数据集：

- [Middlebury Stereo Dataset](https://vision.middlebury.edu/stereo/data)
- [Tanks and Temples](https://www.tanksandtemples.org/)
- [Fountain Dataset](https://documents.epfl.ch/groups/c/cv/cvlab-unit/www/data/multiview/denseMVS.html)


#### 征集自愿者
- 框架管理者：管理、维护3d浏览器（3d_viewer_framework）源代码，审核其他自愿者提供的插件，并集成到框架中。
- 插件开发者：开发与3d浏览器有关的插件。
- 联系微信：CAI15899665892

#### 四个实验已整合为插件（折叠菜单）
`3d_viewer_framework` 右侧面板通过 `experiment_hub` 插件把四个实验整合为
可折叠的实验菜单（展开后显示各实验任务），一次展开一个实验效果最佳：

| 折叠分组 | 子插件 | 任务 |
|---|---|---|
| 实验一：颜色应用 | `plugin_color_experiment` | 任务1 彩色三角形 / 任务2 RGB立方体（HSV↔RGB 双显示区） |
| 实验二：纹理映射 | `plugin_texture` + `plugin_environment` | 任务1 2D纹理映射 / 任务2 环境映射（天球/球体采样/立方体反射） |
| 实验三：光照与材质 | `plugin_light` + `plugin_material` | 任务1 光照控制 / 任务2 多模型加载+材质（含真实材质进阶） |
| 实验四：光线追踪与凹凸映射 | `plugin_raytracer` + `plugin_bump` | 任务1 CPU光线追踪：参考场景（多物体多材质）/ 加载模型（展示场景：天空+网格展示台+自动布光，BVH加速，材质/光源可调） / 任务2 凹凸映射（法线贴图，缺UV/法线自动补算） ★进阶：加载模型 + 光线追踪 + 凹凸映射一体化 |

运行方式：在 `3d_viewer_framework` 目录执行 `python main.py`
（需安装 `PyQt5`、`vtk`、`pyyaml`）。启动后右侧即见"实验菜单"，
点击各组标题可折叠/展开，展开时对应实验的插件面板才会创建并激活。

