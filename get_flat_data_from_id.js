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
    let pages_from_file = [];
    require('fs').readFileSync('flat_id_list.txt', 'utf-8').split(/\r?\n/).forEach(function (line) {
        if (line != '') {
            pages_from_file.push(line);
        }
    })
    const thread_pages = lodash.chunk(pages_from_file, Math.ceil(pages_from_file.length / threads_count))[thread];
    for (const page_iter of thread_pages) {
        const browser = await puppeteer.launch({
            headless: true
        });
        const page = await browser.newPage();

        await page.setExtraHTTPHeaders({
            'Accept-Language': 'ru'
        });

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
        for (let j = 0; j < 10; j++) {
            await page.goto("https://api.investmoscow.ru/investmoscow/tender/v1/object-info/gettenderobjectinformation?tenderId=" + page_iter, {
                timeout: 1000
            }).then(() => {
                open_page_success = 1;
            }).catch((res) => { })
            if (open_page_success === 1) {
                for (let timer = 0; timer < 10; timer++) {
                    await sleep(100);
                    if ((await page.$('.json-formatter-container')) === null) {
                        open_page_success = 0;
                    } else {
                        open_page_success = 1;
                        break;
                    }
                }
                if (open_page_success === 1) {
                    break;
                }
            } else {
                await sleep(100);
            }
        }

        if (open_page_success === 0) {
            console.log(thread, " page problem:", page_iter);
            await page.close();
            await browser.close();
            continue;
        }

        const out_string = page_iter + ".json";
        try {
            fs.unlinkSync('data/' + out_string);
        } catch (err) { }

        //const pageSourceHTML = await page.content();
        //console.log(pageSourceHTML);

        const pre_tag = await page.$('pre');
        let pre_tag_data = await page.evaluate(pre_tag => pre_tag.innerHTML, pre_tag);

        fs.appendFileSync('data/' + out_string, pre_tag_data);

        console.log(thread, " page:", page_iter);
        await page.close();
        await browser.close();
    }
}

//require('events').EventEmitter.defaultMaxListeners = 20;

for (let thread = 0; thread < threads_count; thread++) {
    asyncCall(thread);
}
