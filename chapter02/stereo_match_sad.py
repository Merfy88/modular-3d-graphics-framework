'''
    立体匹配 - SAD滑动窗口方法
'''
import cv2
import numpy as np
import random

def read_images(path0: str, path1: str):
    """读取左右视图，返回BGR图与灰度图"""
    img0 = cv2.imread(path0)
    img1 = cv2.imread(path1)
    if img0 is None or img1 is None:
        raise FileNotFoundError("图片读取失败，请检查路径")
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    return img0, img1, gray0, gray1

def extract_sift_keypoints(gray_img):
    """SIFT提取关键点与描述子"""
    sift = cv2.SIFT_create()
    kps, des = sift.detectAndCompute(gray_img, None)
    return kps, des

def sad_sliding_window_match(kp_list, gray_left, gray_right, window_size=7, max_disp=120):
    """
    滑动窗口SAD立体匹配（校正立体对：只在同一y行搜索）
    :param kp_list: 左图关键点kp0列表
    :param gray_left: 左灰度图
    :param gray_right: 右灰度图
    :param window_size: SAD窗口大小，奇数
    :param max_disp: 最大视差搜索范围
    :return: matches list [ (kp_left, kp_right) ]
    """
    h, w = gray_left.shape
    half_win = window_size // 2
    match_pairs = []
    for kp in kp_list:
        x0, y0 = int(kp.pt[0]), int(kp.pt[1])
        # 窗口边界校验
        if (x0 - half_win) < 0 or (x0 + half_win) >= w:
            continue
        if (y0 - half_win) < 0 or (y0 + half_win) >= h:
            continue
        # 取左图关键点处窗口模板
        template = gray_left[y0-half_win:y0+half_win+1, x0-half_win:x0+half_win+1]
        best_sad = float("inf")
        best_x = None
        # 在校正立体图上，y固定不变，x向左搜索视差
        start_x = max(half_win, x0 - max_disp)
        end_x = x0 - half_win
        for xr in range(start_x, end_x + 1):
            # 右图滑动窗口
            patch_r = gray_right[y0-half_win:y0+half_win+1, xr-half_win:xr+half_win+1]
            sad_val = np.sum(np.abs(template.astype(np.int16) - patch_r.astype(np.int16)))
            if sad_val < best_sad:
                best_sad = sad_val
                best_x = xr
        if best_x is not None:
            # 构造右图关键点对象
            kp_right = cv2.KeyPoint(x=best_x, y=y0, size=kp.size)
            match_pairs.append((kp, kp_right))
    return match_pairs

def sample_matches(match_pairs, sample_num=100):
    """随机采样最多sample_num对匹配"""
    num = min(sample_num, len(match_pairs))
    return random.sample(match_pairs, num)

def draw_match_lines(img_left, img_right, sampled_pairs, save_path="sad_sift_match.png"):
    """
    绘制：左特征点红色，右特征点绿色
    """
    h_l, w_l = img_left.shape[:2]
    h_r, w_r = img_right.shape[:2]
    out_h = max(h_l, h_r)
    out_w = w_l + w_r
    out_img = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    out_img[:h_l, :w_l] = img_left
    out_img[:h_r, w_l:] = img_right

    radius = 4
    line_thickness = 2
    for (kp_l, kp_r) in sampled_pairs:
        xl, yl = int(kp_l.pt[0]), int(kp_l.pt[1])
        xr, yr = int(kp_r.pt[0]), int(kp_r.pt[1])
        # 左图：红色圆点 BGR (0,0,255)
        cv2.circle(out_img, (xl, yl), radius, (0, 0, 255), -1)
        # 右图：绿色圆点，右图坐标需要偏移w_l
        cv2.circle(out_img, (xr + w_l, yr), radius, (0, 255, 0), -1)
        # 加粗连线
        cv2.line(out_img, (xl, yl), (xr + w_l, yr), (255, 120, 0), thickness=line_thickness)

    cv2.imwrite(save_path, out_img)
    print(f"匹配图已保存至: {save_path}")
    return out_img


def main():
    path0 = r"images\Middlebury_Stereo_Dataset\Moebius\view1.png"
    path1 = r"images\Middlebury_Stereo_Dataset\Moebius\view5.png"
    save_match_path = r"images\Middlebury_Stereo_Dataset\Moebius\view1_view5_matches.png"
    save_disp_path = r"images\Middlebury_Stereo_Dataset\Moebius\sad_sparse_disp.png"

    # 1读取图像
    img0, img1, gray0, gray1 = read_images(path0, path1)
    h, w = gray0.shape
    # 2 SIFT提取左图关键点
    kp0, _ = extract_sift_keypoints(gray0)
    print(f"左图SIFT关键点总数: {len(kp0)}")
    # 3 SAD滑动窗口立体匹配
    match_pairs = sad_sliding_window_match(kp0, gray0, gray1, window_size=7, max_disp=120)
    print(f"SAD窗口匹配得到有效配对: {len(match_pairs)}")
    # 4 随机采样100对用于绘制
    sampled = sample_matches(match_pairs, sample_num=100)
    print(f"实际绘制匹配对数: {len(sampled)}")
    # 5绘制保存匹配图（红特征点、绿特征点、连线）
    draw_match_lines(img0, img1, sampled, save_path=save_match_path)


if __name__ == "__main__":
    start_time = cv2.getTickCount()
    main()
    end_time = cv2.getTickCount()
    print(f"执行时间: {(end_time - start_time) / cv2.getTickFrequency():.2f} s")
