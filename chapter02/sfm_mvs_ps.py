'''
    两视图SfM+MVS重建：
        使用OpenCV SIFT特征提取，FLANN匹配，RANSAC+8point或5point求解E，三角化生成稀疏点云，获取相机位姿
        使用平面扫描MVS(ZNCC窗口代价)生成稠密点云
'''
import os
import glob
import argparse
import numpy as np
import cv2

def load_two_images(image_dir: str):
    """仅读取文件夹前2张jpg图像"""
    img_paths = sorted(glob.glob(os.path.join(image_dir, "*.jpg")))
    if len(img_paths) < 2:
        raise RuntimeError("文件夹至少需要2张jpg图片")
    img_list = []
    for path in img_paths[:2]:
        img = cv2.imread(path)
        if img is None:
            raise RuntimeError(f"读取图片失败 {path}")
        img_list.append(img)
    print(f"[load_two_images] 加载图像数量 = {len(img_list)}")
    return img_list

def feature_detect_sift_two(img_two):
    """对两张图像做SIFT特征检测，返回关键点、描述子，同时绘制特征图"""
    sift = cv2.SIFT_create()
    gray0 = cv2.cvtColor(img_two[0], cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(img_two[1], cv2.COLOR_BGR2GRAY)
    kp1, des1 = sift.detectAndCompute(gray0, None)
    kp2, des2 = sift.detectAndCompute(gray1, None)
    print("[feature_detect_sift_two] 完成两张图SIFT特征提取")
    return kp1, des1, kp2, des2

def draw_and_save_feat_images(img_two, kp1, kp2, out_dir):
    """绘制并保存特征点图，红色圆点"""
    feat_img0 = img_two[0].copy()
    for kp in kp1:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        cv2.circle(feat_img0, (x, y), 2, (0, 0, 255), -1)
    feat_img1 = img_two[1].copy()
    for kp in kp2:
        x, y = int(kp.pt[0]), int(kp.pt[1])
        cv2.circle(feat_img1, (x, y), 2, (0, 0, 255), -1)
    path0 = os.path.join(out_dir, "feat_0.png")
    path1 = os.path.join(out_dir, "feat_1.png")
    cv2.imwrite(path0, feat_img0)
    cv2.imwrite(path1, feat_img1)
    print(f"[draw_and_save_feat_images] 保存特征图：{path0}, {path1}")

def feature_match_flann_knn(des1, des2, ratio_thresh=0.75):
    """FLANN‑KNN特征匹配 + Lowe比率测试"""
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    matches = flann.knnMatch(des1, des2, k=2)
    good = []
    for m, n in matches:
        if m.distance < ratio_thresh * n.distance:
            good.append(m)
    print(f"[feature_match_flann_knn] 有效匹配对数：{len(good)}")
    return good

def draw_and_save_match_image(img_two, kp1, kp2, good_matches, out_dir):
    """绘制匹配连线图并保存，随机选取最多100对匹配点绘制"""
    import random
    # 随机采样最多100对匹配
    sample_num = min(100, len(good_matches))
    draw_matches = random.sample(good_matches, sample_num)
    img1 = img_two[0].copy()
    img2 = img_two[1].copy()
    # 左图：红色实心圆；右图：绿色实心圆
    for m in draw_matches:
        pt1 = (int(kp1[m.queryIdx].pt[0]), int(kp1[m.queryIdx].pt[1]))
        pt2 = (int(kp2[m.trainIdx].pt[0]), int(kp2[m.trainIdx].pt[1]))
        cv2.circle(img1, pt1, 6, (0, 0, 255), -1)   # 红色实心圆
        cv2.circle(img2, pt2, 6, (0, 255, 0), -1)   # 绿色实心圆
    # 拼接两张图
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]
    canvas_h = max(h1, h2)
    canvas_w = w1 + w2
    match_img = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    match_img[:h1, :w1] = img1
    match_img[:h2, w1:w1 + w2] = img2
    # 画彩色连线
    for m in draw_matches:
        pt1 = (int(kp1[m.queryIdx].pt[0]), int(kp1[m.queryIdx].pt[1]))
        pt2 = (int(kp2[m.trainIdx].pt[0]) + w1, int(kp2[m.trainIdx].pt[1]))
        cv2.line(match_img, pt1, pt2, (255, 120, 0), 1, cv2.LINE_AA)
    match_path = os.path.join(out_dir, "match.png")
    cv2.imwrite(match_path, match_img)
    print(f"[draw_and_save_match_image] 随机选取 {sample_num} 对匹配绘制，保存匹配连线图：{match_path}")

