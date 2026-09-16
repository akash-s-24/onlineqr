#!/usr/bin/env python

import random
import sys

def DNA(length):
    return ''.join(random.choice('CGTA') for _ in xrange(length))

print DNA(int(sys.argv[1]))
