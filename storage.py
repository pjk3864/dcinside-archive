"""Non-destructive capacity reporting and sealed public-media shard support."""
import re
import shutil
from urllib.parse import quote

SOFT_WARNING_BYTES = 2 * 1024 ** 3


def capacity(root):
    assets = root/'assets'
    files = [p for p in assets.rglob('*') if p.is_file()] if assets.exists() else []
    size = sum(p.stat().st_size for p in files)
    return {'active_media_bytes':size,'media_files':len(files),
            'soft_warning_bytes':SOFT_WARNING_BYTES,
            'warning':size>=SOFT_WARNING_BYTES,
            'free_disk_bytes':shutil.disk_usage(root).free,
            'policy':'Warn only; never delete archives or rewrite Git history automatically.'}


def sealed_media_url(location):
    """Only explicit immutable references to the owner's public storage repos."""
    repo = location.get('repository','')
    commit = location.get('commit','')
    path = location.get('path','')
    if not re.fullmatch(r'pjk3864/dcinside-archive-media-[a-zA-Z0-9_-]+',repo):
        raise ValueError('Invalid media storage repository')
    if not re.fullmatch('[a-f0-9]{40}',commit):
        raise ValueError('Media storage needs a verified immutable commit')
    if not path.startswith('assets/') or '..' in path.split('/') or '\\' in path:
        raise ValueError('Invalid media storage path')
    return f'https://raw.githubusercontent.com/{repo}/{commit}/'+quote(path,safe='/')
