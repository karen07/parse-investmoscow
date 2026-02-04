const puppeteer = require('puppeteer');
const fs = require('node:fs');

function sleep(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

async function asyncCall() {
    const browser = await puppeteer.launch({
        headless: false,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
        ],
    });

    const page = await browser.newPage();

    await page.setViewport({
        width: 1920,
        height: 1080
    });

    let open_page_success = 0;

    await page.goto('https://platform.2gis.ru/ru/playground/geocoder', {
        waitUntil: 'load',
        timeout: 1000
    }).then(() => {
        open_page_success = 1;
    }).catch((res) => { });

    let pages_from_file = [];
    require('fs').readFileSync('renovation_addresses.txt', 'utf-8').split(/\r?\n/).forEach(function (line) {
        if (line != '') {
            pages_from_file.push(line);
        }
    });

    const all_p = await page.$$('p');
    let p_with_data;
    for (const k of all_p) {
        const elementText = await page.evaluate(k => k.innerText, k);
        if (elementText === "Ответ") {
            p_with_data = k;
            break;
        }
    }

    await sleep(1000);
    p_with_data.click();
    await sleep(1000);

    const all_divs = await page.$$('input');
    let div_with_data;
    for (const k of all_divs) {
        const elementText = await page.evaluate(k => k.placeholder, k);
        if (elementText === "Начните вводить") {
            div_with_data = k;
            break;
        }
    }

    for (const page_iter of pages_from_file) {
        await div_with_data.type(page_iter);
        await sleep(500);

        const all_pre = await page.$('pre');
        const elementText_pre = await page.evaluate(all_pre => all_pre.innerText, all_pre);

        const obj = JSON.parse(elementText_pre);

        console.log(obj['result']['items'][0]['point']['lat'], ',', obj['result']['items'][0]['point']['lon']);

        await page.evaluate(div_with_data => div_with_data.value = '', div_with_data);
        await sleep(500);
    }
    await browser.close();
}

asyncCall();
