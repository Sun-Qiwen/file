from __future__ import annotations
from dataclasses import dataclass
import math
import numbers
import numpy as np

DEFAULT_CROP_MARGIN = 0.35

@dataclass(frozen=True)
class HandDetection:
    xyxy: tuple[float,float,float,float]
    confidence: float

    def __post_init__(self):
        box=tuple(float(x) for x in self.xyxy)
        if (len(box)!=4 or not all(math.isfinite(x) for x in box)
                or box[2]<=box[0] or box[3]<=box[1]
                or not math.isfinite(self.confidence) or not 0<=self.confidence<=1):
            raise ValueError("Invalid hand detection")
        object.__setattr__(self,"xyxy",box)


@dataclass(frozen=True)
class Selection:
    detection: HandDetection | None
    status: str
    recovery_candidate: HandDetection | None = None  # Not yet eligible for inference.


def validate_margin(margin):
    if isinstance(margin,bool) or not isinstance(margin,numbers.Real) or not math.isfinite(margin) or not 0<=margin<=1:
        raise ValueError("Crop margin must be finite and between 0 and 1")
    return float(margin)


def expanded_square_bounds(box, image_shape, margin=DEFAULT_CROP_MARGIN):
    """Return integer, exclusive bounds; pad outside the image rather than distort."""
    margin=validate_margin(margin)
    h,w=image_shape[:2]
    if h<1 or w<1: raise ValueError("Empty image")
    x0,y0,x1,y1=map(float,box)
    if (not all(math.isfinite(v) for v in (x0,y0,x1,y1)) or x1<=x0 or y1<=y0
            or x1<=0 or y1<=0 or x0>=w or y0>=h):
        raise ValueError("Invalid or nonintersecting hand box")
    x0,y0,x1,y1=max(0,x0),max(0,y0),min(w,x1),min(h,y1)
    side=max(2,math.ceil(max(x1-x0,y1-y0)*(1+2*margin)))
    left=math.floor((x0+x1-side)/2); top=math.floor((y0+y1-side)/2)
    return left,top,left+side,top+side


def box_iou(first,second):
    ax0,ay0,ax1,ay1=first; bx0,by0,bx1,by1=second
    intersection=max(0,min(ax1,bx1)-max(ax0,bx0))*max(0,min(ay1,by1)-max(ay0,by0))
    union=(ax1-ax0)*(ay1-ay0)+(bx1-bx0)*(by1-by0)-intersection
    return intersection/union if union>0 else 0.


def suppress_duplicate_hands(detections):
    # Remove duplicate detections whose box coordinates match exactly.
    # Nearby/high-IoU boxes may be distinct real hands and must remain visible
    # to conservative target/ambiguity checks.
    kept=[]
    for detection in sorted(detections,key=lambda d:d.confidence,reverse=True):
        if all(detection.xyxy!=previous.xyxy for previous in kept):
            kept.append(detection)
    return kept


class TargetSelector:
    """Acquire a unique hand anywhere in the image; tolerate short gaps optionally.

    minimum_iou=None accepts a unique hand without comparing box overlap.
    With a numeric minimum, matching uses box overlap. Runtime may confirm the
    same target after transient ambiguity; expired gaps need explicit reset.
    """
    def __init__(self, *, minimum_iou=.2, lost_grace_frames=0, recovery_confirm_frames=3,
                 recover_ambiguity=False):
        if minimum_iou is not None and (not math.isfinite(minimum_iou) or not 0<minimum_iou<=1):
            raise ValueError("Invalid target selection settings")
        for value,minimum in ((lost_grace_frames,0),(recovery_confirm_frames,1)):
            if isinstance(value,bool) or not isinstance(value,numbers.Integral) or value<minimum:
                raise ValueError("Recovery frame counts must be integers: grace >= 0, confirmation >= 1")
        self.minimum_iou=None if minimum_iou is None else float(minimum_iou)
        self.lost_grace_frames=int(lost_grace_frames)
        self.recovery_confirm_frames=int(recovery_confirm_frames)
        self.recover_ambiguity=bool(recover_ambiguity)
        self.reset()

    def reset(self):
        self.previous=None; self.blocked_status=None; self.frame_shape=None
        self.recovery_age=0; self.recovery_streak=0
        self.recovery_ambiguity=False
        self._previous_before_frame=None; self._age_before_frame=0

    def reject_ambiguous(self):
        """Pause this frame, including a crop-neighbor rejection after select().

        Roll back provisional selection/confirmation before counting this frame
        once. Repeated extra detections cannot move the anchor or renew the gap.
        """
        self.previous=self._previous_before_frame
        self.recovery_age=self._age_before_frame+1
        self.recovery_streak=0
        self.recovery_ambiguity=True
        if (not self.recover_ambiguity or self.previous is None
                or self.recovery_age>self.lost_grace_frames):
            self.blocked_status='ambiguous_target'
        return Selection(None,'ambiguous_target')

    def select(self,detections,image_shape):
        shape=tuple(image_shape[:2])
        if len(shape)!=2 or min(shape)<1:
            raise ValueError("Target selection requires a nonempty image shape")
        if self.frame_shape!=shape:
            self.reset(); self.frame_shape=shape
        self._previous_before_frame=self.previous
        self._age_before_frame=self.recovery_age
        if self.blocked_status is not None:
            return Selection(None,self.blocked_status)
        if self.previous is None:
            if len(detections)!=1:
                status='no_hand' if not detections else 'choose_one_hand'
                return Selection(None,status)
            selected=detections[0]
        else:
            matches=list(detections) if self.minimum_iou is None else [d for d in detections if box_iou(self.previous.xyxy,d.xyxy)>=self.minimum_iou]
            if len(matches)>1:
                return self.reject_ambiguous()
            # Count every frame since the first miss, including confirmation
            # frames. Intermittent matches cannot extend the grace indefinitely.
            if self.recovery_age:
                self.recovery_age+=1
            elif not matches:
                self.recovery_age=1
            if self.recovery_age>self.lost_grace_frames:
                self.blocked_status='ambiguous_target' if self.recovery_ambiguity else 'target_lost'
                return Selection(None,self.blocked_status)
            if not matches:
                self.recovery_streak=0
                return Selection(None,'target_temporarily_lost')
            if self.recovery_age:
                # Keep matching to the last confirmed box until recovery; do
                # not drift across successive provisional candidate boxes.
                self.recovery_streak+=1
                if self.recovery_streak<self.recovery_confirm_frames:
                    return Selection(None,'confirming_target',recovery_candidate=matches[0])
                self.recovery_age=0; self.recovery_streak=0
                self.recovery_ambiguity=False
            selected=matches[0]
        self.previous=selected
        return Selection(selected,'selected')


def resize_matrix(old_width: int, old_height: int, width: int, height: int) -> np.ndarray:
    # OpenCV resize maps pixel centers: new_x = (old_x + .5) * scale - .5.
    sx, sy = width / old_width, height / old_height
    return np.array([[sx, 0, (sx - 1) / 2],
                     [0, sy, (sy - 1) / 2], [0, 0, 1]], dtype=np.float64)
