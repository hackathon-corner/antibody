import numpy as np, wave
SR=44100; DUR=22.0; N=int(SR*DUR); rng=np.random.default_rng(7)
def tt(d): return np.arange(int(SR*d))/SR
def hz(m): return 440*2**((m-69)/12)
def env(n,a=.005,r=.2,hold=0):
    t=np.arange(n)/SR; e=np.minimum(1,t/max(a,1e-4)); return e*np.exp(-np.maximum(0,t-hold)/r)
def lp(x,fc):  # one-pole lowpass
    a=np.exp(-2*np.pi*fc/SR); y=np.empty_like(x); s=0.
    for i in range(len(x)): s=(1-a)*x[i]+a*s; y[i]=s
    return y
def lpf(x,fc): return lp(lp(x,fc),fc)
def put(bus,sig,t0,g=1.):
    i=int(t0*SR); j=min(N,i+len(sig));
    if i<N: bus[i:j]+=g*sig[:j-i]
music=np.zeros(N); sfx=np.zeros(N); drums=np.zeros(N)

def pad(notes,d,g=.12):
    t=tt(d); s=sum(np.sin(2*np.pi*hz(m)*t*(1+dt))+.5*np.sin(2*np.pi*2*hz(m)*t*(1+dt)) for m in notes for dt in(-.003,.003))
    e=np.minimum(1,t/.35)*np.minimum(1,(d-t)/.4); return g*s*e/len(notes)
def pluck(m,d=.5,g=.2,br=6):
    t=tt(d); f=hz(m); s=np.sin(2*np.pi*f*t+ .8*np.exp(-t*br)*np.sin(2*np.pi*2*f*t))
    return g*s*env(len(t),.002,d/4)
def bell(m,d=2.5,g=.15):
    t=tt(d); f=hz(m); s=np.sin(2*np.pi*f*t)+.4*np.sin(2*np.pi*2.76*f*t)*np.exp(-t*3)+.2*np.sin(2*np.pi*5.4*f*t)*np.exp(-t*6)
    return g*s*env(len(t),.003,d/3)
def kick(g=.55):
    t=tt(.45); f=45+90*np.exp(-t*30); ph=2*np.pi*np.cumsum(f)/SR; return g*np.sin(ph)*np.exp(-t*7)*np.minimum(1,t/.003)
def hat(g=.05):
    n=rng.standard_normal(int(.06*SR)); n=lpf(n-lpf(n,6000),11000); return g*n*env(len(n),.002,.012)
def click(g=.03):
    n=rng.standard_normal(int(.03*SR)); n=lpf(n-lpf(n,1500),5000); return g*n*env(len(n),.001,.006)
def noise_riser(d,f0,f1,g=.08):
    n=rng.standard_normal(int(d*SR)); t=tt(d); out=np.zeros_like(n); seg=int(.05*SR)
    for k in range(0,len(n),seg):
        fc=f0*(f1/f0)**(k/len(n)); x=n[k:k+seg]; out[k:k+seg]=lpf(x,fc)-lpf(x,fc*.3)
    return g*out*(t/d)**2

# --- HOOK 0-3.5: drone, typing, leak hit, tension pulse, riser
t=tt(3.6); drone=(np.sin(2*np.pi*hz(33)*t)+.5*np.sin(2*np.pi*hz(45)*t)+.25*np.sin(2*np.pi*hz(52)*t))*np.minimum(1,t/.4)*np.minimum(1,(3.6-t)/.3)
put(music,.16*drone,0)
for i in range(15): put(sfx,click(.022+.006*rng.random()),.05+i*.03+.008*rng.random())
put(drums,kick(.55),.88); put(music,pad([33,45,52],1.8,.22)*np.exp(-tt(1.8)*1.2),.88)
put(sfx,noise_riser(.35,400,3000,.04),.52)
for b in range(1,6): put(music,pluck(45,.25,.07,10),.88+b*.5); put(music,pluck(57,.2,.035,10),1.13+b*.5)
put(sfx,noise_riser(1.0,200,4500,.04),2.5)

# --- GROOVE 3.5-19 : Am F C G, bar=2s
prog=[[57,60,64],[53,57,60],[55,60,64],[55,59,62]]; bass=[45,41,48,43]
arp=[[69,72,76,72],[69,72,77,72],[67,72,76,72],[67,71,74,71]]
for bar in range(8):
    t0=3.5+bar*2; 
    if t0>=19: break
    ch=prog[bar%4]; d=min(2.0,19-t0)
    put(music,pad(ch,d+.3,.10),t0)
    for k in range(4):
        tb=t0+k*.5
        if tb>=19: break
        put(music,pluck(bass[bar%4]-12,.45,.13,4),tb)
        put(music,pluck(arp[bar%4][k],.3,.045,8),tb+.25)
for b in range(int((19-3.5)/.5)):
    tb=3.5+b*.5
    if 16.75<=tb<17.75: continue   # drop out under the REJECTED stamp
    put(drums,kick(.42),tb); put(drums,hat(.022),tb+.25)
# S3 patch proposed shimmer
for i,m in enumerate([76,79,81,84]): put(sfx,bell(m,1.2,.035),9.25+i*.05)
# S4 check ticks ascending pentatonic
for i,m in enumerate([69,72,74,76,79,81,84]): put(sfx,pluck(m,.35,.07,5),11.75+i*.2+.12)
# S5: pass tick, two fail tones, stamp thud
put(sfx,pluck(76,.35,.07,5),15.97)
for i,m in enumerate([52,50]): put(sfx,lpf(pluck(m,.5,.12,2),900),16.2+i*.35+.12)
th=kick(.62); n=rng.standard_normal(int(.25*SR)); n=lpf(n,400)*env(len(n),.001,.06)*.25
put(drums,th,16.78); put(sfx,n,16.78); put(music,pad([40,41],1.0,.12)*np.exp(-tt(1.0)*3),16.78)
# OUTRO 19-22: resolve Am(add9), bell
put(drums,kick(.5),19.0)
put(music,pad([45,57,60,64,71],3.0,.16),19.0)
for i,m in enumerate([69,76,81]): put(sfx,bell(m,2.8,.07),19.0+i*.12)

def reverb(x,dec=1.6,mix=.25):
    L=int(dec*SR); ir=rng.standard_normal(L)*np.exp(-np.arange(L)/SR*6.9/dec); ir=lpf(ir,5000); ir/=np.sqrt((ir**2).sum())
    n=1<<int(np.ceil(np.log2(len(x)+L))); y=np.fft.irfft(np.fft.rfft(x,n)*np.fft.rfft(ir,n),n)[:len(x)]
    return y
dry=music*1.0+drums*.9+sfx*.85
wet=reverb(music*.8+sfx*1.0+drums*.15)
mix=dry+.22*wet
# gentle sidechain-ish duck of music under kicks is implicit; master: tanh limiter, fade out
side=.12*(wet-np.roll(wet,int(.013*SR)))
L=mix+side; R=mix-side
L=np.tanh(L*1.4)/1.4; R=np.tanh(R*1.4)/1.4
fo=int(.7*SR); g=np.ones(N); g[-fo:]=np.linspace(1,0,fo)**1.5; g[:441]=np.linspace(0,1,441)
pk=max(np.abs(L).max(),np.abs(R).max()); L=L*g/pk*.89; R=R*g/pk*.89
st=(np.stack([L,R],1)*32767).astype(np.int16)
with wave.open('audio.wav','wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes())
print('ok', st.shape)
