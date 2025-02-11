import locale
import threading
import unittest
from contextlib import contextmanager
from os.path import dirname, join

import hidateinfer.ruleproc as ruleproc
import yaml
from hidateinfer.date_elements import (
    DayOfMonth,
    Filler,
    Hour12,
    Hour24,
    Minute,
    MonthNum,
    MonthTextShort,
    Second,
    Timezone,
    WeekdayShort,
    Year2,
    Year4,
)
from hidateinfer.infer import (
    _mode,
    _most_restrictive,
    _percent_match,
    _tag_most_likely,
    _tokenize_by_character_class,
    infer,
)

LOCALE_LOCK = threading.Lock()


@contextmanager
def setlocale(name):
    with LOCALE_LOCK:
        saved = locale.setlocale(locale.LC_ALL)
        try:
            yield locale.setlocale(locale.LC_ALL, name)
        finally:
            locale.setlocale(locale.LC_ALL, saved)


def load_tests(loader, standard_tests, ignored):
    """
    Return a TestSuite containing standard_tests plus generated test cases
    """
    suite = unittest.TestSuite()
    suite.addTests(standard_tests)

    with open(join(dirname(__file__), "examples.yaml"), "r") as f:
        examples = yaml.safe_load_all(f)
        for example in examples:
            suite.addTest(test_case_for_example(example))

    return suite


def test_case_for_example(test_data):
    """
    Return an instance of TestCase containing a test for a date-format example
    """

    # This class definition placed inside method to prevent discovery by test loader
    class TestExampleDate(unittest.TestCase):
        def testFormat(self):
            # verify initial conditions
            self.assertTrue(
                hasattr(self, "test_data"), "testdata field not set on test object"
            )

            expected = self.test_data["format"]
            testcase_locale = self.test_data.get("locale", "en_US.UTF-8")
            arguments = self.test_data.get("arguments", {})
            with setlocale(testcase_locale):
                actual = infer(self.test_data["examples"], **arguments)

            error_fmt = "{0}: Inferred `{1}`!=`{2}`"

            self.assertEqual(
                expected,
                actual,
                error_fmt.format(self.test_data["name"], actual, expected),
            )

    test_case = TestExampleDate(methodName="testFormat")
    test_case.test_data = test_data
    return test_case


class TestAmbiguousDateCases(unittest.TestCase):
    """
    TestCase for tests which results are ambiguous but can be assumed to fall in a small set of
    possibilities.
    """

    def testAmbg1(self):
        dateformat = infer(["1/1/2012"])
        self.assertIn(dateformat, ["%m/%d/%Y", "%d/%m/%Y"])

    def testAmbg2(self):
        # Note: as described in Issue #5 (https://github.com/jeffreystarr/dateinfer/issues/5), the
        # result should be %d/%m/%Y as the more likely choice. However, at this point, we will
        # allow %m/%d/%Y.
        self.assertIn(
            infer(["04/12/2012", "05/12/2012", "06/12/2012", "07/12/2012"]),
            ["%d/%m/%Y", "%m/%d/%Y"],
        )


class TestMode(unittest.TestCase):
    def testMode(self):
        self.assertEqual(5, _mode([1, 3, 4, 5, 6, 5, 2, 5, 3]))
        self.assertEqual(2, _mode([1, 2, 2, 3, 3]))  # with ties, pick least value


class TestMostRestrictive(unittest.TestCase):
    def testMostRestrictive(self):
        t = _most_restrictive

        self.assertEqual(MonthNum(), t([DayOfMonth(), MonthNum, Year4()]))
        self.assertEqual(Year2(), t([Year4(), Year2()]))


class TestPercentMatch(unittest.TestCase):
    def testPercentMatch(self):
        t = _percent_match
        patterns = (DayOfMonth, MonthNum, Filler)
        examples = ["1", "2", "24", "b", "c"]

        percentages = t(patterns, examples)

        self.assertAlmostEqual(percentages[0], 0.6)  # DayOfMonth 1..31
        self.assertAlmostEqual(percentages[1], 0.4)  # Month 1..12
        self.assertAlmostEqual(percentages[2], 1.0)  # Filler any


