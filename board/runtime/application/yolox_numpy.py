"""YOLOX board preprocessing and postprocessing; NumPy/OpenCV only.

The detector session returns three raw NCHW heads (strides 8/16/32). Their last
two channels already contain the objectness/class probabilities.
"""
import math

import cv2
import numpy as np


def _build_input_int8_lut():
    # Evaluate the immutable original float32 operations once, in their original
    # order. uint8 resize/canvas values have exactly 256 possibilities/channel.
    rgb=np.arange(256,dtype=np.uint8).astype(np.float32)[:,None]/255.
    rgb=(rgb-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
    ratio=rgb/np.float32(2.640000104904175/127.)
    table=np.clip(np.sign(ratio)*np.floor(np.abs(ratio)+.5),-127,127).astype(np.int8).T.copy()
    table.flags.writeable=False
    return table


_INPUT_INT8_LUT=_build_input_int8_lut()
# OpenCV applies each BGR channel's table in place on the private uint8 canvas.
# The uint8 view carries the exact signed output bytes; no arithmetic changes.
_INPUT_INT8_BGR_LUT=_INPUT_INT8_LUT[::-1].T.copy().view(np.uint8).reshape(1,256,3)
_INPUT_INT8_BGR_LUT.flags.writeable=False


def can_prepare_input_int8(bgr,size=640):
    return (isinstance(bgr,np.ndarray) and bgr.dtype==np.uint8
            and bgr.shape==(480,640,3) and type(size) is int and size==640)


def prepare_input_int8(bgr,size=640):
    if not can_prepare_input_int8(bgr,size):
        raise ValueError('Fused YOLOX input requires uint8 BGR [480,640,3] and size 640')
    # Keep the original OpenCV resize call, including its supported stride
    # domain. At this exact geometry scale=1 and the old canvas is fully filled.
    canvas=cv2.resize(bgr,(640,480),interpolation=cv2.INTER_LINEAR)
    tensor=np.empty((1,3,480,640),dtype=np.int8)
    cv2.LUT(canvas,_INPUT_INT8_BGR_LUT,dst=canvas)
    cv2.mixChannels([canvas],[tensor[0,channel].view(np.uint8) for channel in range(3)],
                    [2,0,1,1,0,2])
    return tensor,1.


def prepare_input(bgr, size=640):
    if (not isinstance(bgr,np.ndarray) or bgr.dtype!=np.uint8 or bgr.ndim!=3
            or bgr.shape[2]!=3 or min(bgr.shape[:2])<1):
        raise ValueError('YOLOX requires a nonempty uint8 BGR image')
    if type(size) is not int or size<32 or size%32:
        raise ValueError('YOLOX size must be a positive multiple of 32')
    height,width=bgr.shape[:2]
    scale=float(size)/max(height,width)
    rh,rw=max(1,int(height*scale)),max(1,int(width*scale))
    ph,pw=(rh+31)//32*32,(rw+31)//32*32
    canvas=np.full((ph,pw,3),114,dtype=np.uint8)
    canvas[:rh,:rw]=cv2.resize(bgr,(rw,rh),interpolation=cv2.INTER_LINEAR)
    # Write RGB directly into the final contiguous NCHW allocation. Keep each
    # float32 divide/subtract/divide in its original order (no folded affine).
    rgb=np.empty((1,3,ph,pw),dtype=np.float32)
    rgb[0]=canvas[:,:,::-1].transpose(2,0,1)
    rgb/=255.
    rgb-=np.array([.485,.456,.406],np.float32)[None,:,None,None]
    rgb/=np.array([.229,.224,.225],np.float32)[None,:,None,None]
    return rgb,scale


def _nms(boxes,scores,threshold):
    order=np.argsort(-scores,kind='stable')
    areas=(boxes[:,2]-boxes[:,0])*(boxes[:,3]-boxes[:,1])
    keep=[]
    while order.size and len(keep)<10:
        current=int(order[0]);keep.append(current)
        rest=order[1:]
        left=np.maximum(boxes[current,:2],boxes[rest,:2])
        right=np.minimum(boxes[current,2:],boxes[rest,2:])
        intersection=np.maximum(right-left,0).prod(axis=1)
        union=areas[current]+areas[rest]-intersection
        overlap=np.divide(intersection,union,out=np.zeros_like(intersection),where=union>0)
        order=rest[overlap<=threshold]
    return keep


def decode_heads(heads,padded_shape,confidence=.3,nms_threshold=.45):
    if len(heads)!=3:
        raise ValueError('Expected three YOLOX heads at strides 8,16,32')
    if any(isinstance(x,bool) or not math.isfinite(x) or not 0<x<=1
           for x in (confidence,nms_threshold)):
        raise ValueError('YOLOX score/NMS thresholds must be in (0,1]')
    ph,pw=map(int,padded_shape)
    if min(ph,pw)<32 or ph%32 or pw%32:
        raise ValueError('YOLOX padded dimensions must be positive multiples of 32')
    rows=[]
    for head,stride in zip(heads,(8,16,32)):
        head=np.asarray(head,dtype=np.float32)
        if head.shape!=(1,6,ph//stride,pw//stride) or not np.isfinite(head).all():
            raise ValueError('Unexpected shape or nonfinite YOLOX raw head')
        flat=head[0].transpose(1,2,0).reshape(-1,6)
        score=flat[:,4]*flat[:,5]
        mask=score>confidence
        if not mask.any():continue
        gy,gx=np.indices((ph//stride,pw//stride),dtype=np.float32)
        cx=(flat[mask,0]+gx.ravel()[mask])*stride
        cy=(flat[mask,1]+gy.ravel()[mask])*stride
        width=np.exp(flat[mask,2])*stride
        height=np.exp(flat[mask,3])*stride
        proposal=np.stack((cx-width/2,cy-height/2,cx+width/2,cy+height/2,score[mask]),axis=1)
        if not np.isfinite(proposal).all():
            raise ValueError('Nonfinite YOLOX decoded box')
        rows.append(proposal)
    if not rows:return np.empty((0,5),dtype=np.float32)
    rows=np.concatenate(rows,axis=0)
    return rows[_nms(rows[:,:4],rows[:,4],nms_threshold)]


def map_boxes(rows,image_shape,scale):
    # PC converts each float32 head coordinate to a Python float before undoing
    # resize. Preserve that float64 division before integer crop-bound rounding.
    rows=np.array(rows,dtype=np.float64,copy=True)
    if rows.ndim!=2 or rows.shape[1]!=5 or not np.isfinite(rows).all():
        raise ValueError('Expected finite YOLOX rows with shape (K,5)')
    height,width=image_shape[:2]
    if min(height,width)<1 or not math.isfinite(scale) or scale<=0:
        raise ValueError('Invalid source image geometry')
    rows[:,:4]/=scale
    rows[:,[0,2]]=np.clip(rows[:,[0,2]],0,width-1)
    rows[:,[1,3]]=np.clip(rows[:,[1,3]],0,height-1)
    return rows
