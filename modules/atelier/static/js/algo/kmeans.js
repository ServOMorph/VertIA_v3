const distance = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

export function extraireCouleurs(rgba, n = 8, { ignorerPapierTrait = true, iterations = 20 } = {}) {
  let graine = 0x12345678;
  const alea = () => { graine = (Math.imul(1664525, graine) + 1013904223) >>> 0; return graine / 4294967296; };
  const pixels = [], total = rgba.length / 4, limite = Math.min(50000, total);
  for (let j = 0; j < limite; j++) {
    const p = Math.floor((j + alea()) * total / limite) * 4;
    if (!rgba[p + 3]) continue;
    const rgb = [rgba[p], rgba[p + 1], rgba[p + 2]];
    if (ignorerPapierTrait && (Math.min(...rgb) >= 245 || Math.max(...rgb) <= 20)) continue;
    pixels.push(rgb);
  }
  if (!pixels.length) return [];
  n = Math.max(2, Math.min(24, Math.round(n)));
  const centres = [pixels[Math.floor(alea() * pixels.length)].slice()];
  const distances = new Float64Array(pixels.length); distances.fill(Infinity);
  while (centres.length < n) {
    let somme = 0;
    for (let p = 0; p < pixels.length; p++) {
      distances[p] = Math.min(distances[p], distance(pixels[p], centres.at(-1))); somme += distances[p];
    }
    if (!somme) break;
    let choix = alea() * somme, index = pixels.length - 1;
    for (let p = 0; p < pixels.length; p++) { choix -= distances[p]; if (choix < 0) { index = p; break; } }
    centres.push(pixels[index].slice());
  }
  const affecter = () => {
    const groupes = centres.map(() => [0, 0, 0, 0]);
    for (const pixel of pixels) {
      let index = 0, minimum = Infinity;
      for (let c = 0; c < centres.length; c++) {
        const d = distance(pixel, centres[c]); if (d < minimum) { minimum = d; index = c; }
      }
      const groupe = groupes[index];
      for (let c = 0; c < 3; c++) groupe[c] += pixel[c];
      groupe[3]++;
    }
    return groupes;
  };
  for (let tour = 0; tour < Math.max(1, Math.min(20, iterations)); tour++) {
    const groupes = affecter(); let changement = 0;
    for (let c = 0; c < centres.length; c++) {
      if (!groupes[c][3]) continue;
      const nouveau = groupes[c].slice(0, 3).map(v => v / groupes[c][3]);
      changement += distance(centres[c], nouveau); centres[c] = nouveau;
    }
    if (changement < 0.01) break;
  }
  return affecter().map((g, i) => ({ r: Math.round(centres[i][0]), g: Math.round(centres[i][1]),
    b: Math.round(centres[i][2]), part: g[3] / pixels.length })).filter(c => c.part > 0)
    .sort((a, b) => b.part - a.part || a.r - b.r || a.g - b.g || a.b - b.b);
}