def estimate_camera_pose(kp1, kp2, matches, img_shape, method="8point"):
    """
    支持两种模式：
        "8point": RANSAC八点法求F → E=K^T F K
        "5point": RANSAC五点法直接求解本质矩阵E
    :param kp1: 图1关键点
    :param kp2: 图2关键点
    :param matches: 匹配对
    :param img_shape: (H,W)
    :param method: "8point" / "5point"
    :return R, t, K, pts1_in, pts2_in
    """
    H, W = img_shape
    fx = 0.7 * W
    fy = 0.7 * W
    cx = W / 2.0
    cy = H / 2.0
    K = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0, 0, 1]
    ], dtype=np.float64)
    print(f"[estimate_camera_pose] 相机内参矩阵K:\n{K}")
    print(f"[estimate_camera_pose] 使用求解方法: {method}")
    pts1 = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    pts2 = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    if method == "8point":
        # 八点法：先求基础矩阵F，再推导E
        F, mask_F = cv2.findFundamentalMat(
            pts1, pts2,
            cv2.FM_8POINT + cv2.FM_RANSAC,
            ransacReprojThreshold=1.0
        )
        mask_inlier = mask_F.ravel()
        pts1_in = pts1[mask_inlier == 1]
        pts2_in = pts2[mask_inlier == 1]
        print(f"[estimate_camera_pose] RANSAC八点法F，内点数量: {len(pts1_in)}")
        if len(pts1_in) < 8:
            raise RuntimeError("内点数目不足8点，无法三角化")
        E = K.T @ F @ K
        U, S, Vt = np.linalg.svd(E)
        avg_s = (S[0] + S[1]) / 2.0
        S = np.diag([avg_s, avg_s, 0.0])
        E = U @ S @ Vt
    elif method == "5point":
        # 五点法：RANSAC直接求解本质矩阵E
        E, mask_E = cv2.findEssentialMat(
            pts1, pts2, K,
            method=cv2.RANSAC,
            prob=0.999,
            threshold=1.0
        )
        mask_inlier = mask_E.ravel()
        pts1_in = pts1[mask_inlier == 1]
        pts2_in = pts2[mask_inlier == 1]
        print(f"[estimate_camera_pose] RANSAC五点法E，内点数量: {len(pts1_in)}")
        if len(pts1_in) < 5:
            raise RuntimeError("内点数目不足5点，无法三角化")
    else:
        raise ValueError(f"不支持method={method}, 可选: 8point /5point")
    # E分解得到4组R/t候选
    U, S, Vt = np.linalg.svd(E)
    avg_s = (S[0] + S[1]) / 2.0
    S = np.diag([avg_s, avg_s, 0.0])
    E = U @ S @ Vt
    W_mat = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    Wt_mat = W_mat.T
    R1 = U @ W_mat @ Vt
    R2 = U @ Wt_mat @ Vt
    if np.linalg.det(R1) < 0:
        R1 = -R1
    if np.linalg.det(R2) < 0:
        R2 = -R2
    t_vec = U[:, 2]
    candidates = [(R1, t_vec), (R1, -t_vec), (R2, t_vec), (R2, -t_vec)]
    best_R = None
    best_t = None
    max_pos_depth = -1
    P1 = K @ np.hstack((np.eye(3), np.zeros((3, 1))))
    pts1_sq = np.squeeze(pts1_in).T
    pts2_sq = np.squeeze(pts2_in).T
    for R_cand, t_cand in candidates:
        P2 = K @ np.hstack((R_cand, t_cand.reshape(3, 1)))
        pts4d = cv2.triangulatePoints(P1, P2, pts1_sq, pts2_sq)
        pts3d = pts4d[:3, :] / pts4d[3, :]
        pos_depth = np.sum(pts3d[2, :] > 0)
        if pos_depth > max_pos_depth:
            max_pos_depth = pos_depth
            best_R = R_cand
            best_t = t_cand
    print(f"[estimate_camera_pose] 筛选后正深度点数 {max_pos_depth}")
    print(f"[estimate_camera_pose] 最终旋转矩阵R:\n{best_R}")
    print(f"[estimate_camera_pose] 最终平移向量t:\n{best_t}")
    return best_R, best_t, K, pts1_in, pts2_in

