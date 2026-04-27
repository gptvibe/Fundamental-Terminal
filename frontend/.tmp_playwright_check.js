const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const results = [];
  const tickers = ["AAPL", "RKLB"];

  for (const ticker of tickers) {
    const url = "http://localhost:3000/company/" + ticker + "/models";
    const consoleErrors = [];
    const pageErrors = [];
    const requestFailures = [];

    const onConsole = (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    };
    const onPageError = (err) => pageErrors.push(String(err));
    const onRequestFailed = (req) => {
      const failure = req.failure();
      requestFailures.push(req.method() + " " + req.url() + " :: " + (failure ? failure.errorText : "failed"));
    };

    page.on("console", onConsole);
    page.on("pageerror", onPageError);
    page.on("requestfailed", onRequestFailed);

    let gotoError = null;
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    } catch (e) {
      gotoError = String(e);
    }

    let loadingGone = null;
    try {
      const loadingLocator = page.getByText(/loading/i);
      const count = await loadingLocator.count();
      if (count > 0) {
        try {
          await loadingLocator.first().waitFor({ state: "hidden", timeout: 60000 });
          loadingGone = true;
        } catch {
          loadingGone = false;
        }
      } else {
        loadingGone = true;
      }
    } catch {
      loadingGone = null;
    }

    const bodyText = (await page.locator("body").innerText().catch(() => "")).toLowerCase();
    const hasROIC = bodyText.includes("roic");
    const loadingStillPresent = /loading/i.test(bodyText);

    results.push({
      ticker,
      url,
      hasROIC,
      loadingStillPresent,
      loadingGone,
      gotoError,
      consoleErrors,
      pageErrors,
      requestFailures
    });

    page.off("console", onConsole);
    page.off("pageerror", onPageError);
    page.off("requestfailed", onRequestFailed);
  }

  await browser.close();
  console.log(JSON.stringify(results));
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
