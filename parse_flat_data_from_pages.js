const fs = require('node:fs');

function sleep(ms) {
	return new Promise((resolve) => {
		setTimeout(resolve, ms);
	});
}

async function asyncCall() {
	let renovation_coordinate = [];
	require('fs').readFileSync("renovation_coordinates.txt", 'utf-8').split(/\r?\n/).forEach(function (line) {
		if (line != '') {
			renovation_coordinate.push({ x: line.split(",")[0], y: line.split(",")[1] });
		}
	})

	const pages = fs.readdirSync("data/");
	console.log("tenderId;viewsCount;addreess;start price;end price;data;area;div;price/area");
	for (const i of pages) {
		lines = '';
		require('fs').readFileSync("data/" + i, 'utf-8').split(/\r?\n/).forEach(function (line) {
			if (line != '') {
				lines += line;
			}
		})

		const obj = JSON.parse(lines);

		const names_map = new Map();
		for (const tmp of obj["procedureInfo"]) {
			names_map.set(tmp["label"], tmp["value"]);
		}
		for (const tmp of obj["objectInfo"]) {
			names_map.set(tmp["label"], tmp["value"]);
		}

		try {
			if (obj["sidebar"]["tenderStatusInfo"]["statusText"] == "Признаны состоявшимися" || obj["sidebar"]["tenderStatusInfo"]["statusText"] == "Единственный участник") {
				for (const j of renovation_coordinate) {
					let x = obj["mapInfo"]["coords"]["lat"];
					let y = obj["mapInfo"]["coords"]["long"];
					let dist = Math.sqrt((j.x - x) * (j.x - x) + (j.y - y) * (j.y - y));
					if (dist < 0.0005) {
						console.log(
							obj["tenderId"], ";",
							obj["headerInfo"]["viewsCount"], ";",
							obj["mapInfo"]["address"].replaceAll(";", " ").replaceAll("\n", " "), ";",
							obj["mapInfo"]["price"].toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							names_map.get("Подведение итогов").split(" ")[0], ";",
							names_map.get("Площадь объекта").toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							Math.ceil((parseInt(names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0]) / parseInt(obj["mapInfo"]["price"].toString().split(" ")[0].split(",")[0].split(".")[0]) - 1) * 100), ";",
							Math.ceil((names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0]) / (names_map.get("Площадь объекта").toString().split(" ")[0].split(",")[0].split(".")[0])), ";"
						);
						break;
					}
				}
			}
		} catch (e) {
		}
	}
}

asyncCall();
