function bouton(texte, action, desactive = false) {
  const b = document.createElement('button'); b.type = 'button';
  b.textContent = texte; b.title = texte; b.disabled = desactive; b.onclick = action; return b;
}

export function installerCalques(doc, historique, panneau) {
  const rendre = () => {
    panneau.replaceChildren();
    for (const calque of [...doc.calques].reverse()) {
      const ligne = document.createElement('div'); ligne.className = 'calque';
      const selection = bouton(calque.nom, () => { doc.actifId = calque.id; doc.notifier(); });
      selection.className = 'selection';
      selection.setAttribute('aria-pressed', String(doc.actifId === calque.id));
      ligne.append(selection);
      const modifier = (valeurs, libelle) => doc.modifier(historique, calque, valeurs, libelle);
      ligne.append(bouton(calque.visible ? 'Masquer' : 'Afficher', () =>
        modifier({ visible: !calque.visible }, 'Visibilité')));
      const index = doc.calques.indexOf(calque);
      const deplacer = delta => doc.transaction(historique, 'Ordre des calques', () => {
        doc.calques.splice(index, 1); doc.calques.splice(index + delta, 0, calque);
      });
      ligne.append(bouton('Monter', () => deplacer(1), index === doc.calques.length - 1),
        bouton('Descendre', () => deplacer(-1), index === 0));
      const label = document.createElement('label'); label.textContent = 'Opacité ';
      const opacite = document.createElement('input'); opacite.type = 'range';
      opacite.min = 0; opacite.max = 100; opacite.value = Math.round(calque.opacite * 100);
      opacite.setAttribute('aria-label', `Opacité de ${calque.nom}`);
      opacite.title = `${opacite.value} %`;
      opacite.onchange = () => modifier({ opacite: Number(opacite.value) / 100 }, 'Opacité');
      label.append(opacite); ligne.append(label);
      const fusionLabel = document.createElement('label'); fusionLabel.textContent = 'Fusion ';
      const fusion = document.createElement('select');
      for (const [valeur, texte] of [['source-over', 'Normale'], ['multiply', 'Produit']]) {
        const option = document.createElement('option'); option.value = valeur; option.textContent = texte;
        fusion.append(option);
      }
      fusion.value = calque.fusion;
      fusion.onchange = () => modifier({ fusion: fusion.value }, 'Mode de fusion');
      fusionLabel.append(fusion); ligne.append(fusionLabel);
      ligne.append(bouton('Renommer', () => {
        const nom = prompt('Nom du calque', calque.nom)?.trim();
        if (nom) modifier({ nom }, 'Renommer');
      }), bouton('Supprimer', () => {
        if (!confirm(`Supprimer « ${calque.nom} » ?`)) return;
        doc.transaction(historique, 'Supprimer le calque', () => {
          doc.calques.splice(index, 1);
          if (doc.actifId === calque.id) doc.actifId = doc.calques.at(-1)?.id ?? null;
        });
      }));
      panneau.append(ligne);
    }
  };
  doc.abonner(rendre); rendre();
}
