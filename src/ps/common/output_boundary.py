"""The hardware returns three INT8 NCHW heads; only the model boundary is float."""
import numpy as np

def dequantize_heads(arena,program):
    view=np.asarray(arena).view(np.int8).reshape(-1)
    heads={}
    for desc in program['heads']:
        n=int(np.prod(desc['shape']));raw=view[desc['offset']:desc['offset']+n].reshape(desc['shape'])
        heads[desc['blob']]=raw.astype(np.float32)*np.asarray(desc['scales'],dtype=np.float32)[:,None,None]
    return [heads[name][None] for name in ('980','1013','1046')]

def ncnn_output(heads):
    """Equivalent to the final Reshape/Concat(axis=1)/Permute of the NCNN file."""
    if [tuple(x.shape) for x in heads]!=[(1,6,60,80),(1,6,30,40),(1,6,15,20)]:
        raise ValueError('expected the three fixed-size YOLOX heads')
    return np.concatenate([x[0].reshape(6,-1) for x in heads],axis=1).T.copy()
