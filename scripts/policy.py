"""Credential-free policies shared by the uploader and its tests."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath


def redact(text, token=''):
    value = str(text)
    if token:
        value = value.replace(token, '[REDACTED]')
    value = re.sub(r'(access_token=)[^\s&"\'<>\\]+', r'\1[REDACTED]', value, flags=re.I)
    return re.sub(r'Bearer\s+[^\s"\']+', 'Bearer [REDACTED]', value, flags=re.I)


def expiry_status(saved, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        created = datetime.fromisoformat(saved['saved_at_utc'].replace('Z', '+00:00'))
        if created.tzinfo is None:
            raise ValueError('Timezone required')
        seconds = int(saved['expires_in'])
        if seconds <= 0:
            raise ValueError('Positive lifetime required')
        expires = created + timedelta(seconds=seconds)
        remaining = int((expires - now).total_seconds())
        return {'status': 'expired' if remaining <= 0 else ('expiring' if remaining <= 7 * 86400 else 'valid'),
                'expiresAtUtc': expires.isoformat(), 'remainingSeconds': remaining}
    except (ValueError, TypeError, KeyError, OverflowError):
        return {'status': 'unknown'}


def remote_target(directory, filename):
    if not directory.startswith('/') or '\\' in directory or '\x00' in directory:
        raise ValueError('Use an absolute Netdisk directory')
    directory = directory.rstrip('/') or '/'
    if any(part in ('.', '..') for part in directory.split('/')) or '//' in directory:
        raise ValueError('Use a normalized Netdisk directory')
    if not filename or '/' in filename or '\\' in filename or filename in ('.', '..'):
        raise ValueError('Invalid filename')
    return str(PurePosixPath(directory) / filename)


def upload_policy(overwrite):
    return 3 if overwrite else 0
