export function caseOption(panneau, texte, valeur, changer) {
  const label = document.createElement('label'), input = document.createElement('input');
  input.type = 'checkbox'; input.checked = valeur; input.onchange = () => changer(input.checked);
  label.append(input, texte); panneau.append(label); return input;
}
export function nombreOption(panneau, texte, valeur, min, max, changer, type = 'range') {
  const label = document.createElement('label'), input = document.createElement('input'), sortie = document.createElement('output');
  input.type = type; input.min = min; input.max = max; input.step = 1; input.value = valeur;
  sortie.value = valeur; input.oninput = () => { sortie.value = input.value; changer(Number(input.value)); };
  label.append(texte, input, sortie); panneau.append(label); return input;
}
export function sourceOption(panneau, valeur, changer) {
  const label = document.createElement('label'), select = document.createElement('select'); label.append('Source ');
  for (const [value, texte] of [['actif', 'Calque actif'], ['visibles', 'Calques visibles']]) {
    const option = document.createElement('option'); option.value = value; option.textContent = texte; select.append(option);
  }
  select.value = valeur; select.onchange = () => changer(select.value); label.append(select); panneau.append(label);
}
