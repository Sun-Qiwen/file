import sys, os
sys.path.append(os.pardir)
import numpy as np
from collections import OrderedDict
from layers import *
import pickle

class ConvNet:
    # 初始化
    def __init__(self, input_dim=(1, 28, 28),
                 conv_param={'filter_num': 30, 'filter_size': 5, 'filter_pad': 0, 'filter_stride': 1},
                 hidden_size=100, output_size=10, weight_init_std=0.01):

        filter_num = conv_param['filter_num']
        filter_size = conv_param['filter_size']
        filter_pad = conv_param['filter_pad']
        filter_stride = conv_param['filter_stride']

        input_size = input_dim[1]
        conv_output_size = input_size - filter_size + 1
        pool_output_size = filter_num * (conv_output_size // 2) * (conv_output_size // 2)

        # 初始化权重
        self.params = {}
        self.params['W1'] = weight_init_std * \
                            np.random.randn(filter_num, input_dim[0], filter_size, filter_size)
        self.params['b1'] = np.zeros(filter_num)
        self.params['W2'] = weight_init_std * \
                            np.random.randn(pool_output_size, hidden_size)
        self.params['b2'] = np.zeros(hidden_size)
        self.params['W3'] = weight_init_std * \
                            np.random.randn(hidden_size, output_size)
        self.params['b3'] = np.zeros(output_size)

        # 生成层
        self.layers = OrderedDict()  # 使用OrderedDict会根据放入元素的先后顺序进行排序
        self.layers['Conv1'] = Convolution(self.params['W1'], self.params['b1'],
                                           conv_param['filter_stride'], conv_param['filter_pad'])
        self.layers['Relu1'] = Relu()
        self.layers['Pool1'] = Pooling(pool_h=2, pool_w=2, stride=2)
        self.layers['Affine1'] = Affine(self.params['W2'], self.params['b2'])
        self.layers['Relu2'] = Relu()
        self.layers['Affine2'] = Affine(self.params['W3'], self.params['b3'])

        self.last_layer = SoftmaxWithLoss()

    def forward(self, x):

        for layer in self.layers.values():
            x = layer.forward(x)

        return x

    def loss(self, x, t):
        y = self.forward(x)
        loss = self.last_layer.forward(y, t)

        return loss

    def accuracy(self, x, t, batch_size=100):
        # 计算精度
        # y = self.forward(x)
        #
        # acc = np.argmax(y, axis=-1) == np.argmax(t, axis=-1) # mp.argmax(),获取最大值的索引，axis=-1表示从水平方向
        #
        # return acc.mean()
        
        if t.ndim != 1 : t = np.argmax(t, axis=1)

        acc = 0.0

        for i in range(0, x.shape[0], batch_size):
            tx = x[i:i+batch_size]
            tt = t[i:i+batch_size]
            y = self.forward(tx)
            y = np.argmax(y, axis=1)
            acc += np.sum(y == tt)

        return acc / x.shape[0]


    def numerical_gradient(self, x, t):
        """
        数值微分方法
        :param x:
        :param t:
        :return:
        """
        loss_w = lambda w: self.loss(x, t) # 匿名函数

        grads = {}
        for idx in (1, 2, 3):
            grads['W' + str(idx)] = numerical_gradient(loss_w, self.params['W' + str(idx)])
            grads['b' + str(idx)] = numerical_gradient(loss_w, self.params['b' + str(idx)])

        return grads

    def gradient(self, x, t):
        """求梯度（误差反向传播法）

        Parameters
        ----------
        x : 输入数据
        t : 教师标签

        Returns
        -------
        具有各层的梯度的字典变量
            grads['W1']、grads['W2']、...是各层的权重
            grads['b1']、grads['b2']、...是各层的偏置
        """
        # forward
        self.loss(x, t)

        # backward
        dout = 1
        dout = self.last_layer.backward(dout)

        layers = list(self.layers.values())
        layers.reverse()
        for layer in layers:
            dout = layer.backward(dout)

        # 设定
        grads = {}
        grads['W1'], grads['b1'] = self.layers['Conv1'].dW, self.layers['Conv1'].db
        grads['W2'], grads['b2'] = self.layers['Affine1'].dW, self.layers['Affine1'].db
        grads['W3'], grads['b3'] = self.layers['Affine2'].dW, self.layers['Affine2'].db

        return grads
        
    def save_params(self, file_name="params.pkl"):
        params = {}
        for key, val in self.params.items():
            params[key] = val
        with open(file_name, 'wb') as f:
            pickle.dump(params, f)

