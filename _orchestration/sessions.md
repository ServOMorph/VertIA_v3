# Sessions orchestrées — rapports du 2026-11-12

Source : rapports envoyés par chaque session à VertIA_v3. Données déclaratives, non vérifiées par VertIA.

## creation_3d (D:\ServOMorph\creation_3d)
- Objectif : modèles 3D générés et animés localement, export GLB/FBX (Godot, Unreal).
- État : phases 0-2 faites (MPFB2 -> Kimodo -> retarget Blender -> GLB/FBX -> rendu Cycles CPU) ; phase 3 benchmark image vers 3D (6 cas non figés).
- VRAM : Kimodo pic 2,3 Go, quelques minutes par clip, interruptible entre clips ; TripoSR/SF3D quelques minutes par cas ; TRELLIS.2 ~6,2 Go annoncés, non installé.
- Dépôt : github.com/ServOMorph/creation_3d, public.
- Réutilisable : pipeline/vram.py, mpfb_human.py, retarget_soma.py, export_web.py, render_still.py, render_anim.py.
- Règles locales à lever : accord GPU par usage, aucune initiative. Défauts : tête relevée après retarget, pas de run.py d'orchestration.

## creation_llm (D:\ServOMorph\creation_llm)
- Objectif : LLM français from scratch, assistant conversationnel.
- État : assistant v2 retenu (49,7 % bench interne) ; roadmap 369M, phase 1 (grad_checkpoint, run_369m.py, rodage) non commencée.
- VRAM : rodage ~6,3 Go ~1 h ; pré-entraînement ~6,3-6,5 Go ~12 jours, interruptible (--resume) ; puis évals/SFT quelques heures. Marge ~1 Go, aucune cohabitation possible.
- Dépôt : github.com/ServOMorph/creation_llm, public. 3,3 Go de checkpoints et logs hors .gitignore : à corriger avant tout push.
- Réutilisable : model.py, tokenizer_fr32k.json, convert_chat.py, run_assistant.py, bench_assistant.py, eval_frenchbench.py.
- Règles locales à lever : accord GPU par usage, aucune initiative, commit/push sur demande.

## creation_videos (D:\ServOMorph\creation_videos)
- Objectif : T2V/I2V locales via WanGP (D:\AI\WanGP).
- État : phase 4 (stack figée) en cours ; t2v Wan 2.1 14B retenu, i2v provisoire ; correction du ralenti I2V puis phase 5 (run.py).
- VRAM : ~5,5 Go, pic 7,8 Go, ~54 min par clip, non interruptible.
- Dépôt : github.com/ServOMorph/creation_videos, visibilité non vérifiée ; benchmark/ 64 Mo avec images.
- Réutilisable : benchmark/bench_wangp.py, run_queue.py.
- Règles locales à lever : accord GPU par usage, commit/push sur demande, CLAUDE.md réservé à l'utilisateur.

## worldmodel (D:\ServOMorph\WorldModel)
- Objectif : world model interactif local, UI web (run.py).
- État : phases 1-2 faites ; phase 3 (DIAMOND Atari, CS:GO, Open-Oasis mesurés ; Matrix-Game 2.0 en attente) ; phases 4-6 TODO.
- VRAM : Matrix-Game 2.0 non estimé (24 Go officiel, offload CPU requis), poids 11 Go sur D:, non interruptible.
- Dépôt : github.com/ServOMorph/WorldModel, visibilité non vérifiée ; models/ et third_party/ ignorés, historique non audité.
- Réutilisable : WorldModelAdapter (load/reset/step/unload), 3 adaptateurs, banc de test FPS/VRAM/dérive.
- Règles locales à lever : aucun GPU sans signal utilisateur, push à confirmer. Risques : FlashAttention/Apex sous Windows.
