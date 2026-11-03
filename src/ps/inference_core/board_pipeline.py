"""BGR frames to hand landmarks and pointing angles using injected hardware sessions.

The application owns the overlay and supplies its session factory. NumPy/OpenCV
perform preprocessing, target selection and output decoding on the PS.
"""
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np

from geometry import (HandDetection, TargetSelector, box_iou, expanded_square_bounds,
                      resize_matrix, suppress_duplicate_hands)
from yolox_numpy import (prepare_input, prepare_input_int8, can_prepare_input_int8,
                         decode_heads, map_boxes)


def rgb565_to_bgr(raw):
    raw = np.asarray(raw, dtype=np.uint16)
    return np.stack(((raw & 31) << 3, ((raw >> 5) & 63) << 2,
                     ((raw >> 11) & 31) << 3), axis=-1).astype(np.uint8)


def prepare_crop(frame, box, margin=.35, size=96):
    if type(size) is not int or size not in (96,128):
        raise ValueError('CNN crop size must be 96 or 128')
    bounds = expanded_square_bounds(box, frame.shape, margin)
    left, top, right, bottom = bounds
    side = right - left
    h, w = frame.shape[:2]
    gray = np.full((side, side), 128, dtype=np.uint8)
    x0, y0, x1, y1 = max(left,0), max(top,0), min(right,w), min(bottom,h)
    # BGR2GRAY is per pixel and maps (128,128,128) exactly to 128; transform
    # the intersecting ROI before padding rather than materializing BGR padding.
    if x1 > x0 and y1 > y0:
        gray[y0-top:y1-top, x0-left:x1-left] = cv2.cvtColor(
            np.asarray(frame[y0:y1, x0:x1], dtype=np.uint8), cv2.COLOR_BGR2GRAY)
    working = min(side, 384)
    if working != side:
        gray = cv2.resize(gray, (working,working), interpolation=cv2.INTER_AREA)
    image = cv2.resize(gray, (size,size), interpolation=cv2.INTER_AREA if working>size else cv2.INTER_LINEAR)
    offset = np.array([[1,0,-left],[0,1,-top],[0,0,1]], dtype=np.float64)
    matrix = resize_matrix(working,working,size,size) @ resize_matrix(side,side,working,working) @ offset
    return image, matrix, bounds


