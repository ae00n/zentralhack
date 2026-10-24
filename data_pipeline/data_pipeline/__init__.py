"""Scope 1 (Data): records, splits, similarity search and archive lookups for the agent.

    from data_pipeline import get_record, similar_images, archive_lookup, timeline
    from data_pipeline import address_lookup, named_buildings   # Ortschaft, Gemeinde, Strasse, Gebaeude
    from data_pipeline import photos_near                       # reference photos taken near a point
    from data_pipeline import aerial_image                      # swisstopo aerial photo around a point, as of a year
    from data_pipeline import horizon                           # mountain skyline seen from a point

Set DATA_PIPELINE_STUB=1 to answer everything from contracts/fixtures/ instead of data/.
Set DATA_PIPELINE_URL + DATA_PIPELINE_TOKEN to use a data server instead of a local data/ (remote.py).
"""

import os

if os.environ.get("DATA_PIPELINE_URL") and os.environ.get("DATA_PIPELINE_STUB") != "1":
    from . import remote as _remote
    _remote.install()  # before the import below, so it picks up the remote functions

if os.environ.get("DATA_PIPELINE_STUB") == "1":
    from .stub import (address_lookup, archive_lookup, eval_ids, gazetteer, get_record, image_file,
                       named_buildings, photos_near, reload, similar_images, split_composite, timeline)
    from .stub import aerial_image, horizon
else:
    from .api import (archive_lookup, eval_ids, gazetteer, get_record, image_file, photos_near, reload,
                      similar_images, split_composite, timeline)
    from .places import address_lookup, named_buildings
    from .registers import address_at, find_address, find_building, landmarks_near
    from .matches import matches
    from .aerial import aerial_image
    from .horizon import horizon

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
    "address_lookup", "aerial_image", "horizon", "named_buildings", "photos_near", "archive_lookup", "eval_ids", "gazetteer", "get_record", "image_file", "reload",
    "similar_images", "split_composite", "timeline",
    "address_at", "find_address", "find_building", "landmarks_near", "matches",
]
