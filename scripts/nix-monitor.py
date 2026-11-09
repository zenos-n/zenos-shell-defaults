#!/usr/bin/env python3
"""Monitor Nix's separate JSON socket, preserving the launched program's terminal."""
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile

NIX = '@nix@/bin/nix'
NOM = '@nom@/bin/nom'


def eligible(args):
    if not sys.stderr.isatty() or os.environ.get('NIX_GET_COMPLETIONS') or os.environ.get('ZENOS_NOM') == '0':
        return False
    # Explicit output contracts and help belong to Nix, including future formats.
    nix_args = []
    for arg in args:
        if arg in ('--', '-c', '--command'):
            break
        nix_args.append(arg)
    if any(a in ('--json', '--raw', '--quiet', '-q', '--help', '-h', '--version', '--log-format', '--json-log-path')
           or a.startswith(('--log-format=', '--json-log-path=')) for a in nix_args):
        return False
    if any(a == '--option' and i + 1 < len(nix_args) and nix_args[i + 1] in ('json-log-path', 'log-format') for i, a in enumerate(nix_args)):
        return False
    prefix = iter(args)
    for arg in prefix:
        if arg in ('--offline', '--refresh', '--impure', '--no-write-lock-file', '--no-update-lock-file', '-v', '-L', '--show-trace'):
            continue
        if arg in ('--option', '--override-input', '--override-flake'):
            if next(prefix, None) is None or next(prefix, None) is None:
                return False
            continue
        if arg in ('--extra-experimental-features', '--experimental-features', '--store'):
            if next(prefix, None) is None:
                return False
            continue
        if arg == 'env':
            return next(prefix, None) == 'shell'
        return arg in ('build', 'run', 'shell', 'develop', 'copy')
    return False


def monitor_socket(listener, parent_fd, keep_until_exit, terminal=None):
    """The sidecar owns no app streams or exit status; the caller execs real Nix."""
    with selectors.DefaultSelector() as selector:
        selector.register(listener, selectors.EVENT_READ, None)
        selector.register(parent_fd, selectors.EVENT_READ, None)
        monitor = None
        connected = False
        parent_done = False
        try:
            while not parent_done or len(selector.get_map()) > 2:
                for key, _ in selector.select(timeout=0.1):
                    if key.fileobj == parent_fd:
                        parent_done = True
                        continue
                    if key.fileobj is listener:
                        connection, _ = listener.accept()
                        connection.setblocking(False)
                        selector.register(connection, selectors.EVENT_READ, bytearray())
                        connected = True
                        continue
                    data = key.fileobj.recv(65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    key.data.extend(data)
                    if len(key.data) > 8 * 1024 * 1024:
                        key.data.clear()
                    while b'\n' in key.data:
                        line, _, rest = key.data.partition(b'\n')
                        key.data[:] = rest
                        try:
                            # Diagnostics already go straight to the terminal.
                            if json.loads(line).get('action') not in ('start', 'stop', 'result'):
                                continue
                            if monitor is None:
                                monitor = subprocess.Popen([NOM, '--json'], stdin=subprocess.PIPE,
                                                           stdout=subprocess.DEVNULL, stderr=terminal)
                            if not monitor.stdin.closed:
                                monitor.stdin.write(b'@nix ' + line + b'\n')
                                monitor.stdin.flush()
                        except (ValueError, BrokenPipeError, OSError):
                            if monitor and not monitor.stdin.closed:
                                try: monitor.stdin.close()
                                except OSError: pass
                # Nix's close-on-exec socket closes when run/shell hands over.
                if connected and not keep_until_exit and len(selector.get_map()) == 2:
                    break
        finally:
            for key in list(selector.get_map().values()):
                if key.fileobj not in (listener, parent_fd):
                    key.fileobj.close()
            if monitor:
                try: monitor.stdin.close()
                except OSError: pass
                try: monitor.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    monitor.kill()
                    monitor.wait()


def monitored(command, keep_until_exit=False, terminal=None):
    if not os.access(NOM, os.X_OK):
        os.execvp(command[0], command)
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    temporary = tempfile.TemporaryDirectory(prefix='zenos-nom-', dir=runtime or '/tmp')
    endpoint = str(Path(temporary.name) / 'log')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(endpoint)
    listener.listen()
    listener.setblocking(False)
    parent_fd = os.pidfd_open(os.getpid())
    if os.fork() == 0:
        try:
            os.setsid()
            monitor_socket(listener, parent_fd, keep_until_exit, terminal)
        finally:
            listener.close()
            os.close(parent_fd)
            temporary.cleanup()
        os._exit(0)
    listener.close()
    os.close(parent_fd)
    log_args = ['--option', 'json-log-path', endpoint, '--log-format', 'raw']
    args = [*command, *log_args] if keep_until_exit else [command[0], *log_args, *command[1:]]
    os.execvp(command[0], args)


def main(args):
    if args and args[0] == '--rebuild':
        command = args[1:]
        terminal = int(os.environ.pop('ZENOS_NOM_TTY_FD', '2'))
        if os.isatty(terminal) and os.environ.get('ZENOS_NOM') != '0':
            return monitored(command, keep_until_exit=True, terminal=terminal)
        os.execvp(command[0], command)
    if not eligible(args):
        os.execv(NIX, [NIX, *args])
    return monitored([NIX, *args])


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
