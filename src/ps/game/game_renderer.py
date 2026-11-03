"""DDR-only pixel renderer. The frozen source art is never re-quantized."""
from pathlib import Path
import math
import cv2
import numpy as np

class GameRenderer:
    glyph_cache={}
    def __init__(self, asset_path):
        with np.load(Path(asset_path),allow_pickle=False) as a:
            bg=a['background'].copy();car=a['car'].copy();wheel=a['wheel'].copy()
            self.coin=a['coin'].copy();self.coin_alpha=a['coin_alpha'].copy()
        if bg.shape!=(144,256) or car.shape!=(12,48,48) or self.coin.shape!=(80,80):
            raise ValueError('incompatible image dimensions')
        self.background=np.repeat(np.repeat(bg,5,axis=0),5,axis=1)
        self.sprites=[]
        self.masks=[]
        for heading in range(12):
            mask=np.repeat(np.repeat((car[heading]&65536)!=0,5,axis=0),5,axis=1)
            self.masks.append(mask)
            colors=[]
            for phase in range(4):
                sprite=(car[heading]&65535).astype(np.uint16)
                tire=(wheel[heading]&4)!=0
                tread=((wheel[heading]&3)+phase)%4==0
                sprite[tire&~tread]=0x2104
                sprite[tire&tread]=0xA514
                colors.append(np.repeat(np.repeat(sprite,5,axis=0),5,axis=1))
            self.sprites.append(colors)
        self.previous={}

    @staticmethod
    def text(frame,text,x,y,scale=1.0,color=0xffff,thickness=2):
        key=(str(text),float(scale),int(thickness))
        item=GameRenderer.glyph_cache.get(key)
        if item is None:
            (w,h),baseline=cv2.getTextSize(str(text),cv2.FONT_HERSHEY_SIMPLEX,scale,thickness)
            mask=np.zeros((h+baseline+4,w+4),np.uint8)
            cv2.putText(mask,str(text),(2,h+2),cv2.FONT_HERSHEY_SIMPLEX,scale,255,thickness,cv2.LINE_8)
            item=(mask!=0,h+2);GameRenderer.glyph_cache[key]=item
        mask,offset=item;x=int(x)-2;y=int(y)-offset
        x0,y0=max(0,x),max(0,y);x1,y1=min(frame.shape[1],x+mask.shape[1]),min(frame.shape[0],y+mask.shape[0])
        if x1>x0 and y1>y0:
            np.copyto(frame[y0:y1,x0:x1],np.uint16(color),where=mask[y0-y:y1-y,x0-x:x1-x])

    @staticmethod
    def centered(frame,text,y,scale=1.8):
        width=cv2.getTextSize(str(text),cv2.FONT_HERSHEY_SIMPLEX,scale,3)[0][0]
        GameRenderer.text(frame,text,(1024-width)//2,y,scale,thickness=3)

    def draw(self,frame,game,now,*,ready=None,preview=None,reason='WAITING'):
        if frame.shape!=(720,1280) or frame.dtype!=np.uint16:
            raise ValueError('frame must be 720x1280 RGB565')
        key=id(frame)
        old=self.previous.get(key)
        dirty=[]
        if old is None:
            frame[:]=self.background
            dirty.append((0,720))
        else:
            for x,y,w,h in old['rects']:
                frame[y:y+h,x:x+w]=self.background[y:y+h,x:x+w]
                dirty.append((y,y+h))
        x,y=int(game.x),int(game.y)
        rects=[(x,y,240,240)]
        if game.coin is not None:
            cx,cy=game.coin
            np.copyto(frame[cy:cy+80,cx:cx+80],self.coin,where=self.coin_alpha)
            rects.append((cx,cy,80,80))
        np.copyto(frame[y:y+240,x:x+240],self.sprites[game.heading][game.wheel_phase],where=self.masks[game.heading])
        dirty.extend((ry,ry+rh) for _,ry,_,rh in rects)
        overlay=None
        if ready is not None:
            overlay=(276,210,472,300)
            frame[210:510,276:748]=0x08c3
            self.centered(frame,'READY',300,2.0)
            self.centered(frame,str(ready),440,3.5)
        elif game.phase=='finished':
            overlay=(236,180,552,360)
            frame[180:540,236:788]=0x08c3
            self.centered(frame,'TIME UP',270,2.0)
            self.centered(frame,'FINAL SCORE',345,1.25)
            self.centered(frame,str(game.score),465,3.0)
            self.centered(frame,'BTN0 TO RESTART',515,.8)
        if overlay is not None:
            rects.append(overlay);dirty.append((overlay[1],overlay[1]+overlay[3]))
        signature=(game.phase,game.remaining(now),game.score,id(preview),str(reason))
        if old is None or old['hud']!=signature:
            frame[:,1024:]=0x08c3
            self.text(frame,'COIN RUN',1048,35,.8,color=0xff00)
            if preview is not None:
                gray=np.asarray(preview)
                if gray.shape!=(96,96) or gray.dtype!=np.uint8: raise ValueError('invalid CNN preview')
                v=np.repeat(np.repeat(gray.astype(np.uint16),2,axis=0),2,axis=1)
                frame[64:256,1056:1248]=((v>>3)<<11)|((v>>2)<<5)|(v>>3)
            frame[62:64,1054:1250]=0x07ff;frame[256:258,1054:1250]=0x07ff
            frame[62:258,1054:1056]=0x07ff;frame[62:258,1248:1250]=0x07ff
            self.text(frame,'TIME',1050,310,.9,color=0xafff)
            self.text(frame,game.remaining(now),1050,375,2.2)
            self.text(frame,'SCORE',1050,435,.9,color=0xff00)
            self.text(frame,game.score,1050,500,2.0,color=0xffe0)
            self.text(frame,'FINISHED' if game.phase=='finished' else ('READY' if ready is not None else 'PLAYING'),1048,555,.68)
            label=str(reason).upper().replace('_',' ')[:17]
            self.text(frame,label,1048,600,.48,thickness=1)
            self.text(frame,'BTN0: RESTART',1048,635,.46,thickness=1)
            self.text(frame,'1 COIN = 1 POINT',1048,665,.46,thickness=1)
            dirty.append((0,720))
        self.previous[key]={'rects':rects,'hud':signature}
        # Contiguous full-width row bands support PYNQ sub-buffer cache flushes.
        bands=[]
        for top,bottom in sorted(dirty):
            if bands and top<=bands[-1][1]: bands[-1]=(bands[-1][0],max(bottom,bands[-1][1]))
            else: bands.append((top,bottom))
        return bands
