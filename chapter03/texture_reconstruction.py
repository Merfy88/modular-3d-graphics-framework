'''
    基于 Open3D 的三维重建演示程序
    步骤：TSDF 融合 → 表面重建 → 纹理映射
    重建算法：Poisson / Ball Pivoting
'''
import os
import numpy as np
import open3d as o3d

OUTPUT_DIR = os.path.abspath("output")
VOXEL_SIZE = 0.005             # 下采样体素，用于轻量去冗

# ============================================================
# 开关区
# ============================================================
# 重建算法： "poisson" / "ball"
RECON_METHOD = "ball"

# ----- TSDF 参数 -----
TSDF_VOXEL_SIZE = 0.005        # 体素边长（米）
TSDF_SDF_TRUNC = 0.04          # 截断距离（米），一般 3~8 倍 voxel
TSDF_DEPTH_SCALE = 1000.0      # 深度图单位：1 = 1mm
TSDF_DEPTH_TRUNC = 3.0         # 最大有效深度（米）

# ----- Poisson 参数 -----
POISSON_DEPTH = 9
DENSITY_QUANTILE = 0.02

# ----- Ball Pivoting 参数 -----
BALL_RADII = [
    0.0040,   # ≈ 1.0d，主力半径
    0.0070,   # ≈ 1.8d
    0.0120,   # ≈ 3.2d，补少量孔洞
]

# ----- 通用参数 -----
KNN_NORMAL = 30
INVERT_POSE = False            # 若位姿 log 方向反了，置 True


def log(msg):
    print(msg, flush=True)


# ============================================================
# 工具：读取 pose log
# ============================================================
def read_pose_log(path):
    poses = []
    current_rows = []

    with open(path, "r") as f:
        for line_no, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            try:
                vals = list(map(float, parts))
            except ValueError:
                log(f"      ⚠️ 跳过无法解析的行 {line_no}: {line[:60]}")
                continue

            if len(vals) == 3:          # 帧头
                current_rows = []
                continue
            if len(vals) == 4:          # 矩阵一行
                current_rows.append(vals)
                if len(current_rows) == 4:
                    poses.append(np.array(current_rows, dtype=np.float64))
                    current_rows = []
                continue
            log(f"      ⚠️ 行 {line_no} 数字个数={len(vals)}，跳过")

    return poses


# ============================================================
# 工具：RGB-D → 相机坐标系点云（仅用于步骤 3 的顶点着色）
# ============================================================
def rgbd_to_pointcloud(cpath, dpath, intrinsic,
                       depth_scale=1000.0, depth_trunc=3.0):
    color = o3d.io.read_image(cpath)
    depth = o3d.io.read_image(dpath)
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color, depth,
        depth_scale=depth_scale,
        depth_trunc=depth_trunc,
        convert_rgb_to_intensity=False,
    )
    return o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, intrinsic)


# ============================================================
# 步骤 1：TSDF 融合 → 点云
# ============================================================
def step1_tsdf_pointcloud(color_paths, depth_paths, intrinsic, poses):
    log("[步骤 1/3] TSDF 融合 → 点云 ...")
    log(f"      voxel_size={TSDF_VOXEL_SIZE}, "
        f"sdf_trunc={TSDF_SDF_TRUNC}, "
        f"depth_trunc={TSDF_DEPTH_TRUNC}")

    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=TSDF_VOXEL_SIZE,
        sdf_trunc=TSDF_SDF_TRUNC,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )

    for i, (cpath, dpath) in enumerate(zip(color_paths, depth_paths)):
        color = o3d.io.read_image(cpath)
        depth = o3d.io.read_image(dpath)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            color, depth,
            depth_scale=TSDF_DEPTH_SCALE,
            depth_trunc=TSDF_DEPTH_TRUNC,
            convert_rgb_to_intensity=False,
        )

        # 位姿：integrate 需要 T_cw（世界→相机）
        T = poses[i]
        if INVERT_POSE:
            T = np.linalg.inv(T)

        volume.integrate(rgbd, intrinsic, np.linalg.inv(T))
        log(f"      帧 {i + 1}/{len(color_paths)} 已融合 "
            f"(位姿平移={np.round(T[:3, 3], 3)})")

    log("      提取点云 ...")
    pcd = volume.extract_point_cloud()
    log(f"      原始点数: {len(pcd.points)}")

    log(f"      体素下采样 (voxel_size={VOXEL_SIZE}) ...")
    pcd = pcd.voxel_down_sample(voxel_size=VOXEL_SIZE)
    log(f"      下采样后: {len(pcd.points)} 点")

    log("      统计离群点去除 ...")
    pcd, _ = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    log(f"      去噪后: {len(pcd.points)} 点")

    pc_path = os.path.join(OUTPUT_DIR, "step1_pointcloud.ply")
    o3d.io.write_point_cloud(pc_path, pcd)
    log(f"      ✅ 已保存: {pc_path}")
    return pcd