def decode_heatmaps(logits):
    maps = np.asarray(logits, dtype=np.float64)
    if maps.ndim==4 and maps.shape[:2]==(1,2):maps=maps[0]
    if maps.ndim!=3 or maps.shape[0]!=2 or min(maps.shape[1:])<3:
        raise ValueError('Expected one pair of heatmaps: [1,2,H,W] or [2,H,W]')
    height,width=maps.shape[1:]
    decoded = []
    for heatmap in maps:
        flat = heatmap.reshape(-1)
        peak = int(flat.argmax())
        center = flat[peak]
        coordinates = []
        for axis, stride, bound in [(peak % width, 1, width), (peak // width, width, height)]:
            low, high = flat[max(0,peak-stride)], flat[min(len(flat)-1,peak+stride)]
            curvature = low - 2*center + high
            offset = 0.
            if 0 < axis < bound-1 and curvature < -1e-6:
                offset = float(np.clip(.5*(low-high)/curvature, -.5, .5))
            for edge, direction in [(0,1),(bound-1,-1)]:
                a = flat[min(len(flat)-1,max(0,peak+direction*stride))]
                b = flat[min(len(flat)-1,max(0,peak+2*direction*stride))]
                second = center - 2*a + b
                if axis == edge and second < -1e-6:
                    offset = direction * float(np.clip((3*center-4*a+b)/(2*second), 0, .5))
            coordinates.append((axis+offset)/(bound-1))
        decoded.append(coordinates)
    return np.array(decoded)


class Pipeline:
    def __init__(self, root=None, *, session_factory):
        self.root = Path(root or Path(__file__).resolve().parent)
        self.contract = json.loads((self.root/'interface_contract.json').read_text(encoding='utf-8'))
        self.input_size=self.contract['cnn']['input']['shape'][-1]
        if (self.input_size not in (96,128) or self.contract['cnn']['input']['shape']!=[1,1,self.input_size,self.input_size]
                or self.contract['cnn']['architecture']!=f'heatmap{self.input_size}_v1'):
            raise ValueError('Incompatible CNN architecture/input contract')
        detector=self.contract['detector']
        if detector['architecture']!='yolox_hand_relu' or detector['imgsz']!=640:
            raise ValueError('This package requires the YOLOX hand ReLU 640 contract')
        self.detector = session_factory('yolox')
        if (self.detector.get_inputs()[0].shape[:2]!=[1,3]
                or len(self.detector.get_outputs())!=3
                or any(x.shape[:2]!=[1,6] for x in self.detector.get_outputs())):
            raise ValueError('Detector session must return three raw NCHW YOLOX heads')
        self.cnn = session_factory('cnn')
        if (self.cnn.get_inputs()[0].shape!=self.contract['cnn']['input']['shape']
                or [x.shape for x in self.cnn.get_outputs()]!=[
                    self.contract['cnn']['outputs']['heatmap_logits'],self.contract['cnn']['outputs']['valid_logits']]):
            raise ValueError('Session tensor shapes do not match interface_contract.json')
        self.selector = TargetSelector(minimum_iou=None, lost_grace_frames=12, recovery_confirm_frames=3, recover_ambiguity=True)
        self.shape = None
        self.reset()

    def reset(self):
        self.selector.reset()
        self.last_box = self.reacquire_box = None
        self.reacquire_streak = 0

    def detect(self, frame):
        size=self.contract['detector']['imgsz']
        if (can_prepare_input_int8(frame,size)
                and getattr(self.detector,'supports_quantized_input',False)
                and callable(getattr(self.detector,'run_quantized',None))):
            prepared_start=time.perf_counter_ns()
            tensor,scale=prepare_input_int8(frame,size)
            prepared_ns=time.perf_counter_ns()-prepared_start
            heads=self.detector.run_quantized(None,{self.detector.get_inputs()[0].name:tensor},
                                               preprocess_ns=prepared_ns)
        else:
            tensor,scale = prepare_input(frame,size)
            heads = self.detector.run(None, {self.detector.get_inputs()[0].name:tensor})
        rows = decode_heads(heads,tensor.shape[2:],self.contract['detector']['confidence'],
                            self.contract['detector']['nms_threshold'])
        rows = map_boxes(rows,frame.shape,scale)
        detections = []
        for row in rows:
            try:
                detections.append(HandDetection(tuple(row[:4]),float(row[4])))
            except ValueError:
                continue
        return suppress_duplicate_hands(detections)

    def run_frame(self, frame, *, timestamp=None):
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError('Supply continuous-tone uint8 BGR pixels')
        timestamp = time.perf_counter() if timestamp is None else float(timestamp)
        if self.shape != frame.shape[:2]:
            self.reset(); self.shape = frame.shape[:2]
        detections = self.detect(frame)
        selection = self.selector.select(detections, frame.shape)
        if self.selector.blocked_status is not None:
            if len(detections) == 1:
                box = detections[0].xyxy
                match = self.reacquire_box is not None and (self.selector.minimum_iou is None or box_iou(self.reacquire_box,box) >= self.selector.minimum_iou)
                self.reacquire_streak = self.reacquire_streak+1 if match else 1
                self.reacquire_box = box
                if self.reacquire_streak >= 3:
                    self.reset(); selection = self.selector.select(detections,frame.shape)
            else:
                self.reacquire_box = None; self.reacquire_streak = 0
        else:
            self.reacquire_box = None; self.reacquire_streak = 0
        candidate = selection.detection or selection.recovery_candidate
        if candidate is not None:
            l,t,r,b = expanded_square_bounds(candidate.xyxy,frame.shape,.35)
            if any(d is not candidate and l <= (d.xyxy[0]+d.xyxy[2])/2 < r
                   and t <= (d.xyxy[1]+d.xyxy[3])/2 < b for d in detections):
                selection = self.selector.reject_ambiguous()
        status = selection.status
        if self.selector.blocked_status is not None:
            status = 'searching_target'
        selected = selection.detection
        if selected is not None:
            box, margin = selected.xyxy, .35
            self.last_box = box
        elif self.last_box is not None:
            box, margin = self.last_box, .35
        else:
            box, margin = (0,0,frame.shape[1],frame.shape[0]), 0.
        image, matrix, bounds = prepare_crop(frame,box,margin,size=self.input_size)
        tensor = image.astype(np.float32)[None,None]/255
        heatmaps, valid = self.cnn.run(['heatmap_logits','valid_logits'], {'image':tensor})
        normalized = decode_heatmaps(heatmaps)
        pixels = np.c_[normalized*(self.input_size-1),np.ones(2)] @ np.linalg.inv(matrix).T
        points = pixels[:,:2]
        logit = float(valid.reshape(-1)[0])
        probability = 1/(1+math.exp(-logit)) if logit >= 0 else math.exp(logit)/(1+math.exp(logit))
        angle = None
        if selected is not None:
            if probability < .5: status = 'not_pointing'
            elif (not np.isfinite(points).all() or (points<0).any()
                  or (points[:,0]>frame.shape[1]-1).any() or (points[:,1]>frame.shape[0]-1).any()): status = 'outside_image'
            elif np.linalg.norm((normalized[0]-normalized[1])*(self.input_size-1)) < 1: status = 'points_too_close'
            else:
                status = 'ok'
                dx,dy = points[0]-points[1]
                angle = math.degrees(math.atan2(dx,-dy))%360
        return dict(status=status,angle_degrees=angle,valid_probability=probability,points=points.tolist(),
                    hands=len(detections),crop_bounds=list(bounds),cnn_ran=True,
                    frame_timestamp=timestamp)
