from src.toolkit import *

# Define custom filters and global fuctions
# for the generator

# Filter & global for unit tests
def unitLocal(s):
    return s+"/unitlocal"
addFilter('lunit', unitLocal)
addGlobal('lunit', unitLocal)
