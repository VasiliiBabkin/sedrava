"""Scoped directory capabilities for trusted POSIX Sedrava host A2.

Directory descriptors are followed without symlinks. This is NOT an OS sandbox:
the caller must trust the workspace against concurrent hostile rename/mount races.
"""
import os
import stat

from sedrava_host import _parent, _segments, _regular
from sedrava_host_json import MAX_JSON_NODES, validate_json

MAX_LIST_ENTRIES = 32


def open_scope(root_fd, scope):
    if scope == ".":
        return os.dup(root_fd)
    parts = _segments(scope)
    descriptor = os.dup(root_fd)
    try:
        for part in parts:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def list_dir(root_fd, relative):
    if relative == ".":
        descriptor = os.dup(root_fd)
    else:
        parent, name = _parent(root_fd, _segments(relative))
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 dir_fd=parent)
        finally:
            os.close(parent)
    try:
        output = []
        # scandir streams entries; never materialize an unbounded directory.
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if len(output) >= MAX_LIST_ENTRIES:
                    raise ValueError("Host directory exceeds 32-entry limit")
                name = entry.name
                _segments(name)
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    kind = "directory"
                elif stat.S_ISREG(info.st_mode):
                    _regular(info)
                    kind = "file"
                else:
                    raise ValueError("Host directory contains symlink or special entry")
                output.append({"name": name, "kind": kind})
        output.sort(key=lambda item: item["name"])
        return validate_json(output)
    finally:
        os.close(descriptor)


def make_dir(root_fd, relative):
    parent, name = _parent(root_fd, _segments(relative))
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def remove_empty_dir(root_fd, relative):
    parent, name = _parent(root_fd, _segments(relative))
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("Only ordinary empty directories may be removed")
        os.rmdir(name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
