const fs = require('node:fs');

function sleep(ms) {
	return new Promise((resolve) => {
		setTimeout(resolve, ms);
	});
}

async function asyncCall() {
	const pages = fs.readdirSync("data/");

	let user = {
		"type": "FeatureCollection",
		"features": []
	};



	for (const i of pages) {
		lines = '';
		require('fs').readFileSync("data/" + i, 'utf-8').split(/\r?\n/).forEach(function (line) {
			if (line != '') {
				lines += line;
			}
		})

		const obj = JSON.parse(lines);


		const latitude = obj["data"]["objLkLatitude"];
		const longitude = obj["data"]["objLkLongitude"];

		const soldOut = obj["data"]["soldOutPerc"];

		if (soldOut != undefined) {
			let data = {
				"type": "Feature",
				"geometry": {
					"type": "Point",
					"coordinates": [
						parseFloat(longitude),
						parseFloat(latitude)
					]
				},
				"properties": {}
			};
			user["features"].push(data);
		}
	}

	const userJSON = JSON.stringify(user);
	console.log(userJSON);
}

asyncCall();
