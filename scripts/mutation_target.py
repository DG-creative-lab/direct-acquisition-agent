"""Run one mutation target and report behavioral test failures separately from invalid experiments."""

import contextlib
import json
import sys
import unittest


class MutationResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixture_failure = False
        self.body_errors = 0

    def is_fixture_error(self, err):
        traceback = err[2]
        while traceback:
            frame = traceback.tb_frame
            if (frame.f_globals.get('__name__') in ('unittest.case', 'unittest.suite')
                    and frame.f_code.co_name in ('_callSetUp', '_callTearDown', '_callCleanup',
                                                  '_handleClassSetUp', '_handleClassTearDown',
                                                  '_handleModuleFixture', '_handleModuleTearDown')):
                return True
            traceback = traceback.tb_next
        return False

    def addFailure(self, test, err):
        self.fixture_failure |= self.is_fixture_error(err)
        super().addFailure(test, err)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self.fixture_failure |= self.is_fixture_error(err)
            if not issubclass(err[0], test.failureException):
                self.body_errors += 1
        super().addSubTest(test, subtest, err)

    def addError(self, test, err):
        # Loading and class/module fixture errors are not TestCase test bodies.
        traceback = err[2]
        in_body = False
        while traceback:
            frame = traceback.tb_frame
            in_body |= (frame.f_globals.get('__name__') == 'unittest.case'
                        and frame.f_code.co_name == '_callTestMethod')
            traceback = traceback.tb_next
        if not in_body or self.is_fixture_error(err):
            self.fixture_failure = True
        else:
            self.body_errors += 1
        super().addError(test, err)


def main():
    loader = unittest.TestLoader()
    with contextlib.redirect_stdout(sys.stderr):
        suite = loader.loadTestsFromName(sys.argv[1])
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, failfast=True,
                                         resultclass=MutationResult).run(suite)
    # A fixture failure does not prove the target assertion ran.
    detected = (not loader.errors and result.testsRun == 1 and bool(result.failures or result.body_errors)
                and len(result.errors) == result.body_errors and not result.fixture_failure and not result.skipped
                and not result.unexpectedSuccesses)
    print(json.dumps({'detected': detected, 'tests_run': result.testsRun,
                      'failures': len(result.failures), 'errors': len(result.errors)}))
    return 0 if detected else 1


if __name__ == '__main__':
    raise SystemExit(main())
