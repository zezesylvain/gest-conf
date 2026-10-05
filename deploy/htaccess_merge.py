"""Fusionne le bloc GEST-CONF dans le .htaccess existant de public_html.

cPanel (« Setup Python App ») écrit lui-même ses directives Passenger dans un
.htaccess. Écraser ce fichier casserait l'API : on remplace donc uniquement le
bloc délimité par « # BEGIN GEST-CONF » / « # END GEST-CONF », ou on l'ajoute.

Usage : python deploy/htaccess_merge.py <htaccess_existant> <bloc> > <résultat>
"""

import re
import sys
from pathlib import Path

BEGIN = "# BEGIN GEST-CONF"
END = "# END GEST-CONF"

_BLOCK = re.compile(rf"^{re.escape(BEGIN)}$.*?^{re.escape(END)}$\n?", re.MULTILINE | re.DOTALL)


def merge(existing: str, block: str) -> str:
    block = block.strip()
    if not (block.startswith(BEGIN) and block.endswith(END)):
        raise ValueError("Le bloc doit être délimité par les marqueurs GEST-CONF.")
    found = len(_BLOCK.findall(existing))
    if found > 1 or (found == 0 and BEGIN in existing):
        raise ValueError("Marqueurs GEST-CONF incohérents dans le .htaccess existant.")
    if found == 1:
        return _BLOCK.sub(lambda _: block + "\n", existing, count=1)
    if not existing:
        return block + "\n"
    separator = "\n" if existing.endswith("\n") else "\n\n"
    return existing + separator + block + "\n"


if __name__ == "__main__":
    existing_path, block_path = (Path(arg) for arg in sys.argv[1:3])
    existing_text = existing_path.read_text() if existing_path.exists() else ""
    sys.stdout.write(merge(existing_text, block_path.read_text()))
