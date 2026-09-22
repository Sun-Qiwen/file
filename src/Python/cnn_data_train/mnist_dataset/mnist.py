import numpy as np
import gzip
import matplotlib.pyplot as plt

img_size = 784
# 导入图片
def load_img(filename):
    with gzip.open(filename, 'rb') as f:
        data = np.frombuffer(f.read(), np.uint8, offset=16)     # offset=16, 为了过滤文件头信息
    print("Done!")
    data = data.reshape(-1, img_size)

    return data
# 导入标签
def load_label(filename):
    with gzip.open(filename, 'rb') as f:
        label = np.frombuffer(f.read(), np.uint8, offset=8)

    return label

def load_mnist():
    # 先下载好 MNIST 数据集到本地，如果使用 python 代码下载，速度太慢了
    # 下载地址：http://yann.lecun.com/exdb/mnist/
    dataset = {}
    dataset['train_img'] = load_img("./data_train/python_train/mnist_dataset/train-images-idx3-ubyte.gz")
    dataset['train_label'] = load_label("./data_train/python_train/mnist_dataset/train-labels-idx1-ubyte.gz")
    dataset['test_img'] = load_img("./data_train/python_train/mnist_dataset/t10k-images-idx3-ubyte.gz")
    dataset['test_label'] = load_label("./data_train/python_train/mnist_dataset/t10k-labels-idx1-ubyte.gz")
    # 将图像转换成多维数组
    for key in ('train_img', 'test_img'):
        dataset[key] = dataset[key].reshape(-1, 1, 28, 28)

    return (dataset['train_img'], dataset['train_label']), (dataset['test_img'], dataset['test_label'])


# 以下为测试代码
# (x_train, t_train), (x_test, t_test) = load_mnist()
# # print(x_train.shape, t_train.shape, x_test.shape, t_test.shape)
#
# plt.imshow(x_train[10].reshape(28, 28), 'gray')
# plt.title('Number is : ' + str(t_train[10]))
# plt.show()