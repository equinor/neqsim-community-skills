"""Historian adapter for living tasks built on the open-source ``tagreader`` package.

Reads an interpolated window of tags from OSIsoft PI or Aspen IP.21 and writes one CSV part
per pull under ``<out_dir>/<name>/YYYY/MM/``. Authentication is whatever tagreader uses on the
machine (Kerberos/NTLM/Windows); the adapter never handles credentials. Without tagreader the
pull returns ``not_installed`` so the cycle degrades instead of failing.
"""

import csv
import os

from .results import SourceResult


class TagreaderAdapter(object):
    """Pull ``tags`` (logical name -> historian tag) from one tagreader source."""

    def __init__(self, source, tags, imstype="piwebapi", step_seconds=3600, name="historian",
                 read_type="INT", client=None, **_ignored):
        if not tags:
            raise ValueError("TagreaderAdapter needs a non-empty 'tags' mapping")
        self.source = source
        self.tags = dict(tags)
        self.imstype = imstype
        self.step_seconds = int(step_seconds)
        self.name = name
        self.read_type = read_type
        self._client = client  # injectable for tests

    def _connect(self):
        if self._client is not None:
            return self._client
        import tagreader  # noqa: WPS433 - optional dependency
        client = tagreader.IMSClient(self.source, self.imstype)
        client.connect()
        return client

    def pull(self, since, until, out_dir):
        """Read [since, until) and return a SourceResult; never raises for data problems."""
        try:
            client = self._connect()
        except ImportError:
            return SourceResult("not_installed", message="tagreader is not installed")
        except Exception as error:  # connection or authentication problems
            text = str(error)
            return SourceResult("failed", message=text,
                                interaction_required="auth" in text.lower() or "401" in text)
        try:
            read_type = self.read_type
            try:
                import tagreader
                read_type = getattr(tagreader.ReaderType, self.read_type, self.read_type)
            except ImportError:
                pass
            frame = client.read(list(self.tags.values()), since, until, self.step_seconds,
                                read_type=read_type)
        except Exception as error:
            return SourceResult("failed", message=str(error))
        if frame is None or len(frame) == 0:
            return SourceResult("stale", message="no data in window")
        reverse = {tag: logical for logical, tag in self.tags.items()}
        frame = frame.rename(columns=reverse)
        missing = [logical for logical in self.tags if logical not in frame.columns]
        folder = os.path.join(str(out_dir), self.name, since.strftime("%Y"), since.strftime("%m"))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "part_{}.csv".format(since.strftime("%Y%m%dT%H%M%S")))
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            columns = [c for c in self.tags if c in frame.columns]
            writer.writerow(["timestamp"] + columns)
            for stamp, row in frame.iterrows():
                writer.writerow([stamp.isoformat()] + [row[c] for c in columns])
        last = frame.index.max()
        status = "partial" if missing else "ok"
        return SourceResult(status, rows=len(frame), watermark=last.isoformat(), gaps=missing,
                            outputs=[path])
