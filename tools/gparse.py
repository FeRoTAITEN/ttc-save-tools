"""Tolerant GSv parser for City.bin docs.
Extensions vs tools/gsv.py (derived from City.bin, verified by parsing all docs):
 - string len with high bit set = reference to an external string dictionary entry ('<G%d>', no body)
 - table/array id already seen in the doc = back reference (no count/body)
"""
import sys,struct,zlib
sys.path.insert(0,__import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import gsv
from gsv import *
class Dec2(gsv.Dec):
    def __init__(s,b,base=0):
        super().__init__(b,base); s.objs={}
    def val(self,t=None):
        if t is None: t=self.u('H')
        if t==STR:
            n=Node(t,off=self.o+self.base)
            n.sid=self.u('I')
            if n.sid in self.strs:
                n.v,n.new=self.strs[n.sid],False
            else:
                ln=self.u('I')
                if ln&0x80000000: n.v='<G%d>'%(ln&0x7fffffff)
                else:
                    raw=self.b[self.o:self.o+ln]
                    if self.b[self.o+ln]!=0: raise ValueError('str nul')
                    self.o+=ln+1; n.v=raw.decode('utf-8','surrogateescape')
                n.new=True; self.strs[n.sid]=n.v
            return n
        if t in (TABLE,ARRAY):
            n=Node(t,off=self.o+self.base)
            n.tid=self.u('I')
            if n.tid in self.objs:
                r=self.objs[n.tid]; n.v=[]; n.flags=-1; n.kt='ref'; return n
            self.objs[n.tid]=n
            cnt=self.u('I'); n.v=[]
            if cnt:
                n.flags=self.u('H')
                if t==TABLE:
                    if n.flags&~3: raise ValueError('table flags 0x%x at 0x%x'%(n.flags,self.o))
                    n.kt=self.u('H') if n.flags&1 else None
                    n.vt=self.u('H') if n.flags&2 else None
                    for _ in range(cnt):
                        k=self.val(n.kt); n.v.append((k,self.val(n.vt)))
                else:
                    if n.flags&~1: raise ValueError('array flags')
                    n.vt=self.u('H') if n.flags&1 else None
                    for _ in range(cnt): n.v.append(self.val(n.vt))
            return n
        if t==14:
            n=Node(t,off=self.o+self.base); n.v=bytes(self.b[self.o:self.o+TSZ]); self.o+=TSZ; return n
        return super().val(t)
TSZ=64
def parse(b):
    size,h=struct.unpack_from('<II',b,4)
    d=Dec2(b[12:12+size],12)
    root=d.val()
    if d.o!=size: raise ValueError('trailing %d/%d'%(d.o,size))
    return root
