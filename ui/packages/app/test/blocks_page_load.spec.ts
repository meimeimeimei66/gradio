import { test, expect, Page } from "@playwright/test";
import { mock_theme, wait_for_page } from "./utils";

function mock_demo(page: Page, demo: string) {
	return page.route("**/config", (route) => {
		return route.fulfill({
			headers: {
				"Access-Control-Allow-Origin": "*"
			},
			path: `../../../demo/${demo}/config.json`
		});
	});
}

function mock_api(page: Page, body: Array<unknown>) {
	return page.route("**/run/predict", (route) => {
		const id = JSON.parse(route.request().postData()!).fn_index;
		return route.fulfill({
			headers: {
				"Access-Control-Allow-Origin": "*"
			},
			body: JSON.stringify({
				data: body[id]
			})
		});
	});
}

test("renders the correct elements", async ({ page }) => {
	await mock_demo(page, "blocks_page_load");
	await mock_api(page, [["Welcome! This page has loaded for Frank"]]);
	await mock_theme(page);
	await wait_for_page(page);

	const textbox = await page.getByLabel("Name");

	await textbox.fill("Frank");
	await expect(await textbox).toHaveValue("Frank");
	await expect(await page.getByLabel("Output")).toHaveValue(
		"Welcome! This page has loaded for Frank"
	);
});
