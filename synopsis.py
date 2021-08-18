import sys

import k3cat

fn = sys.argv[1]
for x in k3cat.Cat(fn, strip=True).iterate(timeout=0):
    print(x)
