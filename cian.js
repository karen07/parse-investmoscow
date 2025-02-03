const puppeteer = require('puppeteer');
const fs = require('node:fs');
const lodash = require("lodash");

function sleep(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

async function asyncCall(thread) {
    let url_stock = 'https://www.cian.ru/cat.php?' +
        '&deal_type=sale' +
        '&engine_version=2' +
        '&flat_share=2' +
        '&minlift=1' +
        '&mintarea=34' +
        '&is_first_floor=0' +
        '&object_type[0]=1' +
        '&offer_type=flat' +
        '&only_flat=1' +
        '&origin=map';

    const browser = await puppeteer.launch({
        headless: false,
    });
    const page = await browser.newPage();

    await page.setRequestInterception(true);

    await page.setViewport({
        width: 1920,
        height: 1080
    });

    page.on('request', (req) => {
        if (req.resourceType() === 'image') {
            req.abort();
        } else {
            req.continue();
        }
    });

    await page.goto(url_stock, {
        waitUntil: 'load',
        timeout: 3000
    }).then(() => {
        open_page_success = 1
    }).catch((res) => { })

    await sleep(1000);

    let more_flag = 1;

    let price_sum = 0;

    while (more_flag) {
        let current_height = 0;
        let previousHeight = 0;

        while (true) {
            await page.evaluate((current_height) => {
                window.scrollTo(0, current_height)
            }, current_height);
            await sleep(200);
            current_height = current_height - 500;
            if (current_height < -1000) {
                break;
            }
        }

        while (true) {
            await page.evaluate((current_height) => {
                window.scrollTo(0, current_height)
            }, current_height);
            await sleep(200);
            current_height = current_height + 500;
            const newHeight = await page.evaluate(() => document.body.scrollHeight);
            if (newHeight === previousHeight) {
                if (current_height > newHeight + 1000) {
                    current_height = newHeight;
                    break;
                }
            }
            previousHeight = newHeight;
        }

        const all_span = await page.$$('span');
        let next_span;
        for (const k of all_span) {
            const elementText = await page.evaluate(k => k.innerText, k);
            if (elementText.toLowerCase() === "дальше") {
                next_span = k;
                more_flag = 1;
                break;
            }

            const MainPrice = await page.evaluate(k => k.dataset.mark, k);
            if (MainPrice == "MainPrice") {
                const Price = await page.evaluate(k => k.innerText, k);
                let matches = Price.replace(/[^0-9]/g, "");
                price_sum += parseInt(matches);
            }

            more_flag = 0;
        }

        if (more_flag) {
            await sleep(1000);
            next_span.click();
            await sleep(5000);
        }

        console.log(price_sum);
    }

    const all_div = await page.$$('div');
    let flats_div;
    for (const k of all_div) {
        const elementText = await page.evaluate(k => k.className, k);
        if (elementText.includes("Newbuildings__NewBuildingList-sc")) {
            flats_div = k;
            break;
        }
    }

    const all_a = await flats_div.$$('a');
    for (const k of all_a) {
        const elementText = await page.evaluate(k => k.href, k);
        console.log(elementText.slice(elementText.lastIndexOf('/') + 1, elementText.length));
    }

    await browser.close();
}

asyncCall(0);
