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
			renovation_coordinate.push({ x: line.split(";")[1], y: line.split(";")[2] });
		}
	})

	//console.log(renovation_coordinate);

	const pages = fs.readdirSync("pages/");
	//console.log("tenderId;viewsCount;lat;long;addreess;start price;end price;data;area;div;price/area");
	console.log("tenderId;viewsCount;addreess;start price;end price;data;area;div;price/area");
	for (const i of pages) {
		lines = '';
		require('fs').readFileSync("pages/" + i, 'utf-8').split(/\r?\n/).forEach(function (line) {
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
						//console.log(dist);
						console.log(
							obj["tenderId"], ";",
							obj["headerInfo"]["viewsCount"], ";",
							//obj["mapInfo"]["coords"]["lat"], ";",
							//obj["mapInfo"]["coords"]["long"], ";",
							obj["mapInfo"]["address"].replaceAll(";", " ").replaceAll("\n", " "), ";",
							obj["mapInfo"]["price"].toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							names_map.get("Подведение итогов").split(" ")[0], ";",
							names_map.get("Площадь объекта").toString().split(" ")[0].split(",")[0].split(".")[0], ";",
							((parseInt(names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0]) / parseInt(obj["mapInfo"]["price"].toString().split(" ")[0].split(",")[0].split(".")[0]) - 1) * 100).toString().replace(".", ","), ";",
							(names_map.get("Итоговая цена").toString().split(" ")[0].split(",")[0].split(".")[0] / names_map.get("Площадь объекта").toString().split(" ")[0].split(",")[0].split(".")[0]).toString().replace(".", ","), ";"
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
