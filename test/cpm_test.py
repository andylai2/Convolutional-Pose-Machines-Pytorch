import torch
import numpy as np
import cv2
import math
import cpm_model
import os
import glob

stride = 8
sigma = 3.0


def construct_model(pre_model_path):

    model = cpm_model.CPM(k=14)
    state_dict = torch.load(pre_model_path)['state_dict']
    from collections import OrderedDict
    new_state_dict = OrderedDict()
    # print(state_dict)
    print('Populating State Dict')
    for k, v in state_dict.items():
        #name = k[7:]
        name = k
        new_state_dict[name] = v
    model.load_state_dict(new_state_dict)
    #model = torch.nn.DataParallel(model, device_ids=[0]).cuda()

    return model


def get_kpts(maps, img_h = 368.0, img_w = 368.0):

    # maps (1,15,46,46)
    maps = maps.clone().cpu().data.numpy()
    map_6 = maps[0]

    kpts = []
    conf = []
    for m in map_6[1:]:
        h, w = np.unravel_index(m.argmax(), m.shape)
        x = int(w * img_w / m.shape[1])
        y = int(h * img_h / m.shape[0])
        kpts.append([x,y])
        conf.append([np.amax(m)])
    return kpts,conf


def draw_paint(img_path, kpts):

    colors = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], \
              [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255]]
    limbSeq = [[13, 12], [12, 9], [12, 8], [9, 10], [8, 7], [10, 11], [7, 6], [12, 3], [12, 2], [2, 1], [1, 0], [3, 4],
               [4, 5]]

    im = cv2.imread(img_path)
    # draw points
    for k in kpts:
        x = k[0]
        y = k[1]
        cv2.circle(im, (x, y), radius=1, thickness=-1, color=(0, 0, 255))

    # draw lines
    for i in range(len(limbSeq)):
        cur_im = im.copy()
        limb = limbSeq[i]
        [Y0, X0] = kpts[limb[0]]
        [Y1, X1] = kpts[limb[1]]
        mX = np.mean([X0, X1])
        mY = np.mean([Y0, Y1])
        length = ((X0 - X1) ** 2 + (Y0 - Y1) ** 2) ** 0.5
        angle = math.degrees(math.atan2(X0 - X1, Y0 - Y1))
        polygon = cv2.ellipse2Poly((int(mY), int(mX)), (int(length / 2), 4), int(angle), 0, 360, 1)
        cv2.fillConvexPoly(cur_im, polygon, colors[i])
        im = cv2.addWeighted(im, 0.4, cur_im, 0.6, 0)

    cv2.imshow('test_example', im)
    cv2.waitKey(0)
    cv2.imwrite('test_example.png', im)

def gaussian_kernel(size_w, size_h, center_x, center_y, sigma):
    gridy, gridx = np.mgrid[0:size_h, 0:size_w]
    D2 = (gridx - center_x) ** 2 + (gridy - center_y) ** 2
    return np.exp(-D2 / 2.0 / sigma / sigma)

def test_loop(model, img_dir, center):
    image_arr = image_arr = np.array(glob.glob(os.path.join(img_dir, '*.jpg')))
    image_arr = np.r_[image_arr, np.array(glob.glob(os.path.join(img_dir, '*.png')))]
    N = len(image_arr)
    est_joints = np.zeros((3,14,N)) 
    for i in range(N):
        img_path = image_arr[i]
        est_joints[:,:,i] = test_example(model, img_path, center)

    return est_joints

def test_example(model, img_path, center):

    # Read in all jpg files in image path
    print('Testing on image:', img_path)

    img = np.array(cv2.imread(img_path), dtype=np.float32)
    # h, w, c -> c, h, w
    img = torch.from_numpy(img.transpose((2, 0, 1)))
    # normalize
    mean = [128.0, 128.0, 128.0]
    std = [256.0, 256.0, 256.0]
    for t, m, s in zip(img, mean, std):
        t.sub_(m).div_(s)

    # center-map:368*368*1
    centermap = np.zeros((368, 368, 1), dtype=np.float32)
    center_map = gaussian_kernel(size_h=368, size_w=368, center_x=center[0], center_y=center[1], sigma=3)
    center_map[center_map > 1] = 1
    center_map[center_map < 0.0099] = 0
    centermap[:, :, 0] = center_map
    centermap = torch.from_numpy(centermap.transpose((2, 0, 1)))

    img = torch.unsqueeze(img, 0)
    centermap = torch.unsqueeze(centermap, 0)

    print('Evaluating Model')

    model.eval()
    input_var = torch.autograd.Variable(img)
    center_var = torch.autograd.Variable(centermap)

    print('Getting Heatmap')
    # get heatmap
    heat1, heat2, heat3, heat4, heat5, heat6 = model(input_var, center_var)

    print('Getting Keypoints')
    kpts,conf = get_kpts(heat6, img_h=368.0, img_w=368.0)
    print(kpts)
    print(np.array(kpts).T.shape)
    print(np.array(conf).T.shape)
    img_est_joints = np.r_[np.array(kpts).T,np.array(conf).T]

    # print('Drawing Image')

    # draw_paint(img_path, kpts)

    return img_est_joints

if __name__ == '__main__':

    pre_model_path = '../ckpt/cpm_latest.pth.tar'
    img_dir = './images'
    center = [184, 184]

    print('Constructing Model')
    model = construct_model(pre_model_path)
    print('Performing Inference')
    est_joints = test_loop(model, img_dir, center)
    np.savez('est_joints.npz',est_joints=est_joints)
