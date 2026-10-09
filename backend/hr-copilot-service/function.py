# Workshop entry point -> HR Ops Copilot
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lambda_handler import handler as _h


def handler(event=None, context=None):
    return _h(event or {}, context)
