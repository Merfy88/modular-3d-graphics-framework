import os
import shutil
import open3d as o3d


def download_and_save_eagle(save_dir: str = "obj", filename: str = "eagle.ply"):
    """
    下载 Open3D 自带的 EaglePointCloud，并保存为 .ply 到指定目录。

    参数:
        save_dir:  保存目录，默认 "obj"
        filename:  保存文件名，默认 "eagle.ply"
    返回:
        保存后的完整文件路径
    """
    # ---------- 1. 创建保存目录 ----------
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    # ---------- 2. 下载 / 加载 Eagle 点云 ----------
    print("[1/3] 正在加载 EaglePointCloud (首次运行会自动下载)...")
    eagle = o3d.data.EaglePointCloud()
    pcd = o3d.io.read_point_cloud(eagle.path)

    print(f"      原始文件路径: {eagle.path}")
    print(f"      点云信息: {pcd}")

    # ---------- 3. 保存到 obj 目录 ----------
    print(f"[2/3] 正在保存到: {save_path}")
    success = o3d.io.write_point_cloud(save_path, pcd)

    if success:
        print(f"[3/3] ✅ 保存成功！文件大小: "
              f"{os.path.getsize(save_path) / 1024 / 1024:.2f} MB")
    else:
        print("[3/3] ❌ 保存失败！")
        return None

    return save_path


if __name__ == "__main__":
    # 下载并保存到项目根目录下的 obj/ 文件夹
    saved_file = download_and_save_eagle(save_dir="obj", filename="eagle.ply")

    # ---------- 可视化（可选） ----------
    if saved_file and os.path.exists(saved_file):
        print(f"\n👁  打开可视化窗口查看: {saved_file}")
        pcd = o3d.io.read_point_cloud(saved_file)

        # 给场景加个坐标轴，便于观察朝向和尺度
        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=1.0)

        # 如果点云没有法线，顺便估计一下，方便后续重建
        if not pcd.has_normals():
            print("      点云无法线信息，正在估计法线...")
            pcd.estimate_normals(
                search_param=o3d.geometry.KDTreeSearchParamKNN(knn=30)
            )

        o3d.visualization.draw_geometries(
            [pcd, coord],
            window_name="Eagle Point Cloud",
            width=960,
            height=720,
        )