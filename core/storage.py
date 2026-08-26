import json
import os
import shutil
import tempfile

import msgpack
import yaml

import core

TEMPORARY = False


def _atomic_write(path, content, binary=False, backup=True):
    """write content to a file atomically.

    writes to a temp file in the same directory, flushes + fsyncs it, keeps a
    single .bak copy of the previous good file, then os.replace()s it over the
    target. a crash mid-write leaves either the old file or the new file intact,
    never a truncated/partial one. raises on failure (temp file is cleaned up).
    """
    write_mode = "wb" if binary else "w"
    encoding = None if binary else "utf-8"
    directory = os.path.dirname(path) or "."

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, write_mode, encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # keep a backup of the previous good file before overwriting it, so a
        # later corrupt/failed parse can fall back to it
        if backup and os.path.exists(path):
            try:
                shutil.copy2(path, f"{path}.bak")
            except OSError as e:
                core.log("error", f"error backing up {path}: {e}")

        os.replace(tmp_path, path)
    except BaseException:
        # never leave a stray temp file behind on failure
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


class StorageList(list):
    """subclassed list that handles storage of data. supports a variety of storage formats."""

    def __init__(self, name: str, type: str, manager=None, path=None, autoload=True, *args):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)
        self.name = name
        self.binary = False

        # create path if it doesnt exist
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        # cache for change detection (mtime + size, so two writes within the
        # same 1s mtime granularity are not missed)
        self._last_modified = 0.0
        self._last_size = -1

        # lets not overwrite a builtin
        file_type = type
        if not type:
            # default to json
            file_type = "json"

        file_ext = None
        match file_type:
            case "text":
                file_ext = "txt"
            case "json":
                file_ext = "json"
            case "yaml":
                file_ext = "yml"
            case "msgpack":
                file_ext = "mp"
                self.binary = True

        self.type = file_type
        self.ext = file_ext

        self.path += f".{self.ext}"

        if manager:
            self.manager = manager

        if os.path.exists(self.path):
            if autoload and not TEMPORARY:
                self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            _atomic_write(self.path, content, binary=self.binary)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True

    def _read_path(self, path):
        """read raw content from a specific path; returns content or raises"""
        read_mode = "rb" if self.binary else "r"
        encoding = "utf-8" if not self.binary else None
        with open(path, read_mode, encoding=encoding) as f:
            return f.read()

    def _read(self):
        try:
            return self._read_path(self.path)
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def _parse(self, raw):
        """deserialize raw file content into a python list for this storage type"""
        match self.type:
            case "json":
                return list(json.loads(raw))
            case "yaml":
                return list(yaml.safe_load(raw))
            case "msgpack":
                return list(msgpack.unpackb(raw))
            case "text":
                return raw.split("\n")
        return []

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            st = os.stat(self.path)
            return (st.st_mtime, st.st_size) != (self._last_modified, self._last_size)
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time and size"""
        try:
            st = os.stat(self.path)
            self._last_modified = st.st_mtime
            self._last_size = st.st_size
        except OSError:
            pass

    def save(self):
        """save content to file"""
        if TEMPORARY:
            return True

        match self.type:
            case "json":
                self._write(json.dumps(self, indent=2))
            case "yaml":
                self._write(
                    yaml.safe_dump(
                        self, default_flow_style=False, sort_keys=False, allow_unicode=True
                    )
                )
            case "msgpack":
                self._write(msgpack.packb(self))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(self))

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()

    def load(self, data=None):
        """load content from file or data argument"""
        if data is not None:
            self.clear()
            self.extend(data)
            return self

        # skip reload if file hasn't changed on disk
        if not self._file_changed():
            self._update_mtime()
            return self

        # read + parse into a local first; only replace in-memory state after a
        # fully-successful read. a transient read/parse error must never wipe
        # the data we already hold.
        raw = self._read()
        parsed = None
        if raw:
            try:
                parsed = self._parse(raw)
            except Exception as e:
                core.log("error", f"error parsing {self.name}: {e}")
                parsed = None

        # fall back to the .bak copy if the primary was unreadable/corrupt
        if parsed is None:
            bak = f"{self.path}.bak"
            if os.path.exists(bak):
                try:
                    parsed = self._parse(self._read_path(bak))
                    core.log("warning", f"recovered {self.name} from backup")
                except Exception as e:
                    core.log("error", f"error reading backup for {self.name}: {e}")
                    parsed = None

        if parsed is None:
            # keep existing in-memory data rather than clearing it
            return None

        self.clear()
        self.extend(parsed)

        # update mtime after loading
        self._update_mtime()
        return self

    def get(self, *args, **kwargs):
        if not TEMPORARY:
            self.load()

        return super().__getitem__(args[0])


class StorageDict(dict):
    """subclassed dict that handles storage of data. supports a variety of storage formats."""

    def __init__(
        self,
        name: str,
        type: str,
        manager=None,
        path=None,
        autoload=True,
        override_temporary=False,
        *args,
    ):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)

        self.name = name
        self.binary = False

        # create path if it doesnt exist
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        # this is mainly for the config, so that we can still make changes in temporary mode
        # but who knows what it might be needed for in the future
        self.override_temporary = override_temporary

        # cache for change detection (mtime + size, so two writes within the
        # same 1s mtime granularity are not missed)
        self._last_modified = 0.0
        self._last_size = -1

        # lets not overwrite a builtin
        file_type = type
        if not type:
            # default to json
            file_type = "json"

        file_ext = None
        match file_type:
            case "text":
                file_ext = "txt"
            case "json":
                file_ext = "json"
            case "yaml":
                file_ext = "yml"
            case "markdown":
                file_ext = "md"
            case "msgpack":
                file_ext = "mp"
                self.binary = True

        self.type = file_type
        self.ext = file_ext

        if file_type not in ["markdown"]:
            self.path += f".{self.ext}"

        if manager:
            self.manager = manager

        if os.path.exists(self.path):
            if autoload and not (TEMPORARY and not self.override_temporary):
                self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            _atomic_write(self.path, content, binary=self.binary)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True

    def _read_path(self, path):
        """read raw content from a specific path; returns content or raises"""
        read_mode = "rb" if self.binary else "r"
        encoding = "utf-8" if not self.binary else None
        with open(path, read_mode, encoding=encoding) as f:
            return f.read()

    def _read(self):
        try:
            return self._read_path(self.path)
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def _parse(self, raw):
        """deserialize raw file content into a python dict for this storage type"""
        match self.type:
            case "json":
                return dict(json.loads(raw))
            case "yaml":
                return dict(yaml.safe_load(raw))
            case "msgpack":
                return dict(msgpack.unpackb(raw))
            case "text":
                return dict(raw.split("\n"))
        return {}

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            st = os.stat(self.path)
            return (st.st_mtime, st.st_size) != (self._last_modified, self._last_size)
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time and size"""
        try:
            st = os.stat(self.path)
            self._last_modified = st.st_mtime
            self._last_size = st.st_size
        except OSError:
            pass

    def _parse_nested_keys(self, flat_dict):
        """Convert flat keys like 'ideas/openlumara/topic' into nested dict structure."""
        result = {}
        for key, value in flat_dict.items():
            # normalize separators to / to handle Windows-style paths
            parts = key.replace("\\", "/").split("/")
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    def _flatten_nested_keys(self, nested_dict, prefix=""):
        """Convert nested dict into flat keys like 'ideas/openlumara/topic'."""
        result = {}
        for key, value in nested_dict.items():
            full_key = f"{prefix}/{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_nested_keys(value, full_key))
            else:
                result[full_key] = value

        return result

    def _delete_nested_key(self, flat_key):
        """Delete a key from the nested dict structure."""
        # normalize the key to ensure consistent splitting
        parts = flat_key.replace("\\", "/").split("/")

        current = self
        # traverse down to the parent dictionary of the target key
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # the path doesn't exist, nothing to delete
                return

        # delete the target key from the parent dictionary
        if isinstance(current, dict) and parts[-1] in current:
            del current[parts[-1]]

    def save(self):
        """save content to file"""
        if TEMPORARY and not self.override_temporary:
            return True

        match self.type:
            case "json":
                self._write(json.dumps(dict(self), indent=2))
            case "yaml":
                self._write(
                    yaml.safe_dump(
                        dict(self), default_flow_style=False, sort_keys=False, allow_unicode=True
                    )
                )
            case "markdown":
                # NOTE to readers: i suck at recursive programming, so this is where i heavily use AI assistance. ~Rose22

                # recursive file structure
                # keys like "ideas/openlumara/topic" become nested directories
                if not os.path.exists(self.path):
                    os.makedirs(self.path, exist_ok=True)

                # flatten nested dict to path keys
                flat_items = self._flatten_nested_keys(dict(self))
                failed_keys = []

                for key, content in list(flat_items.items()):
                    try:
                        name = core.sandbox_path(self.path, f"{key}.md")
                    except ValueError as e:
                        # if validation fails, delete the key from the in-memory dicts to keep them clean.
                        self._delete_nested_key(key)
                        del flat_items[key]
                        failed_keys.append((key, str(e)))

                        continue  # Skip saving this file

                    file_dir = os.path.dirname(name)

                    if not os.path.exists(file_dir):
                        os.makedirs(file_dir, exist_ok=True)

                    with open(name, "w", encoding="utf-8") as f:
                        f.write(content)

                # Raise an error if any keys were skipped due to validation failure
                if failed_keys:
                    error_msg = (
                        "Failed to save the following keys due to validation errors:\n"
                        + "\n".join([f"- {k}: {e}" for k, e in failed_keys])
                    )
                    raise ValueError(error_msg)

                # remove files that were deleted
                for root, dirs, files in os.walk(self.path, topdown=False):
                    for filename in files:
                        if filename.endswith(".md"):
                            full_path = os.path.join(root, filename)
                            rel_path = os.path.relpath(full_path, self.path)

                            # remove the .md extension
                            path_no_ext = rel_path[:-3]

                            # normalize path to make it cross-platform
                            normalized = os.path.normpath(path_no_ext)
                            logical_key = "/".join(normalized.split(os.sep))

                            if logical_key not in flat_items:
                                os.remove(full_path)

                    # remove empty directories
                    if root != self.path and not os.listdir(root):
                        os.rmdir(root)
            case "msgpack":
                self._write(msgpack.packb(dict(self)))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(dict(self)))

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()

    def load(self, data=None):
        """load content from file or data argument"""
        if data is not None:
            self.clear()
            self.update(data)
            return True

        # skip reload if file hasn't changed on disk
        if self.type not in ["markdown"] and not self._file_changed():
            self._update_mtime()
            return True

        if self.type in ["markdown"]:
            # recursive file structure: build into a local dict first, then
            # replace in-memory state only after the full walk succeeds
            flat_dict = {}
            for root, dirs, files in os.walk(self.path):
                for filename in files:
                    if filename.endswith(".md"):
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(os.path.join(root, filename), self.path)

                        # remove .md extension
                        path_without_ext = rel_path[:-3]

                        # normalize path to make it cross-platform
                        normalized_path = os.path.normpath(path_without_ext)
                        key = "/".join(normalized_path.split(os.sep))

                        with open(full_path, encoding="utf-8") as f:
                            flat_dict[key] = str(f.read())

            # convert flat path keys to nested dict structure
            nested_dict = self._parse_nested_keys(flat_dict)
            self.clear()
            self.update(nested_dict)
            self._update_mtime()
            return True

        # read + parse into a local first; only replace in-memory state after a
        # fully-successful read. a transient read/parse error must never wipe
        # the data we already hold.
        raw = self._read()
        parsed = None
        if raw:
            try:
                parsed = self._parse(raw)
            except Exception as e:
                core.log("error", f"error parsing {self.name}: {e}")
                parsed = None

        # fall back to the .bak copy if the primary was unreadable/corrupt
        if parsed is None:
            bak = f"{self.path}.bak"
            if os.path.exists(bak):
                try:
                    parsed = self._parse(self._read_path(bak))
                    core.log("warning", f"recovered {self.name} from backup")
                except Exception as e:
                    core.log("error", f"error reading backup for {self.name}: {e}")
                    parsed = None

        if parsed is None:
            # keep existing in-memory data rather than clearing it
            return None

        self.clear()
        self.update(parsed)

        # update mtime after loading
        self._update_mtime()
        return True

    def get(self, *args, **kwargs):
        if not TEMPORARY and not self.override_temporary:
            self.load()

        return super().get(*args)


