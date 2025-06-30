import sys
import random

NB_ITERATIONS_TESTS = 100

def create_property_based_test(f):
    regressions = [ ]
    for i in range(0, NB_ITERATIONS_TESTS):
        if i < len(regressions):
            seed = regressions[i]
        else:
            seed = random.randrange(0, 2**64)
        random.seed(seed)
        try:
            addition()
            soustraction()
            
        except AssertionError as err:
            print(seed, "test failed")
            print(err)
            sys.exit(1)


### Example

def addition():
    x = random.randrange(0, 10000)
    y = random.randrange(0, 10000)
    assert x + y >= x
    assert x + y >= y

def soustraction():
    x = random.randrange(0, 10000)
    y = random.randrange(0, 10000)
    assert x - y < x

create_property_based_test(addition)
