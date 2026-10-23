"""Scope 1 (Data): records, splits, similarity search and archive lookups for the agent.

    from data_pipeline import get_record, similar_images, archive_lookup, timeline

Set DATA_PIPELINE_STUB=1 to answer everything from contracts/fixtures/ instead of data/.
Set DATA_PIPELINE_URL + DATA_PIPELINE_TOKEN to use a data server instead of a local data/ (remote.py).
"""

import os

if os.environ.get("DATA_PIPELINE_URL") and os.environ.get("DATA_PIPELINE_STUB") != "1":
    from . import remote as _remote
    _remote.install()  # before the import below, so it picks up the remote functions

if os.environ.get("DATA_PIPELINE_STUB") == "1":
    from .stub import (archive_lookup, eval_ids, gazetteer, get_record, image_file, reload,
                       similar_images, split_composite, timeline)
else:
    from .api import (archive_lookup, eval_ids, gazetteer, get_record, image_file, reload,
                      similar_images, split_composite, timeline)

# `data_pipeline.gazetteer` is both the helper module (scrapers use gazetteer.resolve) and the
# contract function gazetteer(). Make the module callable so both keep working.
import importlib as _importlib
import types as _types

_gazetteer_fn = gazetteer  # capture before importing the submodule rebinds the name
_gaz_module = _importlib.import_module(__name__ + ".gazetteer")


class _CallableModule(_types.ModuleType):
    def __call__(self, *a, **kw):
        return _gazetteer_fn(*a, **kw)


_gaz_module.__class__ = _CallableModule
gazetteer = _gaz_module

__all__ = [
    "archive_lookup", "eval_ids", "gazetteer", "get_record", "image_file", "reload",
    "similar_images", "split_composite", "timeline",
]