class StorageText:
    """simple class that saves its content to a text file"""

    def __init__(self, name: str, manager=None, path=None, autoload=True, *args):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)

        # create path if it doesnt exist
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        self._data = ""

        # cache for change detection (mtime + size, so two writes within the
        # same 1s mtime granularity are not missed)
        self._last_modified = 0.0
        self._last_size = -1

        if os.path.exists(self.path):
            if autoload and not TEMPORARY:
                self.load()
        else:
            self.save()

    def __str__(self, *args, **kwargs):
        return self.get()

    def set(self, new_data: str):
        self._data = str(new_data)
        self.save()

    def get(self):
        if not TEMPORARY:
            self.load()
        return str(self._data)

    def load(self):
        # skip reload if file hasn't changed on disk
        if not self._file_changed():
            self._update_mtime()
            return self

        # read into a local first; only replace in-memory state on success, so a
        # transient read error never wipes the data we already hold. fall back to
        # the .bak copy if the primary is unreadable.
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = f.read()
        except Exception as e:
            core.log("error", f"error while loading text storage: {e}")
            bak = f"{self.path}.bak"
            if os.path.exists(bak):
                try:
                    with open(bak, encoding="utf-8") as f:
                        self._data = f.read()
                    core.log("warning", "recovered text storage from backup")
                except Exception as be:
                    core.log("error", f"error reading text storage backup: {be}")

        # update mtime after loading
        self._update_mtime()
        return self

    def save(self):
        if TEMPORARY:
            return self

        try:
            _atomic_write(self.path, self._data, binary=False)
        except Exception as e:
            core.log("error", f"error while saving text storage: {e}")
            return self

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()
        return self

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            st = os.stat(self.path)
            return (st.st_mtime, st.st_size) != (self._last_modified, self._last_size)
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time and size"""
        try:
            st = os.stat(self.path)
            self._last_modified = st.st_mtime
            self._last_size = st.st_size
        except OSError:
            pass
