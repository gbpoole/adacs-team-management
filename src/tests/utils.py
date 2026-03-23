from adacs_django_playwright.adacs_django_playwright import (
    AsyncPlaywrightTestCase as AsyncPlaywrightTestCaseBase,
    async_playwright_test,
)


class AsyncPlaywrightTestCase(AsyncPlaywrightTestCaseBase):
    """
    Test case for Playwright browser tests
    Provides methods to login and logout users with proper cookie management for browser tests.
    """

    pass
