from src.util import *

# Define custom filters and global fuctions
# for the template

# Filter & global for unit tests
def unitLocal(s):
    return s+"/unitlocal"
addFilter('lunit', unitLocal)
addGlobal('lunit', unitLocal)
