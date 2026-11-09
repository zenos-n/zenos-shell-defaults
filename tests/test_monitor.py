import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts/nix-monitor.py'


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fake = self.root / 'nix'
        fake.write_text(f'#!{sys.executable}\n' + '''
import json, os, socket, sys
args=sys.argv[1:]
if '--option' in args and 'no-log' not in args:
 p=args[args.index('--option')+2]
 s=socket.socket(socket.AF_UNIX);s.connect(p)
 s.sendall((json.dumps({'action':'start','id':1,'level':3,'type':105,'text':'build','fields':[],'parent':0})+'\\n').encode())
 s.sendall(b'{"action":"stop","id":1}\\n');s.close()
print('FACTS='+json.dumps({'tty':[os.isatty(i) for i in range(3)],'args':args}))
if 'read-input' in args: print('INPUT='+input())
if 'fail' in args: sys.exit(37)
''')
        fake.chmod(0o755)
        nom=self.root/'nom'
        nom.write_text(f'#!{sys.executable}\n' + '''
import sys
lines=sys.stdin.read().splitlines()
print('MONITORED='+str(len(lines)),file=sys.stderr)
''')
        nom.chmod(0o755)
        self.script=self.root/'monitor.py'
        self.script.write_text(SCRIPT.read_text().replace("'@nix@/bin/nix'",repr(str(fake))).replace("'@nom@/bin/nom'",repr(str(nom))))

    def run_tty(self,args,typed=None):
        master,slave=pty.openpty()
        proc=subprocess.Popen([sys.executable,str(self.script),*args],stdin=slave,stdout=slave,stderr=slave)
        os.close(slave)
        if typed:os.write(master,typed)
        data=b'';deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if select.select([master],[],[],0.1)[0]:
                try: chunk=os.read(master,65536)
                except OSError:break
                if not chunk:break
                data+=chunk
        os.close(master)
        if proc.poll() is None:proc.kill();self.fail('wrapper/app/monitor failed to hand back terminal')
        return proc.wait(),data.decode()

    def test_run_shell_develop_keep_all_ttys_and_input(self):
        for cmd in ('run','shell','develop'):
            with self.subTest(cmd=cmd):
                status,out=self.run_tty([cmd,'ref','--','read-input'],b'hello\n')
                self.assertEqual(status,0,out)
                self.assertIn('"tty": [true, true, true]',out)
                self.assertIn('INPUT=hello',out)
                self.assertIn('MONITORED=2',out)
                self.assertEqual(out.count('FACTS='),1,out)

    def test_exact_failure_status(self):
        status,out=self.run_tty(['run','ref','--','fail'])
        self.assertEqual(status,37,out)

    def test_machine_output_and_explicit_logging_bypass(self):
        for args in (['build','--json'],['eval','--raw','x'],['build','--log-format','internal-json'],['--help'],['build','--option','json-log-path','/tmp/custom']):
            if 'json-log-path' in args:continue # Fake only models generated socket logs.
            status,out=self.run_tty(args)
            self.assertEqual(status,0,out)
            self.assertNotIn('MONITORED=',out)

    def test_noninteractive_is_exact_passthrough(self):
        p=subprocess.run([sys.executable,str(self.script),'run','ref','--','--json'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        facts=json.loads(p.stdout.split('FACTS=')[1])
        self.assertEqual(facts['args'],['run','ref','--','--json'])
        self.assertEqual(facts['tty'],[False,False,False])
        self.assertEqual(p.stderr,'')

    def test_arguments_after_separator_remain_app_arguments(self):
        code,out=self.run_tty(['run','ref','--','--json','a b'])
        self.assertEqual(code,0,out);self.assertIn('MONITORED=2',out)
        self.assertIn('"a b"',out)

    def test_eligible_command_without_log_connection_cleans_up(self):
        code,out=self.run_tty(['run','no-log'])
        self.assertEqual(code,0,out)
        self.assertNotIn('MONITORED=',out)

    def test_missing_monitor_preserves_the_app(self):
        (self.root/'nom').unlink()
        code,out=self.run_tty(['run','ref'])
        self.assertEqual(code,0,out)
        self.assertNotIn('MONITORED=',out)
        self.assertIn('"tty": [true, true, true]',out)

    def test_monitor_failure_does_not_change_app_exit_status(self):
        (self.root/'nom').write_text(f'#!{sys.executable}\nraise SystemExit(9)\n')
        code,out=self.run_tty(['run','ref','--','fail'])
        self.assertEqual(code,37,out)

    def test_no_connection_does_not_hold_terminal(self):
        code,out=self.run_tty(['run','--help'])
        self.assertEqual(code,0,out)
        self.assertNotIn('MONITORED',out)


if __name__=='__main__':unittest.main()
