# Development enemy roster

| Enemy | HP | Damage | Speed (uu/s) | Range (64 uu tiles) |
|---|---:|---:|---:|---:|
| Infiltrator | 120 | 20 | 280 | 1.25 |
| Hijacker | 180 | 25 | 230 | 1.5 |
| Encrypter | 350 | 35 | 150 | 1 |
| Exfiltrator | 160 | 20 | 190 | 5 |

All four Blueprints derive from `APTKEnemyCharacter`. The existing health,
single-target melee, nearest living guard selection, King fallback, facing,
animation and death paths are reused. Exfiltrator overrides the enemy's projectile
release to aim at its selected target. The shared projectile optionally retains
that intended target; existing guard shots retain their previous behavior.

The existing test-ground spawner retains its Swarm Node configuration and adds
four `AdditionalEnemies` entries with five each. Each entry exposes its class
and count. All types share the spaced ring and `StartGame()` gating. Zero total
counts clear a previous development spawn. This is not a wave system.

## Artwork

Originals remain read-only under `Downloads/gamethon pics/design 2d pics`.
Each new enemy's `ArtSource/Characters/Enemies/<Name>/manifest.json` records source
SHA-256 hashes, visually identified sheet mappings, frame measurements and pivots.

Each enemy has four actual standing reference poses, 32 walk frames, 32 attack
frames and eight death frames. Death sheets are read as 4x2 for Infiltrator and
Hijacker, and 8x1 for Encrypter and Exfiltrator. No frames are interpolated.

Connected silhouettes are separated where nominal source cells cut through
weapons or capes. Exfiltrator's embedded green projectile/impact art is extracted
from measured original rectangles. Released-effect spill is separated from the
character poses; the projectile uses a centered pivot and zero splash radius.

| Enemy | Canvas | Feet pivot | Reference body height |
|---|---|---|---:|
| Infiltrator | 240x240 | 112, 200 | 116 px |
| Hijacker | 240x240 | 112, 200 | 116 px |
| Encrypter | 240x256 | 112, 200 | 124 px |
| Exfiltrator | 256x272 | 125, 200 | 116 px |

Projectile/effect canvases are 129x129 with pivot 64,64. All sprites use one pixel
per Unreal unit, point filtering, no mipmaps and no sprite collision. Canvases
are measured before writing, and every output is checked for border contact.

## Reproduction and verification

1. Run `Tools/ExtractEnemyRoster.py` with Python 3 (the engine's bundled Python works).
2. Compile `ProtectTheKing2DEditor Win64 Development` with Unreal 5.8.
3. Run `Tools/PTK_GenerateEnemyRoster.py` with the Unreal Python commandlet.
4. Run `Tools/PTK_VerifyEnemyRoster.py` using `-ExecutePythonScript`,
   `-RenderOffscreen` and `-unattended` in Unreal Editor.
5. Run the existing `Tools/PTK_VerifyStartScreen.py` the same way.

The tests exercise real PIE movement, exact damage, directional attacks,
player/guard targeting, projectile interception, death, all-dead King fallback,
guard attacks and switching, Swarm Node, and the mapped Enter start flow.
They modify only transient test state, never save the level, and write results
to `Tools/_Output/enemy_roster_results.json` and `start_screen_results.json`.

Validation on 2026-09-07: Win64 Development Editor build passed; 105 roster PIE
checks and all 19 existing start-screen checks passed. The 24 original source
files match their recorded SHA-256 hashes. Existing guard, King and Swarm Node
assets and their dedicated source files are unchanged. No commit or push was made.
