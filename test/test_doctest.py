import doctest

import k3cat


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(k3cat))
    return tests
