"""Point d'entrée Passenger (o2switch, outil cPanel « Setup Python App »).

Dans cPanel : « Application startup file » = passenger_wsgi.py,
« Application Entry point » = application, « Application URL » = /api.
"""

import os
import sys

# Passenger ne garantit pas que la racine de l'application soit dans sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.wsgi import application

__all__ = ["application"]
