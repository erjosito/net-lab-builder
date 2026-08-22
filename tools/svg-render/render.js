const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const diagramsDir = path.resolve(__dirname, '..', '..', 'labs', 'foundry-agent-prompt-vs-hosted-networking', 'diagrams');
const targets = process.argv.slice(2);
if (targets.length === 0) {
  console.error('Usage: node render.js <svgBaseName> [...]');
  process.exit(2);
}

(async () => {
  for (const base of targets) {
    const svgPath = path.join(diagramsDir, `${base}.svg`);
    const pngPath = path.join(diagramsDir, `${base}.png`);
    const svg = fs.readFileSync(svgPath);
    const m = svg.toString('utf8').match(/viewBox="0 0 (\d+) (\d+)"/);
    if (!m) throw new Error(`No viewBox in ${svgPath}`);
    const w = parseInt(m[1], 10) * 2;
    const h = parseInt(m[2], 10) * 2;
    await sharp(svg, { density: 288 })
      .resize(w, h, { fit: 'fill' })
      .png({ compressionLevel: 9 })
      .toFile(pngPath);
    console.log(`rendered ${base}.png (${w}x${h})`);
  }
})().catch(e => { console.error(e); process.exit(1); });
