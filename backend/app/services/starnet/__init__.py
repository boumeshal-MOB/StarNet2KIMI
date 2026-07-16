"""STAR*NET adaptation layer.

Prepared for the production handoff: the Windows worker will execute STAR*NET
Ultimate on the files built here and the native outputs will be read back with
these parsers.  In this mock-up the certified computation is replaced by the
Python engine, but the file contracts are real and tested.
"""

from .dat_builder import build_dat
from .names import engine_name
from .parsers import parse_err, parse_pts
from .prj_builder import build_prj

__all__ = ["build_dat", "build_prj", "engine_name", "parse_pts", "parse_err"]
