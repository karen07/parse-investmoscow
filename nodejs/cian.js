"use strict";

const puppeteer = require('puppeteer');

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

    let url_stock = 'https://www.cian.ru/cat.php?center=55.76504798552593%2C37.51020980243127&currency=2&deal_type=sale&engine_version=2&flat_share=2&in_polygon[0]=37.575706_55.580212%2C37.595388_55.576023%2C37.596551_55.575926%2C37.665301_55.571891%2C37.666604_55.571842%2C37.679876_55.573143%2C37.681083_55.573457%2C37.753128_55.601648%2C37.754037_55.602089%2C37.791688_55.622422%2C37.795321_55.624405%2C37.832122_55.648511%2C37.83285_55.649004%2C37.837549_55.653517%2C37.838054_55.654276%2C37.839874_55.65993%2C37.839905_55.661313%2C37.829528_55.693737%2C37.82959_55.694758%2C37.838558_55.714731%2C37.838741_55.715513%2C37.843493_55.770122%2C37.843494_55.770491%2C37.839019_55.81414%2C37.838881_55.815197%2C37.837934_55.820097%2C37.837403_55.821371%2C37.833954_55.825975%2C37.833446_55.826429%2C37.733124_55.878944%2C37.731852_55.879604%2C37.702716_55.893239%2C37.701444_55.89357%2C37.646595_55.897113%2C37.641869_55.89767%2C37.620504_55.901478%2C37.617324_55.90221%2C37.58914_55.909811%2C37.587785_55.910103%2C37.574222_55.911084%2C37.572882_55.911003%2C37.529954_55.90608%2C37.529021_55.905865%2C37.487397_55.888516%2C37.486792_55.888326%2C37.468564_55.883744%2C37.466949_55.883453%2C37.444797_55.881703%2C37.444225_55.881584%2C37.420125_55.874127%2C37.417594_55.873275%2C37.407317_55.868463%2C37.405791_55.867483%2C37.398737_55.860915%2C37.398413_55.860503%2C37.392188_55.849194%2C37.391826_55.848237%2C37.395782_55.835941%2C37.395783_55.835445%2C37.3877_55.807565%2C37.387627_55.807372%2C37.372308_55.78935%2C37.372093_55.789096%2C37.369965_55.7847%2C37.369732_55.783475%2C37.369001_55.748521%2C37.369413_55.746448%2C37.384985_55.715037%2C37.385853_55.713357%2C37.388659_55.709625%2C37.389615_55.708722%2C37.411655_55.692043%2C37.412208_55.69144%2C37.416344_55.683281%2C37.416872_55.682436%2C37.432795_55.661741%2C37.434362_55.660137%2C37.505215_55.599679%2C37.505994_55.599126%2C37.51559_55.594692%2C37.517305_55.594199%2C37.575706_55.580212&is_first_floor=0&maxprice=12000000&minkarea=7&minlift=1&mintarea=34&object_type[0]=1&offer_type=flat&only_flat=1&polygon_name[0]=%D0%9E%D0%B1%D0%BB%D0%B0%D1%81%D1%82%D1%8C%20%D0%BF%D0%BE%D0%B8%D1%81%D0%BA%D0%B0&wp=1&zoom=10&origin=map';

    await page.goto(url_stock, {
        waitUntil: 'load',
        timeout: 5000
    }).then(() => {
    }).catch((res) => { })

    let more_flag = 1;

    while (more_flag) {
        let current_height = 0;
        let previousHeight = 0;

        await sleep(10000);

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
                current_height = current_height - 2000;
                await page.evaluate((current_height) => {
                    window.scrollTo(0, current_height)
                }, current_height);
                await sleep(1000);
                next_span = k;
                more_flag = 1;
                break;
            }

            more_flag = 0;
        }

        const all_div = await page.$$('div');
        for (const k of all_div) {
            const div_data_name = await page.evaluate(k => k.dataset.name, k);
            if (div_data_name == "SummarySection") {
                const SummarySection_elem = await page.evaluateHandle(k => k.nextElementSibling, k);
                const all_span = await SummarySection_elem.$$('span');
                for (const j of all_span) {
                    const dataset_mark = await page.evaluate(j => j.dataset.mark, j);
                    if (dataset_mark === "OfferTitle") {
                        const parentNode = await page.evaluateHandle(j => j.parentNode, j);
                        const a_href = await page.evaluate(parentNode => parentNode.href, parentNode);
                        console.log(a_href);
                    }
                }
            }
        }

        if (more_flag) {
            const isDisabled = await page.evaluate((el) => {
                const host = el.closest('button, a, [role="button"]') || el;

                const ariaDisabled =
                    el.getAttribute('aria-disabled') === 'true' ||
                    host.getAttribute('aria-disabled') === 'true';

                const disabledAttr = host.hasAttribute('disabled');

                const cls = (host.className || '') + ' ' + (el.className || '');
                const classDisabled = /disabled|inactive|is-disabled/i.test(cls);

                const style = window.getComputedStyle(host);
                const notClickable =
                    style.pointerEvents === 'none' || style.visibility === 'hidden' || style.display === 'none';

                return ariaDisabled || disabledAttr || classDisabled || notClickable;
            }, next_span);

            if (isDisabled) {
                more_flag = 0;
            } else {
                await next_span.click();
            }
        }
    }

    await browser.close();
}

asyncCall();
