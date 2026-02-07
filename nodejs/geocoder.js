"use strict";

const puppeteer = require("puppeteer");
const fs = require("fs");

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

// node script.js file.txt
// node script.js --file file.txt
// node script.js -f file.txt
function getInputFile() {
    const argv = process.argv.slice(2);

    const idxLong = argv.indexOf("--file");
    if (idxLong !== -1 && argv[idxLong + 1]) return argv[idxLong + 1];

    const idxShort = argv.indexOf("-f");
    if (idxShort !== -1 && argv[idxShort + 1]) return argv[idxShort + 1];

    if (argv[0] && !argv[0].startsWith("-")) return argv[0];

    return "renovation_addresses.txt";
}

async function asyncCall() {
    const inputFile = getInputFile();

    if (!fs.existsSync(inputFile)) {
        console.error(`File not found: ${inputFile}`);
        process.exit(1);
    }

    const browser = await puppeteer.launch({
        headless: false,
        args: [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
        ],
    });

    const page = await browser.newPage();

    await page.setRequestInterception(true);
    await page.setViewport({ width: 1920, height: 1080 });

    page.on("request", (req) => {
        if (req.resourceType() === "image") req.abort();
        else req.continue();
    });

    const url_stock = "https://platform.2gis.ru/ru/playground/geocoder";

    await page.goto(url_stock, {
        waitUntil: "load",
        timeout: 5000,
    }).catch(() => { });

    const pages_from_file = fs
        .readFileSync(inputFile, "utf-8")
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);

    const all_p = await page.$$("p");
    let p_with_data;
    for (const k of all_p) {
        const elementText = await page.evaluate((k) => k.innerText, k);
        if (elementText === "Ответ") {
            p_with_data = k;
            break;
        }
    }

    await sleep(1000);
    await p_with_data.click();
    await sleep(1000);

    const all_inputs = await page.$$("input");
    let div_with_data;
    for (const k of all_inputs) {
        const elementText = await page.evaluate((k) => k.placeholder, k);
        if (elementText === "Начните вводить") {
            div_with_data = k;
            break;
        }
    }

    for (const page_iter of pages_from_file) {
        await div_with_data.type(page_iter);
        await sleep(500);

        const all_pre = await page.$("pre");
        const elementText_pre = await page.evaluate((pre) => pre.innerText, all_pre);

        const obj = JSON.parse(elementText_pre);
        console.log(
            obj["result"]["items"][0]["point"]["lat"],
            ",",
            obj["result"]["items"][0]["point"]["lon"]
        );

        await page.evaluate((inp) => (inp.value = ""), div_with_data);
        await sleep(500);
    }

    await browser.close();
}

asyncCall();
