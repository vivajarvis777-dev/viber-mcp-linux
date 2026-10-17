"""Isolated Xvfb + private D-Bus real AT-SPI exercise against synthetic GTK only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from linux_backend import LinuxBackend


def main():
    r,w=os.pipe()
    xvfb=subprocess.Popen(['Xvfb','-displayfd',str(w),'-screen','0','800x600x24','-nolisten','tcp'],pass_fds=(w,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    os.close(w)
    fixture=None
    try:
        with os.fdopen(r) as f: display=f.readline().strip()
        assert display.isdigit()
        os.environ['DISPLAY']=':'+display
        os.environ['NO_AT_BRIDGE']='0'
        os.environ['GTK_MODULES']='gail:atk-bridge'
        os.environ['VIBER_ALLOW_GUI']='1'
        import gi
        gi.require_version('Atspi','2.0')
        from gi.repository import Atspi
        fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/synthetic_gtk.py')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        def children(n): return [n.get_child_at_index(i) for i in range(n.get_child_count())]
        deadline=time.monotonic()+10
        app=window=None
        while time.monotonic()<deadline:
            for candidate in children(Atspi.get_desktop(0)):
                for win in children(candidate):
                    if win.get_name()=='Synthetic Fixture': app,window=candidate,win
            if window: break
            time.sleep(.1)
        assert window is not None, 'Synthetic AT-SPI window absent'
        def spec(n): return {'role':n.get_role_name(),'name':n.get_name()}
        paths={}
        def walk(n,path):
            paths[n.get_name()]=path
            for child in children(n): walk(child,path+[spec(child)])
        walk(window,[])
        profile={'application':app.get_name(),'window':spec(window),
                 'selectors':{key:paths[name] for key,name in {'identity':'Identity','composer':'Composer',
                   'search':'Search','results':'Results','conversation':'Conversation','sidebar':'Sidebar','send':'Synthetic Send'}.items()},
                 'outgoing_message':{'role':'text','name':'not-a-real-message'},'self_description':'synthetic-self-marker'}
        with tempfile.TemporaryDirectory(prefix='viber-synthetic-',dir=os.environ['TMPDIR']) as tmp:
            path=Path(tmp)/'profile.json';path.write_text(json.dumps(profile))
            backend=LinuxBackend(str(path))
            # Direct worker check exposes Python API failures only on this synthetic tree.
            from atspi_worker import run
            assert run({'profile':str(path),'action':'identity'},Atspi)=='0981901991'
            assert backend.identity()=='0981901991'
            assert backend.draft()==''
            value='Привіт 👋\nЮнікод ї є І — SYNTHETIC'
            backend.write(value, '0981901991')
            assert backend.draft()==value
            assert backend.navigate('0981901991')['matched']=='0981901991'
            assert backend.read('conversation')['lines']==['SYNTHETIC conversation only']
            assert backend.read('sidebar')['lines']==['SYNTHETIC sidebar only']
            assert backend.messages()==[]
            backend.send('0981901991', value)  # Synthetic local GTK callback only, never Viber/network.
            assert backend.draft()==''
            assert backend.read('conversation')['lines']==[value]
            assert backend.stop()['stopped']
            print(json.dumps({'synthetic_real_atspi':True,'identity':'passed','unicode_readback':'passed',
                 'exact_search':'passed','scoped_reads':'passed','local_button_action':'passed','live_viber':False}))
    finally:
        if fixture:
            fixture.terminate();fixture.wait(timeout=5)
        xvfb.terminate();xvfb.wait(timeout=5)

if __name__=='__main__': main()
