const puppeteer = require('puppeteer');
const fs = require('node:fs');
const lodash = require("lodash");

function sleep(ms) {
    return new Promise((resolve) => {
        setTimeout(resolve, ms);
    });
}

const threads_count = 4;

async function asyncCall(thread) {
    let url_stock = 'https://investmoscow.ru/tenders?' +
        'pageNumber=%url&' +
        'pageSize=100&' +
        'orderBy=CreateDate&' +
        'orderAsc=%flag&' +
        'objectTypes=nsi:41:30011568,nsi:41:30020049&' +
        'tenderStatus=nsi:tender_status_tender_filter:2&' +
        'timeToPublicTransportStop.max=0&' +
        'timeToPublicTransportStop.foot=false&' +
        'timeToPublicTransportStop.publicTransport=false&' +
        'timeToPublicTransportStop.noMatter=true';
    let pages_num = [];
    for (let page_num = 1; page_num <= 150; page_num++) {
        pages_num.push(page_num);
    }
    const thread_pages = lodash.chunk(pages_num, Math.ceil(pages_num.length / threads_count))[thread];
    for (const page_num of thread_pages) {

        const browser = await puppeteer.launch({
            headless: true
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
        let open_page_success = 0;

        console.log(thread, " page:", page_num, ' start');

        while (open_page_success === 0) {
            let url = ''
            if (page_num <= 100) {
                url = url_stock.replace("%url", page_num.toString()).replace("%flag", "false");
            } else {
                url = url_stock.replace("%url", (page_num - 100).toString()).replace("%flag", "true");
            }
            await page.goto(url, {
                waitUntil: 'load',
                timeout: 1000
            }).then(() => {
                open_page_success = 1
            }).catch((res) => { })
            if (open_page_success === 1) {
                for (let timer = 0; timer < 30; timer++) {
                    await sleep(1000);
                    const flat_data = await page.$$('.list');
                    if (flat_data.length != 0) {
                        const flats = await flat_data[0].$$('a');
                        if (flats.length === 0) {
                            open_page_success = 0;
                        } else {
                            open_page_success = 1;
                            break;
                        }
                    } else {
                        open_page_success = 0;
                    }
                }
            }
        }

        console.log(thread, " page:", page_num, ' end');

        const flat_data = await page.$('.list');
        const flats = await flat_data.$$('a');

        let flat_count = 0;

        if (flats.length != 100) {
            let finded_nested_lists = 0;
            while (finded_nested_lists != (100 - flats.length)) {
                const nested_list = await flat_data.$$('.uid-group-card__collapse');
                finded_nested_lists = nested_list.length;
            }
            const all_spans = await page.$$('span');
            for (const i of all_spans) {
                const elementText = await page.evaluate(i => i.textContent, i);
                if (elementText.includes("Все предложения")) {
                    let numbers = elementText.match(/\d+/g);
                    flat_count += parseInt(numbers);
                }
            }
            await page.$$eval('.uid-group-card-toggle-inner', elHandles => elHandles.forEach(el => el.click()));
        }

        flat_count += flats.length;

        console.log(thread, " page:", page_num, ' ', flat_count);

        let iter_count = 0;
        while (true) {
            const new_flat = await flat_data.$$('a');
            //console.log(iter_count, ' ', new_flat.length);
            if (flat_count === new_flat.length) {
                break;
            }
            if (iter_count % 2 === 0) {
                let current_height = 0;
                let previousHeight = 0;
                while (true) {
                    await page.evaluate((current_height) => {
                        window.scrollTo(0, current_height)
                    }, current_height);
                    await sleep(300);
                    current_height = current_height + 1000;
                    const newHeight = await page.evaluate(() => document.body.scrollHeight);
                    if (newHeight === previousHeight) {
                        if (current_height > newHeight + 10000) {
                            break;
                        }
                    }
                    previousHeight = newHeight;
                }
            } else {
                let current_height = await page.evaluate(() => document.body.scrollHeight);
                while (true) {
                    await page.evaluate((current_height) => {
                        window.scrollTo(0, current_height)
                    }, current_height);
                    await sleep(300);
                    current_height = current_height - 1000;
                    if (current_height < -10000) {
                        break;
                    }
                }
            }
            iter_count++;
        }

        try {
            fs.unlinkSync('ids/' + page_num.toString() + '.txt');
        } catch (err) { }

        const new_flat = await flat_data.$$('a');
        let new_flat_array = '';
        for (const i of new_flat) {
            let elementText = await page.evaluate(i => i.href, i);
            elementText += "\n";
            fs.appendFileSync('ids/' + page_num.toString() + '.txt', elementText);
        }

        await browser.close();
    }
}

//require('events').EventEmitter.defaultMaxListeners = 20;

for (let thread = 0; thread < threads_count; thread++) {
    asyncCall(thread);
}
