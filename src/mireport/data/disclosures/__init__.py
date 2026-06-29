import logging

from mireport.json import getJsonFiles, getObject

L = logging.getLogger(__name__)


def _loadConfigs() -> tuple[dict[str, dict], dict[str, dict]]:
    byFilename: dict[str, dict] = {}
    byEntryPoint: dict[str, dict] = {}
    for resource in getJsonFiles(__name__):
        config = byFilename[resource.name] = getObject(resource)
        entryPoints = config.get("taxonomyEntryPoints", {})
        for ep in (
            entryPoints.get("supportedEntryPoint"),
            *entryPoints.get("oldEntryPoints", []),
        ):
            if not ep:
                continue
            if ep in byEntryPoint:
                L.warning(
                    "Entry point %s already registered; ignoring duplicate in %s",
                    ep,
                    resource.name,
                )
            else:
                byEntryPoint[ep] = config
    return byFilename, byEntryPoint


_CONFIG_BY_FILENAME, _CONFIG_BY_ENTRY_POINT = _loadConfigs()


def getDisclosureConfig(entry_point: str) -> dict | None:
    return _CONFIG_BY_ENTRY_POINT.get(entry_point)


# Back-compat: existing callers (e.g. processor.py) import this by name
VSME_DEFAULTS: dict = _CONFIG_BY_FILENAME["vsme.json"]
