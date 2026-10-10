"""Reloadable authorization for the local uploader; no tokens in subprocess args."""
import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from policy import redact


def install_log_redaction(provider):
    # Rich formats and wraps log messages before writing stderr. Redact at the
    # LogRecord boundary too, so a token cannot survive as separately wrapped
    # fragments. Suppress raw exception/stack payloads from SDK retry logging.
    previous = logging.getLogRecordFactory()
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.msg = provider.redact(record.getMessage())
        record.args = ()
        if record.exc_info:
            record.msg += ' [exception details suppressed]'
        record.exc_info = record.exc_text = record.stack_info = None
        return record
    logging.setLogRecordFactory(factory)


class AuthorizationProvider:
    def __init__(self, here, settings):
        self.here, self.settings = Path(here), settings
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.tokens = set()
        self.token = None
        self.next_check = 0
        self.stamp = None
        self.check()

    def run(self, script, *args):
        child = subprocess.run([self.settings['powershell'], '-NoProfile', '-NonInteractive',
                                '-File', str(self.here / script), *args],
                               capture_output=True, text=True, encoding='utf-8', timeout=95,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if child.returncode:
            raise RuntimeError('Authorization helper failed')
        return child.stdout

    def file_stamp(self):
        try:
            return Path(self.settings['tokenFile']).stat().st_mtime_ns
        except OSError:
            return None

    def check(self):
        with self.lock:
            state = json.loads(self.run('ensure-authorization.ps1'))
            if state['status'] in ('expired', 'unknown'):
                raise RuntimeError('Authorization expired or unavailable; reauthorize')
            # Another MCP can replace the file between decrypting and recording
            # its timestamp. Only accept a read whose before/after stamps agree.
            for _ in range(3):
                before = self.file_stamp()
                token = self.run('read-credential.ps1', '-TokenFile', self.settings['tokenFile'], '-Mode', 'token').strip()
                if not token:
                    raise RuntimeError('Empty authorization')
                self.tokens.add(token)
                after = self.file_stamp()
                if before == after:
                    break
            else:
                raise RuntimeError('Authorization changed repeatedly while reading')
            self.token = token
            os.environ['BAIDU_NETDISK_ACCESS_TOKEN'] = token
            self.stamp = after
            failed = state.get('refreshAction') in ('failed', 'unavailable')
            self.next_check = time.monotonic() + (3600 if failed else 86400)
            if failed:
                reason = state.get('refreshFailure', 'unavailable')
                print(f'Baidu refresh unavailable ({reason}); current authorization remains in use while valid.', file=sys.stderr)
            return state

    @contextlib.contextmanager
    def lease(self):
        with self.lock:
            if time.monotonic() >= self.next_check or self.file_stamp() != self.stamp:
                self.check()
            yield self.token

    def redact(self, text):
        with self.lock:
            for token in self.tokens:
                text = redact(text, token)
        return redact(text)

    def start_monitor(self):
        def monitor():
            while not self.stop.wait(max(1, self.next_check - time.monotonic())):
                try:
                    self.check()
                except Exception:
                    self.next_check = time.monotonic() + 3600
                    print('Baidu authorization check failed; retrying later. Reauthorize if expired.', file=sys.stderr)
        threading.Thread(target=monitor, name='baidu-authorization', daemon=True).start()
