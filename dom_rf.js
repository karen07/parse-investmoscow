const puppeteer = require('puppeteer');
const fs = require('node:fs');
const lodash = require("lodash");

function sleep(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

async function asyncCall(thread) {
    let url_stock = 'https://xn--80az8a.xn--d1aqf.xn--p1ai/' +
        '/%D1%81%D0%B5%D1%80%D0%B2%D0%B8%D1%81%D1%8B' +
        '/%D0%BA%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3-%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D1%80%D0%BE%D0%B5%D0%BA' +
        '/%D1%81%D0%BF%D0%B8%D1%81%D0%BE%D0%BA-%D0%BE%D0%B1%D1%8A%D0%B5%D0%BA%D1%82%D0%BE%D0%B2' +
        '/%D1%81%D0%BF%D0%B8%D1%81%D0%BE%D0%BA?' +
        'place=77' +
        '&objStatus=0' +
        '&toQuarter=2027-12-31' +
        '&residentialBuildings=1' +
        '&escrowFlag=1';

    //console.log(url_stock);

    const browser = await puppeteer.launch({
        headless: false
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
        timeout: 1000
    }).then(() => {
        open_page_success = 1
    }).catch((res) => { })

    await sleep(1000);

    let more_flag = 1;

    while (more_flag) {
        let current_height = await page.evaluate(() => document.body.scrollHeight);
        while (true) {
            await page.evaluate((current_height) => {
                window.scrollTo(0, current_height)
            }, current_height);
            await sleep(50);
            current_height = current_height - 1000;
            if (current_height < -10000) {
                break;
            }
        }

        current_height = 0;
        let previousHeight = 0;

        while (true) {
            await page.evaluate((current_height) => {
                window.scrollTo(0, current_height)
            }, current_height);
            await sleep(50);
            current_height = current_height + 1000;
            const newHeight = await page.evaluate(() => document.body.scrollHeight);
            if (newHeight === previousHeight) {
                if (current_height > newHeight + 10000) {
                    break;
                }
            }
            previousHeight = newHeight;
        }

        const all_div = await page.$$('div');
        let more_button_div;
        for (const k of all_div) {
            const elementText = await page.evaluate(k => k.innerText, k);
            if (elementText.toLowerCase() === "показать ещё") {
                more_button_div = k;
                more_flag = 1;
                break;
            }
            more_flag = 0;
        }

        if (more_flag) {
            await sleep(50);
            more_button_div.click();
            await sleep(50);
        }
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
