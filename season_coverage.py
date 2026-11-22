"""Availability audit metadata; this does not certify complete historical injuries."""
import json
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).parent/'data/season_coverage.json'
    if not path.exists():return {'seasons':{}}
    return json.loads(path.read_text())

def for_season(year):
    return catalog().get('seasons',{}).get(str(year),dict(status='not_audited',label='coverage not audited',note='This season has not been included in the saved availability audit.'))
