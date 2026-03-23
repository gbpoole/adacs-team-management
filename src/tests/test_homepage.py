from .utils import AsyncPlaywrightTestCase, async_playwright_test
from playwright.async_api import expect

# Normally, tests are co-located with the app they are testing, however
#


class TestHomepage(AsyncPlaywrightTestCase):
    @async_playwright_test
    async def test_homepage_renders(self):
        """Basic smoke test that shows the homepage renders."""
        page = await self.browser_context.new_page()
        await page.goto(self.live_server_url)

        await expect(page.locator("h1")).to_have_text("ADACS Django template")
