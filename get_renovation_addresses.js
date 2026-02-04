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

    await page.goto('https://fr.mos.ru/uchastnikam-programmy/karta-renovatsii/?ft=1&category[]=NEW&status[]=FINISHED', {
        waitUntil: 'load',
        timeout: 1000
    }).then(() => {
        open_page_success = 1;
    }).catch((res) => { });

    await sleep(5000);

    const pages_array = await page.evaluate(() =>
        Array.from(document.querySelectorAll('.js-page-num-selector option')).map(element => element.value)
    );

    for (const i of pages_array) {
        page.select('.js-page-num-selector', i);
        await sleep(1000);
        const address_list = await page.$$('.table-title');
        for (const address of address_list) {
            const elementText = await page.evaluate(
                address => address.innerText.replace(/\s*\n\s*/g, ' ').trim(),
                address
            );
            console.log(elementText);
        }
    }

    await browser.close();
}

asyncCall();
