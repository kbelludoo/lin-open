# Terceira implementacao independente do mesmo contrato (oracle de conferencia).
# Nem LIN, nem C upstream: re-deriva os dois goldens a partir das regras do port,
# para que a forja de um golden exija mudar este arquivo em conjunto (visivel em diff).
# Uso: python3 ref_oracle.py corpus.c | python3 ref_oracle.py boundary.c
import sys
data = open(sys.argv[1] if len(sys.argv) > 1 else 'corpus.c', 'rb').read()
n = len(data)
def ws(c): return c in (32,9,13,10)
def dig(c): return 48 <= c <= 57
def ids(c): return (65<=c<=90) or (97<=c<=122) or c==95 or c==36
def idc(c): return ids(c) or dig(c)
PAIR = {ord('='):[ord('=')], ord('!'):[ord('=')], ord('<'):[ord('='),ord('<')],
        ord('>'):[ord('='),ord('>'),], ord('&'):[ord('&'),ord('=')],
        ord('|'):[ord('|'),ord('=')], ord('^'):[ord('=')], ord('%'):[ord('=')],
        ord('*'):[ord('=')], ord('/'):[ord('=')],
        ord('+'):[ord('+'),ord('=')], ord('-'):[ord('-'),ord('>'),ord('=')]}
def pair_len(a,b,c):
    if a not in PAIR or b is None: return 0
    if a in (60,62) and b==a and c==61: return 3      # <<=  >>=
    if b in PAIR[a]: return 2
    return 0
M=(1<<64)-1
def s64(x): return x-(1<<64) if x>(1<<63)-1 else x
h=0; ntok=0; i=0; kinds={}
while i<n:
    c=data[i]; tstart=i; kind=0; tlen=1
    if ws(c): i+=1
    elif c==47 and i+1<n and data[i+1]==47:
        while i<n and data[i]!=10: i+=1
    elif c==47 and i+1<n and data[i+1]==42:
        i+=2
        while i+1<n and not (data[i]==42 and data[i+1]==47): i+=1
        i+=2
    elif c==34:
        i+=1
        while i<n and data[i]!=34:
            if data[i]==92 and i+1<n: i+=1
            i+=1
        if i<n: i+=1
        kind=4; tlen=i-tstart
    elif dig(c):
        while i<n and dig(data[i]): i+=1
        kind=2; tlen=i-tstart
    elif ids(c):
        while i<n and idc(data[i]): i+=1
        kind=1; tlen=i-tstart
    else:
        b=data[i+1] if i+1<n else None
        cc=data[i+2] if i+2<n else None
        pl=pair_len(c,b,cc)
        tlen=pl if pl else 1
        kind=9 if pl else 100+c
        i=tstart+tlen
    if kind:
        th=0
        for k in range(tlen): th=((th+data[tstart+k])*31)&M
        h=((h*31+kind))&M; h=((h*31+tlen))&M; h=((h*31+th))&M
        ntok+=1; kinds[kind]=kinds.get(kind,0)+1
print('tokens=%d id=%d num=%d str=%d op=%d' % (ntok, kinds.get(1,0), kinds.get(2,0), kinds.get(4,0), kinds.get(9,0)+sum(v for k,v in kinds.items() if k>=100)))
print('fold=%d' % s64(h))
