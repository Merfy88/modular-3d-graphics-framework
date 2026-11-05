'''
    根据视差图生成三维模型obj
'''
import cv2
import numpy as np
import open3d as o3d
import trimesh
import argparse
import os


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="Middlebury2005 视差图转点云obj")
    parser.add_argument("--disp", type=str, default=r"images\Middlebury_Stereo_Dataset\Moebius\disp1.png",
                        help="视差图完整路径，例如 images\\Middlebury_Stereo_Dataset\\Moebius\\disp1.png")
    args = parser.parse_args()
    return args


def load_data(disp_path):
    """
    读取视差图、左图、dmin.txt
    返回：disp_img, img_color, dmin, disp_dir
    """
    disp_dir = os.path.dirname(disp_path)
    img_left_path = os.path.join(disp_dir, "view1.png")
    dmin_file = os.path.join(disp_dir, "dmin.txt")
    # 读取dmin
    with open(dmin_file, "r") as fp:
        dmin = int(fp.read().strip())
    disp_img = cv2.imread(disp_path, cv2.IMREAD_GRAYSCALE)
    img_color = cv2.imread(img_left_path)
    img_color = cv2.cvtColor(img_color, cv2.COLOR_BGR2RGB)
    return disp_img, img_color, dmin, disp_dir


def disparity_to_pointcloud(disp_img, img_color, dmin, focal, b):
    """
    视差图转彩色点云
    :return: points(n,3), colors(n,3)
    """
    h, w = disp_img.shape
    cx, cy = w / 2, h / 2  # 图像中心近似主点
    u_grid, v_grid = np.meshgrid(np.arange(w), np.arange(h))
    disp_raw = disp_img.astype(np.float32)
    mask = disp_raw > 0  # 0代表无效视差
    d_real = disp_raw[mask] + dmin
    Z = (focal * b) / d_real
    u_valid = u_grid[mask]
    v_valid = v_grid[mask]
    X = (u_valid - cx) * Z / focal
    Y = (v_valid - cy) * Z / focal
    points = np.stack([X, Y, Z], axis=-1)
    colors = img_color[mask] / 255.0
    return points, colors


def save_pointcloud_obj(points, colors, save_path):
    """trimesh保存点云obj"""
    pc_trimesh = trimesh.PointCloud(points, colors=colors)
    pc_trimesh.export(save_path)
    print(f"obj已保存 {save_path}")


def visualize_pointcloud(points, colors):
    """open3d可视化点云"""
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors)
    o3d.visualization.draw_geometries([pcd])


def main():
    # 1.解析参数
    args = parse_args()
    disp_path = args.disp
    # 2.加载数据
    disp_img, img_color, dmin, disp_dir = load_data(disp_path)
    # --------Middlebury Stereo Dataset 2005 Moebius FullSize参数 --------
    focal = 3740  # 像素焦距
    b = 160       # mm基线

    # 取视差图文件名（不带后缀），生成obj文件名
    disp_basename = os.path.splitext(os.path.basename(disp_path))[0]
    save_obj_path = os.path.join(disp_dir, f"{disp_basename}.obj")

    # 3.视差转点云
    start_time = cv2.getTickCount()
    points, colors = disparity_to_pointcloud(disp_img, img_color, dmin, focal, b)
    end_time = cv2.getTickCount()
    print(f"视差转点云时间: {(end_time - start_time) / cv2.getTickFrequency():.2f} s")

    # 4.保存obj
    save_pointcloud_obj(points, colors, save_obj_path)
    # 5.可视化
    visualize_pointcloud(points, colors)


if __name__ == "__main__":
    
    main()
