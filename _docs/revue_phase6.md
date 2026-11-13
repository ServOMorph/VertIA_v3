# Revue de consolidation — 2 novembre 2026

Revue statique des couches livrées aux phases 1 à 5 : composition, contexte et Chat,
registre et orchestration, moteurs, arbitre et file, ressources, stockage, routes et modules
du front. Les essais de cette phase utilisent des clients et processus simulés, sans lancer
de serveur ou de génération GPU.

## Corrections

| Problème relevé | Correction | Régression automatisée |
|---|---|---|
| ComfyUI oubliait ses enfants survivants si le parent mourait lors d’un arrêt incomplet. | Arrêt commun `ProcessOwner`, références conservées jusqu’à arrêt confirmé ; démarrage et changement de moteur bloqués. | Même scénario pour Qwen et ACE, puis récupération et passage au moteur suivant. |
| Annuler l’attente de `to_thread` pouvait rendre le verrou GPU alors que le thread d’arrêt travaillait encore. | Attente protégée de la tâche d’arrêt, y compris après plusieurs annulations ; propagation de l’annulation après la fin. | Deux annulations pendant un arrêt simulé : verrou maintenu jusqu’à libération. |
| Un ComfyUI détenu mais sans réponse pouvait être remplacé sans arrêt préalable. | Arrêter le processus détenu avant de tenter un nouveau lancement. | Échec d’arrêt empêchant le remplacement. |
| Une liste de périphériques limitée au CPU validait implicitement une VRAM libérée (`all([])`). | Refus du changement de moteur si aucun GPU n’est mesuré. | Réponses avec liste vide ou CPU seul. |
| Une réponse de santé JSON non objet levait une exception dans Qwen. | Santé indisponible pour ce format incompatible. | Réponse JSON liste, sur les deux adaptateurs. |
| Un fichier catalogué supprimé du disque provoquait une erreur 500 dans l’aperçu de carte. | Réponse 404 fixe, sans accès au moteur. | Routes historiques `/images`, génériques `/medias` et contenu des fichiers. |

Les tests existants de lancement, d’arrêt et de musique utilisent maintenant le point commun
de simulation psutil. Les règles propres aux moteurs restent dans leurs adaptateurs : ComfyUI
peut décharger une instance externe dédiée par API ; ACE doit posséder son processus.

## Couverture et limites

| Domaine | Vérifications automatisées existantes ou complétées |
|---|---|
| Chat | Contexte, résumé, streaming, arrêt, messages en attente, persistance et éphémère. |
| Ressources et jobs | Exclusivité, priorités, mémoire, reprise et échec de libération. |
| Outils | Filtres à cas verrouillés, proposition JSON simulée, modification et confirmation. |
| Adaptateurs | Contrats HTTP simulés, graphes, progression, soumission perdue et annulation. |
| Fichiers | Catalogue, lecture partielle, références, copie, suppression, éphémère et fichier absent. |
| Interface | Edge simulé : Chat, cartes, galerie, pièces jointes, protection XSS et mobile. |

Cette couverture décrit les scénarios testés ; aucun pourcentage de couverture de lignes
n’a été mesuré. Elle ne prouve ni la compatibilité d’une installation externe réelle ni
la qualité de génération, le temps d’exécution ou la consommation mémoire.

Le routage reste lexical. La syllabation et le budget musical restent heuristiques.
Les besoins mémoire complets de Qwen et ACE restent à mesurer. Les formulaires de cartes
connaissent encore leurs types ; un registre de rendus pourra être introduit quand le
prochain outil le justifiera. Le protocole d’extension est décrit dans `developpement.md`.

Les essais matériels et téléchargements réels restent dans `tests_manuels.md`. La phase vidéo
dépend toujours du choix du modèle par l’utilisateur. Les statuts de roadmap restent à mettre
à jour par `/close` après validation.
