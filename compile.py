#!python3
# We use relative here, so we can work in envs
# This is meant to be executed in a seperate process to avoid importing anything from klippy into the main buld

import logging
import sys
import os

# The following is a nasty hack to work around Kalico importing printer.* in __init__
sys.path.insert(0,f"{os.path.dirname(__file__)}/klippy")
from chelper import builder


logging.basicConfig(level=logging.DEBUG)

builder.build_chelper()
builder.build_hub_ctrl()

