"""Read-only cache reuse with fresh complete hashing and end-use preservation."""
from contextlib import contextmanager
import datetime
import hashlib
import json
from pathlib import Path
import stat
import time
from src.round13.archive import Archive,safe_name
from src.round13.common import require,write,Unavailable


def safe_path(root,name):
    safe_name(name)
    root=Path(root).absolute();candidate=root/name
    require(candidate.resolve().is_relative_to(root.resolve()),'R24_CACHE_ROOT_ESCAPE')
    for p in [candidate,*candidate.parents]:
        if p.exists() or p.is_symlink():
            s=p.lstat()
            require(not p.is_symlink() and not (getattr(s,'st_file_attributes',0)&0x400),'R24_CACHE_LINK_REPARSE')
        # Include ancestors of the named cache root: a junction above it must
        # not silently redirect the supposedly read-only evidence boundary.
    return candidate


class Progress:
    def __init__(self,work,check):
        self.folder=Path(work)/'input_progress';self.folder.mkdir(parents=True,exist_ok=True)
        self.check=check;self.completed_assets=0;self.asset=None;self.latest=None
        from .control import Lifecycle
        clock=next((p/'lifecycle.json' for p in [Path(work),*Path(work).parents] if (p/'lifecycle.json').is_file()),None)
        self.life=Lifecycle(clock) if clock else None
    def event(self,stage,event,**data):
        self.check()
        row=dict(stage=stage,event=event,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            utc_epoch=time.time(),monotonic_seconds=time.perf_counter(),monotonic_basis='QueryPerformanceCounter',cpu_seconds=time.process_time(),
            remaining_compute_s=self.life.remaining(True) if self.life else None,
            remaining_total_s=self.life.remaining(False) if self.life else None,
            asset=self.asset,completed_assets=self.completed_assets,**data)
        self.latest=row
        with (self.folder/'events.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        write(self.folder/'latest.json',row)
    @contextmanager
    def phase(self,stage,**data):
        u,m,c=time.time(),time.perf_counter(),time.process_time()
        self.event(stage,'START',**data)
        try:yield
        except BaseException as e:
            # Preserve the last phase even when compute has expired.
            with (self.folder/'failure.json').open('w',encoding='utf8') as f:
                json.dump(dict(stage=stage,asset=self.asset,completed_assets=self.completed_assets,
                    error=type(e).__name__+': '+str(e),utc_wall_s=time.time()-u,
                    monotonic_wall_s=time.perf_counter()-m,cpu_s=time.process_time()-c),f)
            raise
        self.event(stage,'END',utc_wall_s=time.time()-u,monotonic_wall_s=time.perf_counter()-m,
            cpu_s=time.process_time()-c,**data)


class FrozenArchive(Archive):
    def __init__(self,cfg,work,check):
        self.locations={};self.progress=Progress(work,check)
        self.roots=[Path(cfg['r22_materialized']),Path(cfg['k13_work'])/'vendor']
        with self.progress.phase('archive_full_hash_inventory'):
            super().__init__(cfg,Path(work)/'materialized',check)
    def digest(self,path):
        h=hashlib.sha256();n=0
        with Path(path).open('rb') as f:
            while b:=f.read(1024*1024):
                self.check();h.update(b);n+=len(b)
                if n%(64*1024*1024)==0:self.progress.event('hash','CHUNK',path=str(path),bytes_completed=n)
        return n,h.hexdigest()
    def path(self,name):
        self.check();safe_name(name)
        if name in self.locations:return self.locations[name]
        if name not in self.manifest['files']:raise Unavailable('R24_MISSING_MEMBER:'+name)
        expected=self.manifest['files'][name]
        for root in self.roots:
            p=safe_path(root,name)
            if p.exists():
                require(p.is_file(),'R24_CACHE_NONFILE')
                with self.progress.phase('hash',member=name,path=str(p),cache_hit=True,bytes=expected['bytes']):
                    size,digest=self.digest(p)
                    require(size==expected['bytes'] and digest==expected['sha256'],'R24_CACHE_BYTES_CHANGED:'+name)
                self.used[name]=dict(bytes=size,sha256=digest,path=str(p),source='REUSED_CURRENT_BYTES_FULLY_HASHED',cache_root=str(root))
                self.locations[name]=p
                return p
        target=safe_path(self.vendor,name)
        with self.progress.phase('extract_and_hash',member=name,path=str(target),cache_hit=False,bytes=expected['bytes']):
            p=super().path(name)
        self.used[name].update(path=str(p),source='EXTRACTED_CURRENT_ARCHIVE')
        self.locations[name]=p
        return p
    def preserve(self):
        with self.progress.phase('end_preserve_complete_used_bytes'):
            for name,row in self.used.items():
                path=safe_path(Path(row['cache_root']) if 'cache_root' in row else self.vendor,name)
                size,digest=self.digest(path)
                require(size==row['bytes'] and digest==row['sha256'],'R24_MEMBER_CHANGED_AFTER_READ:'+name)
            size,digest=self.digest(self.zip_path)
            require(size==self.cfg['archive_bytes'] and digest==self.cfg['archive_sha256'],'R24_ARCHIVE_CHANGED_AFTER_READ')
        return dict(status='PASS',actual_used_members=self.used,archive_sha256=digest,
            reused_members=sum(r['source'].startswith('REUSED') for r in self.used.values()),
            extracted_members=sum(r['source'].startswith('EXTRACTED') for r in self.used.values()),
            current_hashes_and_full_npz_row_checks_retained=True)
