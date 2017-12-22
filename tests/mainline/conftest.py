import sys

collect_ignore = ["old_test_di.py"]

if sys.version_info < (3,):
    collect_ignore.append("test_di_py3.py")