def triangulate_sparse_cloud(K, R, t, pts1, pts2):
    """三角测量生成稀疏点云，过滤Z>0有效点"""
    P1 = K @ np.hstack((np.eye(3), np.zeros((3, 1))))
    P2 = K @ np.hstack((R, t.reshape(3, 1)))
    pts1_sq = np.squeeze(pts1).T
    pts2_sq = np.squeeze(pts2).T
    pts4d_homo = cv2.triangulatePoints(P1, P2, pts1_sq, pts2_sq)
    pts3d = pts4d_homo[:3, :] / pts4d_homo[3, :]
    pts3d = pts3d.T
    valid_mask = pts3d[:, 2] > 0
    pts3d_valid = pts3d[valid_mask]
    print(f"[triangulate_sparse_cloud] 稀疏点云有效点数 {pts3d_valid.shape[0]}")
    return pts3d_valid

def save_point_cloud_obj(points3d, output_path):
    """保存obj点云"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding="utf-8") as f:
        for p in points3d:
            f.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
    print(f"[save_point_cloud_obj] 点云保存成功 → {output_path}")

def generate_dense_mvs_cloud(img_two, K, R, t, sparse_points, depth_num=40, win_size=5, step=8):
    """标准平面扫描MVS，逐像素+ZNCC窗口代价"""
    print("[generate_dense_mvs_cloud] 标准平面扫描MVS(ZNCC窗口代价)开始")
    ref_img = img_two[0]
    h, w = ref_img.shape[:2]
    gray1 = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gray2 = cv2.cvtColor(img_two[1], cv2.COLOR_BGR2GRAY).astype(np.float32)
    P1 = K @ np.hstack((np.eye(3), np.zeros((3, 1))))
    P2 = K @ np.hstack((R, t.reshape(3, 1)))
    # 深度候选平面，沿用之前策略
    z_vals = sparse_points[:, 2]
    z_min = float(np.percentile(z_vals, 5))
    z_max = float(np.percentile(z_vals, 95))
    if abs(z_max - z_min) < 1e-6:
        z_min -= 2.0
        z_max += 2.0
    depth_candidates = np.linspace(z_min, z_max, depth_num)
    half_win = win_size // 2
    dense_points = []
    # 逐像素遍历 step由外部传入
    num = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            num += 1
            if (num % 10000 == 0):
                print(f"[generate_dense_mvs_cloud] 扫描像素点 {num} / {h * w // (step * step)}")
                
            # =========新增：参考图patch边界检查=========
            if (x - half_win) < 0 or (x + half_win) >= w or (y - half_win) <0 or (y + half_win)>=h:
                continue
            best_zncc = -2.0
            best_3d = None
            # 遍历所有深度平面
            for d in depth_candidates:
                # 参考图像素(x,y)反投影3D点
                X3d = np.linalg.inv(K) @ np.array([x * d, y * d, d])
                # 投影到第二张图
                proj_h = P2 @ np.hstack((X3d, 1.0))
                proj_h = proj_h / proj_h[2]
                u2, v2 = proj_h[0], proj_h[1]
                # 窗口边界检查：整个窗口必须落在图2内
                u2i = int(round(u2))
                v2i = int(round(v2))
                if (u2i - half_win) < 0 or (u2i + half_win) >= w or (v2i - half_win) <0 or (v2i + half_win)>=h:
                    continue
                # 提取两个窗口
                patch1 = gray1[y-half_win:y+half_win+1, x-half_win:x+half_win+1]
                patch2 = gray2[v2i-half_win:v2i+half_win+1, u2i-half_win:u2i+half_win+1]
                # ZNCC 零均值归一化互相关
                p1 = patch1 - np.mean(patch1)
                p2 = patch2 - np.mean(patch2)
                std1 = np.sqrt(np.sum(p1**2) + 1e-8)
                std2 = np.sqrt(np.sum(p2**2) + 1e-8)
                zncc = np.sum(p1 * p2) / (std1 * std2)
                # 过滤nan
                if np.isnan(zncc):
                    continue
                if zncc > best_zncc:
                    best_zncc = zncc
                    best_3d = X3d
            # ZNCC阈值，大于0.6认为匹配可靠，可以调整
            if best_3d is not None and best_zncc > 0.6:
                dense_points.append(best_3d)
    if len(dense_points) == 0:
        print("[generate_dense_mvs_cloud] 警告：没有生成任何稠密点")
        return np.empty((0, 3))
    dense_cloud = np.array(dense_points)
    print(f"[generate_dense_mvs_cloud] MVS生成稠密点数量 {dense_cloud.shape[0]}")
    return dense_cloud

def main(IMAGE_FOLDER, OUTPUT_FOLDER, pose_method, step):
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    sparse_obj = os.path.join(OUTPUT_FOLDER, "sparse_cloud.obj")
    dense_obj = os.path.join(OUTPUT_FOLDER, "dense_cloud.obj")
    # 只加载两张图片
    img_two = load_two_images(IMAGE_FOLDER)
    H, W = img_two[0].shape[:2]
    # SIFT特征提取
    kp1, des1, kp2, des2 = feature_detect_sift_two(img_two)
    # 保存特征点图（红色圆点）
    draw_and_save_feat_images(img_two, kp1, kp2, OUTPUT_FOLDER)
    # FLANN匹配
    good_matches = feature_match_flann_knn(des1, des2)
    if len(good_matches) < 10:
        raise RuntimeError("匹配特征点太少，无法重建")
    # 保存匹配连线图
    draw_and_save_match_image(img_two, kp1, kp2, good_matches, OUTPUT_FOLDER)
    # 位姿求解，传入选择的方法
    R, t, K_mat, pts1_in, pts2_in = estimate_camera_pose(
        kp1, kp2, good_matches, (H, W), method=pose_method
    )
    # 稀疏三角化
    sparse_pts = triangulate_sparse_cloud(K_mat, R, t, pts1_in, pts2_in)
    save_point_cloud_obj(sparse_pts, sparse_obj)
    # MVS稠密，传入step参数
    dense_pts = generate_dense_mvs_cloud(img_two, K_mat, R, t, sparse_pts, step=step)
    save_point_cloud_obj(dense_pts, dense_obj)
    print("\n========两视图SfM+MVS重建完成========")
    print(f"求解模式: {pose_method}")
    print(f"MVS采样步长 step: {step}")
    print(f"稀疏点云: {sparse_obj}")
    print(f"稠密点云: {dense_obj}")
    print(f"输出目录图片：feat_0.png, feat_1.png, match.png")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="两视图SfM+MVS，支持8point/5point求解E")
    parser.add_argument("--image-folder", type=str, default=r"images\Tanks_and_Temples\Horse", help="图像文件夹")
    parser.add_argument("--output-folder", type=str, default=r"output\Tanks_and_Temples\Horse", help="输出目录")
    parser.add_argument("--method", type=str, choices=["8point", "5point"], default="8point",
                        help="位姿求解方法：8point(RANSAC八点法F→E) / 5point(RANSAC五点法直接求E)")
    parser.add_argument("--step", type=int, default=8, help="平面扫描MVS像素采样步长，越小点云越密，速度越慢，推荐：2/4/8")
    args = parser.parse_args()
    start_time = cv2.getTickCount()
    main(args.image_folder, args.output_folder, args.method, args.step)
    end_time = cv2.getTickCount()
    elapsed = (end_time - start_time) / cv2.getTickFrequency()
    print(f"[main] 总耗时: {elapsed:.2f} s")