class TestRuleElements(unittest.TestCase):
    def testFind(self):
        elem_list = [
            Filler(" "),
            DayOfMonth(),
            Filler("/"),
            MonthNum(),
            Hour24(),
            Year4(),
        ]
        t = ruleproc.Sequence.find

        self.assertEqual(0, t([Filler(" ")], elem_list))
        self.assertEqual(3, t([MonthNum], elem_list))
        self.assertEqual(2, t([Filler("/"), MonthNum()], elem_list))
        self.assertEqual(4, t([Hour24, Year4()], elem_list))

        elem_list = [
            WeekdayShort,
            MonthTextShort,
            Filler(" "),
            Hour24,
            Filler(":"),
            Minute,
            Filler(":"),
            Second,
            Filler(" "),
            Timezone,
            Filler(" "),
            Year4,
        ]
        self.assertEqual(3, t([Hour24, Filler(":")], elem_list))

    def testMatch(self):
        t = ruleproc.Sequence.match

        self.assertTrue(t(Hour12, Hour12))
        self.assertTrue(t(Hour12(), Hour12))
        self.assertTrue(t(Hour12, Hour12()))
        self.assertTrue(t(Hour12(), Hour12()))
        self.assertFalse(t(Hour12, Hour24))
        self.assertFalse(t(Hour12(), Hour24))
        self.assertFalse(t(Hour12, Hour24()))
        self.assertFalse(t(Hour12(), Hour24()))

    def testNext(self):
        elem_list = [
            Filler(" "),
            DayOfMonth(),
            Filler("/"),
            MonthNum(),
            Hour24(),
            Year4(),
        ]

        next1 = ruleproc.Next(DayOfMonth, MonthNum)
        self.assertTrue(next1.is_true(elem_list))

        next2 = ruleproc.Next(MonthNum, Hour24)
        self.assertTrue(next2.is_true(elem_list))

        next3 = ruleproc.Next(Filler, Year4)
        self.assertFalse(next3.is_true(elem_list))


class TestTagMostLikely(unittest.TestCase):
    def testTagMostLikely(self):
        examples = ["8/12/2004", "8/14/2004", "8/16/2004", "8/25/2004"]
        t = _tag_most_likely

        actual = t(examples)
        expected = [MonthNum(), Filler("/"), DayOfMonth(), Filler("/"), Year4()]

        self.assertListEqual(actual, expected)


class TestTokenizeByCharacterClass(unittest.TestCase):
    def testTokenize(self):
        t = _tokenize_by_character_class

        self.assertListEqual([], t(""))
        self.assertListEqual(["2013", "-", "08", "-", "14"], t("2013-08-14"))
        self.assertListEqual(
            [
                "Sat",
                " ",
                "Jan",
                " ",
                "11",
                " ",
                "19",
                ":",
                "54",
                ":",
                "52",
                " ",
                "MST",
                " ",
                "2014",
            ],
            t("Sat Jan 11 19:54:52 MST 2014"),
        )
        self.assertListEqual(
            ["4", "/", "30", "/", "1998", " ", "4", ":", "52", " ", "am"],
            t("4/30/1998 4:52 am"),
        )

class TestOctober(unittest.TestCase):

    def testOctoberDates(self):
        examples = ["10/1/2021", "10/2/2021", "10/3/2021", "10/4/2021", "10/5/2021", "10/6/2021", "10/7/2021", "10/8/2021", "10/9/2021", "10/10/2021", "10/11/2021", "10/12/2021", "10/13/2021", "10/14/2021", "10/15/2021", "10/16/2021", "10/17/2021", "10/18/2021", "10/19/2021", "10/20/2021", "10/21/2021", "10/22/2021", "10/23/2021", "10/24/2021", "10/25/2021", "10/26/2021", "10/27/2021", "10/28/2021", "10/29/2021", "10/30/2021", "10/31/2021"]
        t = _tag_most_likely

        actual = t(examples)
        expected = [MonthNum(), Filler("/"), DayOfMonth(), Filler("/"), Year4()]

        self.assertListEqual(actual, expected)

    def testOctoberDates2(self):
        examples = ["2023-10-11 21:14:00"]
        format = infer(examples, day_first=True, day_last=True, format_type="moment")
        expected = "YYYY-MM-DD HH:mm:ss"

        self.assertEqual(format, expected)