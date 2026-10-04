"""Read Kemper Rig Manager libraries — `.rmbackup` archives, the live directory, dated
snapshots and packs. Nothing here writes to a source."""

from importlib.metadata import PackageNotFoundError, version

from ._enums import DEFAULT_PATH as DEFAULT_STOMPS_XML
from ._enums import use_effect_names
from .model import Backup, Info, Performance, Preset, Rig, Slot

try:
    __version__ = version("kemperrig")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0.dev0"

__all__ = ["DEFAULT_STOMPS_XML", "Backup", "Info", "Performance", "Preset", "Rig", "Slot",
           "__version__", "use_effect_names"]
