'''
    根据左右图生成视差图
'''
import cv2
import numpy as np
import argparse
import os


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="立体匹配生成视差图，支持 SGBM / SAD(BM)")
    parser.add_argument("--left", type=str,
                        default=r"images\Middlebury_Stereo_Dataset\Moebius\view1.png",
                        help="左图路径")
    parser.add_argument("--right", type=str,
                        default=r"images\Middlebury_Stereo_Dataset\Moebius\view5.png",
                        help="右图路径")
    parser.add_argument("--method", type=str, default="sgbm", choices=["sgbm", "sad"],
                        help="匹配算法：sgbm | sad (SAD即BlockMatch BM)")
    parser.add_argument("--max_disp", type=int, default=128, help="最大视差，必须是16的倍数")
    parser.add_argument("--block", type=int, default=7, help="匹配块大小，奇数")

    args = parser.parse_args()
    return args


def read_stereo_images(path_left: str, path_right: str):
    """读取左右立体图像，返回彩色、灰度图"""
    img_l = cv2.imread(path_left)
    img_r = cv2.imread(path_right)
    if img_l is None or img_r is None:
        raise FileNotFoundError("图像读取失败，请检查路径")
    gray_l = cv2.cvtColor(img_l, cv2.COLOR_BGR2GRAY)
    gray_r = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY)
    return img_l, img_r, gray_l, gray_r


def compute_sgbm_disparity(gray_left, gray_right, max_disp=128, block_size=7):
    """
    SGBM半全局立体匹配，返回视差图
    :param gray_left: 左灰度图
    :param gray_right: 右灰度图
    :param max_disp: 最大视差，必须是16的倍数
    :param block_size: 匹配块大小，奇数
    """
    stereo = cv2.StereoSGBM_create(
        minDisparity=0,
        numDisparities=max_disp,
        blockSize=block_size,
        P1=8 * block_size * block_size,
        P2=32 * block_size * block_size,
        disp12MaxDiff=1,
        uniquenessRatio=10,
        speckleWindowSize=100,
        speckleRange=2,
        preFilterCap=63,
        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
    )
    disp_scaled = stereo.compute(gray_left, gray_right)
    disp_float = disp_scaled.astype(np.float32) / 16.0
    disp_float[disp_float < 0] = 0
    disp_uint16 = disp_float.astype(np.uint16)
    return disp_uint16, disp_scaled, stereo


def compute_sad_disparity(gray_left, gray_right, max_disp=128, block_size=7):
    """
    SAD(BlockMatch BM) 局部立体匹配，返回uint16视差图
    :param gray_left: 左灰度
    :param gray_right: 右灰度
    :param max_disp: 最大视差，16倍数
    :param block_size: 块大小，奇数
    """
    stereo_bm = cv2.StereoBM_create(
        numDisparities=max_disp,
        blockSize=block_size
    )
    disp_scaled = stereo_bm.compute(gray_left, gray_right)
    disp_float = disp_scaled.astype(np.float32) / 16.0
    disp_float[disp_float < 0] = 0
    return disp_float, disp_scaled, stereo_bm

def run_disparity_algorithm(algo_name, gray_l, gray_r, max_disp, block_size):
    """调度选择对应匹配算法"""
    if algo_name.lower() == "sgbm":
        return compute_sgbm_disparity(gray_l, gray_r, max_disp, block_size)
    elif algo_name.lower() == "sad":
        return compute_sad_disparity(gray_l, gray_r, max_disp, block_size)
    else:
        raise ValueError(f"不支持的算法 {algo_name}，可选 sgbm / sad")

def disparity_visualize(disp):
    """视差图归一化可视化，输出8bit灰度图"""
    valid = disp[disp > 0]
    if len(valid) == 0:
        return np.zeros(disp.shape, dtype=np.uint8)
    d_min = np.min(valid)
    d_max = np.max(valid)
    vis = np.clip((disp - d_min) / (d_max - d_min) * 255, 0, 255).astype(np.uint8)
    return vis

def save_outputs(disp, out_dir, algo_name):
    """保存视差图、可视化"""
    save_disp_vis_path = os.path.join(out_dir, f"disp_{algo_name}.png")
    disp_vis = disparity_visualize(disp)
    cv2.imwrite(save_disp_vis_path, disp_vis)
    print(f"可视化视差图保存：{save_disp_vis_path}")

    return save_disp_vis_path


def print_statistics(disp):
    """打印有效视差像素统计信息"""
    valid_cnt = np.sum(disp > 0)
    h, w = disp.shape
    total = h * w
    print(f"有效视差像素：{valid_cnt}/{total}  ({valid_cnt / total * 100:.1f}%)")

def main():
    # 1.解析参数
    args = parse_args()
    path_left = args.left
    path_right = args.right
    method = args.method
    max_disp = args.max_disp
    block_size = args.block
    out_dir = os.path.dirname(path_left)

    # 2.读取图像
    _, _, gray_l, gray_r = read_stereo_images(path_left, path_right)

    # 3.执行立体匹配
    start = cv2.getTickCount()
    disp, disp_raw_int16, matcher = run_disparity_algorithm(method, gray_l, gray_r, max_disp, block_size)

    end = cv2.getTickCount()
    cost_s = (end - start) / cv2.getTickFrequency()
    print(f"{method.upper()} 匹配总耗时：{cost_s:.2f} s")

    # 4.保存输出文件
    save_outputs(disp, out_dir, method)

    # 5.输出统计
    print_statistics(disp)


if __name__ == "__main__":
    main()
