"""Opt-in real-provider storyboard/review/speech check on local fixtures.

Blocking Python sockets does not sandbox the separately launched Swift runtime.
"""
import sys
from provider_check import main

if __name__ == "__main__":
    raise SystemExit(main(["--block-python-network", "--stages", "storyboard", "review", *sys.argv[1:]]))
