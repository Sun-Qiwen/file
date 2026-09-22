import numpy as np

# a = np.zeros(30)
# print(a.shape)
# print(a)

# a = np.random.randn(100, 10)
# print(a.shape)
# print(a)
dout = np.random.rand(3,2)
print(dout)
print(np.sum(dout, axis=0))