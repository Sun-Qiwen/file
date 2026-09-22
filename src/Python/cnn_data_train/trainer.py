# coding: utf-8
import sys, os
sys.path.append(os.pardir)  # 为了导入父目录的文件而进行的设定
import numpy as np
from optimizer import *

class Trainer:
    """进行神经网络的训练的类
    """
    def __init__(self, network, x_train, t_train, x_test, t_test,
                 epochs=20, mini_batch_size=100,
                 optimizer='SGD', optimizer_param={'lr':0.01}, 
                 evaluate_sample_num_per_epoch=None, verbose=True):
        self.network = network
        self.verbose = verbose
        self.x_train = x_train
        self.t_train = t_train
        self.x_test = x_test
        self.t_test = t_test
        self.epochs = epochs
        self.batch_size = mini_batch_size
        self.evaluate_sample_num_per_epoch = evaluate_sample_num_per_epoch

        # optimzer
        optimizer_class_dict = {'sgd':SGD, 'momentum':Momentum, 'nesterov':Nesterov,
                                'adagrad':AdaGrad, 'rmsprpo':RMSprop, 'adam':Adam}
        self.optimizer = optimizer_class_dict[optimizer.lower()](**optimizer_param)
        
        self.train_size = x_train.shape[0]  # 60000
        self.iter_per_epoch = max(self.train_size / mini_batch_size, 1) # 600
        self.max_iter = int(epochs * self.iter_per_epoch) # 600*20 = 12000
        self.current_iter = 0
        self.current_epoch = 0
        
        self.train_loss_list = []
        self.train_acc_list = []
        self.test_acc_list = []

    def train_step(self):
        """
        训练过程：
        1、从总样本中挑选 Mini-batch
        2、计算梯度
        3、更新参数
        4、重复
        """
        batch_mask = np.random.choice(self.train_size, self.batch_size) #（60000, 100）
        x_batch = self.x_train[batch_mask]
        t_batch = self.t_train[batch_mask]

        # 用数值微分的方法计算梯度
        # grads = self.network.numerical_gradient(x_batch, t_batch)
        # 用反向传播计算梯度
        grads = self.network.gradient(x_batch, t_batch)

        # 用随机梯度下降法进行更新参数
        self.optimizer.update(self.network.params, grads)
        # 求损失函数的值
        loss = self.network.loss(x_batch, t_batch)

        self.train_loss_list.append(loss)

        if self.verbose: print("train loss:" + str(loss))

        # 当训练完一个epoch后，加入测试数据集，看识别率
        if self.current_iter % self.iter_per_epoch == 0:

            self.current_epoch += 1
            
            x_train_sample, t_train_sample = self.x_train, self.t_train
            x_test_sample, t_test_sample = self.x_test, self.t_test
            if not self.evaluate_sample_num_per_epoch is None:
                t = self.evaluate_sample_num_per_epoch
                x_train_sample, t_train_sample = self.x_train[:t], self.t_train[:t]
                x_test_sample, t_test_sample = self.x_test[:t], self.t_test[:t]
                
            train_acc = self.network.accuracy(x_train_sample, t_train_sample)
            test_acc = self.network.accuracy(x_test_sample, t_test_sample)
            self.train_acc_list.append(train_acc)
            self.test_acc_list.append(test_acc)

            if self.verbose: print("=== epoch:" + str(self.current_epoch) + ", train acc:" + str(train_acc) + ", test acc:" + str(test_acc) + " ===")
        self.current_iter += 1

    def train(self):
        for i in range(self.max_iter):
            self.train_step()

        test_acc = self.network.accuracy(self.x_test, self.t_test)

        if self.verbose:
            print("=============== Final Test Accuracy ===============")
            print("test acc:" + str(test_acc))