# ============================================================
# 步骤 2：点云 → 表面重建
# ============================================================
def step2_mesh(pcd):
    log(f"[步骤 2/3] 点云 → 表面重建 (方法={RECON_METHOD}) ...")

    # ---------- 法线 ----------
    if not pcd.has_normals():
        log(f"      估计法线 (knn={KNN_NORMAL}) ...")
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamKNN(knn=KNN_NORMAL)
        )
    else:
        log("      点云已包含法线，跳过估计")

    log("      统一法线朝向 ...")
    pcd.orient_normals_consistent_tangent_plane(k=KNN_NORMAL)

    # ---------- Poisson ----------
    if RECON_METHOD == "poisson":
        log(f"      Poisson 重建 (depth={POISSON_DEPTH}) ...")
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=POISSON_DEPTH
        )
        log(f"      原始网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面")

        densities = np.asarray(densities)
        keep = densities > np.quantile(densities, DENSITY_QUANTILE)
        mesh.remove_vertices_by_mask(~keep)
        log(f"      密度裁剪 (quantile={DENSITY_QUANTILE}) 完成")

    # ---------- Ball Pivoting ----------
    elif RECON_METHOD == "ball":
        log(f"      Ball Pivoting 重建 (radii={BALL_RADII}) ...")

        distances = pcd.compute_nearest_neighbor_distance()
        avg_dist = np.mean(distances)
        log(f"      平均点间距 ≈ {avg_dist:.5f}")

        radii = o3d.utility.DoubleVector(BALL_RADII)
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_ball_pivoting(
            pcd, radii
        )
        log(f"      原始网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面")

        hole_size = avg_dist * 5.0
        log(f"      填充孔洞 (hole_size={hole_size:.5f}) ...")
        t_mesh = o3d.t.geometry.TriangleMesh.from_legacy(mesh)
        t_mesh_filled = t_mesh.fill_holes(hole_size)
        mesh = t_mesh_filled.to_legacy()
        log(f"      填洞后: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面")

    else:
        raise ValueError(f"未知的重建算法: {RECON_METHOD}")

    # ---------- 后处理 ----------
    mesh.remove_unreferenced_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()

    log("      网格拉普拉斯平滑（消除平面碎片） ...")
    mesh = mesh.filter_smooth_laplacian(
        number_of_iterations=5,
        lambda_filter=0.5,
    )

    mesh.compute_vertex_normals()
    mesh.paint_uniform_color([0.8, 0.8, 0.8])

    log(f"      最终网格: {len(mesh.vertices)} 顶点, {len(mesh.triangles)} 三角面")

    mesh_path = os.path.join(OUTPUT_DIR, "step2_mesh.ply")
    o3d.io.write_triangle_mesh(mesh_path, mesh)
    log(f"      ✅ 已保存: {mesh_path}")
    return mesh


