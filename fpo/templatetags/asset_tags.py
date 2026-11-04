"""Static asset URLs that change when the deployed file changes."""

import hashlib
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()


@lru_cache(maxsize=128)
def _content_version(filename, modified_ns, size):
    # The file metadata invalidates the cache during development and redeploys.
    with open(filename, "rb") as asset:
        return hashlib.file_digest(asset, "sha256").hexdigest()[:16]


@register.simple_tag
def versioned_static(name):
    """Keep normal static URL handling and append a content-based cache version."""
    url = static(name)
    filename = finders.find(name)
    if not filename:
        # Some deployments retain collected assets but omit source directories.
        try:
            filename = staticfiles_storage.path(name)
        except NotImplementedError:
            return url  # Remote/manifest storage manages its own asset URLs.

    try:
        path = Path(filename)
        metadata = path.stat()
        version = _content_version(str(path), metadata.st_mtime_ns, metadata.st_size)
    except OSError:
        return url

    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key != "v"]
    query.append(("v", version))
    return urlunsplit(parts._replace(query=urlencode(query)))
