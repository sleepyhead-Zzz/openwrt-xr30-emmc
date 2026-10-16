#!/usr/bin/env python3
"""Read-only PC-side checker for the exact XR30 backup set in installation.md."""
import hashlib,json,struct,sys,zlib
from pathlib import Path

def header(blob,base_lba):
 off=(1-base_lba)*512 if base_lba==0 else len(blob)-512
 h=blob[off:off+512]
 assert h[:8]==b'EFI PART','GPT signature'
 size,crc=struct.unpack_from('<II',h,12)
 assert 92<=size<=512,'GPT header size'
 h0=bytearray(h[:size]);h0[16:20]=b'\0'*4
 assert zlib.crc32(h0)&0xffffffff==crc,'GPT header CRC'
 current,backup,first,last=struct.unpack_from('<QQQQ',h,24)
 entry_lba,count,entry_size,entry_crc=struct.unpack_from('<QIII',h,72)
 start=(entry_lba-base_lba)*512;length=count*entry_size
 assert start>=0 and start+length<=len(blob),'partition entries outside backup'
 entries=blob[start:start+length]
 assert zlib.crc32(entries)&0xffffffff==entry_crc,'partition array CRC'
 assert first<=8192 and last==120831966,'unexpected usable disk bounds'
 return {'current':current,'backup':backup,'first':first,'last':last,'guid':h[56:72].hex(),'entry_count':count,'entry_size':entry_size},entries

def verify(folder):
 folder=Path(folder)
 for line in (folder/'SHA256SUMS').read_text().splitlines():
  expected,name=line.split(None,1);name=name.lstrip('*')
  p=Path(name);assert not p.is_absolute() and '..' not in p.parts,'unsafe manifest path'
  assert hashlib.sha256((folder/p).read_bytes()).hexdigest()==expected,name+' hash mismatch'
 p,pe=header((folder/'gpt-primary.bin').read_bytes(),0)
 b,be=header((folder/'gpt-backup.bin').read_bytes(),120831967)
 assert p['current']==1 and p['backup']==120831999
 assert b['current']==120831999 and b['backup']==1
 assert p['guid']==b['guid'] and pe==be,'GPT copies disagree'
 for n,name,start,end in [(1,'u-boot-env',8192,9215),(2,'factory',9216,13311),(3,'fip',13312,17407)]:
  entry=pe[(n-1)*p['entry_size']:n*p['entry_size']]
  assert struct.unpack_from('<QQ',entry,32)==(start,end),name+' bounds'
  assert entry[56:128].decode('utf-16le').rstrip('\0')==name,name+' label'
  assert len((folder/(name+'.bin')).read_bytes())==(end-start+1)*512,name+' backup size'
 for name in ['boot0.bin','boot1.bin','userarea-prefix.bin']:
  assert (folder/name).stat().st_size==4*1024**2,name+' size'
 assert (folder/'userarea-prefix.bin').read_bytes()[:34*512]==(folder/'gpt-primary.bin').read_bytes(),'prefix differs from primary GPT'
 print(json.dumps({'status':'passed','primary_gpt':p,'backup_gpt':b,'first_three_partitions':'exact expected boundaries and labels','limits':'Checks saved files only. Repeated on-device reads and PC copies must also match; this is not proof the backup came from the intended router.'},indent=2))

if __name__=='__main__':verify(sys.argv[1])