# ============================================================
# 步骤 3：纹理映射（世界坐标下最近邻加权顶点着色）
# ============================================================
def step3_texture(mesh, color_paths, depth_paths, intrinsic, poses):
    log("[步骤 3/3] Mesh → 纹理映射 (顶点着色) ...")

    vertices = np.asarray(mesh.vertices)
    colors_accum = np.zeros_like(vertices)
    weights_accum = np.zeros(len(vertices)) + 1e-9

    for i, (cpath, dpath) in enumerate(zip(color_paths, depth_paths)):
        pcd_cam = rgbd_to_pointcloud(cpath, dpath, intrinsic)
        if len(pcd_cam.points) == 0:
            continue

        T = poses[i]
        if INVERT_POSE:
            T = np.linalg.inv(T)
        pcd_world = pcd_cam.transform(T)

        kdtree = o3d.geometry.KDTreeFlann(pcd_world)
        frame_colors = np.asarray(pcd_world.colors)

        for vi, v in enumerate(vertices):
            _, idx, dist2 = kdtree.search_knn_vector_3d(v, 1)
            if len(idx) == 0:
                continue
            d = np.sqrt(dist2[0])
            w = 1.0 / (d + 1e-6)
            colors_accum[vi] += w * frame_colors[idx[0]]
            weights_accum[vi] += w

        log(f"      帧 {i + 1}/{len(color_paths)} 颜色融合完成")

    colors = colors_accum / weights_accum[:, None]
    mesh.vertex_colors = o3d.utility.Vector3dVector(np.clip(colors, 0, 1))

    tex_ply = os.path.join(OUTPUT_DIR, "step3_textured.ply")
    o3d.io.write_triangle_mesh(tex_ply, mesh)
    log(f"      ✅ 已保存: {tex_ply}")
    return mesh


# ============================================================
# 主流程
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    log(f"📁 输出目录: {OUTPUT_DIR}")
    log(f"🧠 重建算法: {RECON_METHOD}")
    log("🔀 点云来源: TSDF 融合")

    # ---------- 加载数据集 ----------
    log("📥 加载 SampleRedwoodRGBDImages ...")
    dataset = o3d.data.SampleRedwoodRGBDImages()

    color_paths = list(dataset.color_paths)
    depth_paths = list(dataset.depth_paths)
    intrinsic = o3d.io.read_pinhole_camera_intrinsic(dataset.camera_intrinsic_path)

    log(f"      共 {len(color_paths)} 帧 RGB-D")
    log(f"      内参: {intrinsic.width}x{intrinsic.height}")

    # ---------- 读取位姿 ----------
    log("📐 读取相机位姿 ...")
    base_dir = os.path.dirname(dataset.odometry_log_path)
    trajectory_path = os.path.join(base_dir, "trajectory.log")

    if os.path.exists(trajectory_path):
        log("      使用 trajectory.log")
        poses = read_pose_log(trajectory_path)
    else:
        log("      使用 odometry.log")
        poses = read_pose_log(dataset.odometry_log_path)

    log(f"      ✅ 读到 {len(poses)} 个位姿")
    if len(poses) == 0:
        raise RuntimeError("未能解析出任何位姿")

    n = min(len(poses), len(color_paths))
    poses = poses[:n]
    color_paths = color_paths[:n]
    depth_paths = depth_paths[:n]

    # ---------- 步骤 1：TSDF 融合 ----------
    pcd = step1_tsdf_pointcloud(color_paths, depth_paths, intrinsic, poses)

    # ---------- 步骤 2：表面重建 ----------
    mesh = step2_mesh(pcd)

    # ---------- 步骤 3：纹理映射 ----------
    step3_texture(mesh, color_paths, depth_paths, intrinsic, poses)

    # ---------- 汇总 ----------
    log("\n🎉 全部完成！输出文件：")
    for f in sorted(os.listdir(OUTPUT_DIR)):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, f)) / 1024
        log(f"      - {f}  ({size:.1f} KB)")


if __name__ == "__main__":
    main()