const fs = require('node:fs');

function sleep(ms) {
	return new Promise((resolve) => {
		setTimeout(resolve, ms);
	});
}

function dec2hexString(dec) {
	return (dec + 0x10000).toString(16).substr(-4).toUpperCase().substr(-2);
}

async function asyncCall() {
	const pages = fs.readdirSync("data/");

	let geojson = {
		"type": "FeatureCollection",
		"features": []
	};

	let colors_data = fs.readFileSync('colors.json');
	let colors = JSON.parse(colors_data);

	for (const i of pages) {
		lines = '';
		fs.readFileSync("data/" + i, 'utf-8').split(/\r?\n/).forEach(function (line) {
			if (line != '') {
				lines += line;
			}
		})

		const obj = JSON.parse(lines);

		const latitude = obj["data"]["objLkLatitude"];
		const longitude = obj["data"]["objLkLongitude"];

		const soldOut = obj["data"]["soldOutPerc"];
		const PriceAvg = obj["data"]["objPriceAvg"];

		if (soldOut != undefined && PriceAvg != undefined) {
			let soldOut_int = Math.round(soldOut * 255);
			let max_PriceAvg = 500000;
			if (PriceAvg < max_PriceAvg) {
				soldOut_int = Math.round((PriceAvg / max_PriceAvg) * 255);
			} else {
				soldOut_int = 255;
			}

			let data = {
				"type": "Feature",
				"geometry": {
					"type": "Point",
					"coordinates": [
						parseFloat(longitude),
						parseFloat(latitude)
					]
				},
				"properties": { "marker-color": "#" + dec2hexString(colors[soldOut_int]["R"]) + dec2hexString(colors[soldOut_int]["G"]) + dec2hexString(colors[soldOut_int]["B"]) }
			};
			geojson["features"].push(data);
		}
	}

	console.log(JSON.stringify(geojson));
}

asyncCall();
