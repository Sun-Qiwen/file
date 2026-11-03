"""Real-time one-minute coin game. No PYNQ import or inference dependency."""
import math
import random

# Twelve direction vectors; advance() scales them by elapsed seconds and speed.
VECTORS=((0,-5),(2,-4),(4,-2),(5,0),(4,2),(2,4),(0,5),(-2,4),(-4,2),(-5,0),(-4,-2),(-2,-4))

class CoinGame:
    def __init__(self, *, rng=None, duration=60.0):
        if not math.isfinite(duration) or duration<=0: raise ValueError('duration must be positive')
        self.rng=rng if rng is not None else random.Random()
        self.duration=float(duration)
        self.x=392.0; self.y=240.0; self.heading=0
        self.score=0; self.coin=None; self.phase='ready'; self.distance=0.0
        self.started=None; self.last_time=None; self.deadline=None

    def start(self, now):
        now=float(now)
        if not math.isfinite(now): raise ValueError('non-finite clock')
        self.x=392.0; self.y=240.0; self.heading=0; self.score=0; self.distance=0.0
        self.started=now; self.last_time=now; self.deadline=now+self.duration
        self.phase='playing'; self.spawn_coin()

    def remaining(self, now):
        if self.phase=='ready': return math.ceil(self.duration)
        return max(0,math.ceil(self.deadline-float(now)))

    def coin_overlaps_car(self):
        if self.coin is None: return False
        return math.hypot(self.coin[0]+40-(self.x+120),self.coin[1]+40-(self.y+120))<=104

    def spawn_coin(self):
        # Sample positions outside the car's pickup radius.
        for _ in range(1024):
            self.coin=(self.rng.randint(8,936),self.rng.randint(8,632))
            if not self.coin_overlaps_car(): return
        candidates=((8,8),(936,8),(8,632),(936,632))
        self.coin=max(candidates,key=lambda p:math.hypot(p[0]+40-self.x-120,p[1]+40-self.y-120))

    def advance(self, now, direction):
        now=float(now)
        if not math.isfinite(now): raise ValueError('non-finite clock')
        if self.last_time is not None and now<self.last_time: raise ValueError('backwards clock')
        if self.phase!='playing': return False
        end=min(now,self.deadline)
        dt=end-self.last_time; self.last_time=end
        old_x,old_y=self.x,self.y
        if 0<=direction<12:
            vx,vy=VECTORS[direction]; self.heading=direction
            self.x=min(784.0,max(0.0,self.x+vx*15.0*dt))
            self.y=min(480.0,max(0.0,self.y+vy*15.0*dt))
            self.distance+=math.hypot(self.x-old_x,self.y-old_y)
        if now>=self.deadline:
            self.phase='finished'; return False
        cx,cy=self.coin[0]+40,self.coin[1]+40
        ax,ay=old_x+120,old_y+120; bx,by=self.x+120,self.y+120
        dx,dy=bx-ax,by-ay; length2=dx*dx+dy*dy
        fraction=max(0.0,min(1.0,((cx-ax)*dx+(cy-ay)*dy)/length2)) if length2 else 0.0
        if math.hypot(cx-ax-fraction*dx,cy-ay-fraction*dy)<=104:
            self.score+=1; self.spawn_coin(); return True
        return False

    @property
    def wheel_phase(self): return int(self.distance/16.0)%4


class GameRounds:
    """Reusable rounds; hardware buffers and inference belong to the outer runtime."""
    def __init__(self, now, *, duration=60., rng=None, button_count=0):
        self.duration=duration;self.rng=rng if rng is not None else random.Random()
        self.button_count=int(button_count)&65535;self.round_id=0
        self.restart(now)

    def restart(self, now):
        now=float(now)
        if not math.isfinite(now):raise ValueError('non-finite round clock')
        self.game=CoinGame(duration=self.duration,rng=self.rng)
        self.created=now;self.ready_until=now+3.;self.round_id+=1

    def observe_button(self, count, now):
        count=int(count)&65535
        if count==self.button_count:return False
        self.button_count=count;self.restart(now);return True

    def tick(self, now, direction):
        if self.game.phase=='ready':
            if now>=self.ready_until:self.game.start(now);return 'start'
            return None
        if self.game.phase=='finished':return None
        pickup=self.game.advance(now,direction)
        if self.game.phase=='finished':return 'result'
        return 'coin' if pickup else None
